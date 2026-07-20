"""Transparent market discovery and exact 10x1c order planning."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from .api import ApiError, KalshiClient
from .constants import (
    ALLOWED_SERIES,
    ECONOMIC_BUY_PRICE,
    ORDER_COUNT,
    YES_ASK_PRICE_FOR_NO_BUY,
    YES_BID_PRICE,
)
from .models import MarketCandidate, OrderPlan
from .safety import ticker_is_allowed, ticker_is_canonical


@dataclass(frozen=True)
class DiscoveryResult:
    plans: tuple[OrderPlan, ...]
    notes: tuple[str, ...]


def _decimal(raw: Any) -> Decimal | None:
    if raw in {None, ""}:
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _price(row: dict[str, Any], dollar_key: str, cent_key: str) -> Decimal | None:
    value = _decimal(row.get(dollar_key))
    if value is not None:
        return value
    cents = _decimal(row.get(cent_key))
    return cents / Decimal("100") if cents is not None else None


def _parse_time(raw: Any) -> datetime | None:
    if raw in {None, ""}:
        return None
    if isinstance(raw, (int, float)):
        try:
            stamp = float(raw)
            if stamp > 10_000_000_000:
                stamp /= 1000
            return datetime.fromtimestamp(stamp, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(raw).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _series_for_ticker(ticker: str) -> str | None:
    normalized = ticker.strip().upper()
    for series in ALLOWED_SERIES:
        if normalized == series or normalized.startswith(series + "-"):
            return series
    return None


def market_candidate(row: dict[str, Any], *, now: datetime, min_seconds_to_close: int) -> MarketCandidate | None:
    ticker = str(row.get("ticker") or row.get("market_ticker") or "").strip().upper()
    series = str(row.get("series_ticker") or "").strip().upper() or (_series_for_ticker(ticker) or "")
    if series not in ALLOWED_SERIES or not ticker_is_allowed(ticker):
        return None
    status = str(row.get("status") or "open").strip().lower()
    if status not in {"open", "active"}:
        return None
    close_time = None
    for key in ("close_time", "expected_expiration_time", "expiration_time", "latest_expiration_time"):
        close_time = _parse_time(row.get(key))
        if close_time is not None:
            break
    if close_time is None or (close_time - now).total_seconds() < min_seconds_to_close:
        return None
    yes_ask = _price(row, "yes_ask_dollars", "yes_ask")
    no_ask = _price(row, "no_ask_dollars", "no_ask")
    if yes_ask is None:
        no_bid = _price(row, "no_bid_dollars", "no_bid")
        if no_bid is not None:
            yes_ask = Decimal("1") - no_bid
    if no_ask is None:
        yes_bid = _price(row, "yes_bid_dollars", "yes_bid")
        if yes_bid is not None:
            no_ask = Decimal("1") - yes_bid
    liquidity = _price(row, "liquidity_dollars", "liquidity") or Decimal("0")
    title = str(row.get("title") or row.get("subtitle") or ticker).strip()
    return MarketCandidate(series, ticker, title, close_time, yes_ask, no_ask, liquidity, row)


def choose_outcome(candidate: MarketCandidate, policy: str) -> str | None:
    if policy == "yes":
        return "yes"
    if policy == "no":
        return "no"
    if candidate.yes_ask is None or candidate.no_ask is None:
        return None
    return "yes" if candidate.yes_ask <= candidate.no_ask else "no"


def plan_for_candidate(candidate: MarketCandidate, policy: str) -> OrderPlan | None:
    outcome = choose_outcome(candidate, policy)
    if outcome is None:
        return None
    side = "bid" if outcome == "yes" else "ask"
    price = YES_BID_PRICE if outcome == "yes" else YES_ASK_PRICE_FOR_NO_BUY
    return OrderPlan(
        series=candidate.series,
        ticker=candidate.ticker,
        title=candidate.title,
        close_time=candidate.close_time,
        outcome=outcome,
        side=side,
        count=ORDER_COUNT,
        price=price,
        economic_buy_price=ECONOMIC_BUY_PRICE,
        client_order_id=str(uuid.uuid4()),
    )


def discover_plans(
    client: KalshiClient,
    *,
    direction_policy: str,
    min_seconds_to_close: int,
    now: datetime | None = None,
) -> DiscoveryResult:
    current = now or datetime.now(timezone.utc)
    plans: list[OrderPlan] = []
    notes: list[str] = []
    for series in ALLOWED_SERIES:
        try:
            rows = client.list_markets(series)
        except ApiError as exc:
            notes.append(f"{series}: market discovery failed closed ({exc})")
            continue
        candidates = [
            candidate
            for row in rows
            if (candidate := market_candidate(row, now=current, min_seconds_to_close=min_seconds_to_close)) is not None
        ]
        candidates.sort(key=lambda item: (item.close_time, -item.liquidity, item.ticker))
        if not candidates:
            notes.append(f"{series}: no eligible open market")
            continue
        plan = plan_for_candidate(candidates[0], direction_policy)
        if plan is None:
            notes.append(f"{series}: price fields were insufficient for the cheapest-side policy")
            continue
        plans.append(plan)
    return DiscoveryResult(tuple(plans), tuple(notes))


def _levels(orderbook: dict[str, Any], side: str) -> list[Decimal]:
    fp = orderbook.get("orderbook_fp")
    legacy = orderbook.get("orderbook")
    container = fp if isinstance(fp, dict) else legacy if isinstance(legacy, dict) else None
    if container is None:
        raise ApiError("orderbook response omitted orderbook data")
    key = f"{side}_dollars" if container is fp else side
    raw_levels = container.get(key, [])
    if raw_levels is None:
        raw_levels = []
    if not isinstance(raw_levels, list):
        raise ApiError("orderbook price levels have an unexpected shape")
    prices: list[Decimal] = []
    for row in raw_levels:
        if not isinstance(row, (list, tuple)) or not row:
            continue
        price = _decimal(row[0])
        if price is None:
            continue
        if container is legacy:
            price /= Decimal("100")
        if Decimal("0") <= price <= Decimal("1"):
            prices.append(price)
    return prices


def final_orderbook_check(plan: OrderPlan, orderbook: dict[str, Any]) -> tuple[bool, str]:
    yes_bids = _levels(orderbook, "yes")
    no_bids = _levels(orderbook, "no")
    if plan.outcome == "yes":
        best_no_bid = max(no_bids, default=None)
        if best_no_bid is not None and Decimal("1") - best_no_bid <= ECONOMIC_BUY_PRICE:
            return False, "1c YES bid would cross the current book; post-only order skipped"
    elif plan.outcome == "no":
        best_yes_bid = max(yes_bids, default=None)
        if best_yes_bid is not None and Decimal("1") - best_yes_bid <= ECONOMIC_BUY_PRICE:
            return False, "1c NO bid would cross the current book; post-only order skipped"
    else:
        return False, "order plan outcome is invalid"
    return True, "final book permits a resting exact-1c post-only order"


def _account_row_ticker(row: object, *, label: str) -> str:
    if not isinstance(row, dict):
        raise ApiError(f"{label} account row was not an object; write preflight blocked")
    raw_ticker = row["ticker"] if "ticker" in row else row.get("market_ticker")
    if not ticker_is_canonical(raw_ticker):
        raise ApiError(f"{label} account row omitted a canonical ticker; write preflight blocked")
    return raw_ticker.strip().upper()


def resting_tickers(orders: Iterable[object]) -> set[str]:
    tickers: set[str] = set()
    for order in orders:
        tickers.add(_account_row_ticker(order, label="resting-order"))
    return tickers


def position_tickers(positions: Iterable[object]) -> set[str]:
    """Normalize market tickers returned by the authenticated positions endpoint."""
    tickers: set[str] = set()
    for position in positions:
        tickers.add(_account_row_ticker(position, label="position"))
    return tickers
