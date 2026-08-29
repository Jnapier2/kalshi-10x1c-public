# Security

## Public safety boundary

This repository is an offline, read-only educational planner. It contains no
HTTP client, WebSocket client, request signer, credential loader, private-key
parser, or account mutation route. The runtime cannot authenticate, submit,
cancel, amend, decrease, transfer, withdraw, or otherwise change an account.

`TRADING_DISABLED` is tracked, release verification is read-only, and the
planner rejects a modified or incomplete managed source tree before processing
an input snapshot.

## Supported input

Use synthetic or independently sanitized JSON snapshots. Do not place account
identifiers, credentials, private keys, private endpoints, or production data
in this repository.

## Reporting

Report a suspected vulnerability privately through GitHub's security-reporting
path when available. Do not include credentials or private account evidence.

Copyright © 2026 Gateway Information Group LLC. All rights reserved.
