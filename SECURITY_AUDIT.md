# Security Audit — Public v1.0.1

## Executive result

The published source passed the local release regression suite after the latest hardening changes:

- **114 of 114 unit and security tests passed**;
- Ruff static analysis passed;
- all Python files compiled in memory;
- exact runtime dependency versions installed successfully;
- `pip check` reported no broken requirements;
- the release verifier's secret, key-file, dangerous-code, network-origin, route, default-mode, and immutable-profile checks passed during prepackaging validation.

No demo or production order was submitted during this audit. The build environment had no direct DNS access after ambient proxy use was intentionally disabled, so live Kalshi connectivity was not exercised. Network reads failed closed.

This is an engineering review and automated regression result, not an independent penetration test, exchange certification, legal opinion, or guarantee.

## Critical issues found and remediated

### 1. Private prototype was live-first and 20×1¢

The uploaded private prototype identified itself as a 20-contract-at-1¢ build and disabled paper mode at startup. Publishing that source with documentation-only edits would have been unsafe.

**Remediation:** the public edition was rebuilt around a smaller auditable execution path. Dry-run is now the code and configuration default. Exact 10-contract and 1¢ values are immutable constants checked at planning, payload construction, final authorization, ledger load, verification, and tests.

### 2. Documentation-only release folder

An earlier release folder contained documentation but not a self-contained executable public source tree.

**Remediation:** the final package includes the launcher, public modules, tests, exact dependency files, workflow, kill switch, documentation, and integrity manifest in one archive.

### 3. Known-vulnerable Requests pin

The initial public lock used `requests==2.32.5`, which acquired a published 2026 vulnerability record. Shipping that pin would have knowingly retained a disclosed issue.

**Remediation:** the runtime lock was refreshed and retested with `requests==2.34.2` and current compatible exact pins. The upgraded environment passed all tests, Ruff, compilation, and dependency consistency checks.

### 4. Manifest and verification-attestation trust gap

An authorization check that trusted only the manifest file's digest would not detect source edits made after verification when the manifest itself was unchanged.

**Remediation:** write authorization now recomputes the actual immutable-tree hashes against `MANIFEST.sha256`. A changed, extra, or missing immutable file blocks demo and production writes. Production also requires strict verification to pass within the same running process, bound to the current manifest, Python runtime, and a short validity window. A copied or edited report file cannot authorize an order.

### 5. Incomplete order-acceptance validation

A successful HTTP status alone is insufficient evidence that the response corresponds to the exact submitted order.

**Remediation:** V2 create responses must include a nonblank order ID, echo the submitted client order ID, provide nonnegative fill and remaining counts that reconcile to exactly 10 contracts, and include a positive acceptance timestamp. Uncertain responses are quarantined as ambiguous.

### 6. Existing exposure preflight

Checking resting orders alone could still add an order to a market in which the account already had a filled position.

**Remediation:** every write cycle must successfully read resting orders and non-zero primary-subaccount market positions. Matching tickers are skipped. A preflight read failure blocks the entire cycle.

### 7. Bounded-pagination truncation risk

A fixed page limit without checking the final cursor could silently omit an existing order, position, or eligible market. Missing account exposure is unacceptable before an order write.

**Remediation:** every bounded market, resting-order, and position reader now requires pagination to finish. If a cursor remains after the immutable page limit, the operation fails closed and account preflight blocks the write cycle.

### 8. Runtime symlink and late-tamper risk

Mutable ledger, lock, log, and kill-switch paths are outside the immutable manifest by design. Without local path checks, a symlink could redirect state or a broken kill-switch symlink could be mistaken for an absent switch. Source could also change after initial authorization during a long-running process.

**Remediation:** runtime state and evidence paths reject symlink redirection; any kill-switch symlink is treated as engaged; the tracked switch is required during verification; and the verified release tree is rechecked again immediately before each mutation request. A local pre-send safety block releases the unsent reservation instead of misclassifying it as a remote ambiguity.

## Final security model

### Default state

- `TRADING_DISABLED` included and ON;
- no `.env` distributed;
- `.env.example` has blank credentials and every write flag OFF;
- scan and dry-run require no credentials;
- production requires a fresh strict verification.

