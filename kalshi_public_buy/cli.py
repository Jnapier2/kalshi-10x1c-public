from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from kalshi_public_buy import __version__
from kalshi_public_buy.planner import plan_buy
from scripts.verify_release import verify_project

MAX_INPUT_BYTES = 1_000_000


def _load_snapshot(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError('input_must_be_regular_file')
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError('input_too_large')
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('input_must_be_json_object')
    return data


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Offline exact-10x1c Kalshi planning preview; no network or live writes.'
    )
    parser.add_argument('snapshot', nargs='?', type=Path)
    parser.add_argument('--version', action='store_true')
    args = parser.parse_args(argv)

    if args.version:
        print(__version__)
        return 0
    if args.snapshot is None:
        parser.error('snapshot is required unless --version is used')

    ok, errors = verify_project()
    if not ok:
        print(json.dumps({'decision': 'INVALID', 'reason_codes': errors}, indent=2))
        return 2
    try:
        snapshot = _load_snapshot(args.snapshot)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({'decision': 'INVALID', 'reason_codes': [str(exc)]}, indent=2))
        return 2

    result = plan_buy(snapshot)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['decision'] == 'PLAN' else 1
