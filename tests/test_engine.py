from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from kalshi_public.api import AmbiguousMutationError, ApiError
from kalshi_public.constants import CREATE_ORDER_PATH, DEMO_REST_URL
from kalshi_public.engine import WriteCycleStop, _append_log, run_write
from kalshi_public.ledger import load_ledger
from kalshi_public.safety import (
    SafetyError,
    authorize_write,
    require_create_order_permission,
    revoke_write,
)
from kalshi_public.strategy import DiscoveryResult
from tests.helpers import TempPublicRoot
from tests.test_safety import valid_plan


class _FakeClient:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.create_calls = 0

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def get_balance(self) -> dict[str, object]:
        return {"balance_dollars": "1.00"}

    def list_resting_orders(self) -> list[dict[str, object]]:
        return []

    def list_positions(self) -> list[dict[str, object]]:
        return []

    def get_orderbook(self, ticker: str) -> dict[str, object]:
        return {}

    def create_order(self, payload: dict[str, object], authorization: object) -> dict[str, object]:
        self.create_calls += 1
        raise self.error


class EngineSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TempPublicRoot()
        self.settings = self.temp.settings("demo-trade")

    def tearDown(self) -> None:
        self.temp.close()

    @unittest.skipIf(os.name == "nt", "symlink semantics differ on Windows")
    def test_symlinked_order_log_is_rejected(self) -> None:
        logs = self.temp.root / "logs"
        logs.mkdir()
        outside = self.temp.base / "outside-log.jsonl"
        outside.write_text("do not change\n", encoding="utf-8")
        (logs / "orders.jsonl").symlink_to(outside)
        with self.assertRaisesRegex(SafetyError, "order log must not be a symlink"):
            _append_log(self.temp.root, {"result": "test"})
        self.assertEqual(outside.read_text(encoding="utf-8"), "do not change\n")

    def test_local_safety_block_releases_unsent_reservation(self) -> None:
        cases = (
            (SafetyError("blocked locally before Session.request"), "released_before_send"),
            (AmbiguousMutationError("transport outcome unknown"), "ambiguous"),
            (ApiError("unexpected mutation response"), "ambiguous"),
        )
        for error, expected_status in cases:
            with self.subTest(error=type(error).__name__):
                temp = TempPublicRoot()
                settings = temp.settings("demo-trade", continuous=True)
                plan = valid_plan()
                with patch("kalshi_public.safety.authorization_failures", return_value=[]):
                    authorization = authorize_write("demo-trade", settings, temp.root, continuous=True)
                client = _FakeClient(error)
                try:
                    with (
                        patch("kalshi_public.engine.load_credentials", return_value=object()),
                        patch("kalshi_public.engine.KalshiClient", return_value=client),
                        patch(
                            "kalshi_public.engine.discover_plans",
                            return_value=DiscoveryResult((plan,), ()),
                        ),
                        patch("kalshi_public.engine.final_orderbook_check", return_value=(True, "safe")),
                        patch("kalshi_public.engine.time.sleep") as sleep,
                        self.assertRaises(WriteCycleStop),
                    ):
                        run_write(
                            temp.root,
                            settings,
                            mode="demo-trade",
                            authorization=authorization,
                            continuous=True,
                        )
                    sleep.assert_not_called()
                    self.assertEqual(client.create_calls, 1)
                    entries = load_ledger(temp.root)["entries"]
                    self.assertEqual(len(entries), 1)
                    self.assertEqual(entries[0]["status"], expected_status)
                    with self.assertRaisesRegex(SafetyError, "no in-process write authorization"):
                        require_create_order_permission(
                            authorization,
                            endpoint=DEMO_REST_URL,
                            method="POST",
                            path=CREATE_ORDER_PATH,
                            payload=plan.payload(),
                            root=temp.root,
                        )
                finally:
                    revoke_write(authorization)
                    temp.close()


if __name__ == "__main__":
    unittest.main()
