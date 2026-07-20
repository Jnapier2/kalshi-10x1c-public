#!/usr/bin/env python3
"""Public command-line launcher for the Kalshi 10x1c bot."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

# Package verification must not create bytecode inside the tree it inspects.
sys.dont_write_bytecode = True

from kalshi_public import BUILD_ID, VERSION
from kalshi_public.auth import credential_status
from kalshi_public.constants import (
    CONTINUOUS_ACK,
    DEMO_RISK_ACK,
    ECONOMIC_BUY_PRICE,
    KILL_SWITCH_OFF_ACK,
    LIVE_LAUNCH_ACK,
    ORDER_COUNT,
    PRIVACY_PURGE_ACK,
    PRODUCTION_RISK_ACK,
    SESSION_RESET_ACK,
    UNLOCK_ACK,
)
from kalshi_public.engine import run_read_only, run_write
from kalshi_public.env import EnvError, RuntimeSettings, load_settings
from kalshi_public.instance_lock import unlock
from kalshi_public.ledger import reset as reset_ledger
from kalshi_public.ledger import status as ledger_status
from kalshi_public.privacy import purge_local_data
from kalshi_public.safety import (
    SafetyError,
    authorization_failures,
    authorize_write,
    create_kill_switch,
    kill_switch_is_on,
    remove_kill_switch,
    revoke_write,
    verification_attestation_failures,
)
from kalshi_public.verify import verify_release

ROOT = Path(__file__).resolve().parent


def command_setup(_: argparse.Namespace) -> int:
    env_path = ROOT / ".env"
    created = False
    if env_path.is_symlink():
        raise EnvError(".env must not be a symlink")
    if env_path.exists() and not env_path.is_file():
        raise EnvError(".env exists but is not a regular file")
    if not env_path.exists():
        shutil.copyfile(ROOT / ".env.example", env_path)
        created = True
    if os.name != "nt":
        env_path.chmod(0o600)
    create_kill_switch(ROOT)
    (ROOT / "runtime").mkdir(exist_ok=True)
    (ROOT / "logs").mkdir(exist_ok=True)
    print(f"{'Created' if created else 'Kept'} {env_path.name}; permissions restricted where supported.")
    print("TRADING_DISABLED is ON. No API mutation can pass while it remains on.")
    print("Next: python run_bot.py verify")
    print("Then: python run_bot.py dry-run")
    return 0


def command_verify(args: argparse.Namespace) -> int:
    result = verify_release(ROOT, ci=bool(args.ci), clean_package=bool(args.clean_package))
    for check in result.checks:
        print(f"[{check.status:<4}] {check.name}: {check.detail}")
    print(f"\nOverall: {'PASS' if result.passed else 'FAIL'}")
    report_label = (
        str(result.report_path)
        if result.report_path is not None
        else "not written (read-only clean-package mode)"
    )
    print(f"Report: {report_label}")
    return 0 if result.passed else 2


def _safe_value(settings: RuntimeSettings, key: str) -> str:
    return str(settings.values.get(key, "")).strip()


def command_status(_: argparse.Namespace) -> int:
    settings = load_settings(ROOT)
    credentials = credential_status(settings.values, ROOT)
    ledger = ledger_status(ROOT)
    attestation = verification_attestation_failures(ROOT)
    print(f"Build: {BUILD_ID}")
    print(f"Order profile: exactly {ORDER_COUNT:.0f} contracts at ${ECONOMIC_BUY_PRICE:.2f} economic price")
    print("Maximum principal per fully filled order before applicable fees: $0.10")
    print(f".env: {'present' if settings.source_exists else 'missing (safe defaults active)'}")
    print(f"Configured mode: {_safe_value(settings, 'PUBLIC_RUN_MODE') or 'dry-run'}")
    print(f"Direction policy: {settings.direction_policy}")
    print(f"Order writes flag: {_safe_value(settings, 'PUBLIC_ORDER_WRITES_ENABLED') or '0'}")
    print(f"Kill switch: {'ON' if kill_switch_is_on(ROOT) else 'OFF'}")
    print(f"Verification: {'PASS/current' if not attestation else 'NOT READY — ' + '; '.join(attestation)}")
    print(f"API key ID: {'present' if credentials.key_id_present else 'missing'}")
    print(f"Private key: {'present as ' + credentials.key_filename if credentials.key_filename else 'missing'}")
    print(
        "Session budget: "
        f"accepted={ledger['accepted_contracts']:.0f}, reserved={ledger['reserved_contracts']:.0f}, "
        f"remaining={ledger['remaining_contracts']:.0f} of {ledger['cap_contracts']:.0f} contracts"
    )
    if settings.unknown_keys:
        print("Unsupported .env keys (ignored; live authorization will fail): " + ", ".join(settings.unknown_keys))
    return 0


def command_read(args: argparse.Namespace) -> int:
    settings = load_settings(ROOT)
    return run_read_only(ROOT, settings, mode=args.command)


def command_write(args: argparse.Namespace) -> int:
    settings = load_settings(ROOT)
    if args.command == "live":
        if not sys.stdin.isatty():
            raise SafetyError("production launch requires an interactive terminal and a fresh typed confirmation")
        print("Running the mandatory strict verification before production authorization...")
        strict_result = verify_release(ROOT, ci=True)
        if not strict_result.passed:
            failed = [check.name for check in strict_result.checks if check.status == "FAIL"]
            raise SafetyError("production strict verification did not pass: " + ", ".join(failed))
        print("Strict verification: PASS (current process)")
        print("\nPRODUCTION ORDER CONFIRMATION")
        print("Endpoint: official Kalshi production API")
        print("Order profile: exactly 10 contracts at a 1c economic price")
        print("Session ceiling: 80 contracts ($0.80 principal before fees if every order fully fills)")
        print(f"Direction policy: {settings.direction_policy}; continuous: {'yes' if args.continuous else 'no'}")
        typed = input(f"Type {LIVE_LAUNCH_ACK} to continue: ").strip()
        if typed != LIVE_LAUNCH_ACK:
            raise SafetyError("production launch confirmation did not match; no order authorization was created")
    failures = authorization_failures(args.command, settings, ROOT, continuous=bool(args.continuous))
    if failures:
        raise SafetyError("Write command blocked:\n- " + "\n- ".join(failures))
    authorization = authorize_write(args.command, settings, ROOT, continuous=bool(args.continuous))
    try:
        accepted = run_write(
            ROOT,
            settings,
            mode=args.command,
            authorization=authorization,
            continuous=bool(args.continuous),
        )
    finally:
        revoke_write(authorization)
    print(f"Run complete. Accepted orders this process: {accepted}")
    return 0


def command_kill_switch(args: argparse.Namespace) -> int:
    if args.action == "status":
        print(f"Kill switch: {'ON' if kill_switch_is_on(ROOT) else 'OFF'}")
    elif args.action == "on":
        create_kill_switch(ROOT)
        print("Kill switch ON. New API mutations are blocked.")
    else:
        remove_kill_switch(ROOT, args.ack or "")
        print("Kill switch OFF. All other live-trading gates remain required.")
    return 0


def command_reset(args: argparse.Namespace) -> int:
    archived = reset_ledger(ROOT, args.ack or "")
    print(f"Session budget reset. Prior ledger archive: {archived}")
    print("Kill switch remains ON.")
    return 0


def command_unlock(args: argparse.Namespace) -> int:
    unlock(ROOT, args.ack or "")
    print("Live-instance lock removed. Kill switch remains ON.")
    return 0


def command_purge_local_data(args: argparse.Namespace) -> int:
    removed = purge_local_data(ROOT, args.ack or "")
    print(
        "Local account-linked bot data removed: "
        f"logs={removed['logs']} files, runtime={removed['runtime']} files."
    )
    print("TRADING_DISABLED remains ON. Configuration and the external private key were not changed.")
    return 0


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(
        description="Security-first public Kalshi 10-contract-at-1-cent educational bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Safety acknowledgements:\n"
            f"  demo:       {DEMO_RISK_ACK}\n"
            f"  production: {PRODUCTION_RISK_ACK}\n"
            f"  live run:   {LIVE_LAUNCH_ACK}\n"
            f"  continuous: {CONTINUOUS_ACK}\n"
            f"  kill off:   {KILL_SWITCH_OFF_ACK}\n"
            f"  reset:      {SESSION_RESET_ACK}\n"
            f"  unlock:     {UNLOCK_ACK}"
            f"\n  data purge: {PRIVACY_PURGE_ACK}"
        ),
    )
    cli.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    commands = cli.add_subparsers(dest="command", required=True)
    commands.add_parser("setup", help="create a safe .env and arm the kill switch").set_defaults(func=command_setup)
    verify = commands.add_parser("verify", help="verify integrity, tests, defaults, and dependencies")
    verify_mode = verify.add_mutually_exclusive_group()
    verify_mode.add_argument("--ci", action="store_true", help="also require ruff and pip-audit")
    verify_mode.add_argument(
        "--clean-package",
        action="store_true",
        help="read-only exact-inventory, text-only, and full-tree secret gate for a clean release",
    )
    verify.set_defaults(func=command_verify)
    commands.add_parser("status", help="show redacted safety and session state").set_defaults(func=command_status)
    commands.add_parser("scan", help="read public market data only").set_defaults(func=command_read)
    commands.add_parser("dry-run", help="create and validate order plans without credentials or writes").set_defaults(
        func=command_read
    )
    for name in ("demo-trade", "live"):
        write = commands.add_parser(name, help=f"run one authorized {name} cycle")
        write.add_argument(
            "--continuous", action="store_true", help="repeat until stopped or the 80-contract budget is exhausted"
        )
        write.set_defaults(func=command_write)
    switch = commands.add_parser("kill-switch", help="inspect or change the local hard stop")
    switch.add_argument("action", choices=("status", "on", "off"))
    switch.add_argument("--ack", default="")
    switch.set_defaults(func=command_kill_switch)
    reset = commands.add_parser("reset-session-cap", help="archive and reset the 80-contract ledger")
    reset.add_argument("--ack", required=True)
    reset.set_defaults(func=command_reset)
    unlock_parser = commands.add_parser("unlock", help="remove a stale single-writer lock while trading is disabled")
    unlock_parser.add_argument("--ack", required=True)
    unlock_parser.set_defaults(func=command_unlock)
    purge = commands.add_parser(
        "purge-local-data",
        help="remove logs and settled runtime state while trading remains disabled",
    )
    purge.add_argument("--ack", required=True)
    purge.set_defaults(func=command_purge_local_data)
    return cli


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (SafetyError, EnvError, ValueError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Stopped by user.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
