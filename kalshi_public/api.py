"""Minimal Kalshi REST client with isolated transport and one mutation route."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from .auth import Credentials
from .constants import (
    APPROVED_REST_URLS,
    CREATE_ORDER_PATH,
    MAX_ACCOUNT_PAGES,
    MAX_MARKET_PAGES_PER_SERIES,
    MAX_RESPONSE_BYTES,
    USER_AGENT,
)
from .safety import (
    SafetyError,
    WriteAuthorization,
    require_create_order_permission,
    ticker_is_allowed,
    ticker_is_canonical,
)


class ApiError(RuntimeError):
    """Base API/transport error with secret-safe messages."""


class AmbiguousMutationError(ApiError):
    """The client cannot prove whether a submitted mutation was accepted."""


class ApiHTTPError(ApiError):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"Kalshi API returned HTTP {status_code}: {message}")
        self.status_code = status_code


class KalshiClient:
    def __init__(
        self,
        endpoint: str,
        *,
        root: Path,
        timeout_seconds: float,
        credentials: Credentials | None = None,
        session: requests.Session | None = None,
    ) -> None:
        normalized = endpoint.rstrip("/")
        if normalized not in APPROVED_REST_URLS:
            raise SafetyError("REST endpoint is outside the immutable Kalshi allowlist")
        self.endpoint = normalized
        self.root = root
        self.timeout = (3.05, float(timeout_seconds))
        self.credentials = credentials
        self.session = session or requests.Session()
        self.session.trust_env = False
        self.session.headers.clear()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> KalshiClient:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def _auth_headers(self, method: str, full_url: str) -> dict[str, str]:
        if self.credentials is None:
            raise ApiError("authenticated request requires validated credentials")
        timestamp = str(int(time.time() * 1000))
        sign_path = urlparse(full_url).path
        signature = self.credentials.sign(timestamp, method, sign_path)
        return {
            "KALSHI-ACCESS-KEY": self.credentials.api_key_id,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "KALSHI-ACCESS-SIGNATURE": signature,
        }

    @staticmethod
    def _safe_error_text(response: requests.Response) -> str:
        try:
            data = response.json()
            if isinstance(data, dict):
                bits = [str(data.get(key, "")) for key in ("code", "message", "details")]
                text = " | ".join(bit for bit in bits if bit)
            else:
                text = "unexpected JSON response"
        except (ValueError, json.JSONDecodeError):
            text = str(getattr(response, "text", "") or "")
        text = " ".join(text.split())
        return text[:300] or "no error details"

    @staticmethod
    def _json(response: requests.Response) -> dict[str, Any]:
        content = response.content
        if len(content) > MAX_RESPONSE_BYTES:
            raise ApiError("Kalshi response exceeded the public-edition size limit")
        if not content:
            return {}
        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise ApiError("Kalshi returned a non-JSON response") from exc
        if not isinstance(data, dict):
            raise ApiError("Kalshi returned an unexpected JSON shape")
        return data

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        payload: Mapping[str, Any] | None = None,
        authenticated: bool = False,
        expected_statuses: tuple[int, ...] = (200,),
        authorization: WriteAuthorization | None = None,
    ) -> dict[str, Any]:
        method = method.upper()
        if not path.startswith("/") or ".." in path or "?" in path or "#" in path:
            raise SafetyError("API path is not canonical")
        full_url = self.endpoint + path
        parsed = urlparse(full_url)
        expected = urlparse(self.endpoint)
        if (
            parsed.scheme != "https"
            or parsed.netloc != expected.netloc
            or not parsed.path.startswith(expected.path + "/")
        ):
            raise SafetyError("request URL escaped the pinned Kalshi API base")
        headers: dict[str, str] = {}
        if authenticated:
            headers.update(self._auth_headers(method, full_url))
        if payload is not None:
            headers["Content-Type"] = "application/json"
        is_mutation = method in {"POST", "PUT", "PATCH", "DELETE"}
        if is_mutation:
            require_create_order_permission(
                authorization,
                endpoint=self.endpoint,
                method=method,
                path=path,
                payload=payload or {},
                root=self.root,
            )
        try:
            response = self.session.request(
                method,
                full_url,
                params=dict(params or {}),
                json=dict(payload) if payload is not None else None,
                headers=headers,
                timeout=self.timeout,
                allow_redirects=False,
                verify=True,
            )
        except requests.RequestException as exc:
            if is_mutation:
                raise AmbiguousMutationError(
                    f"order request transport became ambiguous ({type(exc).__name__})"
                ) from exc
            raise ApiError(f"Kalshi read request failed ({type(exc).__name__})") from exc
        if 300 <= response.status_code < 400:
            if is_mutation:
                raise AmbiguousMutationError("Kalshi mutation returned a blocked redirect response")
            raise ApiError("Kalshi returned a blocked redirect response")
        if response.status_code not in expected_statuses:
            message = self._safe_error_text(response)
            if is_mutation:
                # The request reached the remote endpoint; preserve the ledger reservation
                # because this client cannot prove that no order was accepted.
                raise AmbiguousMutationError(f"HTTP {response.status_code}: {message}")
            raise ApiHTTPError(response.status_code, message)
        return self._json(response)

    def list_markets(self, series_ticker: str) -> list[dict[str, Any]]:
        markets: list[dict[str, Any]] = []
        cursor = ""
        for _ in range(MAX_MARKET_PAGES_PER_SERIES):
            params: dict[str, Any] = {"series_ticker": series_ticker, "status": "open", "limit": 100}
            if cursor:
                params["cursor"] = cursor
            data = self._request("GET", "/markets", params=params)
            batch = data.get("markets", [])
            if not isinstance(batch, list):
                raise ApiError("markets response did not contain a list")
            markets.extend(row for row in batch if isinstance(row, dict))
            cursor = str(data.get("cursor") or "")
            if not cursor:
                return markets
        raise ApiError("market pagination exceeded the immutable page limit; fail closed")

    def get_orderbook(self, ticker: str) -> dict[str, Any]:
        safe_ticker = str(ticker).strip().upper()
        if not ticker_is_allowed(safe_ticker):
            raise SafetyError("market ticker is outside the canonical public-edition allowlist")
        return self._request("GET", f"/markets/{safe_ticker}/orderbook")

    def get_balance(self) -> dict[str, Any]:
        return self._request("GET", "/portfolio/balance", authenticated=True)

    @staticmethod
    def _validated_account_rows(batch: list[Any], *, label: str) -> list[dict[str, Any]]:
        """Reject any malformed account row before write preflight can consume it."""
        rows: list[dict[str, Any]] = []
        for index, row in enumerate(batch):
            if not isinstance(row, dict):
                raise ApiError(f"{label} response row {index} was not an object; write preflight blocked")
            raw_ticker = row["ticker"] if "ticker" in row else row.get("market_ticker")
            if not ticker_is_canonical(raw_ticker):
                raise ApiError(
                    f"{label} response row {index} omitted a canonical ticker; write preflight blocked"
                )
            rows.append(row)
        return rows

    def list_positions(self) -> list[dict[str, Any]]:
        """Return non-zero primary-subaccount market positions, with bounded pagination."""
        positions: list[dict[str, Any]] = []
        cursor = ""
        for _ in range(MAX_ACCOUNT_PAGES):
            params: dict[str, Any] = {"count_filter": "position", "limit": 1000, "subaccount": 0}
            if cursor:
                params["cursor"] = cursor
            data = self._request("GET", "/portfolio/positions", params=params, authenticated=True)
            batch = data.get("market_positions", [])
            if not isinstance(batch, list):
                raise ApiError("positions response did not contain a market_positions list")
            positions.extend(self._validated_account_rows(batch, label="positions"))
            cursor = str(data.get("cursor") or "")
            if not cursor:
                return positions
        raise ApiError("position pagination exceeded the immutable page limit; write preflight blocked")

    def list_resting_orders(self) -> list[dict[str, Any]]:
        orders: list[dict[str, Any]] = []
        cursor = ""
        for _ in range(MAX_ACCOUNT_PAGES):
            params: dict[str, Any] = {"status": "resting", "limit": 100}
            if cursor:
                params["cursor"] = cursor
            data = self._request("GET", "/portfolio/orders", params=params, authenticated=True)
            batch = data.get("orders", [])
            if not isinstance(batch, list):
                raise ApiError("orders response did not contain a list")
            orders.extend(self._validated_account_rows(batch, label="orders"))
            cursor = str(data.get("cursor") or "")
            if not cursor:
                return orders
        raise ApiError("resting-order pagination exceeded the immutable page limit; write preflight blocked")

    def create_order(self, payload: Mapping[str, Any], authorization: WriteAuthorization) -> dict[str, Any]:
        data = self._request(
            "POST",
            CREATE_ORDER_PATH,
            payload=payload,
            authenticated=True,
            expected_statuses=(201,),
            authorization=authorization,
        )
        required = ("order_id", "client_order_id", "fill_count", "remaining_count", "ts_ms")
        if any(key not in data for key in required):
            raise AmbiguousMutationError("order response omitted required acceptance fields")
        if str(data.get("client_order_id")) != str(payload.get("client_order_id")):
            raise AmbiguousMutationError("order response client_order_id did not match the submitted order")
        if not str(data.get("order_id", "")).strip():
            raise AmbiguousMutationError("order response contained a blank order_id")
        try:
            fill_count = Decimal(str(data["fill_count"]))
            remaining_count = Decimal(str(data["remaining_count"]))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise AmbiguousMutationError("order response contained invalid fill counts") from exc
        if fill_count < 0 or remaining_count < 0 or fill_count + remaining_count != Decimal("10.00"):
            raise AmbiguousMutationError("order response fill counts did not reconcile to exactly 10 contracts")
        try:
            if int(data["ts_ms"]) <= 0:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise AmbiguousMutationError("order response contained an invalid acceptance timestamp") from exc
        return data
