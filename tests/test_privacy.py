from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from kalshi_public.constants import PRIVACY_PURGE_ACK
from kalshi_public.privacy import purge_local_data
from kalshi_public.safety import SafetyError, create_kill_switch


class PrivacyCleanupTests(unittest.TestCase):
    def test_cleanup_removes_logs_and_settled_state_but_keeps_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            create_kill_switch(root)
            (root / "logs").mkdir()
            (root / "runtime").mkdir()
            (root / "logs" / ".gitkeep").write_text("", encoding="utf-8")
            (root / "runtime" / ".gitkeep").write_text("", encoding="utf-8")
            (root / "logs" / "orders.jsonl").write_text("account-linked\n", encoding="utf-8")
            (root / "runtime" / "session_ledger.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "cap_contracts": "80.00",
                        "created_utc": "2026-01-01T00:00:00Z",
                        "updated_utc": "2026-01-01T00:00:00Z",
                        "entries": [],
                    }
                ),
                encoding="utf-8",
            )
            result = purge_local_data(root, PRIVACY_PURGE_ACK)
            self.assertEqual(result, {"logs": 1, "runtime": 1})
            self.assertTrue((root / "logs" / ".gitkeep").is_file())
            self.assertTrue((root / "runtime" / ".gitkeep").is_file())

    def test_cleanup_requires_kill_switch_and_exact_ack(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(SafetyError):
                purge_local_data(root, PRIVACY_PURGE_ACK)
            create_kill_switch(root)
            with self.assertRaises(SafetyError):
                purge_local_data(root, "")

    def test_cleanup_preserves_ambiguous_submission_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            create_kill_switch(root)
            (root / "runtime").mkdir()
            (root / "runtime" / "session_ledger.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "cap_contracts": "80.00",
                        "created_utc": "2026-01-01T00:00:00Z",
                        "updated_utc": "2026-01-01T00:00:00Z",
                        "entries": [
                            {
                                "reservation_id": "11111111-1111-4111-8111-111111111111",
                                "status": "ambiguous",
                                "mode": "demo-trade",
                                "series": "KXBTC15M",
                                "ticker": "KXBTC15M-TEST",
                                "outcome": "yes",
                                "side": "bid",
                                "count": "10.00",
                                "economic_price": "0.0100",
                                "yes_book_price": "0.0100",
                                "client_order_id": "22222222-2222-4222-8222-222222222222",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(SafetyError, "reserved or ambiguous"):
                purge_local_data(root, PRIVACY_PURGE_ACK)
            self.assertTrue((root / "runtime" / "session_ledger.json").is_file())


if __name__ == "__main__":
    unittest.main()
