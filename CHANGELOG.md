# Changelog

All notable public-edition changes are documented here.

## 1.0.1 — 2026-08-11

### Security

- Updated `cryptography` from 49.0.0 to 50.0.0 to resolve the PKCS#7 EnvelopedData oracle advisory reported against the earlier lock.
- Refreshed dependency documentation, release identity, and the immutable-file manifest.
- Preserved all dry-run defaults, activation gates, order limits, and strategy behavior.

## 1.0.0 — 2026-07-19

### Added

- Security-first public launcher and modular runtime.
- Exact 10-contract-at-1¢ immutable order profile.
- Eight-series crypto 15-minute allowlist.
- Dry-run scan, demo-trade, live, status, verify, kill-switch, reset, and unlock commands.
- Root-only safe `.env` parser.
- External RSA key validation and RSA-PSS request signing.
- Official Kalshi V2 single-order client.
- Existing resting-order and non-zero-position preflight.
- Persistent 80-contract ledger and ambiguity quarantine.
- Single-writer lock.
- Source manifest, verifier, strict CI workflow, and 114 regression and security tests.
- Security, operations, licensing, and support documentation.

### Security fixes during release preparation

- Replaced the private 20×1¢ live-first execution path with a dry-run-first public architecture.
- Replaced vulnerable `requests==2.32.5` with `requests==2.34.2`.
- Added actual-tree rehashing at write authorization and the final HTTP-send boundary.
- Added strict V2 acceptance-response reconciliation.
- Added non-zero account-position skipping and fail-closed account pagination completion.
- Added symlink-resistant runtime ledger, lock, log, and kill-switch handling.
- Added provably-unsent reservation release for local pre-send safety blocks.
- Made the default kill switch a tracked release file.

### Removed from public scope

- Private strategy internals.
- Private WebSocket/third-party feed integrations.
- Adaptive sizing and price logic.
- Broad environment compatibility aliases.
- Batch and unrelated mutation routes.
- Automatic live-first behavior.

Copyright © 2026 Gateway Information Group LLC. Licensed under the MIT License.
