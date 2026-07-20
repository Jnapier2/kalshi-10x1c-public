# Kalshi 10×1¢ Public Edition

**A verification-led, educational order planner for selected Kalshi crypto 15-minute markets.**

> Start with verification, not trading. The packaged release ships with `TRADING_DISABLED` present, write flags off, dry-run settings on, blank credentials, an exact 10-contract-at-1¢ profile, and an 80-contract persistent session cap. These controls reduce risk; they do not guarantee safety, fills, compatibility, or profit.

## Verify before use

If you received a packaged release with a separately published SHA-256 checksum,
first follow [VERIFY_RELEASE.md](VERIFY_RELEASE.md). GitHub's automatically
generated source archives are not sealed release packages; cloned source can
continue with the repository verifier below.

From the verified project directory:

```bash
python -m venv .venv
```

Activate the environment with `source .venv/bin/activate` on macOS/Linux or `.venv\Scripts\Activate.ps1` in Windows PowerShell. Then run:

```bash
python -m pip install -r requirements-dev.txt
python run_bot.py setup
python run_bot.py verify --ci
python run_bot.py status
```

Continue only if strict verification reports `Overall: PASS` and status shows the kill switch `ON`, order writes `0`, blank credentials, and 80 contracts remaining. The strict verifier checks the manifest and source, scans for secrets and unsafe patterns, validates pinned origins, routes, defaults, and invariants, compiles the code, runs the regression suite, checks dependencies, runs Ruff, and performs a live vulnerability audit. If any required check or advisory service fails, production authorization remains blocked.

A PASS is point-in-time evidence that the included checks completed as designed. It is not a warranty, formal penetration test, legal approval, or permission to trade.

## Safe first run

No credentials are needed:

```bash
python run_bot.py scan
python run_bot.py dry-run
```

`scan` reads public market data. `dry-run` builds plans and performs final order-book checks, but the command has no write authorization and cannot submit an order.

## What it plans

For each allowlisted series, the bot considers at most the soonest eligible open market and applies one transparent direction policy:

- `cheapest`: choose the outcome with the lower displayed ask;
- `yes`: plan a YES order;
- `no`: plan a NO order.

This is a simple planning heuristic, not a prediction model, performance record, or claim of market edge.

Every permitted write has the same code-level profile:

| Property | Enforced value |
|---|---:|
| Contracts | exactly `10.00` |
| Economic buy price | exactly `$0.0100` per contract |
| Maximum principal if fully filled | `$0.10` before applicable fees |
| Order behavior | post-only, good-till-canceled |
| Persistent session cap | `80` accepted/reserved contracts (`$0.80` principal before fees) |
| Create attempts per process | at most `8` |
| Mutation surface | one V2 single-order create route |

Kalshi V2 represents a 1¢ YES purchase as a YES-book `bid` at `$0.0100`. A 1¢ NO purchase is represented as a YES-book `ask` at `$0.9900`.

The immutable series allowlist is `KXBTC15M`, `KXETH15M`, `KXSOL15M`, `KXDOGE15M`, `KXXRP15M`, `KXBNB15M`, `KXHYPE15M`, and `KXNEAR15M`. Changing the markets, count, price, or cap creates a different build and invalidates the packaged manifest.

## Safety boundaries

- Dry-run is the default and has no mutation authority.
- A tracked `TRADING_DISABLED` file blocks order creation.
- The launcher reads only the repository's `.env`; it ignores ambient shell credentials, proxy settings, `.netrc`, and broader credential aliases.
- The private key must be an unencrypted RSA key of at least 2048 bits, stored outside the repository at an absolute path.
- On POSIX, the key must be owned by the current user with permissions no broader than `600`.
- On Windows, credential loading performs a fail-closed NTFS ACL check. The current user must have access; ownership must be the current user or local Administrators; and no broader principal may have access. If the system ACL check cannot complete, write authorization is blocked.
- Runtime HTTPS is pinned to the official Kalshi demo or production REST origins, with TLS verification on and redirects rejected.
- Batch, amend, decrease, cancel, transfer, withdrawal, and unrelated portfolio mutations are absent from the public runtime.
- Final authorization rechecks source integrity, the kill switch, endpoint, route, payload, count, price, ticker, post-only setting, and process limit immediately before the request.
- Existing resting orders, non-zero positions, duplicate ledger markets, crossing books, incomplete pagination, and ambiguous results fail closed or are skipped.
- An 80-contract ledger persists across restarts. Ambiguous submissions retain their reservation for human review.
- A single-writer lock prevents concurrent bot writers, and runtime paths reject symlink redirection.

