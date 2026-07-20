# Quick Start: Verify, Then Stay Read-Only

## 1. Verify the package

If you downloaded a ZIP, compare its separately published SHA-256 checksum and extract it into a clean directory before running anything. Follow [VERIFY_RELEASE.md](VERIFY_RELEASE.md); stop on any mismatch.

## 2. Create an isolated environment

```bash
python -m venv .venv
```

Activate it with `source .venv/bin/activate` on macOS/Linux or `.venv\Scripts\Activate.ps1` in Windows PowerShell.

## 3. Install and initialize safe defaults

```bash
python -m pip install -r requirements-dev.txt
python run_bot.py setup
```

`setup` creates a local `.env` with blank credentials and write-disabled defaults, creates `logs/` and `runtime/`, and ensures `TRADING_DISABLED` is on.

## 4. Require a strict PASS

```bash
python run_bot.py verify --ci
python run_bot.py status
```

Continue only if verification reports `Overall: PASS` and status shows the kill switch `ON`, writes `0`, blank credentials, and 80 contracts remaining. A required audit or network failure is a failure—not a reason to bypass the check.

## 5. Run without credentials

```bash
python run_bot.py scan
python run_bot.py dry-run
```

Both commands are read-only. `dry-run` displays exact 10-contract, 1¢ plans and performs final order-book checks without write authorization.

## Credentials and live modes are advanced

Do not add credentials during the quick start. If you later test the demo flow, use a dedicated private key at an absolute path outside the repository.

- POSIX: current-user ownership and permissions no broader than `600` are required.
- Windows: the private-key NTFS ACL must grant the current user access, be owned by that user or local Administrators, and grant no broader principal access. Credential loading blocks writes if the system ACL check cannot complete or fails.
- Cloud sync: do not operate a credentialed copy or store the key in OneDrive, Dropbox, Google Drive, iCloud, or a shared folder. `.gitignore` does not prevent cloud syncing.

Read [LIVE_TRADING.md](LIVE_TRADING.md) in full before demo mode. Production `live` is an advanced, real-money path that also requires an interactive terminal and a fresh exact confirmation on every launch; non-interactive production launches are blocked.

Emergency stop:

```bash
python run_bot.py kill-switch on
```

Local-data inventory, retention, cleanup, and incident-preservation guidance are in [PRIVACY_AND_LOCAL_DATA.md](PRIVACY_AND_LOCAL_DATA.md).

Copyright © 2026 Gateway Information Group LLC. Licensed under the MIT License.
