from __future__ import annotations

import os
import unittest
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from kalshi_public.constants import (
    CREATE_ORDER_PATH,
    DEMO_REST_URL,
    KILL_SWITCH_OFF_ACK,
    ORDER_COUNT,
    PRODUCTION_REST_URL,
)
from kalshi_public.models import OrderPlan
from kalshi_public.safety import (
    SafetyError,
    authorization_failures,
    authorize_write,
    create_kill_switch,
    remove_kill_switch,
    require_create_order_permission,
    revoke_write,
    ticker_is_allowed,
    validate_endpoint,
    validate_order_payload,
)
from tests.helpers import TempPublicRoot


def valid_plan(outcome: str = "yes") -> OrderPlan:
    return OrderPlan(
        "KXBTC15M",
        "KXBTC15M-TEST",
        "Test",
        datetime.now(timezone.utc),
        outcome,
        "bid" if outcome == "yes" else "ask",
        ORDER_COUNT,
        Decimal("0.01") if outcome == "yes" else Decimal("0.99"),
        Decimal("0.01"),
        str(uuid.uuid4()),
    )


class PayloadTests(unittest.TestCase):
    def test_yes_payload_is_valid(self) -> None:
        self.assertEqual(validate_order_payload(valid_plan("yes").payload()), [])

    def test_no_payload_is_valid(self) -> None:
        self.assertEqual(validate_order_payload(valid_plan("no").payload()), [])

    def test_wrong_count_is_blocked(self) -> None:
        payload = valid_plan().payload()
        payload["count"] = "11.00"
        self.assertTrue(any("count" in item for item in validate_order_payload(payload)))

    def test_wrong_yes_price_is_blocked(self) -> None:
        payload = valid_plan().payload()
        payload["price"] = "0.0200"
        self.assertTrue(any("economic buy price" in item for item in validate_order_payload(payload)))

    def test_wrong_no_price_is_blocked(self) -> None:
        payload = valid_plan("no").payload()
        payload["price"] = "0.9800"
        self.assertTrue(any("economic buy price" in item for item in validate_order_payload(payload)))

    def test_outside_ticker_is_blocked(self) -> None:
        payload = valid_plan().payload()
        payload["ticker"] = "NOT-ALLOWED"
        self.assertTrue(any("allowlist" in item for item in validate_order_payload(payload)))

    def test_non_uuid_client_id_is_blocked(self) -> None:
        payload = valid_plan().payload()
        payload["client_order_id"] = "k10pub1:abc"
        self.assertTrue(any("UUID" in item for item in validate_order_payload(payload)))

    def test_post_only_cannot_be_disabled(self) -> None:
        payload = valid_plan().payload()
        payload["post_only"] = False
        self.assertTrue(any("post_only" in item for item in validate_order_payload(payload)))

    def test_extra_payload_field_is_blocked(self) -> None:
        payload = valid_plan().payload()
        payload["order_group_id"] = "x"
        self.assertTrue(any("unexpected" in item for item in validate_order_payload(payload)))

    def test_allowed_ticker_prefixes(self) -> None:
        self.assertTrue(ticker_is_allowed("KXBTC15M-26JUL191200"))
        self.assertFalse(ticker_is_allowed("KXBTC-OTHER"))

    def test_ticker_control_and_url_delimiters_are_blocked(self) -> None:
        for ticker in ("KXBTC15M-TEST#FRAGMENT", "KXBTC15M-TEST/CHILD", "KXBTC15M-TEST\nINJECT"):
            with self.subTest(ticker=ticker):
                self.assertFalse(ticker_is_allowed(ticker))


class AuthorizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.windows_acl = patch("kalshi_public.auth._windows_acl_failures", return_value=[])
        self.windows_acl.start()
        self.temp = TempPublicRoot()

    def tearDown(self) -> None:
        self.temp.close()
        self.windows_acl.stop()

    def test_demo_authorization_passes_with_every_gate(self) -> None:
        settings = self.temp.settings("demo-trade")
        auth = authorize_write("demo-trade", settings, self.temp.root)
        self.assertEqual(auth.endpoint, DEMO_REST_URL)
        revoke_write(auth)

    def test_live_authorization_uses_production_endpoint(self) -> None:
        settings = self.temp.settings("live")
        with patch("kalshi_public.verify.strict_verification_failures", return_value=[]):
            auth = authorize_write("live", settings, self.temp.root)
        self.assertEqual(auth.endpoint, PRODUCTION_REST_URL)
        revoke_write(auth)

    def test_live_requires_strict_ci_attestation(self) -> None:
        settings = self.temp.settings("live")
        self.temp.set_attestation_ci(False)
        failures = authorization_failures("live", settings, self.temp.root)
        self.assertTrue(any("strict verification" in item for item in failures))

    def test_source_tamper_after_verification_blocks_write(self) -> None:
        settings = self.temp.settings("demo-trade")
        self.temp.fixture_path.write_text("edited after verification\n", encoding="utf-8")
        failures = authorization_failures("demo-trade", settings, self.temp.root)
        self.assertTrue(any("verified manifest" in item for item in failures))

    def test_kill_switch_blocks_authorization(self) -> None:
        settings = self.temp.settings("demo-trade")
        create_kill_switch(self.temp.root)
        failures = authorization_failures("demo-trade", settings, self.temp.root)
        self.assertTrue(any("kill switch" in item for item in failures))

    def test_expired_attestation_blocks_authorization(self) -> None:
        settings = self.temp.settings("demo-trade")
        self.temp.expire_attestation()
        failures = authorization_failures("demo-trade", settings, self.temp.root)
        self.assertTrue(any("older" in item for item in failures))

    def test_production_ack_cannot_authorize_demo(self) -> None:
        settings = self.temp.settings("demo-trade")
        values = dict(settings.values)
        values["PUBLIC_RISK_ACK"] = "I_ACCEPT_REAL_MONEY_RISK"
        changed = type(settings)(values=values, source_exists=True, unknown_keys=())
        self.assertTrue(
            any("PUBLIC_RISK_ACK" in item for item in authorization_failures("demo-trade", changed, self.temp.root))
        )

    def test_unknown_env_key_blocks_write(self) -> None:
        settings = self.temp.settings("demo-trade")
        changed = type(settings)(values=settings.values, source_exists=True, unknown_keys=("MYSTERY",))
        self.assertTrue(
            any("unsupported" in item for item in authorization_failures("demo-trade", changed, self.temp.root))
        )

    @unittest.skipIf(os.name == "nt", "POSIX permissions test")
    def test_broad_env_permissions_block_write(self) -> None:
        settings = self.temp.settings("demo-trade")
        (self.temp.root / ".env").chmod(0o644)
        self.assertTrue(
            any("permissions" in item for item in authorization_failures("demo-trade", settings, self.temp.root))
        )

    def test_environment_values_alone_do_not_authorize_mutation(self) -> None:
        with self.assertRaises(SafetyError):
            require_create_order_permission(
                None,
                endpoint=DEMO_REST_URL,
                method="POST",
                path=CREATE_ORDER_PATH,
                payload=valid_plan().payload(),
                root=self.temp.root,
            )

    def test_mutation_route_is_exact(self) -> None:
        settings = self.temp.settings("demo-trade")
        auth = authorize_write("demo-trade", settings, self.temp.root)
        try:
            with self.assertRaises(SafetyError):
                require_create_order_permission(
                    auth,
                    endpoint=DEMO_REST_URL,
                    method="POST",
                    path="/portfolio/events/orders/batched",
                    payload=valid_plan().payload(),
                    root=self.temp.root,
                )
        finally:
            revoke_write(auth)

    def test_endpoint_mismatch_is_blocked(self) -> None:
        settings = self.temp.settings("demo-trade")
        auth = authorize_write("demo-trade", settings, self.temp.root)
        try:
            with self.assertRaises(SafetyError):
                require_create_order_permission(
                    auth,
                    endpoint=PRODUCTION_REST_URL,
                    method="POST",
                    path=CREATE_ORDER_PATH,
                    payload=valid_plan().payload(),
                    root=self.temp.root,
                )
        finally:
            revoke_write(auth)

    def test_process_limit_blocks_ninth_order(self) -> None:
        settings = self.temp.settings("demo-trade")
        auth = authorize_write("demo-trade", settings, self.temp.root)
        try:
            for _ in range(8):
                require_create_order_permission(
                    auth,
                    endpoint=DEMO_REST_URL,
                    method="POST",
                    path=CREATE_ORDER_PATH,
                    payload=valid_plan().payload(),
                    root=self.temp.root,
                )
            with self.assertRaises(SafetyError):
                require_create_order_permission(
                    auth,
                    endpoint=DEMO_REST_URL,
                    method="POST",
                    path=CREATE_ORDER_PATH,
                    payload=valid_plan().payload(),
                    root=self.temp.root,
                )
        finally:
            revoke_write(auth)

    def test_kill_switch_is_rechecked_at_final_boundary(self) -> None:
        settings = self.temp.settings("demo-trade")
        auth = authorize_write("demo-trade", settings, self.temp.root)
        create_kill_switch(self.temp.root)
        try:
            with self.assertRaises(SafetyError):
                require_create_order_permission(
                    auth,
                    endpoint=DEMO_REST_URL,
                    method="POST",
                    path=CREATE_ORDER_PATH,
                    payload=valid_plan().payload(),
                    root=self.temp.root,
                )
        finally:
            revoke_write(auth)

    def test_source_tamper_after_authorization_is_blocked_at_final_boundary(self) -> None:
        settings = self.temp.settings("demo-trade")
        auth = authorize_write("demo-trade", settings, self.temp.root)
        self.temp.fixture_path.write_text("edited after authorization\n", encoding="utf-8")
        try:
            with self.assertRaisesRegex(SafetyError, "verification changed after authorization"):
                require_create_order_permission(
                    auth,
                    endpoint=DEMO_REST_URL,
                    method="POST",
                    path=CREATE_ORDER_PATH,
                    payload=valid_plan().payload(),
                    root=self.temp.root,
                )
        finally:
            revoke_write(auth)

    def test_kill_switch_removal_requires_exact_ack(self) -> None:
        create_kill_switch(self.temp.root)
        with self.assertRaises(SafetyError):
            remove_kill_switch(self.temp.root, "yes")
        remove_kill_switch(self.temp.root, KILL_SWITCH_OFF_ACK)
        self.assertFalse((self.temp.root / "TRADING_DISABLED").exists())

    def test_dirty_endpoint_is_rejected(self) -> None:
        with self.assertRaises(SafetyError):
            validate_endpoint(DEMO_REST_URL + "?redirect=x", DEMO_REST_URL)


if __name__ == "__main__":
    unittest.main()
