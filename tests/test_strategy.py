from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from kalshi_public.api import ApiError
from kalshi_public.models import MarketCandidate
from kalshi_public.strategy import (
    choose_outcome,
    discover_plans,
    final_orderbook_check,
    market_candidate,
    plan_for_candidate,
    position_tickers,
    resting_tickers,
)

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)


def candidate(yes_ask: str = "0.20", no_ask: str = "0.80") -> MarketCandidate:
    return MarketCandidate(
        "KXBTC15M",
        "KXBTC15M-TEST",
        "Test",
        NOW + timedelta(minutes=10),
        Decimal(yes_ask),
        Decimal(no_ask),
        Decimal("100"),
        {},
    )


class FakeMarketClient:
    def __init__(self, rows: dict[str, list[dict[str, Any]]]) -> None:
        self.rows = rows

    def list_markets(self, series: str) -> list[dict[str, Any]]:
        return self.rows.get(series, [])


class StrategyTests(unittest.TestCase):
    def test_market_candidate_parses_fixed_point_prices(self) -> None:
        row = {
            "ticker": "KXBTC15M-TEST",
            "series_ticker": "KXBTC15M",
            "status": "open",
            "close_time": (NOW + timedelta(minutes=10)).isoformat(),
            "yes_ask_dollars": "0.2000",
            "no_ask_dollars": "0.8000",
            "liquidity_dollars": "12.34",
        }
        parsed = market_candidate(row, now=NOW, min_seconds_to_close=60)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.yes_ask, Decimal("0.2000"))
        self.assertEqual(parsed.liquidity, Decimal("12.34"))

    def test_market_candidate_converts_legacy_cents(self) -> None:
        row = {
            "ticker": "KXBTC15M-TEST",
            "status": "open",
            "close_time": (NOW + timedelta(minutes=10)).isoformat(),
            "yes_ask": 20,
            "no_ask": 80,
            "liquidity": 1234,
        }
        parsed = market_candidate(row, now=NOW, min_seconds_to_close=60)
        assert parsed is not None
        self.assertEqual(parsed.yes_ask, Decimal("0.2"))
        self.assertEqual(parsed.liquidity, Decimal("12.34"))

    def test_market_too_close_is_skipped(self) -> None:
        row = {
            "ticker": "KXBTC15M-TEST",
            "status": "open",
            "close_time": (NOW + timedelta(seconds=30)).isoformat(),
            "yes_ask_dollars": "0.2",
            "no_ask_dollars": "0.8",
        }
        self.assertIsNone(market_candidate(row, now=NOW, min_seconds_to_close=60))

    def test_non_allowlisted_series_is_skipped(self) -> None:
        row = {
            "ticker": "OTHER-TEST",
            "series_ticker": "OTHER",
            "status": "open",
            "close_time": (NOW + timedelta(minutes=5)).isoformat(),
        }
        self.assertIsNone(market_candidate(row, now=NOW, min_seconds_to_close=60))

    def test_cheapest_policy_selects_yes(self) -> None:
        self.assertEqual(choose_outcome(candidate("0.10", "0.90"), "cheapest"), "yes")

    def test_cheapest_policy_selects_no(self) -> None:
        self.assertEqual(choose_outcome(candidate("0.90", "0.10"), "cheapest"), "no")

    def test_fixed_direction_policy_overrides_prices(self) -> None:
        self.assertEqual(choose_outcome(candidate("0.90", "0.10"), "yes"), "yes")
        self.assertEqual(choose_outcome(candidate("0.10", "0.90"), "no"), "no")

    def test_yes_plan_is_bid_at_one_cent(self) -> None:
        plan = plan_for_candidate(candidate(), "yes")
        assert plan is not None
        self.assertEqual(plan.side, "bid")
        self.assertEqual(plan.price, Decimal("0.01"))
        self.assertEqual(plan.economic_buy_price, Decimal("0.01"))

    def test_no_plan_is_yes_ask_at_ninety_nine_cents(self) -> None:
        plan = plan_for_candidate(candidate(), "no")
        assert plan is not None
        self.assertEqual(plan.side, "ask")
        self.assertEqual(plan.price, Decimal("0.99"))
        self.assertEqual(plan.economic_buy_price, Decimal("0.01"))

    def test_yes_crossing_book_is_skipped(self) -> None:
        plan = plan_for_candidate(candidate(), "yes")
        assert plan is not None
        ok, _ = final_orderbook_check(plan, {"orderbook_fp": {"yes_dollars": [], "no_dollars": [["0.9900", "5.00"]]}})
        self.assertFalse(ok)

    def test_no_crossing_book_is_skipped(self) -> None:
        plan = plan_for_candidate(candidate(), "no")
        assert plan is not None
        ok, _ = final_orderbook_check(plan, {"orderbook_fp": {"yes_dollars": [["0.9900", "5.00"]], "no_dollars": []}})
        self.assertFalse(ok)

    def test_non_crossing_empty_book_passes(self) -> None:
        for policy in ("yes", "no"):
            plan = plan_for_candidate(candidate(), policy)
            assert plan is not None
            ok, _ = final_orderbook_check(plan, {"orderbook_fp": {"yes_dollars": [], "no_dollars": []}})
            self.assertTrue(ok)

    def test_discovery_selects_soonest_eligible_market_per_series(self) -> None:
        later = {
            "ticker": "KXBTC15M-LATER",
            "status": "open",
            "close_time": (NOW + timedelta(minutes=12)).isoformat(),
            "yes_ask_dollars": "0.2",
            "no_ask_dollars": "0.8",
        }
        sooner = {
            "ticker": "KXBTC15M-SOONER",
            "status": "open",
            "close_time": (NOW + timedelta(minutes=8)).isoformat(),
            "yes_ask_dollars": "0.2",
            "no_ask_dollars": "0.8",
        }
        result = discover_plans(
            FakeMarketClient({"KXBTC15M": [later, sooner]}),  # type: ignore[arg-type]
            direction_policy="cheapest",
            min_seconds_to_close=60,
            now=NOW,
        )
        self.assertEqual(result.plans[0].ticker, "KXBTC15M-SOONER")

    def test_discovery_returns_at_most_one_plan_per_series(self) -> None:
        rows = []
        for number in range(3):
            rows.append(
                {
                    "ticker": f"KXBTC15M-{number}",
                    "status": "open",
                    "close_time": (NOW + timedelta(minutes=8 + number)).isoformat(),
                    "yes_ask_dollars": "0.2",
                    "no_ask_dollars": "0.8",
                }
            )
        result = discover_plans(
            FakeMarketClient({"KXBTC15M": rows}),  # type: ignore[arg-type]
            direction_policy="yes",
            min_seconds_to_close=60,
            now=NOW,
        )
        self.assertEqual(len(result.plans), 1)

    def test_resting_tickers_are_normalized(self) -> None:
        result = resting_tickers([{"ticker": "kxbtc15m-test"}, {"market_ticker": "KXETH15M-X"}])
        self.assertEqual(result, {"KXBTC15M-TEST", "KXETH15M-X"})
        for malformed in (None, [], {}, {"ticker": ""}, {"ticker": 123}, {"ticker": "BAD TICKER"}):
            with self.subTest(malformed=malformed), self.assertRaisesRegex(ApiError, "write preflight blocked"):
                resting_tickers([malformed])

    def test_position_tickers_are_normalized(self) -> None:
        result = position_tickers([{"ticker": "kxbtc15m-test"}, {"market_ticker": "KXETH15M-X"}])
        self.assertEqual(result, {"KXBTC15M-TEST", "KXETH15M-X"})
        for malformed in (None, [], {}, {"ticker": ""}, {"ticker": 123}, {"ticker": "BAD TICKER"}):
            with self.subTest(malformed=malformed), self.assertRaisesRegex(ApiError, "write preflight blocked"):
                position_tickers([malformed])


if __name__ == "__main__":
    unittest.main()
