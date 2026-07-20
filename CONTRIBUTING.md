# Contributing

Thank you for helping improve the safety and educational value of this project.

## Licensing and contributions

This package is available under the MIT License. Issues and focused pull
requests are welcome. By submitting a contribution, you represent that you
have the right to provide it and agree that it may be distributed under the
project's MIT License. Do not submit credentials, private data, copied code, or
third-party material without appropriate permission.

## Security reports

Do not open a public issue for a vulnerability, credential exposure, or exploitable live-trading bypass. Use GitHub's private vulnerability-reporting feature through the repository Security tab.

## Safe change requirements

A change must not silently:

- alter the exact 10-contract or 1¢ invariants;
- increase the 80-contract persistent session cap;
- add a mutation route;
- make dry-run capable of writing;
- weaken the kill switch, source attestation, key isolation, endpoint allowlist, ledger, or single-writer lock;
- introduce automatic cancellation, transfer, withdrawal, self-update, arbitrary shell execution, or third-party data transmission.

Behavior changes require regression tests and documentation. Live-capable changes require review of `SECURITY.md`, `ARCHITECTURE.md`, and `LIVE_TRADING.md`.

## Local verification

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
ruff check run_bot.py kalshi_public scripts tests
python -m pip check
python run_bot.py verify --ci
```

Do not commit `.env`, private keys, API key IDs, account balances, orders, positions, logs, runtime state, generated attestations, or screenshots with account information.

The release owner regenerates `FILE_INVENTORY.txt` and `MANIFEST.sha256` after the final reviewed change.

Copyright © 2026 Gateway Information Group LLC. Licensed under the MIT License.