Read [SECURITY.md](SECURITY.md), [ARCHITECTURE.md](ARCHITECTURE.md), and [PRIVACY_AND_LOCAL_DATA.md](PRIVACY_AND_LOCAL_DATA.md) before adding credentials.

## Advanced: demo and live modes

Credentialed modes are advanced operator workflows, not part of the quick start. Use a separate working copy and dedicated credentials, complete demo testing first, and keep the official Kalshi account open for monitoring. The full activation, typed acknowledgements, and emergency-stop procedure are in [LIVE_TRADING.md](LIVE_TRADING.md).

The intended progression is:

```bash
python run_bot.py verify --ci
python run_bot.py status
python run_bot.py dry-run
python run_bot.py demo-trade
# Only after independent review, demo validation, and all production prerequisites:
python run_bot.py live
```

Live mode uses real money. The bot does not automatically cancel resting orders or reconcile ambiguous submissions. Eligibility, jurisdiction, account permissions, current platform terms, and every trading decision remain the operator's responsibility.

## Conditional payoff arithmetic—not expected return

If an order fully fills, ten 1¢ contracts commit `$0.10` before applicable fees. If all ten later settle as winners, the mathematical gross payout is `$10.00`, a gross gain of `$9.90` before applicable fees.

Those numbers describe one conditional payoff, not a forecast. A 1¢ price usually signals a low market-implied likelihood or substantial uncertainty. The order may never fill, fees reduce results, fills may be adversely selected, and the entire principal can be lost. See [PROFIT_AND_RISK.md](PROFIT_AND_RISK.md).

## Project map

- `run_bot.py` — public command-line entry point.
- `kalshi_public/` — API client, planner, safety gates, credentials, ledger, lock, privacy cleanup, and verifier.
- `tests/` — regression and security-boundary tests.
- `.env.example` — write-disabled configuration template.
- `TRADING_DISABLED` — local hard stop included in the release.
- `MANIFEST.sha256` — packaged immutable-file integrity manifest.
- `VERIFY_RELEASE.md` — archive, manifest, strict-verifier, and authenticity procedure.
- `SECURITY.md` and `SECURITY_AUDIT.md` — threat model, controls, evidence, and limitations.
- `QUICKSTART.md` — short verification and read-only path.
- `PRIVACY_AND_LOCAL_DATA.md` — local-data inventory, retention, cleanup, and sharing guidance.
- `DEPENDENCY_AUDIT.md` and `THIRD_PARTY_NOTICES.md` — dependency evidence and notices.

## Official API references

- Create Order V2: https://docs.kalshi.com/api-reference/orders/create-order-v2
- Authenticated requests: https://docs.kalshi.com/getting_started/quick_start_authenticated_requests
- Demo environment: https://docs.kalshi.com/getting_started/demo_env
- Market order book: https://docs.kalshi.com/api-reference/market/get-market-orderbook
- Positions: https://docs.kalshi.com/api-reference/portfolio/get-positions
- Balance: https://docs.kalshi.com/api-reference/portfolio/get-balance

## License

Copyright © 2026 Gateway Information Group LLC.

This project is released under the [MIT License](LICENSE.md). Dependency
obligations remain documented in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

This project is independent and is not affiliated with, endorsed by, or sponsored by Kalshi. Nothing here is financial, investment, legal, tax, or compliance advice.
