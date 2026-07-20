from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from kalshi_public.constants import (
    ATTESTATION_FILENAME,
    BUILD_ID,
    CONTINUOUS_ACK,
    DEMO_RISK_ACK,
    PRODUCTION_RISK_ACK,
)
from kalshi_public.env import SAFE_DEFAULTS, RuntimeSettings
from kalshi_public.verify import generate_manifest


class TempPublicRoot:
    def __init__(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / "repo"
        self.root.mkdir()
        self.key_dir = self.base / "keys"
        self.key_dir.mkdir()
        self.key_path = self.key_dir / "kalshi-private.key"
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.private_key = key
        self.key_path.write_bytes(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        if os.name != "nt":
            self.key_path.chmod(0o600)
        self.fixture_path = self.root / "fixture.txt"
        self.fixture_path.write_text("verified fixture\n", encoding="utf-8")
        manifest = generate_manifest(self.root)
        digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
        (self.root / ATTESTATION_FILENAME).write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "build_id": BUILD_ID,
                    "result": "PASS",
                    "manifest_digest": digest,
                    "verified_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "ci": True,
                }
            ),
            encoding="utf-8",
        )
        if os.name != "nt":
            (self.root / ATTESTATION_FILENAME).chmod(0o600)

    def settings(self, mode: str = "demo-trade", *, continuous: bool = False) -> RuntimeSettings:
        values = dict(SAFE_DEFAULTS)
        values.update(
            {
                "PUBLIC_RUN_MODE": mode,
                "PUBLIC_ORDER_WRITES_ENABLED": "1",
                "LIVE_TRADING": "1",
                "DRY_RUN": "0",
                "KALSHI_DRY_RUN": "0",
                "PAPER_MODE": "0",
                "PAPER_TRADE": "0",
                "SIMULATION_MODE": "0",
                "ALLOW_PRODUCTION_TRADING": "1" if mode == "live" else "0",
                "PUBLIC_RISK_ACK": PRODUCTION_RISK_ACK if mode == "live" else DEMO_RISK_ACK,
                "PUBLIC_CONTINUOUS_ACK": CONTINUOUS_ACK if continuous else "",
                "KALSHI_API_KEY_ID": "11111111-2222-3333-4444-555555555555",
                "KALSHI_PRIVATE_KEY_PATH": str(self.key_path),
            }
        )
        env_lines = [f"{key}={value}" for key, value in values.items()]
        env_path = self.root / ".env"
        env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")
        if os.name != "nt":
            env_path.chmod(0o600)
        return RuntimeSettings(values=values, source_exists=True, unknown_keys=())

    def expire_attestation(self) -> None:
        path = self.root / ATTESTATION_FILENAME
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        data["verified_utc"] = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat().replace("+00:00", "Z")
        path.write_text(json.dumps(data), encoding="utf-8")

    def set_attestation_ci(self, value: bool) -> None:
        path = self.root / ATTESTATION_FILENAME
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        data["ci"] = value
        path.write_text(json.dumps(data), encoding="utf-8")

    def close(self) -> None:
        self.temp.cleanup()
