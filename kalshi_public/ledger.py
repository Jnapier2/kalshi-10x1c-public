"""Persistent, fail-closed 80-contract session ledger."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .constants import (
    ALLOWED_SERIES,
    ECONOMIC_BUY_PRICE,
    LEDGER_RELATIVE_PATH,
    ORDER_COUNT,
    SESSION_CONTRACT_CAP,
    YES_ASK_PRICE_FOR_NO_BUY,
    YES_BID_PRICE,
)
from .models import OrderPlan
from .safety import SafetyError, require_session_reset, ticker_is_allowed

_LOCK = threading.RLock()
_ACTIVE_STATUSES = {"reserved", "ambiguous", "accepted"}
_ALL_STATUSES = _ACTIVE_STATUSES | {"released_before_send"}
_MAX_LEDGER_ENTRIES = 1_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def ledger_path(root: Path) -> Path:
    return root / LEDGER_RELATIVE_PATH


def _guard_state_path(path: Path, *, create_parent: bool) -> None:
    parent = path.parent
    if parent.is_symlink():
        raise SafetyError("runtime state directory must not be a symlink; trading blocked")
    if create_parent:
        parent.mkdir(parents=True, exist_ok=True)
    if parent.exists() and not parent.is_dir():
        raise SafetyError("runtime state path is not a directory; trading blocked")
    if parent.is_symlink():
        raise SafetyError("runtime state directory must not be a symlink; trading blocked")
    if path.is_symlink():
        raise SafetyError("session ledger must not be a symlink; trading blocked")


def _empty() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "cap_contracts": f"{SESSION_CONTRACT_CAP:.2f}",
        "created_utc": _now(),
        "updated_utc": _now(),
        "entries": [],
    }


def _dec(raw: Any) -> Decimal:
    try:
        return Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _totals(data: dict[str, Any]) -> tuple[Decimal, Decimal, Decimal]:
    accepted = Decimal("0")
    reserved = Decimal("0")
    for entry in data.get("entries", []):
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status", ""))
        count = _dec(entry.get("count"))
        if status == "accepted":
            accepted += count
        elif status in {"reserved", "ambiguous"}:
            reserved += count
    return accepted, reserved, accepted + reserved


def _valid_uuid(raw: Any) -> bool:
    try:
        uuid.UUID(str(raw))
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def _validate_entries(entries: list[Any]) -> None:
    if len(entries) > _MAX_LEDGER_ENTRIES:
        raise SafetyError("session ledger has too many entries; trading blocked")
    reservation_ids: set[str] = set()
    active_tickers: set[str] = set()
    for index, entry in enumerate(entries):
        label = f"session ledger entry {index + 1}"
        if not isinstance(entry, dict):
            raise SafetyError(f"{label} is not an object; trading blocked")
        reservation_id = str(entry.get("reservation_id", ""))
        if not _valid_uuid(reservation_id) or reservation_id in reservation_ids:
            raise SafetyError(f"{label} has an invalid or duplicate reservation ID; trading blocked")
        reservation_ids.add(reservation_id)
        status = str(entry.get("status", ""))
        if status not in _ALL_STATUSES:
            raise SafetyError(f"{label} has an unsupported status; trading blocked")
        if str(entry.get("mode", "")) not in {"demo-trade", "live"}:
            raise SafetyError(f"{label} has an unsupported mode; trading blocked")
        series = str(entry.get("series", "")).strip().upper()
        ticker = str(entry.get("ticker", "")).strip().upper()
        if series not in ALLOWED_SERIES or not ticker_is_allowed(ticker):
            raise SafetyError(f"{label} is outside the immutable series/ticker allowlist; trading blocked")
        if not (ticker == series or ticker.startswith(series + "-")):
            raise SafetyError(f"{label} has a series/ticker mismatch; trading blocked")
        outcome = str(entry.get("outcome", "")).strip().lower()
        side = str(entry.get("side", "")).strip().lower()
        if (outcome, side) not in {("yes", "bid"), ("no", "ask")}:
            raise SafetyError(f"{label} has an invalid outcome/side pairing; trading blocked")
        if _dec(entry.get("count")) != ORDER_COUNT:
            raise SafetyError(f"{label} does not contain exactly 10 contracts; trading blocked")
        if _dec(entry.get("economic_price")) != ECONOMIC_BUY_PRICE:
            raise SafetyError(f"{label} does not contain an exact 1c economic price; trading blocked")
        expected_book_price = YES_BID_PRICE if side == "bid" else YES_ASK_PRICE_FOR_NO_BUY
        if _dec(entry.get("yes_book_price")) != expected_book_price:
            raise SafetyError(f"{label} has an invalid YES-book price; trading blocked")
        if not _valid_uuid(entry.get("client_order_id")):
            raise SafetyError(f"{label} has an invalid client order ID; trading blocked")
        if status in _ACTIVE_STATUSES:
            if ticker in active_tickers:
                raise SafetyError(f"{label} duplicates an active market ticker; trading blocked")
            active_tickers.add(ticker)


def load_ledger(root: Path) -> dict[str, Any]:
    path = ledger_path(root)
    _guard_state_path(path, create_parent=False)
    if not path.exists():
        return _empty()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SafetyError(f"session ledger is unreadable; trading blocked ({type(exc).__name__})") from exc
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise SafetyError("session ledger schema is invalid; trading blocked")
    if data.get("schema_version") != 1:
        raise SafetyError("session ledger schema version is invalid; trading blocked")
    if _dec(data.get("cap_contracts")) != SESSION_CONTRACT_CAP:
        raise SafetyError("session ledger cap does not match the immutable 80-contract limit")
    _validate_entries(data["entries"])
    _, _, total = _totals(data)
    if total > SESSION_CONTRACT_CAP:
        raise SafetyError("session ledger exceeds the immutable contract limit")
    return data


def _save(root: Path, data: dict[str, Any]) -> None:
    path = ledger_path(root)
    _guard_state_path(path, create_parent=True)
    data["cap_contracts"] = f"{SESSION_CONTRACT_CAP:.2f}"
    data["updated_utc"] = _now()
    payload = json.dumps(data, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=".ledger-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != "nt":
            os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def status(root: Path) -> dict[str, Any]:
    with _LOCK:
        data = load_ledger(root)
        accepted, reserved, total = _totals(data)
        return {
            "cap_contracts": SESSION_CONTRACT_CAP,
            "accepted_contracts": accepted,
            "reserved_contracts": reserved,
            "total_committed_contracts": total,
            "remaining_contracts": SESSION_CONTRACT_CAP - total,
            "entry_count": len(data.get("entries", [])),
        }


def contains_ticker(root: Path, ticker: str) -> bool:
    with _LOCK:
        data = load_ledger(root)
        normalized = ticker.strip().upper()
        return any(
            isinstance(entry, dict)
            and str(entry.get("ticker", "")).strip().upper() == normalized
            and str(entry.get("status", "")) in _ACTIVE_STATUSES
            for entry in data.get("entries", [])
        )


def reserve(root: Path, plan: OrderPlan, mode: str) -> str:
    with _LOCK:
        data = load_ledger(root)
        if contains_ticker(root, plan.ticker):
            raise SafetyError(f"session ledger already owns or reserved {plan.ticker}")
        _, _, total = _totals(data)
        if total + ORDER_COUNT > SESSION_CONTRACT_CAP:
            raise SafetyError("80-contract persistent session budget would be exceeded")
        reservation_id = str(uuid.uuid4())
        data["entries"].append(
            {
                "reservation_id": reservation_id,
                "created_utc": _now(),
                "mode": mode,
                "status": "reserved",
                "series": plan.series,
                "ticker": plan.ticker,
                "outcome": plan.outcome,
                "side": plan.side,
                "count": f"{ORDER_COUNT:.2f}",
                "economic_price": f"{plan.economic_buy_price:.4f}",
                "yes_book_price": f"{plan.price:.4f}",
                "client_order_id": plan.client_order_id,
            }
        )
        _save(root, data)
        return reservation_id


def _find(data: dict[str, Any], reservation_id: str) -> dict[str, Any]:
    for entry in data.get("entries", []):
        if isinstance(entry, dict) and entry.get("reservation_id") == reservation_id:
            return entry
    raise SafetyError("session ledger reservation was not found")


def mark_accepted(root: Path, reservation_id: str, response: dict[str, Any]) -> None:
    with _LOCK:
        data = load_ledger(root)
        entry = _find(data, reservation_id)
        if entry.get("status") != "reserved":
            raise SafetyError("reservation is not in a committable state")
        entry.update(
            {
                "status": "accepted",
                "accepted_utc": _now(),
                "order_id": str(response.get("order_id", "")),
                "fill_count": str(response.get("fill_count", "")),
                "remaining_count": str(response.get("remaining_count", "")),
                "ts_ms": response.get("ts_ms"),
            }
        )
        _save(root, data)


def mark_ambiguous(root: Path, reservation_id: str, reason: str) -> None:
    with _LOCK:
        data = load_ledger(root)
        entry = _find(data, reservation_id)
        if entry.get("status") == "reserved":
            entry.update({"status": "ambiguous", "ambiguous_utc": _now(), "reason": reason[:300]})
            _save(root, data)


def release_before_send(root: Path, reservation_id: str, reason: str) -> None:
    """Release only when the caller can prove no mutation request was sent."""
    with _LOCK:
        data = load_ledger(root)
        entry = _find(data, reservation_id)
        if entry.get("status") != "reserved":
            raise SafetyError("only an unsent reservation can be released")
        entry.update({"status": "released_before_send", "released_utc": _now(), "reason": reason[:300]})
        _save(root, data)


def reset(root: Path, ack: str) -> Path:
    require_session_reset(root, ack)
    with _LOCK:
        path = ledger_path(root)
        _guard_state_path(path, create_parent=True)
        if path.exists():
            archive = path.with_name(
                f"session_ledger.reset-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
            )
            os.replace(path, archive)
            if os.name != "nt":
                archive.chmod(0o600)
        else:
            archive = path
        _save(root, _empty())
        return archive
