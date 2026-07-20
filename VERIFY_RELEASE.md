# Verify the Release Before Running It

Security verification should be the first user action, not an afterthought.

## 1. Verify a packaged release

This step applies when a release provides both a project ZIP and a separately
published SHA-256 checksum. GitHub's automatically generated source archives
are not sealed packages and do not include a project-issued checksum sidecar.

The publisher should provide these two separate files:

- `kalshi_10x1c_public_v1.0.0.zip`
- `kalshi_10x1c_public_v1.0.0.zip.sha256`

From the directory containing both files:

```bash
# macOS / Linux
sha256sum -c kalshi_10x1c_public_v1.0.0.zip.sha256
```

PowerShell:

```powershell
$expected = (Get-Content .\kalshi_10x1c_public_v1.0.0.zip.sha256).Split()[0].ToLower()
$actual = (Get-FileHash .\kalshi_10x1c_public_v1.0.0.zip -Algorithm SHA256).Hash.ToLower()
if ($actual -ne $expected) { throw "ZIP checksum mismatch" }
"ZIP checksum PASS: $actual"
```

A mismatch means stop. Delete the files and obtain the release from the publisher again.

## 2. Understand checksum authenticity

A checksum proves that the ZIP matches the checksum text you received. It does
not prove who published either file. Confirm that both came from release
channels controlled by the repository owner. When no sealed package is
published, clone the repository and use the manifest and strict verifier.

The local `MANIFEST.sha256` is also unkeyed. It detects accidental or unauthorized changes relative to the packaged manifest, but an attacker who can replace the entire package can replace the manifest too. The release owner should additionally use a signed Git tag or cryptographic release signature when an owner-controlled signing key is available.

## 3. Extract into a clean directory

Do not overlay this release on an old bot folder. Confirm the extracted root contains `TRADING_DISABLED` and does not contain `.env`, private keys, logs, or a session ledger.

## 4. Create an isolated Python environment

```bash
python -m venv .venv
```

Activate it, then install exact development and verification dependencies:

```bash
python -m pip install -r requirements-dev.txt
```

## 5. Initialize the safe local state

```bash
python run_bot.py setup
python run_bot.py status
```

Expected status includes:

- exactly 10 contracts at a 1¢ economic price;
- kill switch ON;
- write flag `0`;
- blank credentials;
- 80 contracts remaining.

## 6. Run the strict verifier

```bash
python run_bot.py verify --ci
```

A strict PASS covers manifest matching, secret scanning, dangerous-code scanning, allowed network origins and routes, dry-run defaults, the tracked kill switch, immutable trade limits, exact installed dependency versions, Python compilation, 114 regression and security tests, `pip check`, Ruff, and `pip-audit`.

For production mode, the strict PASS must be completed in the same running process and remains bound to the current manifest, Python runtime, and a short validity window. A copied or edited report file cannot authorize an order.

If the advisory service is unreachable, strict verification fails. Do not reinterpret that failure as a clean vulnerability result. Production authorization remains blocked.

## 7. Inspect before adding credentials

At minimum, read:

- `README.md`
- `SECURITY.md`
- `SECURITY_AUDIT.md`
- `LIVE_TRADING.md`
- `PROFIT_AND_RISK.md`
- `LICENSE.md`
- `.env.example`
- `kalshi_public/constants.py`
- `kalshi_public/safety.py`
- `kalshi_public/api.py`

Run `scan` and `dry-run` before creating demo credentials.

## 8. Reverify after changes

Any change to an immutable file requires a new `MANIFEST.sha256`. Do not regenerate a publisher's manifest merely to make an unexplained change pass. Review the change, document it, rerun all checks, and create a distinctly versioned build.

A PASS is point-in-time engineering evidence, not a warranty, formal penetration test, profitability finding, legal approval, or permission to trade.

Copyright © 2026 Gateway Information Group LLC. Licensed under the MIT License.
