# Kalshi 10×1¢ Public Edition

**Fresh public edition based on the v69.68 engineering lineage.**

This repository turns a sanitized market-state snapshot into a deterministic
plan for the fixed public profile: exactly **10 contracts at exactly 1¢**.
It demonstrates exchange-state truth, shard-conflict handling, stale-evidence
rejection, scoped funding checks, and duplicate-intent protection.

> **Offline and read-only by construction.** This source contains no network
> client, credential loader, request signer, or order mutation code. It cannot
> connect to Kalshi or place a trade.

## Quick start

Python 3.11 or newer is sufficient; there are no runtime dependencies.

```bash
python scripts/verify_release.py
python run_buy_planner.py examples/eligible_snapshot.json
python -m unittest discover -s tests -v
```

On Windows, `Kalshi10x1cPublic.bat examples\eligible_snapshot.json` is the
single BAT convenience launcher. It delegates to the canonical Python entrypoint.

## Fixed public contract

| Property | Value |
| --- | ---: |
| Contracts | `10` |
| Economic price | `1¢` per contract |
| Principal before modeled fees | `10¢` |
| Order style | Post-only planning evidence |
| Network access | None |
| Credential support | None |
| Live write authority | None |

## Evidence reviewed before a plan is emitted

- Snapshot schema and required critical inputs.
- Open market and operational platform state.
- Bounded market-data age.
- One-cent price-grid support.
- Complete fee and scoped-balance evidence.
- Intended exchange shard versus observed REST/order/fill shard evidence.
- Existing open-order and position conflicts.
- Deterministic duplicate intent IDs for the same ticker, round, side, shard,
  count, and price.
- A caller-provided final book-crossing check.

Results are `PLAN`, `HOLD`, `QUARANTINE`, or `INVALID`. `PLAN` is still only
educational output; the public source has no route that can submit it.

## Input

See `examples/eligible_snapshot.json`. The input is a synthetic or independently
sanitized JSON snapshot. Do not include credentials, private account data, or
production identifiers.

## What changed from the previous public repository

- Updated the public lineage from the older v1.0.1 source to v69.68.
- Removed authentication, network transport, credential setup, and live-mode
  documentation from current `main`.
- Added shard-specific evidence reconciliation and ticker-level quarantine.
- Added deterministic duplicate-intent protection.
- Added normalized release-identity verification and a lean standard-library-only
  runtime.
- Preserved the repository name and history while replacing the active source.

Read [PUBLIC_STERILIZATION_REPORT.md](PUBLIC_STERILIZATION_REPORT.md),
[SECURITY.md](SECURITY.md), and [DISCLAIMER.md](DISCLAIMER.md).

## License

MIT. Copyright © 2026 Gateway Information Group LLC. All rights reserved.

This project is independent and is not affiliated with, endorsed by, or sponsored
by Kalshi.
