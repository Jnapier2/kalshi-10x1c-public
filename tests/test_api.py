from __future__ import annotations

import base64
import json
import unittest
from typing import Any
from unittest.mock import patch

import requests
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

from kalshi_public.api import AmbiguousMutationError, ApiError, KalshiClient
from kalshi_public.auth import load_credentials
from kalshi_public.constants import CREATE_ORDER_PATH, DEMO_REST_URL
from kalshi_public.safety import SafetyError, authorize_write, revoke_write
from tests.helpers import TempPublicRoot
from tests.test_safety import valid_plan


class FakeResponse:
    def __init__(self, status_code: int, data: Any) -> None:
        self.status_code = status_code
        self._data = data
        self.content = json.dumps(data).encode("utf-8") if data is not None else b""
        self.text = self.content.decode("utf-8")

    def json(self) -> Any:
        return self._data


class FakeSession:
    def __init__(self, responses: list[FakeResponse] | None = None, exc: Exception | None = None) -> None:
        self.headers: dict[str, str] = {}
        self.trust_env = True
        self.responses = list(responses or [])
        self.exc = exc
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        if self.exc is not None:
            raise self.exc
        if not self.responses:
            raise AssertionError("no fake response queued")
        return self.responses.pop(0)

    def close(self) -> None:
        self.closed = True


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TempPublicRoot()
        self.settings = self.temp.settings("demo-trade")
        self.acl_patch = patch("kalshi_public.auth._windows_acl_failures", return_value=[])
        self.acl_patch.start()
        self.credentials = load_credentials(self.settings.values, self.temp.root)

    def tearDown(self) -> None:
        self.acl_patch.stop()
        self.temp.close()

    def test_transport_ignores_ambient_requests_environment(self) -> None:
        session = FakeSession([FakeResponse(200, {"markets": []})])
        client = KalshiClient(DEMO_REST_URL, root=self.temp.root, timeout_seconds=5, session=session)
        self.assertFalse(session.trust_env)
        client.list_markets("KXBTC15M")
        call = session.calls[0]
        self.assertFalse(call["allow_redirects"])
        self.assertTrue(call["verify"])

    def test_unapproved_endpoint_is_rejected(self) -> None:
        with self.assertRaises(SafetyError):
            KalshiClient("https://example.com", root=self.temp.root, timeout_seconds=5)

    def test_market_pagination_is_bounded_and_combined(self) -> None:
        session = FakeSession(
            [
                FakeResponse(200, {"markets": [{"ticker": "a"}], "cursor": "next"}),
                FakeResponse(200, {"markets": [{"ticker": "b"}], "cursor": ""}),
            ]
        )
        client = KalshiClient(DEMO_REST_URL, root=self.temp.root, timeout_seconds=5, session=session)
        rows = client.list_markets("KXBTC15M")
        self.assertEqual([row["ticker"] for row in rows], ["a", "b"])
        self.assertEqual(len(session.calls), 2)

    def test_market_pagination_limit_fails_closed(self) -> None:
        session = FakeSession(
            [FakeResponse(200, {"markets": [], "cursor": f"next-{index}"}) for index in range(5)]
        )
        client = KalshiClient(DEMO_REST_URL, root=self.temp.root, timeout_seconds=5, session=session)
        with self.assertRaisesRegex(ApiError, "pagination exceeded"):
            client.list_markets("KXBTC15M")
        self.assertEqual(len(session.calls), 5)

    def test_position_pagination_is_bounded_and_uses_nonzero_filter(self) -> None:
        session = FakeSession(
            [
                FakeResponse(200, {"market_positions": [{"ticker": "KXBTC15M-A"}], "cursor": "next"}),
                FakeResponse(200, {"market_positions": [{"ticker": "KXETH15M-B"}], "cursor": ""}),
            ]
        )
        client = KalshiClient(
            DEMO_REST_URL,
            root=self.temp.root,
            timeout_seconds=5,
            credentials=self.credentials,
            session=session,
        )
        rows = client.list_positions()
        self.assertEqual([row["ticker"] for row in rows], ["KXBTC15M-A", "KXETH15M-B"])
        self.assertEqual(session.calls[0]["params"]["count_filter"], "position")
        self.assertEqual(session.calls[0]["params"]["subaccount"], 0)
        self.assertEqual(len(session.calls), 2)
        malformed_rows: list[Any] = [None, [], "ticker", {}, {"ticker": ""}, {"ticker": 123}, {"ticker": "BAD TICKER"}]
        for row in malformed_rows:
            with self.subTest(position_row=row):
                bad_session = FakeSession([FakeResponse(200, {"market_positions": [row], "cursor": ""})])
                bad_client = KalshiClient(
                    DEMO_REST_URL,
                    root=self.temp.root,
                    timeout_seconds=5,
                    credentials=self.credentials,
                    session=bad_session,
                )
                with self.assertRaisesRegex(ApiError, "write preflight blocked"):
                    bad_client.list_positions()

    def test_position_pagination_limit_blocks_write_preflight(self) -> None:
        session = FakeSession(
            [FakeResponse(200, {"market_positions": [], "cursor": f"next-{index}"}) for index in range(5)]
        )
        client = KalshiClient(
            DEMO_REST_URL,
            root=self.temp.root,
            timeout_seconds=5,
            credentials=self.credentials,
            session=session,
        )
        with self.assertRaisesRegex(ApiError, "position pagination exceeded"):
            client.list_positions()
        self.assertEqual(len(session.calls), 5)

    def test_resting_order_pagination_limit_blocks_write_preflight(self) -> None:
        session = FakeSession(
            [FakeResponse(200, {"orders": [], "cursor": f"next-{index}"}) for index in range(5)]
        )
        client = KalshiClient(
            DEMO_REST_URL,
            root=self.temp.root,
            timeout_seconds=5,
            credentials=self.credentials,
            session=session,
        )
        with self.assertRaisesRegex(ApiError, "resting-order pagination exceeded"):
            client.list_resting_orders()
        self.assertEqual(len(session.calls), 5)
        malformed_rows: list[Any] = [None, [], "ticker", {}, {"ticker": ""}, {"ticker": 123}, {"ticker": "BAD TICKER"}]
        for row in malformed_rows:
            with self.subTest(order_row=row):
                bad_session = FakeSession([FakeResponse(200, {"orders": [row], "cursor": ""})])
                bad_client = KalshiClient(
                    DEMO_REST_URL,
                    root=self.temp.root,
                    timeout_seconds=5,
                    credentials=self.credentials,
                    session=bad_session,
                )
                with self.assertRaisesRegex(ApiError, "write preflight blocked"):
                    bad_client.list_resting_orders()

    def test_authenticated_signature_covers_full_path_without_query(self) -> None:
        session = FakeSession([FakeResponse(200, {"balance": 100})])
        client = KalshiClient(
            DEMO_REST_URL,
            root=self.temp.root,
            timeout_seconds=5,
            credentials=self.credentials,
            session=session,
        )
        client.get_balance()
        call = session.calls[0]
        headers = call["headers"]
        timestamp = headers["KALSHI-ACCESS-TIMESTAMP"]
        signature = base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"])
        message = f"{timestamp}GET/trade-api/v2/portfolio/balance".encode()
        self.credentials.private_key.public_key().verify(
            signature,
            message,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )

    def test_create_order_uses_only_v2_single_order_route(self) -> None:
        plan = valid_plan()
        session = FakeSession(
            [
                FakeResponse(
                    201,
                    {
                        "order_id": "3b23c1c7-f4ef-4f0d-8b9a-9e53c61f1a0d",
                        "client_order_id": plan.client_order_id,
                        "fill_count": "0.00",
                        "remaining_count": "10.00",
                        "ts_ms": 1,
                    },
                )
            ]
        )
        auth = authorize_write("demo-trade", self.settings, self.temp.root)
        try:
            client = KalshiClient(
                DEMO_REST_URL,
                root=self.temp.root,
                timeout_seconds=5,
                credentials=self.credentials,
                session=session,
            )
            response = client.create_order(plan.payload(), auth)
            self.assertEqual(response["order_id"], "3b23c1c7-f4ef-4f0d-8b9a-9e53c61f1a0d")
            self.assertEqual(session.calls[0]["url"], DEMO_REST_URL + CREATE_ORDER_PATH)
            self.assertEqual(session.calls[0]["method"], "POST")
        finally:
            revoke_write(auth)

    def test_create_order_mismatched_client_id_is_ambiguous(self) -> None:
        plan = valid_plan()
        session = FakeSession(
            [
                FakeResponse(
                    201,
                    {
                        "order_id": "3b23c1c7-f4ef-4f0d-8b9a-9e53c61f1a0d",
                        "client_order_id": "00000000-0000-0000-0000-000000000000",
                        "fill_count": "0.00",
                        "remaining_count": "10.00",
                        "ts_ms": 1,
                    },
                )
            ]
        )
        auth = authorize_write("demo-trade", self.settings, self.temp.root)
        try:
            client = KalshiClient(
                DEMO_REST_URL,
                root=self.temp.root,
                timeout_seconds=5,
                credentials=self.credentials,
                session=session,
            )
            with self.assertRaises(AmbiguousMutationError):
                client.create_order(plan.payload(), auth)
        finally:
            revoke_write(auth)

    def test_create_order_fill_counts_must_reconcile_to_ten(self) -> None:
        plan = valid_plan()
        session = FakeSession(
            [
                FakeResponse(
                    201,
                    {
                        "order_id": "3b23c1c7-f4ef-4f0d-8b9a-9e53c61f1a0d",
                        "client_order_id": plan.client_order_id,
                        "fill_count": "1.00",
                        "remaining_count": "8.00",
                        "ts_ms": 1,
                    },
                )
            ]
        )
        auth = authorize_write("demo-trade", self.settings, self.temp.root)
        try:
            client = KalshiClient(
                DEMO_REST_URL,
                root=self.temp.root,
                timeout_seconds=5,
                credentials=self.credentials,
                session=session,
            )
            with self.assertRaises(AmbiguousMutationError):
                client.create_order(plan.payload(), auth)
        finally:
            revoke_write(auth)

    def test_mutation_transport_error_is_ambiguous(self) -> None:
        session = FakeSession(exc=requests.ConnectionError("network"))
        auth = authorize_write("demo-trade", self.settings, self.temp.root)
        try:
            client = KalshiClient(
                DEMO_REST_URL,
                root=self.temp.root,
                timeout_seconds=5,
                credentials=self.credentials,
                session=session,
            )
            with self.assertRaises(AmbiguousMutationError):
                client.create_order(valid_plan().payload(), auth)
        finally:
            revoke_write(auth)

    def test_mutation_http_error_is_treated_as_ambiguous(self) -> None:
        session = FakeSession([FakeResponse(400, {"code": "bad", "message": "rejected"})])
        auth = authorize_write("demo-trade", self.settings, self.temp.root)
        try:
            client = KalshiClient(
                DEMO_REST_URL,
                root=self.temp.root,
                timeout_seconds=5,
                credentials=self.credentials,
                session=session,
            )
            with self.assertRaises(AmbiguousMutationError):
                client.create_order(valid_plan().payload(), auth)
        finally:
            revoke_write(auth)

    def test_redirect_is_never_followed(self) -> None:
        session = FakeSession([FakeResponse(302, {"message": "redirect"})])
        client = KalshiClient(DEMO_REST_URL, root=self.temp.root, timeout_seconds=5, session=session)
        with self.assertRaises(ApiError):
            client.list_markets("KXBTC15M")
        self.assertFalse(session.calls[0]["allow_redirects"])

    def test_authenticated_read_requires_credentials(self) -> None:
        session = FakeSession([FakeResponse(200, {})])
        client = KalshiClient(DEMO_REST_URL, root=self.temp.root, timeout_seconds=5, session=session)
        with self.assertRaises(ApiError):
            client.get_balance()

    def test_non_json_response_is_rejected(self) -> None:
        response = FakeResponse(200, {})
        response.content = b"not-json"
        response.text = "not-json"
        response.json = lambda: (_ for _ in ()).throw(ValueError("bad"))  # type: ignore[method-assign]
        session = FakeSession([response])
        client = KalshiClient(DEMO_REST_URL, root=self.temp.root, timeout_seconds=5, session=session)
        with self.assertRaises(ApiError):
            client.list_markets("KXBTC15M")


if __name__ == "__main__":
    unittest.main()
