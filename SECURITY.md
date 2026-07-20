# Security Policy and User Verification Guide

## Security comes first

The safest state is the distributed state: no `.env`, blank credentials, dry-run defaults, and `TRADING_DISABLED` present. Keep that state until you have verified the exact files you received.

## User verification procedure

1. Compare the ZIP SHA-256 with the separately published checksum.
2. Extract into a new directory. Do not run directly inside an old bot folder.
3. Inspect `LICENSE.md`, `README.md`, `.env.example`, `kalshi_public/constants.py`, `kalshi_public/safety.py`, and `kalshi_public/api.py`.
4. Create a new virtual environment and install `requirements-dev.txt`.
5. Run `python run_bot.py setup`.
6. Run `python run_bot.py verify --ci`.
7. Confirm `python run_bot.py status` shows the kill switch ON, writes `0`, blank credentials, and a zero-use 80-contract ledger.
8. Run only `scan` and `dry-run` before adding credentials.

A verification PASS is evidence that the included checks behaved as designed at that moment. It is not a warranty, formal penetration test, legal approval, or trading recommendation.

## Controls included

### Fail-closed configuration

The bot reads only `./.env`; it does not import ambient process environment variables. The parser does not execute shell syntax and rejects duplicate keys, unsupported live keys, symlinks, oversized files, command substitution, and variable expansion syntax. Unsupported keys are ignored for read-only use and block write authorization.

### Credential isolation

Only `KALSHI_API_KEY_ID` and `KALSHI_PRIVATE_KEY_PATH` are recognized. The private key must be an absolute path outside the repository. On POSIX systems the bot requires current-user ownership and permissions no broader than `600`. Key content is never logged. Use a dedicated key, revoke it immediately after suspected exposure, and never commit `.env` or a key file.

Windows users must review the file's NTFS ACL manually because POSIX permission bits are not available. Restrict access to the current account before enabling writes.

### Network and transport isolation

Runtime HTTPS origins are restricted to the official Kalshi production and demo REST bases. The client disables Requests' ambient proxy and `.netrc` behavior, clears inherited headers, verifies TLS, blocks redirects, bounds timeouts and response sizes, and rejects noncanonical paths.

### Mutation isolation

The only allowed mutation is:

```text
POST /trade-api/v2/portfolio/events/orders
```

The public code does not implement batch creation, cancellation, amendment, decreases, transfers, withdrawals, API-key management, or arbitrary request helpers. Every mutation must carry an in-process authorization object created by the launcher after all gates pass.

### Exact order invariants

The final boundary requires:

- an allowlisted canonical ticker;
- exactly `10.00` contracts;
- exactly `$0.0100` economic buy price;
- `bid @ 0.0100` for YES or `ask @ 0.9900` for NO;
- a valid UUID client order ID;
- post-only, good-till-canceled behavior;
- fixed self-trade prevention and pause-cancel settings;
- no extra payload fields;
- no more than eight create requests per process.

### Account preflight

Before discovery can produce a write, the authenticated cycle must successfully read balance, resting orders, and non-zero market positions. A read failure blocks the cycle. Markets with an existing resting order, existing position, active ledger entry, or crossing final book are skipped.

### Persistent exposure ledger

The ledger reserves 10 contracts before a request is sent. Accepted and ambiguous attempts count toward the immutable 80-contract cap. If the network or response is uncertain, the bot stops and keeps the reservation rather than guessing that no order exists. Resetting the ledger requires the kill switch to remain on and an exact typed acknowledgement.

### Integrity and attestation

`MANIFEST.sha256` covers immutable release files. Verification recomputes every hash, rejects extra or missing immutable files, and writes a short-lived attestation only after a PASS. The authorization boundary checks the manifest and re-hashes the source tree again. Production requires a strict attestation no more than 24 hours old.

Dynamic files—including `.env`, logs, runtime state, the kill switch, and generated reports—are intentionally excluded from the manifest. Their safety is enforced through runtime validation rather than release hashing.

## Emergency procedure

From the repository directory:

```bash
python run_bot.py kill-switch on
```

Then:

1. Stop all bot processes.
2. Inspect the official Kalshi account for resting orders, fills, and positions.
3. Revoke the API key if credentials may have been exposed.
4. Preserve `runtime/session_ledger.json` and `logs/orders.jsonl` for review.
5. Do not reset the ledger until every ambiguous entry has been reconciled manually.

The public bot intentionally has no automatic cancel route. Use the official platform to cancel or manage orders.

## Dependency policy

Runtime packages are exact-pinned. Strict verification runs `pip-audit`; the GitHub workflow runs the same check on pushes and pull requests. Dependency locks must be reviewed and regenerated intentionally. A clean audit is point-in-time evidence only; new disclosures can appear later.

## Reporting a vulnerability

Do not include credentials, account IDs, balances, positions, order IDs, or private trading history in a public issue. Repository owners should enable GitHub Private Vulnerability Reporting and ask reporters to use a private security advisory. Include:

- release version and ZIP SHA-256;
- operating system and Python version;
- the smallest non-sensitive reproduction;
- expected and observed behavior;
- whether any API mutation may have occurred.

For an active credential or account incident, stop the bot, arm the kill switch, and revoke the affected key before preparing a report.

## Scope and limitations

The review included automated source checks and regression testing, not a formal third-party penetration test, exchange certification, or guarantee against every vulnerability. Security also depends on the user's machine, Python distribution, package index, account controls, network, repository settings, and operational discipline.

Copyright © 2026 Gateway Information Group LLC. Licensed under the MIT License.
