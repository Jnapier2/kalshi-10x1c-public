# Release Notes — v1.0.0

## Public edition

This is the first public edition of the Kalshi 10×1¢ educational order planner.

### Core profile

- Exactly 10 contracts per permitted order.
- Exactly 1¢ economic buy price per contract.
- 10¢ maximum principal per fully filled order before applicable fees.
- 80-contract persistent session cap.
- Eight create-order maximum per process.
- Eight allowlisted crypto 15-minute series.

### Safety architecture

- Dry-run and blank credentials by default.
- Tracked `TRADING_DISABLED` kill switch.
- Root-only, non-executing `.env` parser.
- External RSA private-key validation.
- Official Kalshi endpoint pinning.
- One allowed V2 single-order mutation route.
- In-process write authorization nonce.
- Final-boundary kill-switch, source-attestation, endpoint, route, payload, count, price, and process checks.
- Existing resting-order and non-zero-position preflight with fail-closed pagination completion.
- Post-only order and final book-crossing check.
- Atomic persistent session ledger.
- Ambiguous submission quarantine.
- Single-writer process lock and symlink-resistant runtime state/log paths.
- Release manifest and short-lived verification attestation.

### Quality evidence

- 114 unit and security regression tests.
- Ruff static analysis.
- Python compilation checks.
- Secret and private-key scanning.
- Dangerous-code and runtime-origin scanning.
- Exact dependency locks and `pip check`.
- Strict online `pip-audit` requirement for production authorization.

### Dependency correction

The prerelease `requests==2.32.5` pin was replaced after a 2026 vulnerability record was identified. The release uses `requests==2.34.2` and refreshed compatible exact pins.

### Documentation

Includes security-first setup, live activation, emergency response, architecture, audit evidence, risk guidance, third-party notices, and concise support documentation.

### Known limitations

- No automatic order cancellation.
- No automatic ambiguity reconciliation.
- No profitability model or performance claim.
- No guarantee of fills or API compatibility.
- Strict vulnerability audit requires external advisory-service connectivity.
- Public-use license requires explicit owner activation.

Copyright © 2026 Gateway Information Group LLC. Licensed under the MIT License.
