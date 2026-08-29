# Public Sterilization Report

## Source lineage

This public edition is derived from the reviewed feature lineage of
**Kalshi 15-Minute 1¢ Buy Bot v69.68**. It is not a copy of the private operational package and
does not inherit private release or live-trading authority.

## Removed from the public edition

- Credentials, private keys, account identifiers, environment templates, and
  local configuration.
- HTTP, WebSocket, authentication, request-signing, and retry transport code.
- Order creation, cancellation, amendment, decrease, transfer, withdrawal, and
  funding behavior.
- Private logs, state, databases, receipts, diagnostics, support exports,
  machine labels, and local paths.
- Live performance evidence, strategy-graduation controls, and private
  operational thresholds not required for the public planner.
- Historical compatibility launchers and duplicate implementation surfaces.

## Retained in public-safe form

- Deterministic snapshot validation and explicit evidence states.
- Fail-closed decisions for stale, incomplete, contradictory, or unsupported
  inputs.
- The public planning contract described in the repository README.
- Versioned metadata, normalized manifest verification, regression tests, and
  one thin Windows convenience launcher.

## Result

No configuration switch, environment variable, command-line option, source
edit, or direct module call can enable account mutations because the public
code contains no network or mutation implementation.

Copyright © 2026 Gateway Information Group LLC. All rights reserved.