### Immutable trade profile

- count: `10.00`;
- economic price: `$0.0100`;
- YES representation: `bid` at `$0.0100`;
- NO representation: `ask` at `$0.9900` on the single YES book;
- post-only: `true`;
- session cap: `80.00` contracts;
- process cap: eight create requests;
- eight-series canonical allowlist.

### Credential controls

- only two credential keys accepted;
- private-key path must be absolute and outside the repo;
- symlinks rejected;
- POSIX owner and `600`-or-tighter mode required;
- maximum key size 64 KiB;
- RSA only, minimum 2048 bits;
- private-key contents never logged;
- `.env` mode checked before writes.

### Transport controls

- official production/demo REST bases only;
- HTTPS only;
- TLS verification cannot be disabled;
- automatic redirects disabled;
- Requests ambient environment and `.netrc` ignored;
- inherited session headers cleared;
- canonical paths only;
- response size, timeout, and pagination bounds that fail closed when incomplete;
- safe error truncation.

### Mutation controls

- one allowed mutation route;
- no generic public mutation method;
- in-process unforgeable nonce required;
- kill switch rechecked at send boundary;
- source attestation, endpoint, method, path, payload and count rechecked at final send;
- no extra payload keys;
- batch route absent;
- production endpoint selected by command, not user URL input.

### State controls

- atomic ledger writes;
- fail-closed ledger parsing and schema validation;
- duplicate active market rejection;
- accepted and ambiguous attempts consume cap;
- reset requires kill switch and exact acknowledgement;
- single-writer lock with explicit safe unlock procedure;
- local ledger, lock, and order-log paths reject symlink redirection;
- local order evidence written with restricted permissions.

## Test coverage summary

The 114 tests cover:

- environment isolation, parser rejection, bounds and defaults;
- credential and `.env` permission gates;
- kill-switch, acknowledgement and endpoint gates;
- source-tamper and stale-attestation blocking at authorization and final send;
- exact YES and NO payloads;
- wrong size, wrong price, extra field and invalid ticker rejection;
- final-boundary kill-switch enforcement;
- process and session caps;
- ledger tampering, duplicate market, reset and ambiguity behavior;
- single-writer lock and safe unlock;
- API signing, redirect, TLS and ambient-environment behavior;
- market, position and order pagination, including limit-exhaustion blocking;
- V2 route restriction and acceptance-response reconciliation;
- strategy parsing, outcome selection and book-crossing checks;
- release manifest, tracked kill-switch, runtime symlink, private-key and embedded-secret detection.

## Dependency-audit qualification

The isolated build container could install exact packages from its controlled package mirror but could not resolve `pypi.org` when `pip-audit` attempted its online advisory lookup. That strict audit attempt failed because the service was unreachable; it was not reported as a clean audit. The release therefore retains a fail-closed rule: `verify --ci` must complete successfully in the user's connected environment before production authorization.

The GitHub Actions workflow performs the same strict verification on pushes, pull requests, and manual dispatches. Repository owners should require that workflow before merging or publishing a release.

## Remaining risks

- No software can guarantee profitable trading or eliminate market risk.
- A compromised operating system can read credentials or alter processes.
- Package-index or build-chain compromise is outside the source verifier's complete control; exact pins are used, but artifact hashes are not yet cross-platform locked.
- Windows private-key ACLs are checked automatically and block write authorization when ownership or access is broader than the documented policy. Operators should still follow their organization's credential-handling requirements.
- The public bot does not automatically cancel orders or reconcile ambiguous outcomes.
- API behavior, market tickers, fees, platform rules, and legal requirements can change.
- The first-party source is licensed under MIT; third-party components retain their own terms.

## Release recommendation

Technically, publish only the final hashed ZIP and its external SHA-256 after clean-extraction verification. Operationally, keep live trading disabled in all examples, demonstrate dry-run first, use demo credentials in any video, redact all account details, enable private vulnerability reporting, and require strict CI.

The complete MIT license is in [LICENSE.md](LICENSE.md).

Copyright © 2026 Gateway Information Group LLC. Licensed under the MIT License.
