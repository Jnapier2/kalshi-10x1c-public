# Dependency Audit Record

## Release lock

The runtime dependency set is exact-pinned in `requirements.txt`. Development verification adds exact direct pins for `pip-audit` and Ruff through `requirements-dev.txt`.

| Package | Version | Role | Declared license |
|---|---:|---|---|
| certifi | 2026.6.17 | CA certificate bundle | MPL-2.0 |
| cffi | 2.1.0 | cryptography dependency | MIT-0 |
| charset-normalizer | 3.4.9 | Requests dependency | MIT |
| cryptography | 49.0.0 | RSA key loading and RSA-PSS signing | Apache-2.0 OR BSD-3-Clause |
| idna | 3.18 | Requests dependency | BSD-3-Clause |
| pycparser | 3.0 | CFFI dependency | BSD-3-Clause |
| requests | 2.34.2 | isolated HTTPS client | Apache-2.0 |
| urllib3 | 2.7.0 | Requests transport dependency | MIT |
| pip-audit | 2.10.1 | strict advisory scan | Apache-2.0 |
| ruff | 0.15.22 | static analysis | MIT |

License identifiers are based on installed package metadata and bundled license files in the release-validation environment. See `THIRD_PARTY_NOTICES.md`; upstream license texts remain controlling.

## Validation performed

The exact lock was installed into a clean virtual environment. The following passed after the final source changes:

```bash
python -m pip check
python -m unittest discover -s tests -v
ruff check run_bot.py kalshi_public scripts tests
```

Result: dependency consistency passed, Ruff passed, and 114 of 114 tests passed.

As an additional point-in-time check on July 20, 2026, the package records for the exact runtime pins reported no current vulnerabilities through the PyPI JSON API. This is useful corroborating evidence, but it is not a substitute for `pip-audit`; the strict verifier still requires that independent advisory scan to complete before production authorization.

## Requests correction

The prerelease lock used `requests==2.32.5`. During release preparation, that pin was removed after a 2026 vulnerability record was identified. The final lock uses `requests==2.34.2` with refreshed compatible transitive pins and a full regression rerun.

## Online vulnerability qualification

The isolated packaging container could install from its controlled package mirror, but direct DNS access to the advisory service was unavailable. Therefore the local `pip-audit` attempt failed for connectivity and is **not** represented as a vulnerability-free result.

This is fail-closed by design:

- standard `python run_bot.py verify` reports the online audit as not run;
- strict `python run_bot.py verify --ci` requires `pip-audit` to complete successfully;
- production authorization requires a current strict PASS.

The included GitHub workflow runs the strict verifier in a connected environment. Repository owners should require that workflow before merging or publishing.

## Refresh policy

Do not run an unattended dependency upgrade on a live release. For every refresh:

1. review upstream release notes and advisories;
2. update exact pins intentionally;
3. install in a clean environment;
4. run `pip check`, Ruff, all tests, and strict verification;
5. regenerate the inventory and manifest;
6. build a new versioned ZIP and checksum;
7. repeat clean-extraction verification.

Copyright © 2026 Gateway Information Group LLC. Licensed under the MIT License.
