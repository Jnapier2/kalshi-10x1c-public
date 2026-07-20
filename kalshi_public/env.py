"""Small, non-executing .env loader for the public edition."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .constants import (
    DEFAULT_DIRECTION_POLICY,
    DEFAULT_HTTP_TIMEOUT_SECONDS,
    DEFAULT_MIN_SECONDS_TO_CLOSE,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DIRECTION_POLICIES,
)

_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_FORBIDDEN_VALUE_FRAGMENTS = ("`", "$(", "${")
_MAX_ENV_BYTES = 64 * 1024

ALLOWED_ENV_KEYS = frozenset(
    {
        "PUBLIC_RUN_MODE",
        "PUBLIC_ORDER_WRITES_ENABLED",
        "LIVE_TRADING",
        "DRY_RUN",
        "KALSHI_DRY_RUN",
        "PAPER_MODE",
        "PAPER_TRADE",
        "SIMULATION_MODE",
        "ALLOW_PRODUCTION_TRADING",
        "PUBLIC_RISK_ACK",
        "PUBLIC_CONTINUOUS_ACK",
        "KALSHI_API_KEY_ID",
        "KALSHI_PRIVATE_KEY_PATH",
        "PUBLIC_DIRECTION_POLICY",
        "PUBLIC_SCAN_INTERVAL_SECONDS",
        "PUBLIC_MIN_SECONDS_TO_CLOSE",
        "PUBLIC_HTTP_TIMEOUT_SECONDS",
        "PUBLIC_LOG_LEVEL",
    }
)

SAFE_DEFAULTS: dict[str, str] = {
    "PUBLIC_RUN_MODE": "dry-run",
    "PUBLIC_ORDER_WRITES_ENABLED": "0",
    "LIVE_TRADING": "0",
    "DRY_RUN": "1",
    "KALSHI_DRY_RUN": "1",
    "PAPER_MODE": "1",
    "PAPER_TRADE": "1",
    "SIMULATION_MODE": "1",
    "ALLOW_PRODUCTION_TRADING": "0",
    "PUBLIC_RISK_ACK": "",
    "PUBLIC_CONTINUOUS_ACK": "",
    "KALSHI_API_KEY_ID": "",
    "KALSHI_PRIVATE_KEY_PATH": "",
    "PUBLIC_DIRECTION_POLICY": DEFAULT_DIRECTION_POLICY,
    "PUBLIC_SCAN_INTERVAL_SECONDS": str(DEFAULT_SCAN_INTERVAL_SECONDS),
    "PUBLIC_MIN_SECONDS_TO_CLOSE": str(DEFAULT_MIN_SECONDS_TO_CLOSE),
    "PUBLIC_HTTP_TIMEOUT_SECONDS": str(DEFAULT_HTTP_TIMEOUT_SECONDS),
    "PUBLIC_LOG_LEVEL": "INFO",
}


class EnvError(ValueError):
    """Raised for malformed or unsafe .env content."""


@dataclass(frozen=True)
class RuntimeSettings:
    values: Mapping[str, str]
    source_exists: bool
    unknown_keys: tuple[str, ...]

    @property
    def direction_policy(self) -> str:
        value = self.values.get("PUBLIC_DIRECTION_POLICY", DEFAULT_DIRECTION_POLICY).strip().lower()
        return value if value in DIRECTION_POLICIES else DEFAULT_DIRECTION_POLICY

    @property
    def scan_interval_seconds(self) -> int:
        return _bounded_int(self.values.get("PUBLIC_SCAN_INTERVAL_SECONDS"), DEFAULT_SCAN_INTERVAL_SECONDS, 5, 3600)

    @property
    def min_seconds_to_close(self) -> int:
        return _bounded_int(self.values.get("PUBLIC_MIN_SECONDS_TO_CLOSE"), DEFAULT_MIN_SECONDS_TO_CLOSE, 15, 3600)

    @property
    def http_timeout_seconds(self) -> float:
        return _bounded_float(self.values.get("PUBLIC_HTTP_TIMEOUT_SECONDS"), DEFAULT_HTTP_TIMEOUT_SECONDS, 1.0, 60.0)


def _bounded_int(raw: str | None, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(raw))
    except (TypeError, ValueError):
        return default
    return min(maximum, max(minimum, value))


def _bounded_float(raw: str | None, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(str(raw))
    except (TypeError, ValueError):
        return default
    return min(maximum, max(minimum, value))


def _decode_value(raw: str, *, line_number: int) -> str:
    value = raw.strip()
    if any(fragment in value for fragment in _FORBIDDEN_VALUE_FRAGMENTS):
        raise EnvError(f"line {line_number}: command or variable expansion syntax is not accepted")
    if not value:
        return ""
    if value[0] in {"'", '"'}:
        quote = value[0]
        if len(value) < 2 or value[-1] != quote:
            raise EnvError(f"line {line_number}: unterminated quoted value")
        value = value[1:-1]
    else:
        # Unquoted comments begin only after whitespace, preserving # in paths.
        match = re.search(r"\s+#", value)
        if match:
            value = value[: match.start()].rstrip()
    if "\x00" in value or "\r" in value or "\n" in value:
        raise EnvError(f"line {line_number}: control characters are not accepted")
    return value


def parse_env_text(text: str) -> tuple[dict[str, str], tuple[str, ...]]:
    parsed: dict[str, str] = {}
    unknown: list[str] = []
    for line_number, original in enumerate(text.splitlines(), start=1):
        line = original.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise EnvError(f"line {line_number}: expected KEY=VALUE")
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not _KEY_RE.fullmatch(key):
            raise EnvError(f"line {line_number}: invalid environment key {key!r}")
        if key in parsed:
            raise EnvError(f"line {line_number}: duplicate key {key}")
        value = _decode_value(raw_value, line_number=line_number)
        if key in ALLOWED_ENV_KEYS:
            parsed[key] = value
        else:
            unknown.append(key)
    return parsed, tuple(sorted(unknown))


def load_settings(root: Path) -> RuntimeSettings:
    """Load only ``root/.env``; ambient process variables are intentionally ignored."""
    env_path = root / ".env"
    values = dict(SAFE_DEFAULTS)
    if not env_path.exists():
        return RuntimeSettings(values=values, source_exists=False, unknown_keys=())
    if env_path.is_symlink():
        raise EnvError(".env must be a regular file, not a symlink")
    if not env_path.is_file():
        raise EnvError(".env is not a regular file")
    if env_path.stat().st_size > _MAX_ENV_BYTES:
        raise EnvError(".env exceeds the 64 KiB public-edition limit")
    parsed, unknown = parse_env_text(env_path.read_text(encoding="utf-8"))
    values.update(parsed)
    return RuntimeSettings(values=values, source_exists=True, unknown_keys=unknown)
