# Profit Potential and Risk

## The attractive arithmetic

Each permitted order is exactly 10 contracts at an economic price of 1¢:

```text
10 contracts × $0.01 = $0.10 principal before applicable fees
```

If all ten contracts settle as winners:

```text
Gross payout: 10 × $1.00 = $10.00
Gross gain:   $10.00 − $0.10 = $9.90 before applicable fees
```

That is a **99× gross gain on the committed principal**, or a 100× gross payout multiple, before fees—when a fully filled 1¢ position wins.

## What that number does not mean

It is not an expected return, forecast, promise, backtest, or proof of edge. A 1¢ contract usually represents an outcome the market considers very unlikely, uncertain, or difficult to fill at that price. The corresponding downside is simple: a losing contract settles at zero, so the full principal can be lost.

Practical results can also be worse than headline arithmetic because:

- the order may never fill;
- only part of the order may fill;
- fills may occur when better-informed participants are willing to trade against it;
- fees reduce gross gains and can materially affect tiny-price orders;
- market definitions and resolution criteria may not match a casual reading;
- an order can remain resting until filled, cancelled, expired, or otherwise handled by the platform;
- API, network, clock, credential, or operational failures can interrupt monitoring;
- resetting the session ledger permits new exposure beyond the previous `$0.80` session principal.

## Public-edition exposure limits

A single fully filled order commits at most `$0.10` before fees. The persistent session cap reserves or accepts no more than 80 contracts, equivalent to `$0.80` principal before fees across eight exact-size orders. Ambiguous submissions count against that cap because assuming they failed would be unsafe.

The cap is a software guardrail, not an account-wide loss limit. It does not include manual trades, other bots, existing positions, fees, or a new session started after an intentional ledger reset.

## The right way to present this project

Use language such as:

> The 10×1¢ profile offers asymmetric payoff arithmetic: ten fully filled winning contracts can turn ten cents of principal into a ten-dollar gross payout before fees. That mathematical ceiling is compelling for education, but it is not a profitability claim. Fills are uncertain, low-priced outcomes are usually unlikely, fees matter, and the full principal can be lost.

Avoid claims such as “guaranteed profit,” “passive income,” “99× strategy,” “low risk,” or “wins for pennies.”

## Educational value

The strongest value of the release is not a promise of profit. It is a small, inspectable case study in:

- API authentication and RSA-PSS signing;
- fail-closed configuration;
- immutable trade invariants;
- order-book reciprocity in binary markets;
- persistent risk budgets;
- ambiguous distributed-system outcomes;
- secure secret handling;
- regression testing and release manifests;
- moving from a dry run to a deliberately gated production command.

This document is educational and is not financial, investment, legal, tax, or compliance advice.

Copyright © 2026 Gateway Information Group LLC. Licensed under the MIT License.
