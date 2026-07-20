# Support

## Start here

For setup and expected behavior, read in this order:

1. `VERIFY_RELEASE.md`
2. `QUICKSTART.md`
3. `SECURITY.md`
4. `FAQ.md`
5. `LIVE_TRADING.md`

Run these commands before reporting a problem:

```bash
python run_bot.py status
python run_bot.py verify
```

For live-readiness questions, use the strict form:

```bash
python run_bot.py verify --ci
```

## Good bug reports

Include:

- operating system and Python version;
- bot version/build ID;
- command used;
- redacted error text;
- whether the kill switch was ON;
- the relevant verification check result;
- minimal steps to reproduce in dry-run or demo.

Never include `.env`, key contents, API key IDs, full private paths, account balances, order IDs, positions, logs, or a session ledger containing account-linked data.

## Security issues

Use private vulnerability reporting, not a public issue. See `SECURITY.md`.

## Trading and platform support

This repository cannot provide account, market-resolution, eligibility, jurisdiction, fee, deposit, withdrawal, or platform-policy support. Use Kalshi's official support and current documentation for those matters.

No support response is financial, investment, legal, tax, or compliance advice. Live trading remains the user's decision and risk.

Copyright © 2026 Gateway Information Group LLC. Licensed under the MIT License.
