# Architecture and Trust Boundaries

## Design goal

The public edition is intentionally small: make one narrow order idea easy to inspect, difficult to enable accidentally, and incapable of mutating unrelated account resources.

## Execution flow

```text
CLI command
  ↓
root-only .env parser
  ↓
read-only scan OR write authorization gates
  ↓
authenticated account preflight
  ↓
market discovery and transparent direction policy
  ↓
final order-book check
  ↓
persistent 10-contract reservation
  ↓
final in-process mutation guard
  ↓
Kalshi V2 single-order endpoint
  ↓
acceptance validation and local evidence
```

## Components

### `run_bot.py`

The only supported launcher. It exposes setup, verification, status, read-only commands, deliberately gated demo/live commands, kill-switch control, session reset, and stale-lock removal.

### `kalshi_public/env.py`

A non-executing `.env` reader. It ignores ambient environment variables and accepts only a fixed key allowlist. Numeric convenience settings are bounded; live flags are validated exactly rather than coerced.

### `kalshi_public/constants.py`

The build identity and immutable safety profile: exact size, price, session/process limits, market allowlist, official endpoints, route, and typed acknowledgements.

### `kalshi_public/auth.py`

Validates the key ID and external RSA private-key file, then creates Kalshi RSA-PSS/SHA-256 signatures over timestamp + HTTP method + full API path without query parameters.

### `kalshi_public/api.py`

A minimal Requests client. It contains bounded read methods for markets, order books, balance, positions, and resting orders, plus exactly one write method for V2 single-order creation. A still-present cursor after the fixed page limit is a hard failure rather than silent truncation.

### `kalshi_public/strategy.py`

Parses current and legacy price fields, selects the soonest eligible open market per allowlisted series, applies `cheapest`/`yes`/`no`, constructs exact plans, and verifies that a post-only 1¢ order would not cross the final book.

### `kalshi_public/safety.py`

The primary authorization boundary. It validates all independent live gates, verification freshness, credentials, endpoint, route, payload, process count, and kill-switch state. It creates a short-lived in-memory authorization nonce that cannot be supplied through `.env`, then revalidates the source tree again immediately before the HTTP send.

### `kalshi_public/ledger.py`

An atomic persistent risk budget. It reserves before send, records acceptance, quarantines ambiguity, releases only provably unsent reservations, blocks duplicate active markets, rejects symlinked state paths, and caps the session at 80 contracts.

### `kalshi_public/instance_lock.py`

An exclusive single-writer file lock with no-follow and parent-directory checks. Uncertain locks remain in place for deliberate operator review.

### `kalshi_public/verify.py`

Generates and validates the immutable-file manifest, scans for secrets and unsafe code, checks origins and defaults, runs tests and dependency consistency, and optionally requires Ruff and `pip-audit` in strict mode.

## Trust zones

### Immutable release zone

Source, tests, documentation, workflows, exact dependency declarations, and templates are covered by `MANIFEST.sha256`. A source change requires a new manifest and verification.

### Mutable local zone

`.env`, the kill switch, attestation, generated verification report, logs, and runtime ledger/lock are mutable by design. They are excluded from the manifest and validated at runtime.

### External credential zone

The RSA private key must live outside the repository. The repository contains only its absolute path. The operating system is responsible for protecting the file beyond the bot's permission checks.

### Remote service zone

Only the pinned official Kalshi demo or production REST base is accepted. API responses are untrusted input and are shape-, size-, and value-checked before use.

## Why NO is an ask

Kalshi's V2 event order endpoint uses a single YES book with `bid` and `ask`. A YES bid at 1¢ buys YES for 1¢. A YES ask at 99¢ sells YES for 99¢ and is economically equivalent to buying NO for 1¢. The code records both the YES-book price and the economic buy price to make that transformation auditable.

## Failure philosophy

- Missing data: skip or block.
- Uncertain credentials: block.
- Uncertain account preflight: block.
- Uncertain source integrity at authorization or final send: block and revoke write authorization.
- Incomplete account pagination: block the write cycle.
- Uncertain order result after a possible send: reserve, log, stop, and require human review.
- Uncertain stale lock: leave it in place until trading is disabled and the operator acknowledges removal.

## Deliberately excluded features

The public edition does not include private WebSocket feeds, third-party data feeds, adaptive sizing, dynamic prices, arbitrary market configuration, batch orders, automated cancellation, amend/decrease flows, transfers, withdrawals, key management, performance claims, or self-updating code. These omissions reduce attack surface and make the behavior easier to teach and review.

Copyright © 2026 Gateway Information Group LLC. Licensed under the MIT License.
