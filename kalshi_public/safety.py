"""Fail-closed authorization boundary for every order mutation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from secrets import token_urlsafe
from typing import Any
from urllib.parse import urlparse

from .auth import credential_status
from .constants import (
    ALLOWED_SERIES,
    ATTESTATION_FILENAME,
    BUILD_ID,
    CONTINUOUS_ACK,
    CREATE_ORDER_PATH,
    DEMO_REST_URL,
    DEMO_RISK_ACK,
    DIRECTION_POLICIES,
    ECONOMIC_BUY_PRICE,
    KILL_SWITCH_FILENAME,
    KILL_SWITCH_OFF_ACK,
    MANIFEST_FILENAME,
    MAX_CREATE_ORDERS_PER_PROCESS,
    ORDER_COUNT,
    PRODUCTION_REST_URL,
    PRODUCTION_RISK_ACK,
    SESSION_RESET_ACK,
    UNLOCK_ACK,
)
from .env import RuntimeSettings


class SafetyError(RuntimeError):
    """Raised when a public-edition safety boundary blocks an action."""


@dataclass(frozen=True)
class WriteAuthorization:
    mode: str
    endpoint: str
    continuous: bool
    nonce: str
    issued_monotonic: float


_ACTIVE_AUTHORIZATIONS: dict[str, int] = {}
_AUTHORIZATION_MAX_AGE_SECONDS = 8 * 60 * 60
_TICKER_RE = re.compile(r"^[A-Z0-9-]{1,128}$")


def kill_switch_path(root: Path) -> Path:
    return root / KILL_SWITCH_FILENAME


def kill_switch_is_on(root: Path) -> bool:
    """Treat a regular file or any symlink at the switch path as engaged."""
    path = kill_switch_path(root)
    return path.exists() or path.is_symlink()


def manifest_digest(root: Path) -> str:
    path = root / MANIFEST_FILENAME
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verification_attestation_failures(
    root: Path,
    *,
    max_age_hours: int = 24,
    require_ci: bool = False,
) -> list[str]:
    path = root / ATTESTATION_FILENAME
    if not path.is_file():
        return ["verification attestation is missing; run: python run_bot.py verify"]
    if path.is_symlink():
        return ["verification attestation must not be a symlink"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["verification attestation is unreadable; rerun verification"]
    failures: list[str] = []
    if data.get("schema_version") != 1:
        failures.append("verification attestation schema is not recognized")
    if data.get("build_id") != BUILD_ID:
        failures.append("verification attestation belongs to a different build")
    if data.get("result") != "PASS":
        failures.append("latest verification result is not PASS")
    if require_ci and data.get("ci") is not True:
        failures.append("production requires a current strict verification; run: python run_bot.py verify --ci")
    digest = manifest_digest(root)
    if not digest or data.get("manifest_digest") != digest:
        failures.append("release manifest changed after verification")
    else:
        # Re-hash the actual release tree at the authorization boundary. Checking
        # only the manifest file's digest would not detect an edited source file.
        from .verify import _check_manifest  # Local import avoids a module cycle.

        manifest_check = _check_manifest(root)
        if manifest_check.status != "PASS":
            failures.append("release files no longer match the verified manifest: " + manifest_check.detail)
    try:
        stamp = datetime.fromisoformat(str(data.get("verified_utc", "")).replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)
        if age.total_seconds() < -300:
            failures.append("verification timestamp is unexpectedly in the future")
        elif age.total_seconds() > max_age_hours * 3600:
            failures.append(f"verification is older than {max_age_hours} hours")
    except (TypeError, ValueError):
        failures.append("verification timestamp is invalid")
    return failures


def _exact(values: Mapping[str, str], key: str, expected: str, failures: list[str]) -> None:
    actual = str(values.get(key, "")).strip()
    if actual != expected:
        failures.append(f"{key} must be exactly {expected!r}")


def authorization_failures(
    mode: str,
    settings: RuntimeSettings,
    root: Path,
    *,
    continuous: bool = False,
) -> list[str]:
    mode = str(mode).strip().lower()
    values = settings.values
    failures: list[str] = []
    if mode not in {"demo-trade", "live"}:
        return ["write authorization is available only for demo-trade or live"]
    if not settings.source_exists:
        failures.append(".env is missing; run: python run_bot.py setup")
    if settings.unknown_keys:
        failures.append(".env contains unsupported keys: " + ", ".join(settings.unknown_keys))
    if kill_switch_is_on(root):
        failures.append("TRADING_DISABLED kill switch is on")
    if os.name != "nt" and (root / ".env").exists():
        mode_bits = stat.S_IMODE((root / ".env").stat().st_mode)
        if mode_bits & 0o077:
            failures.append(f".env permissions are too broad ({oct(mode_bits)}); use chmod 600 .env")

    _exact(values, "PUBLIC_RUN_MODE", mode, failures)
    for key, expected in {
        "PUBLIC_ORDER_WRITES_ENABLED": "1",
        "LIVE_TRADING": "1",
        "DRY_RUN": "0",
        "KALSHI_DRY_RUN": "0",
        "PAPER_MODE": "0",
        "PAPER_TRADE": "0",
        "SIMULATION_MODE": "0",
    }.items():
        _exact(values, key, expected, failures)

    if mode == "live":
        _exact(values, "ALLOW_PRODUCTION_TRADING", "1", failures)
        _exact(values, "PUBLIC_RISK_ACK", PRODUCTION_RISK_ACK, failures)
    else:
        _exact(values, "ALLOW_PRODUCTION_TRADING", "0", failures)
        _exact(values, "PUBLIC_RISK_ACK", DEMO_RISK_ACK, failures)
    if continuous:
        _exact(values, "PUBLIC_CONTINUOUS_ACK", CONTINUOUS_ACK, failures)
    elif str(values.get("PUBLIC_CONTINUOUS_ACK", "")).strip() not in {"", CONTINUOUS_ACK}:
        failures.append("PUBLIC_CONTINUOUS_ACK is not recognized")

    raw_policy = str(values.get("PUBLIC_DIRECTION_POLICY", "")).strip().lower()
    if raw_policy not in DIRECTION_POLICIES:
        failures.append("PUBLIC_DIRECTION_POLICY must be cheapest, yes, or no")
    credentials = credential_status(values, root)
    failures.extend(credentials.failures)
    failures.extend(verification_attestation_failures(root, require_ci=mode == "live"))
    if mode == "live":
        from .verify import strict_verification_failures

        failures.extend(strict_verification_failures(root))
    return failures


def authorize_write(
    mode: str,
    settings: RuntimeSettings,
    root: Path,
    *,
    continuous: bool = False,
) -> WriteAuthorization:
    failures = authorization_failures(mode, settings, root, continuous=continuous)
    if failures:
        raise SafetyError("Write authorization blocked:\n- " + "\n- ".join(failures))
    endpoint = PRODUCTION_REST_URL if mode == "live" else DEMO_REST_URL
    authorization = WriteAuthorization(
        mode=mode,
        endpoint=endpoint,
        continuous=continuous,
        nonce=token_urlsafe(32),
        issued_monotonic=time.monotonic(),
    )
    _ACTIVE_AUTHORIZATIONS[authorization.nonce] = 0
    return authorization


def revoke_write(authorization: WriteAuthorization | None) -> None:
    if authorization is not None:
        _ACTIVE_AUTHORIZATIONS.pop(authorization.nonce, None)


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("-1")


def ticker_is_canonical(ticker: object) -> bool:
    """Return whether an API ticker is a non-empty canonical ticker string."""
    if not isinstance(ticker, str):
        return False
    return bool(_TICKER_RE.fullmatch(ticker.strip().upper()))


def ticker_is_allowed(ticker: str) -> bool:
    normalized = str(ticker or "").strip().upper()
    return ticker_is_canonical(ticker) and any(
        normalized == series or normalized.startswith(series + "-") for series in ALLOWED_SERIES
    )


def validate_order_payload(payload: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    allowed_keys = {
        "ticker",
        "client_order_id",
        "side",
        "count",
        "price",
        "time_in_force",
        "self_trade_prevention_type",
        "post_only",
        "cancel_order_on_pause",
        "reduce_only",
        "subaccount",
        "exchange_index",
    }
    extras = sorted(set(payload) - allowed_keys)
    if extras:
        failures.append("unexpected payload fields: " + ", ".join(extras))
    ticker = str(payload.get("ticker", "")).strip().upper()
    if not ticker_is_allowed(ticker):
        failures.append("ticker is outside the immutable crypto-15-minute allowlist")
    if _decimal(payload.get("count")) != ORDER_COUNT:
        failures.append(f"count must be exactly {ORDER_COUNT:.2f}")
    side = str(payload.get("side", "")).strip().lower()
    price = _decimal(payload.get("price"))
    if side == "bid":
        economic_price = price
    elif side == "ask":
        economic_price = Decimal("1") - price
    else:
        economic_price = Decimal("-1")
        failures.append("side must be bid or ask")
    if economic_price != ECONOMIC_BUY_PRICE:
        failures.append(f"economic buy price must be exactly {ECONOMIC_BUY_PRICE:.4f}")
    try:
        uuid.UUID(str(payload.get("client_order_id", "")))
    except (ValueError, AttributeError):
        failures.append("client_order_id must be a valid UUID")
    expected = {
        "time_in_force": "good_till_canceled",
        "self_trade_prevention_type": "taker_at_cross",
        "post_only": True,
        "cancel_order_on_pause": True,
        "reduce_only": False,
        "subaccount": 0,
        "exchange_index": 0,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            failures.append(f"{key} must be exactly {value!r}")
    return failures


def validate_endpoint(endpoint: str, expected: str) -> None:
    parsed = urlparse(str(endpoint))
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SafetyError("REST endpoint is not a clean HTTPS base URL")
    if endpoint.rstrip("/") != expected:
        raise SafetyError(f"REST endpoint must be pinned to {expected}")


def require_create_order_permission(
    authorization: WriteAuthorization | None,
    *,
    endpoint: str,
    method: str,
    path: str,
    payload: Mapping[str, Any],
    root: Path,
) -> None:
    """Final guard called immediately before the HTTP request is sent."""
    if authorization is None or authorization.nonce not in _ACTIVE_AUTHORIZATIONS:
        raise SafetyError("no in-process write authorization; use run_bot.py demo-trade or live")
    if time.monotonic() - authorization.issued_monotonic > _AUTHORIZATION_MAX_AGE_SECONDS:
        revoke_write(authorization)
        raise SafetyError("write authorization expired; restart through the public launcher")
    if kill_switch_is_on(root):
        raise SafetyError("TRADING_DISABLED kill switch blocks order creation")
    verification_failures = verification_attestation_failures(
        root,
        require_ci=authorization.mode == "live",
    )
    if verification_failures:
        revoke_write(authorization)
        raise SafetyError(
            "release verification changed after authorization; order creation blocked: "
            + "; ".join(verification_failures)
        )
    if authorization.mode == "live":
        from .verify import strict_verification_failures

        strict_failures = strict_verification_failures(root)
        if strict_failures:
            revoke_write(authorization)
            raise SafetyError(
                "in-process strict verification is no longer current; order creation blocked: "
                + "; ".join(strict_failures)
            )
    expected_endpoint = PRODUCTION_REST_URL if authorization.mode == "live" else DEMO_REST_URL
    validate_endpoint(endpoint, expected_endpoint)
    if method.upper() != "POST" or path != CREATE_ORDER_PATH:
        raise SafetyError(f"mutation route is not allowed: {method.upper()} {path}")
    failures = validate_order_payload(payload)
    if failures:
        raise SafetyError("order payload blocked: " + "; ".join(failures))
    count = _ACTIVE_AUTHORIZATIONS[authorization.nonce]
    if count >= MAX_CREATE_ORDERS_PER_PROCESS:
        raise SafetyError(f"process order limit reached ({MAX_CREATE_ORDERS_PER_PROCESS})")
    _ACTIVE_AUTHORIZATIONS[authorization.nonce] = count + 1


def create_kill_switch(root: Path) -> Path:
    path = kill_switch_path(root)
    if path.is_symlink():
        raise SafetyError("TRADING_DISABLED must not be a symlink")
    if path.exists() and not path.is_file():
        raise SafetyError("TRADING_DISABLED must be a regular file")
    path.write_text("Trading disabled by local safety switch.\n", encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)
    return path


def remove_kill_switch(root: Path, ack: str) -> None:
    if ack != KILL_SWITCH_OFF_ACK:
        raise SafetyError(f"exact acknowledgement required: {KILL_SWITCH_OFF_ACK}")
    path = kill_switch_path(root)
    if path.exists():
        path.unlink()


def require_session_reset(root: Path, ack: str) -> None:
    if not kill_switch_is_on(root):
        raise SafetyError("session reset requires TRADING_DISABLED to remain on")
    if ack != SESSION_RESET_ACK:
        raise SafetyError(f"exact acknowledgement required: {SESSION_RESET_ACK}")


def require_unlock(root: Path, ack: str) -> None:
    if not kill_switch_is_on(root):
        raise SafetyError("unlock requires TRADING_DISABLED to remain on")
    if ack != UNLOCK_ACK:
        raise SafetyError(f"exact acknowledgement required: {UNLOCK_ACK}")
