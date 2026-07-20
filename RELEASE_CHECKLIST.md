# Public Release Checklist

## Critical safety

- [ ] Confirm the release contains the sanitized public source, not the private monolith.
- [ ] Confirm `ORDER_COUNT` is exactly `10.00` and economic price is exactly `0.0100`.
- [ ] Confirm `TRADING_DISABLED` is present in the archive and tracked by Git.
- [ ] Confirm `.env` and every private-key format are absent.
- [ ] Confirm `.env.example` has blank credentials and all write flags OFF.
- [ ] Confirm only the official Kalshi demo/production origins appear in runtime source.
- [ ] Confirm only `POST /portfolio/events/orders` is implemented as a mutation.
- [ ] Confirm the persistent session cap is 80 contracts and the process cap is eight orders.
- [ ] Confirm existing resting orders and non-zero positions are checked before writing.
- [ ] Confirm ambiguous submissions reserve budget and stop the cycle.
- [ ] Confirm no automatic cancellation, transfer, withdrawal, or arbitrary request feature slipped into runtime.

## Verification

- [ ] Install the exact final `requirements-dev.txt` in a fresh virtual environment.
- [ ] Run `python -m pip check`.
- [ ] Run `python run_bot.py verify --ci` with advisory-service connectivity.
- [ ] Confirm all 100 tests pass.
- [ ] Confirm Ruff passes.
- [ ] Confirm secret and dangerous-code scans pass.
- [ ] Confirm the final `MANIFEST.sha256` matches every immutable file.
- [ ] Confirm editing one source file makes verification fail.
- [ ] Restore the clean tree and regenerate/verify the manifest.

## Documentation

- [ ] README starts with verification and dry-run, not profit claims.
- [ ] Every document says 10 contracts at 1¢.
- [ ] Profit arithmetic includes fees, fill uncertainty, and total-loss language.
- [ ] Live instructions require demo first and list every exact gate.
- [ ] Emergency-stop and ambiguous-result procedures are visible.
- [ ] No documentation contains real keys, IDs, balances, positions, orders, or personal paths.
- [ ] Current official Kalshi API references were reviewed.
- [ ] The unaffiliated/not-financial-advice disclaimer is present.

## Licensing and ownership

- [ ] Rights holder confirms authority to distribute all first-party code and documentation.
- [ ] A public license is intentionally selected and activated, or the release is clearly labeled inspection-only.
- [ ] `LICENSE.md`, `pyproject.toml`, README, repository metadata, and release page agree.
- [ ] Third-party notices and license obligations are preserved.
- [ ] The repository owner has reviewed trademark and affiliation language.

## GitHub and portfolio

- [ ] Replace no placeholder owner/repository links; this package intentionally includes none.
- [ ] Enable private vulnerability reporting.
- [ ] Enable branch protection and require security verification.
- [ ] Review workflow permissions and action versions.
- [ ] Upload only the final versioned ZIP and matching checksum.
- [ ] Publish clean-extraction verification evidence.
- [ ] Use demo or fabricated screenshots only.
- [ ] Do not claim profit, win rate, formal audit, endorsement, or guaranteed safety.

## Packaging

- [ ] Remove `.env`, attestations, generated reports, caches, logs, and runtime state.
- [ ] Keep `runtime/.gitkeep`, `logs/.gitkeep`, and `TRADING_DISABLED`.
- [ ] Generate `FILE_INVENTORY.txt`.
- [ ] Generate `MANIFEST.sha256` after every final content change.
- [ ] Verify the final source tree.
- [ ] Build the ZIP from a clean directory.
- [ ] Generate a separate ZIP SHA-256 sidecar.
- [ ] Extract the ZIP into another clean directory.
- [ ] Install and run standard verification on the extracted copy.
- [ ] When network access is available, run strict verification on the extracted copy.
- [ ] Scan the ZIP contents for keys, `.env`, cache files, and unexpected binaries.

## Final owner sign-off

- [ ] I understand production mode risks real money.
- [ ] I understand the maximum principal numbers exclude fees, manual trades, other bots, and post-reset sessions.
- [ ] I approve the public description, story, profit language, disclaimers, and license.
- [ ] I approve the exact final ZIP SHA-256.

Copyright © 2026 Gateway Information Group LLC. Licensed under the MIT License.
