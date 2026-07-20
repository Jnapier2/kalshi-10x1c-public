"""Local-data inventory and fail-closed cleanup for the public edition."""

from __future__ import annotations

import os
from pathlib import Path

from .constants import LOCK_RELATIVE_PATH, PRIVACY_PURGE_ACK
from .ledger import status
from .safety import SafetyError, kill_switch_is_on


def _purge_directory(directory: Path) -> int:
    """Remove regular descendants without following links; keep `.gitkeep`."""

    if directory.is_symlink():
        raise SafetyError(f"refusing to clean symlinked local-data directory: {directory.name}")
    directory.mkdir(exist_ok=True)
    if not directory.is_dir():
        raise SafetyError(f"local-data path is not a directory: {directory.name}")

    removed = 0

    def visit(current: Path) -> None:
        nonlocal removed
        entries = list(os.scandir(current))
        for entry in entries:
            child = Path(entry.path)
            if entry.is_symlink():
                raise SafetyError(f"refusing to clean symlinked local-data entry: {child.name}")
            if entry.is_dir(follow_symlinks=False):
                visit(child)
                child.rmdir()
            elif entry.is_file(follow_symlinks=False):
                if child.name == ".gitkeep" and child.parent == directory:
                    continue
                child.unlink()
                removed += 1
            else:
                raise SafetyError(f"refusing to clean unsupported local-data entry: {child.name}")

    visit(directory)
    return removed


def purge_local_data(root: Path, ack: str) -> dict[str, int]:
    """Delete logs and settled runtime state while preserving uncertain evidence."""

    if ack != PRIVACY_PURGE_ACK:
        raise SafetyError(f"exact acknowledgement required: {PRIVACY_PURGE_ACK}")
    if not kill_switch_is_on(root):
        raise SafetyError("local-data cleanup requires TRADING_DISABLED to remain on")
    lock_path = root / LOCK_RELATIVE_PATH
    if lock_path.exists() or lock_path.is_symlink():
        raise SafetyError("local-data cleanup requires every bot process to be stopped and the instance lock cleared")
    ledger = status(root)
    if ledger["reserved_contracts"] > 0:
        raise SafetyError(
            "local-data cleanup is blocked while a submission is reserved or ambiguous; "
            "reconcile the official account and preserve evidence"
        )
    return {
        "logs": _purge_directory(root / "logs"),
        "runtime": _purge_directory(root / "runtime"),
    }
