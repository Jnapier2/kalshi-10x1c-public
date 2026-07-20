"""One-cycle and continuous execution engine for the public edition."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from .api import AmbiguousMutationError, ApiError, KalshiClient
from .auth import load_credentials
from .constants import (
    DEMO_REST_URL,
    ECONOMIC_BUY_PRICE,
    ORDER_COUNT,
    ORDER_LOG_RELATIVE_PATH,
    PRODUCTION_REST_URL,
)
from .env import RuntimeSettings
from .instance_lock import InstanceLock
from .ledger import contains_ticker, mark_accepted, mark_ambiguous, release_before_send, reserve, status
from .safety import SafetyError, WriteAuthorization, kill_switch_is_on, revoke_write
from .strategy import DiscoveryResult, discover_plans, final_orderbook_check, position_tickers, resting_tickers


class WriteCycleStop(SafetyError):
    """A terminal write-cycle condition that must stop continuous execution."""


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _append_log(root: Path, record: dict[str, Any]) -> None:
    path = root / ORDER_LOG_RELATIVE_PATH
    if path.parent.is_symlink():
        raise SafetyError("order-log directory must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise SafetyError("order-log directory is unsafe")
    if path.is_symlink():
        raise SafetyError("order log must not be a symlink")
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise SafetyError(f"order log could not be opened safely ({type(exc).__name__})") from exc
    with os.fdopen(fd, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    if os.name != "nt":
        path.chmod(0o600)


def _balance_money(balance: dict[str, Any]) -> str:
    """Format the canonical fixed-point dollar balance, with cents fallback."""
    try:
        if balance.get("balance_dollars") not in {None, ""}:
            value = Decimal(str(balance["balance_dollars"]))
        elif balance.get("balance") not in {None, ""}:
            value = Decimal(str(balance["balance"])) / Decimal("100")
        else:
            return "unavailable"
    except Exception:
        return "unavailable"
    return f"${value:.2f}"


def _print_plans(result: DiscoveryResult, *, heading: str) -> None:
    print(heading)
    if not result.plans:
        print("  No eligible order plans were found.")
    for plan in result.plans:
        print(
            f"  {plan.series:<10} {plan.ticker:<38} buy {plan.outcome.upper():<3} "
            f"{plan.count:.0f} @ ${plan.economic_buy_price:.2f} | closes {plan.close_time.isoformat()}"
        )
    if result.notes:
        print("Notes:")
        for note in result.notes:
            print(f"  - {note}")


def endpoint_for_mode(mode: str) -> str:
    return DEMO_REST_URL if mode == "demo-trade" else PRODUCTION_REST_URL


def run_read_only(root: Path, settings: RuntimeSettings, *, mode: str) -> int:
    endpoint = endpoint_for_mode(mode)
    with KalshiClient(endpoint, root=root, timeout_seconds=settings.http_timeout_seconds) as client:
        result = discover_plans(
            client,
            direction_policy=settings.direction_policy,
            min_seconds_to_close=settings.min_seconds_to_close,
        )
        heading = "Public market scan" if mode == "scan" else "DRY RUN — no order can be submitted"
        _print_plans(result, heading=heading)
        if mode == "dry-run" and result.plans:
            print("Final order-book checks:")
            for plan in result.plans:
                try:
                    ok, reason = final_orderbook_check(plan, client.get_orderbook(plan.ticker))
                except ApiError as exc:
                    ok, reason = False, f"orderbook unavailable; fail closed ({exc})"
                print(f"  {'PASS' if ok else 'SKIP'} {plan.ticker}: {reason}")
    return 0


def _run_write_cycle(
    root: Path,
    settings: RuntimeSettings,
    *,
    mode: str,
    authorization: WriteAuthorization,
) -> int:
    credentials = load_credentials(settings.values, root)
    endpoint = endpoint_for_mode(mode)
    accepted = 0
    with KalshiClient(
        endpoint,
        root=root,
        timeout_seconds=settings.http_timeout_seconds,
        credentials=credentials,
    ) as client:
        balance = client.get_balance()
        print(f"Authenticated {mode} preflight passed. Reported balance: {_balance_money(balance)}")
        try:
            existing = resting_tickers(client.list_resting_orders())
            positions = position_tickers(client.list_positions())
        except ApiError as exc:
            raise SafetyError(f"could not verify existing orders and positions; write cycle blocked ({exc})") from exc
        result = discover_plans(
            client,
            direction_policy=settings.direction_policy,
            min_seconds_to_close=settings.min_seconds_to_close,
        )
        _print_plans(result, heading=f"Authorized {mode} order plans")
        for plan in result.plans:
            if kill_switch_is_on(root):
                raise WriteCycleStop("kill switch detected; write cycle and continuous mode stopped")
            ledger_state = status(root)
            if ledger_state["remaining_contracts"] < ORDER_COUNT:
                print("Persistent 80-contract session budget is exhausted; stopping.")
                break
            if plan.ticker in existing:
                print(f"SKIP {plan.ticker}: an account resting order already exists for this market")
                continue
            if plan.ticker in positions:
                print(f"SKIP {plan.ticker}: the account already has a non-zero position in this market")
                continue
            if contains_ticker(root, plan.ticker):
                print(f"SKIP {plan.ticker}: session ledger already reserved or accepted this market")
                continue
            try:
                ok, reason = final_orderbook_check(plan, client.get_orderbook(plan.ticker))
            except ApiError as exc:
                print(f"SKIP {plan.ticker}: final orderbook unavailable; fail closed ({exc})")
                continue
            if not ok:
                print(f"SKIP {plan.ticker}: {reason}")
                continue
            reservation_id = reserve(root, plan, mode)
            record = {
                "time": _utc(),
                "mode": mode,
                "ticker": plan.ticker,
                "series": plan.series,
                "outcome": plan.outcome,
                "count": f"{ORDER_COUNT:.2f}",
                "economic_price": f"{ECONOMIC_BUY_PRICE:.4f}",
                "client_order_id": plan.client_order_id,
                "reservation_id": reservation_id,
            }
            try:
                response = client.create_order(plan.payload(), authorization)
            except SafetyError as exc:
                # SafetyError is raised by the local guard before Session.request is called,
                # so the reservation can be released without creating hidden exposure.
                release_before_send(root, reservation_id, str(exc))
                record.update({"result": "blocked_before_send", "error": str(exc)[:300]})
                _append_log(root, record)
                print(f"STOP {plan.ticker}: local safety boundary blocked the order before send")
                raise WriteCycleStop("local safety boundary stopped the write cycle") from exc
            except (AmbiguousMutationError, ApiError) as exc:
                mark_ambiguous(root, reservation_id, str(exc))
                record.update({"result": "ambiguous_review_required", "error": str(exc)[:300]})
                _append_log(root, record)
                print(f"STOP {plan.ticker}: submission outcome is ambiguous; ledger reservation retained for review")
                raise WriteCycleStop(
                    "submission outcome is ambiguous; continuous mode stopped for human review"
                ) from exc
            mark_accepted(root, reservation_id, response)
            record.update(
                {
                    "result": "accepted",
                    "order_id": response.get("order_id"),
                    "fill_count": response.get("fill_count"),
                    "remaining_count": response.get("remaining_count"),
                    "ts_ms": response.get("ts_ms"),
                }
            )
            _append_log(root, record)
            accepted += 1
            print(
                f"ACCEPTED {plan.ticker}: 10 contracts at 1c economic price "
                f"(order {str(response.get('order_id', ''))[:12]}…)"
            )
    return accepted


def run_write(
    root: Path,
    settings: RuntimeSettings,
    *,
    mode: str,
    authorization: WriteAuthorization,
    continuous: bool,
) -> int:
    try:
        with InstanceLock(root):
            total_accepted = 0
            while True:
                total_accepted += _run_write_cycle(root, settings, mode=mode, authorization=authorization)
                ledger_state = status(root)
                print(
                    "Session budget: "
                    f"accepted={ledger_state['accepted_contracts']:.0f}, "
                    f"reserved={ledger_state['reserved_contracts']:.0f}, "
                    f"remaining={ledger_state['remaining_contracts']:.0f} contracts"
                )
                if not continuous or ledger_state["remaining_contracts"] < ORDER_COUNT:
                    break
                if kill_switch_is_on(root):
                    revoke_write(authorization)
                    print("Kill switch detected; continuous mode stopped and write authorization revoked.")
                    break
                try:
                    time.sleep(settings.scan_interval_seconds)
                except KeyboardInterrupt:
                    revoke_write(authorization)
                    print("Continuous mode stopped by user; write authorization revoked.")
                    break
            return total_accepted
    except ApiError as exc:
        revoke_write(authorization)
        raise WriteCycleStop("API failure stopped the write cycle and revoked write authorization") from exc
    except SafetyError:
        revoke_write(authorization)
        raise
