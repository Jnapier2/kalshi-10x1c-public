"""Fail-closed single-writer process lock."""

from __future__ import annotations

import json
import os
import socket
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .constants import LOCK_RELATIVE_PATH
from .safety import SafetyError, require_unlock


class InstanceLock:
    def __init__(self, root: Path) -> None:
        self.path = root / LOCK_RELATIVE_PATH
        self.token = str(uuid.uuid4())
        self.acquired = False

    def __enter__(self) -> InstanceLock:
        if self.path.parent.is_symlink():
            raise SafetyError("runtime lock directory must not be a symlink")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.parent.is_symlink() or not self.path.parent.is_dir():
            raise SafetyError("runtime lock directory is unsafe")
        if self.path.is_symlink():
            raise SafetyError("live-instance lock must not be a symlink")
        record = {
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "started_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "token": self.token,
        }
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(self.path, flags, 0o600)
        except FileExistsError as exc:
            raise SafetyError(
                "another live writer may be running, or a stale lock exists; "
                "turn on the kill switch, confirm no bot process is active, then use run_bot.py unlock"
            ) from exc
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.acquired = True
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if not self.acquired:
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data.get("token") == self.token:
                self.path.unlink(missing_ok=True)
        except (OSError, json.JSONDecodeError):
            # Fail closed: leave an uncertain lock for explicit operator review.
            pass
        self.acquired = False


def unlock(root: Path, ack: str) -> None:
    require_unlock(root, ack)
    path = root / LOCK_RELATIVE_PATH
    if path.parent.is_symlink():
        raise SafetyError("runtime lock directory must not be a symlink")
    path.unlink(missing_ok=True)
