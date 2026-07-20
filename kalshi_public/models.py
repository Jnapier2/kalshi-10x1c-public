"""Typed data models used by the public scanner and order planner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class MarketCandidate:
    series: str
    ticker: str
    title: str
    close_time: datetime
    yes_ask: Decimal | None
    no_ask: Decimal | None
    liquidity: Decimal
    raw: dict[str, Any]


@dataclass(frozen=True)
class OrderPlan:
    series: str
    ticker: str
    title: str
    close_time: datetime
    outcome: str
    side: str
    count: Decimal
    price: Decimal
    economic_buy_price: Decimal
    client_order_id: str

    def payload(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "client_order_id": self.client_order_id,
            "side": self.side,
            "count": f"{self.count:.2f}",
            "price": f"{self.price:.4f}",
            "time_in_force": "good_till_canceled",
            "self_trade_prevention_type": "taker_at_cross",
            "post_only": True,
            "cancel_order_on_pause": True,
            "reduce_only": False,
            "subaccount": 0,
            "exchange_index": 0,
        }
