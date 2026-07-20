from __future__ import annotations

import json
import os
import unittest
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from kalshi_public.constants import SESSION_RESET_ACK
from kalshi_public.ledger import (
    contains_ticker,
    load_ledger,
    mark_accepted,
    mark_ambiguous,
    release_before_send,
    reserve,
    reset,
    status,
)
from kalshi_public.models import OrderPlan
from kalshi_public.safety import SafetyError, create_kill_switch
from tests.helpers import TempPublicRoot


def plan(number: int) -> OrderPlan:
    return OrderPlan(
        "KXBTC15M",
        f"KXBTC15M-TEST-{number}",
        "Test",
        datetime.now(timezone.utc),
        "yes",
        "bid",
        Decimal("10"),
        Decimal("0.01"),
        Decimal("0.01"),
        str(uuid.uuid4()),
    )


class LedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TempPublicRoot()

    def tearDown(self) -> None:
        self.temp.close()

    def test_new_ledger_has_eighty_contracts_remaining(self) -> None:
        current = status(self.temp.root)
        self.assertEqual(current["remaining_contracts"], Decimal("80"))

    def test_reservation_consumes_ten_contracts(self) -> None:
        reserve(self.temp.root, plan(1), "demo-trade")
        current = status(self.temp.root)
        self.assertEqual(current["reserved_contracts"], Decimal("10"))
        self.assertEqual(current["remaining_contracts"], Decimal("70"))

    def test_acceptance_moves_reserved_to_accepted(self) -> None:
        reservation = reserve(self.temp.root, plan(1), "demo-trade")
        mark_accepted(
            self.temp.root,
            reservation,
            {"order_id": "order-1", "fill_count": "0.00", "remaining_count": "10.00", "ts_ms": 1},
        )
        current = status(self.temp.root)
        self.assertEqual(current["reserved_contracts"], Decimal("0"))
        self.assertEqual(current["accepted_contracts"], Decimal("10"))

    def test_ambiguous_submission_keeps_budget_reserved(self) -> None:
        reservation = reserve(self.temp.root, plan(1), "live")
        mark_ambiguous(self.temp.root, reservation, "timeout")
        current = status(self.temp.root)
        self.assertEqual(current["reserved_contracts"], Decimal("10"))

    def test_unsent_reservation_can_be_released(self) -> None:
        reservation = reserve(self.temp.root, plan(1), "demo-trade")
        release_before_send(self.temp.root, reservation, "preflight")
        self.assertEqual(status(self.temp.root)["remaining_contracts"], Decimal("80"))

    def test_duplicate_ticker_is_blocked(self) -> None:
        first = plan(1)
        reserve(self.temp.root, first, "demo-trade")
        self.assertTrue(contains_ticker(self.temp.root, first.ticker))
        with self.assertRaises(SafetyError):
            reserve(self.temp.root, first, "demo-trade")

    def test_ninth_reservation_is_blocked(self) -> None:
        for number in range(8):
            reserve(self.temp.root, plan(number), "demo-trade")
        with self.assertRaises(SafetyError):
            reserve(self.temp.root, plan(9), "demo-trade")
        self.assertEqual(status(self.temp.root)["remaining_contracts"], Decimal("0"))

    def test_modified_cap_fails_closed(self) -> None:
        reserve(self.temp.root, plan(1), "demo-trade")
        path = self.temp.root / "runtime/session_ledger.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["cap_contracts"] = "8000"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(SafetyError):
            load_ledger(self.temp.root)

    def test_negative_count_tamper_fails_closed(self) -> None:
        reserve(self.temp.root, plan(1), "demo-trade")
        path = self.temp.root / "runtime/session_ledger.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["entries"][0]["count"] = "-10.00"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(SafetyError):
            load_ledger(self.temp.root)

    def test_duplicate_active_ticker_tamper_fails_closed(self) -> None:
        reserve(self.temp.root, plan(1), "demo-trade")
        reserve(self.temp.root, plan(2), "demo-trade")
        path = self.temp.root / "runtime/session_ledger.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["entries"][1]["ticker"] = data["entries"][0]["ticker"]
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(SafetyError):
            load_ledger(self.temp.root)

    @unittest.skipIf(os.name == "nt", "symlink semantics differ on Windows")
    def test_symlinked_ledger_file_fails_closed(self) -> None:
        runtime = self.temp.root / "runtime"
        runtime.mkdir()
        target = self.temp.base / "outside-ledger.json"
        target.write_text("{}\n", encoding="utf-8")
        (runtime / "session_ledger.json").symlink_to(target)
        with self.assertRaisesRegex(SafetyError, "must not be a symlink"):
            load_ledger(self.temp.root)

    @unittest.skipIf(os.name == "nt", "symlink semantics differ on Windows")
    def test_symlinked_runtime_directory_fails_closed(self) -> None:
        outside = self.temp.base / "outside-runtime"
        outside.mkdir()
        (self.temp.root / "runtime").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(SafetyError, "runtime state directory"):
            status(self.temp.root)

    def test_malformed_ledger_fails_closed(self) -> None:
        path = self.temp.root / "runtime/session_ledger.json"
        path.parent.mkdir()
        path.write_text("not json", encoding="utf-8")
        with self.assertRaises(SafetyError):
            status(self.temp.root)

    def test_reset_requires_kill_switch(self) -> None:
        reserve(self.temp.root, plan(1), "demo-trade")
        with self.assertRaises(SafetyError):
            reset(self.temp.root, SESSION_RESET_ACK)

    def test_reset_requires_exact_ack(self) -> None:
        reserve(self.temp.root, plan(1), "demo-trade")
        create_kill_switch(self.temp.root)
        with self.assertRaises(SafetyError):
            reset(self.temp.root, "yes")

    def test_reset_archives_prior_ledger_and_keeps_zero_state(self) -> None:
        reserve(self.temp.root, plan(1), "demo-trade")
        create_kill_switch(self.temp.root)
        archive = reset(self.temp.root, SESSION_RESET_ACK)
        self.assertTrue(archive.exists())
        self.assertEqual(status(self.temp.root)["remaining_contracts"], Decimal("80"))
        self.assertTrue((self.temp.root / "TRADING_DISABLED").exists())


if __name__ == "__main__":
    unittest.main()
