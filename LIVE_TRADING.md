# Demo and Live Trading Activation

## Read this first

Live mode uses real money. The entire principal can be lost. Orders may remain resting, may fill later, and are not automatically cancelled by this release. Confirm eligibility and current platform rules yourself. Demo must come before production.

The bot cannot be made live by changing only `DRY_RUN`. It requires independent configuration, credential, integrity, acknowledgement, endpoint, kill-switch, ledger, account-preflight, and final-payload gates.

## Stage 0 — remain safe

```bash
python run_bot.py setup
python run_bot.py verify --ci
python run_bot.py status
python run_bot.py dry-run
```

Expected status before credentials:

- order profile: 10 contracts at 1¢;
- kill switch: ON;
- writes flag: 0;
- dry-run mode;
- blank API key and private-key path;
- 80 contracts remaining.

## Stage 1 — create dedicated demo credentials

Create credentials in Kalshi's demo environment. Demo and production credentials are separate. Save the private key outside this repository. On macOS/Linux:

```bash
mkdir -p "$HOME/.config/kalshi-10x1c"
chmod 700 "$HOME/.config/kalshi-10x1c"
chmod 600 "$HOME/.config/kalshi-10x1c/demo-private.key"
```

Do not paste key contents into `.env`. Store only its absolute path.

## Stage 2 — configure one demo cycle

Edit `.env` so the write-related values are exactly:

```dotenv
PUBLIC_RUN_MODE=demo-trade
PUBLIC_ORDER_WRITES_ENABLED=1
LIVE_TRADING=1
DRY_RUN=0
KALSHI_DRY_RUN=0
PAPER_MODE=0
PAPER_TRADE=0
SIMULATION_MODE=0
ALLOW_PRODUCTION_TRADING=0
PUBLIC_RISK_ACK=I_ACCEPT_DEMO_ORDER_RISK
PUBLIC_CONTINUOUS_ACK=
KALSHI_API_KEY_ID=<YOUR_DEMO_KEY_ID>
KALSHI_PRIVATE_KEY_PATH=/absolute/path/outside/repository/demo-private.key
```

Keep the direction policy at `cheapest` or explicitly set `yes`/`no`. The choice is a transparent heuristic, not a prediction.

Run strict verification again after any immutable-file edit. `.env` changes do not alter the manifest, but a fresh check is still recommended:

```bash
python run_bot.py verify --ci
python run_bot.py status
```

Remove the local kill switch only with the exact acknowledgement:

```bash
python run_bot.py kill-switch off --ack I_UNDERSTAND_REMOVING_KILL_SWITCH
```

Submit one authorized demo cycle:

```bash
python run_bot.py demo-trade
```

Immediately confirm the order, fills, and positions in the official demo interface. Then re-arm the stop:

```bash
python run_bot.py kill-switch on
```

## Stage 3 — production prerequisites

Do not proceed unless all are true:

- the owner has selected an appropriate public license;
- strict verification passes on the exact extracted release;
- demo authentication, order placement, ledger behavior, and emergency stop were personally verified;
- no ambiguous ledger entries exist;
- the production key is dedicated and stored outside the repository;
- you understand that one full order risks `$0.10` before fees and the default session cap can commit `$0.80` before fees;
- you have reviewed current Kalshi API documentation, fees, terms, eligibility, and jurisdiction rules;
- you can monitor and cancel orders in the official interface.

## Stage 4 — configure one production cycle

Use a separate production key and set:

```dotenv
PUBLIC_RUN_MODE=live
PUBLIC_ORDER_WRITES_ENABLED=1
LIVE_TRADING=1
DRY_RUN=0
KALSHI_DRY_RUN=0
PAPER_MODE=0
PAPER_TRADE=0
SIMULATION_MODE=0
ALLOW_PRODUCTION_TRADING=1
PUBLIC_RISK_ACK=I_ACCEPT_REAL_MONEY_RISK
PUBLIC_CONTINUOUS_ACK=
KALSHI_API_KEY_ID=<YOUR_PRODUCTION_KEY_ID>
KALSHI_PRIVATE_KEY_PATH=/absolute/path/outside/repository/production-private.key
```

Then:

```bash
python run_bot.py verify --ci
python run_bot.py status
python run_bot.py kill-switch off --ack I_UNDERSTAND_REMOVING_KILL_SWITCH
python run_bot.py live
python run_bot.py kill-switch on
```

Production authorization requires the strict verification attestation to be current and no more than 24 hours old. The bot re-hashes the release before authorization and again at the final HTTP-send boundary, so source edits made after verification or after authorization are blocked.

## Continuous mode

Continuous mode is intentionally harder to enable. Add this exact line:

```dotenv
PUBLIC_CONTINUOUS_ACK=I_ACCEPT_CONTINUOUS_LIVE_TRADING
```

Then use either:

```bash
python run_bot.py demo-trade --continuous
python run_bot.py live --continuous
```

The loop stops when interrupted, the kill switch appears, an ambiguity occurs, or fewer than 10 session contracts remain. The 80-contract ledger persists across restarts.

Run continuous production only while actively monitoring the official account. From another terminal, arm the kill switch at any time:

```bash
python run_bot.py kill-switch on
```

## Session reset

A reset does not prove an old order is gone. Reconcile all orders, fills, positions, and ambiguous entries first. Keep the kill switch ON, then run:

```bash
python run_bot.py reset-session-cap --ack I_ACCEPT_RESETTING_THE_80_CONTRACT_SESSION_BUDGET
```

The previous ledger is archived locally. Resetting allows a new 80-contract session and therefore creates new potential exposure.

## Stale writer lock

Only after confirming no bot process is running and keeping the kill switch ON:

```bash
python run_bot.py unlock --ack I_CONFIRM_NO_OTHER_BOT_INSTANCE_IS_RUNNING
```

## Emergency response

1. `python run_bot.py kill-switch on`
2. Stop all bot processes.
3. Review official resting orders, fills, and positions.
4. Cancel/manage orders in the official interface.
5. Revoke the API key if compromise is possible.
6. Preserve logs and ledger evidence.
7. Do not reset or delete state while an outcome is ambiguous.

Copyright © 2026 Gateway Information Group LLC. Licensed under the MIT License.
