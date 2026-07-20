# Frequently Asked Questions

## Is this bot safe?

It has multiple fail-closed controls and 100 passing regression tests, but no trading bot is universally safe. Review the source, verify the exact archive, use a dedicated demo key first, keep the kill switch armed, and understand the limitations in `SECURITY.md`.

## Can dry-run submit an order?

No. `scan` and `dry-run` never receive an in-process write authorization. Even a fully edited `.env` cannot turn those commands into mutation commands.

## How do I turn dry-run off?

Follow `LIVE_TRADING.md`. You must change a full set of exact flags, add validated credentials, pass current verification, remove the kill switch with a typed acknowledgement, and invoke `demo-trade` or `live`. There is intentionally no single toggle.

## Why 10 contracts at 1¢?

It makes the exposure easy to understand: a fully filled order commits ten cents before fees. The exact values are immutable in this public build so users can audit and discuss one consistent profile.

## Can I change the size to 20 or the price to 2¢?

Not without creating a different build. The verifier and final send boundary reject those values. Forking the source is technically possible, but the supplied manifest, test claims, documentation, and release identity would no longer apply.

## What is the maximum bot principal?

One fully filled order commits `$0.10` before fees. The persistent session cap allows up to eight exact orders, or `$0.80` principal before fees. Resetting the ledger starts a new session and permits new exposure.

## Does the bot guarantee a 99× return?

No. `$9.90` is the mathematical gross gain when ten fully filled 1¢ contracts all settle at `$1.00`. It is not an expected return. Orders may not fill, losses can consume all principal, fees matter, and low-price outcomes are usually unlikely.

## What does `cheapest` predict?

Nothing. It chooses the outcome with the lower displayed ask. It is a transparent selection rule, not a forecast or trading edge.

## Why are NO orders sent as `ask @ 0.9900`?

Kalshi V2 uses a single YES book. Selling YES at 99¢ is economically equivalent to buying NO at 1¢. The payload validator verifies the economic price rather than treating the book price as the cost of NO.

## Why post-only?

Post-only asks the exchange to reject rather than immediately cross the current book. The bot also performs a final local crossing check, but the exchange-side post-only rule protects against a book change between check and submission.

## Does it cancel orders automatically?

No. This public edition contains no cancel mutation. Monitor and manage orders through the official Kalshi interface.

## What happens after a network error during submission?

The result is treated as ambiguous. The 10-contract reservation remains in the ledger, the bot logs the uncertainty, and the cycle stops. Check the official account before doing anything else.

## Why does it skip an existing position?

To avoid unintentionally adding to or offsetting account exposure in the same market. The authenticated preflight also skips existing resting orders and bot-ledger duplicates.

## Why did strict verification fail while standard verification passed?

Strict mode also requires Ruff and an online known-vulnerability audit. If the advisory service is unreachable, production remains blocked. Restore network access and rerun `python run_bot.py verify --ci`; do not edit around the gate.

## Can I put the key in the project folder for convenience?

No. The credential validator blocks repository-contained keys. Use an absolute external path and restrictive file permissions.

## Does it use shell environment variables or a system proxy?

No. The bot intentionally reads only the local `.env` and creates a Requests session with ambient environment behavior disabled. This reduces accidental credential or proxy injection, but can require network configuration changes in corporate environments.

## Is the project affiliated with Kalshi?

No. It is an independent educational project that interacts with Kalshi's documented API.

## Can anyone reuse the code?

Yes. The project is available under the MIT License. Preserve the copyright
and permission notice, review the risk documentation, and verify the code in
your own environment before use. See `LICENSE.md` and
`LICENSE_OWNER_ACTION.md`.

Copyright © 2026 Gateway Information Group LLC. Licensed under the MIT License.
