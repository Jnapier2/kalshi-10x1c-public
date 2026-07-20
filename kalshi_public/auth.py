"""Credential validation and Kalshi RSA-PSS request signing."""

from __future__ import annotations

import base64
import json
import os
import stat
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


@dataclass(frozen=True)
class CredentialStatus:
    ok: bool
    failures: tuple[str, ...]
    warnings: tuple[str, ...]
    key_id_present: bool
    key_filename: str


@dataclass(frozen=True)
class Credentials:
    api_key_id: str
    private_key: rsa.RSAPrivateKey
    key_path: Path

    def sign(self, timestamp_ms: str, method: str, path_without_query: str) -> str:
        message = f"{timestamp_ms}{method.upper()}{path_without_query}".encode()
        signature = self.private_key.sign(
            message,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("ascii")


def _windows_acl_failures(path: Path) -> list[str]:
    """Return fail-closed findings for a private key's NTFS access rules.

    PowerShell is invoked without a shell, with a fully encoded script and a
    fixed System32 executable. Only SIDs and numeric access masks are returned;
    the key path and key contents are never printed.
    """

    script = """
$ErrorActionPreference = 'Stop'
$sidType = [System.Security.Principal.SecurityIdentifier]
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$acl = Get-Acl -LiteralPath $env:KALSHI_ACL_TARGET
try {
    $ownerSid = ([System.Security.Principal.NTAccount]$acl.Owner).Translate($sidType).Value
} catch {
    $ownerSid = ([System.Security.Principal.SecurityIdentifier]$acl.Owner).Value
}
$rules = @($acl.Access | ForEach-Object {
    [PSCustomObject]@{
        Sid = $_.IdentityReference.Translate($sidType).Value
        Type = $_.AccessControlType.ToString()
        Rights = [int64]$_.FileSystemRights
        Inherited = [bool]$_.IsInherited
    }
})
[PSCustomObject]@{
    CurrentSid = $identity.User.Value
    OwnerSid = $ownerSid
    Rules = $rules
} | ConvertTo-Json -Compress -Depth 4
""".strip()
    powershell = (
        Path(os.environ.get("SYSTEMROOT", r"C:\Windows"))
        / "System32"
        / "WindowsPowerShell"
        / "v1.0"
        / "powershell.exe"
    )
    if not powershell.is_file():
        return ["Windows ACL verification is unavailable because System32 PowerShell was not found"]
    try:
        probe_env = dict(os.environ)
        probe_env["KALSHI_ACL_TARGET"] = str(path)
        completed = subprocess.run(
            [str(powershell), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            env=probe_env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [f"Windows ACL verification could not complete ({type(exc).__name__})"]
    if completed.returncode != 0:
        return ["Windows ACL verification did not complete successfully"]
    try:
        data = json.loads(completed.stdout.strip())
        current_sid = str(data["CurrentSid"])
        owner_sid = str(data["OwnerSid"])
        raw_rules = data.get("Rules", [])
        rules = raw_rules if isinstance(raw_rules, list) else [raw_rules]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return ["Windows ACL verification returned an unexpected result"]

    administrators_sid = "S-1-5-32-544"
    allowed_sids = {current_sid, "S-1-5-18", administrators_sid}
    failures: list[str] = []
    if owner_sid not in {current_sid, administrators_sid}:
        failures.append("the private-key file must be owned by the current user or local Administrators")
    current_user_has_access = False
    broad_access = False
    for rule in rules:
        if not isinstance(rule, dict) or str(rule.get("Type", "")) != "Allow":
            continue
        sid = str(rule.get("Sid", ""))
        try:
            rights = int(rule.get("Rights", 0))
        except (TypeError, ValueError):
            broad_access = True
            continue
        if rights == 0:
            continue
        if sid == current_sid:
            current_user_has_access = True
        elif sid not in allowed_sids:
            broad_access = True
    if not current_user_has_access:
        failures.append("the private-key ACL does not grant the current user access")
    if broad_access:
        failures.append("the private-key ACL grants access to a broader Windows principal")
    return failures


def _inside(path: Path, parent: Path) -> bool:
    try:
        resolved = path.resolve(strict=False)
        base = parent.resolve(strict=False)
        return resolved == base or base in resolved.parents
    except OSError:
        return True


def credential_status(values: Mapping[str, str], root: Path) -> CredentialStatus:
    failures: list[str] = []
    warnings: list[str] = []
    key_id = str(values.get("KALSHI_API_KEY_ID", "")).strip()
    raw_path = str(values.get("KALSHI_PRIVATE_KEY_PATH", "")).strip()
    filename = ""
    if not key_id:
        failures.append("KALSHI_API_KEY_ID is blank")
    elif len(key_id) > 128 or any(character.isspace() or ord(character) < 32 for character in key_id):
        failures.append("KALSHI_API_KEY_ID contains whitespace/control characters or is too long")
    if not raw_path:
        failures.append("KALSHI_PRIVATE_KEY_PATH is blank")
        return CredentialStatus(False, tuple(failures), tuple(warnings), bool(key_id), filename)

    key_path = Path(raw_path).expanduser()
    filename = key_path.name
    if not key_path.is_absolute():
        failures.append("KALSHI_PRIVATE_KEY_PATH must be an absolute path")
    if _inside(key_path, root):
        failures.append("the private key must be stored outside the repository")
    if key_path.is_symlink():
        failures.append("private-key symlinks are not accepted")
    if not key_path.exists():
        failures.append("the private-key file does not exist")
    elif not key_path.is_file():
        failures.append("the private-key path is not a regular file")
    else:
        if os.name != "nt":
            metadata = key_path.stat()
            mode = stat.S_IMODE(metadata.st_mode)
            if mode & 0o077:
                failures.append(f"private-key permissions are too broad ({oct(mode)}); use chmod 600")
            if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
                failures.append("the private-key file is not owned by the current user")
        else:
            failures.extend(_windows_acl_failures(key_path))
        if key_path.stat().st_size > 64 * 1024:
            failures.append("the private-key file exceeds the 64 KiB public-edition limit")
        try:
            key: Any = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
            if not isinstance(key, rsa.RSAPrivateKey):
                failures.append("the private key is not an RSA private key")
            elif key.key_size < 2048:
                failures.append("the RSA private key must be at least 2048 bits")
        except Exception as exc:  # Do not expose key contents or parser details.
            failures.append(f"the private key is not a readable unencrypted PEM RSA key ({type(exc).__name__})")
    return CredentialStatus(not failures, tuple(failures), tuple(warnings), bool(key_id), filename)


def load_credentials(values: Mapping[str, str], root: Path) -> Credentials:
    status = credential_status(values, root)
    if not status.ok:
        raise ValueError("Credential validation failed: " + "; ".join(status.failures))
    key_path = Path(str(values["KALSHI_PRIVATE_KEY_PATH"])).expanduser().resolve(strict=True)
    key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError("Private key is not RSA")
    return Credentials(str(values["KALSHI_API_KEY_ID"]).strip(), key, key_path)
