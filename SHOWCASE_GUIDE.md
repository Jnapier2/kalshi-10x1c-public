# GitHub and Portfolio Showcase Guide

## Recommended presentation order

1. **Security first:** show the tracked `TRADING_DISABLED` file, blank credentials, and strict verifier.
2. **Dry-run demo:** show a public scan and exact 10×1¢ plans without any account data.
3. **Architecture:** explain the one-route mutation boundary, in-memory authorization, persistent ledger, and ambiguity handling.
4. **Testing:** show the 113-test pass and the GitHub security workflow.
5. **Economics:** present the 10¢ principal / $10 gross payout arithmetic alongside the full-risk warning.
6. **Story:** explain how the project moved from a fast private prototype to a deliberately constrained public release.

## Suggested repository layout

Keep the release root uncluttered. Pin these files near the top of the README:

- `QUICKSTART.md`
- `SECURITY.md`
- `SECURITY_AUDIT.md`
- `LIVE_TRADING.md`
- `PROFIT_AND_RISK.md`
- `WHY_I_RELEASED_THIS.md`
- `LICENSE_OWNER_ACTION.md`

Publish versioned ZIP files and separate `.sha256` sidecars under GitHub Releases. Do not commit `.env`, keys, runtime ledgers, order logs, screenshots containing account data, or generated attestations.

## Release page copy

**Kalshi 10×1¢ Public Edition v1.0.0** is a verification-led educational bot for selected crypto 15-minute markets. Every authorized order is exactly 10 contracts at a 1¢ economic price. The release includes a tracked stop control, fixed exposure limits, RSA-PSS signing, official-endpoint controls, account order and position preflights, uncertain-result preservation, source-manifest verification, and 113 automated tests.

Start with `QUICKSTART.md`. Do not add credentials until `verify --ci` passes. Demo credentials and production credentials are separate. Live trading risks real money and is not enabled by default.

## Suggested screenshots

Use only fabricated or demo data:

1. `python run_bot.py status` with blank credentials and kill switch ON.
2. A successful strict verification summary.
3. A dry-run plan showing `10 @ $0.01`.
4. A stop-control demonstration that shows order authorization remaining off.
5. A unit-test summary showing 113 tests passed.
6. A simple architecture diagram based on `ARCHITECTURE.md`.

Redact usernames, computer paths, API key IDs, account balances, order IDs, positions, timestamps that identify an account, and all private-key information.

## Suggested 60-second video script

> This is the Kalshi 10×1¢ Public Edition, a case study in responsible automation. It begins with blank credentials, a tracked stop control, and a credential-free dry-run path. Before a production command can proceed, the application checks its source, dependencies, tests, static analysis, and vulnerability status. Every permitted order is fixed at ten contracts and a one-cent economic price, while a persistent ledger limits the session to eighty contracts. The client accepts only official Kalshi endpoints and one order route, checks existing account exposure, and preserves uncertain results for review. The project shows how clear requirements, governed data, and deliberate controls can make a complex workflow easier to inspect and trust.

## Badges to consider

Use badges only when they link to real, passing checks:

- security verification workflow;
- Python 3.10+;
- release version;
- license, after the owner activates one;
- latest ZIP SHA-256, placed in release notes rather than a dynamic badge.

Do not use performance, win-rate, profit, “audited,” or “secure” badges unless supported by a defined independent process.

## Repository settings

Before publication:

- enable branch protection for the default branch;
- require the security workflow;
- enable Dependabot alerts and dependency review where available;
- enable private vulnerability reporting;
- disable force pushes to the protected branch;
- require review for workflow-file changes;
- create a release from a clean signed tag if your workflow supports signing;
- upload the ZIP and checksum generated from the same final tree;
- complete the licensing decision.

## Portfolio framing

Frame the project as a secure software-engineering and API-integration case study, not as a money-making product. Strong themes include:

- sanitizing a private codebase for public distribution;
- reducing features to reduce attack surface;
- converting business rules into code-level invariants;
- designing for ambiguous distributed-system outcomes;
- making dry-run and live mode structurally different;
- creating trust evidence users can reproduce.

## Additional public-friendly ideas

- Publish a short article: “From Prototype to Verification-Led Automation.”
- Add a diagram showing every live gate and where it is rechecked.
- Record a demo-only walkthrough in a fresh account with mock funds.
- Create a companion exercise asking learners to add a harmless read-only metric and its tests.
- Publish a threat-model update with each release.
- Maintain a compatibility table for Python and current Kalshi API versions.
- Add signed release provenance later, without weakening the existing local verifier.

Copyright © 2026 Gateway Information Group LLC. Licensed under the MIT License.
