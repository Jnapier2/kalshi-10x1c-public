"""Self-verifier and release-manifest generator."""

from __future__ import annotations

import ast
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from .constants import (
    ALLOWED_SERIES,
    APPROVED_REST_URLS,
    ATTESTATION_FILENAME,
    BUILD_ID,
    ECONOMIC_BUY_PRICE,
    KILL_SWITCH_FILENAME,
    MANIFEST_FILENAME,
    MAX_CREATE_ORDERS_PER_PROCESS,
    ORDER_COUNT,
    SESSION_CONTRACT_CAP,
)
from .env import SAFE_DEFAULTS, parse_env_text

_DYNAMIC_NAMES = {
    ".env",
    ATTESTATION_FILENAME,
    "TRADING_DISABLED",
    "VERIFICATION_REPORT.md",
    "CLEAN_EXTRACTION_VERIFICATION.txt",
    MANIFEST_FILENAME,
}
_DYNAMIC_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "logs",
    "runtime",
}
_SECRET_SCAN_IGNORED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "venv",
}
_KEY_EXTENSIONS = {".key", ".pem", ".p12", ".pfx", ".jks", ".keystore"}
_CLEAN_FORBIDDEN_DIRS = {
    ".cache",
    ".hypothesis",
    ".ipynb_checkpoints",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "node_modules",
    "venv",
}
_CLEAN_BINARY_EXTENSIONS = {
    ".a",
    ".class",
    ".dll",
    ".dylib",
    ".exe",
    ".lib",
    ".o",
    ".obj",
    ".pyd",
    ".pyc",
    ".pyo",
    ".so",
}
_CLEAN_ARCHIVE_EXTENSIONS = {
    ".7z",
    ".bz2",
    ".egg",
    ".gz",
    ".jar",
    ".rar",
    ".tar",
    ".tgz",
    ".txz",
    ".war",
    ".whl",
    ".xz",
    ".zip",
}
_CLEAN_GENERATED_NAMES = {
    ATTESTATION_FILENAME.casefold(),
    "clean_extraction_verification.txt",
    "verification_report.md",
}
_CLEAN_MAX_FILE_BYTES = 4 * 1024 * 1024
_CLEAN_MAX_TOTAL_BYTES = 32 * 1024 * 1024
_STRICT_PASS_MAX_AGE_SECONDS = 15 * 60
_STRICT_PASSES: dict[str, tuple[str, str, float]] = {}


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    checks: tuple[Check, ...]
    report_path: Path | None


@dataclass(frozen=True)
class TreeSnapshot:
    files: tuple[Path, ...]
    directories: tuple[str, ...]
    unsafe_entries: tuple[str, ...]


def _strict_root_key(root: Path) -> str:
    try:
        return str(root.resolve(strict=True)).casefold()
    except OSError:
        return str(root.absolute()).casefold()


def strict_verification_failures(root: Path) -> list[str]:
    """Require a recent strict PASS produced inside this Python process."""

    key = _strict_root_key(root)
    record = _STRICT_PASSES.get(key)
    if record is None:
        return ["production requires a strict verification PASS in this process"]
    expected_manifest, expected_python, verified_monotonic = record
    manifest = root / MANIFEST_FILENAME
    if not manifest.is_file() or hashlib.sha256(manifest.read_bytes()).hexdigest() != expected_manifest:
        _STRICT_PASSES.pop(key, None)
        return ["release manifest changed after the in-process strict verification"]
    if sys.version.split()[0] != expected_python:
        _STRICT_PASSES.pop(key, None)
        return ["Python runtime changed after the in-process strict verification"]
    if time.monotonic() - verified_monotonic > _STRICT_PASS_MAX_AGE_SECONDS:
        _STRICT_PASSES.pop(key, None)
        return ["in-process strict verification is older than 15 minutes; restart the production command"]
    return []


def _excluded(relative: Path) -> bool:
    if any(part in _DYNAMIC_DIRS for part in relative.parts):
        return True
    return relative.name in _DYNAMIC_NAMES or relative.name.endswith(".zip") or relative.name.endswith(".sha256")


def immutable_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"symlink is not allowed in release tree: {path.relative_to(root)}")
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if not _excluded(relative):
            files.append(path)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generate_manifest(root: Path) -> Path:
    lines = [f"{sha256_file(path)}  {path.relative_to(root).as_posix()}" for path in immutable_files(root)]
    output = root / MANIFEST_FILENAME
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def _parse_manifest(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise ValueError(f"manifest line {number} is malformed")
        digest, name = match.groups()
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or name in entries:
            raise ValueError(f"manifest line {number} has an unsafe or duplicate path")
        entries[name] = digest
    return entries


def _check_manifest(root: Path) -> Check:
    path = root / MANIFEST_FILENAME
    if not path.is_file():
        return Check("Release integrity manifest", "FAIL", "MANIFEST.sha256 is missing")
    try:
        entries = _parse_manifest(path)
        actual = {file.relative_to(root).as_posix(): sha256_file(file) for file in immutable_files(root)}
    except (OSError, ValueError) as exc:
        return Check("Release integrity manifest", "FAIL", str(exc))
    missing = sorted(set(entries) - set(actual))
    extra = sorted(set(actual) - set(entries))
    changed = sorted(name for name in entries.keys() & actual.keys() if entries[name] != actual[name])
    if missing or extra or changed:
        detail = f"missing={missing[:5]}, extra={extra[:5]}, changed={changed[:5]}"
        return Check("Release integrity manifest", "FAIL", detail)
    return Check("Release integrity manifest", "PASS", f"{len(entries)} immutable files matched")


def _snapshot_tree(
    root: Path,
    *,
    skip_directories: frozenset[str] = frozenset(),
) -> TreeSnapshot:
    """Enumerate a tree without following symlinks, junctions, or reparse points."""
    files: list[Path] = []
    directories: list[str] = []
    unsafe: list[str] = []
    pending = [root]
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    while pending:
        directory = pending.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name.casefold())
        except OSError as exc:
            label = "." if directory == root else directory.relative_to(root).as_posix()
            unsafe.append(f"unreadable directory {label} ({type(exc).__name__})")
            continue
        for entry in entries:
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix()
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError as exc:
                unsafe.append(f"unreadable entry {relative} ({type(exc).__name__})")
                continue
            if entry.is_symlink() or (reparse_flag and getattr(metadata, "st_file_attributes", 0) & reparse_flag):
                unsafe.append(f"link or reparse point is not allowed: {relative}")
            elif stat.S_ISDIR(metadata.st_mode):
                if directory == root and entry.name in skip_directories:
                    continue
                directories.append(relative)
                pending.append(path)
            elif stat.S_ISREG(metadata.st_mode):
                files.append(path)
            else:
                unsafe.append(f"special filesystem entry is not allowed: {relative}")
    files.sort(key=lambda path: path.relative_to(root).as_posix())
    return TreeSnapshot(tuple(files), tuple(sorted(directories)), tuple(sorted(unsafe)))


def _parse_file_inventory(root: Path) -> set[str]:
    path = root / "FILE_INVENTORY.txt"
    lines = path.read_text(encoding="utf-8").splitlines()
    headers = [
        (index, re.fullmatch(r"Expected packaged files:\s*(\d+)", line.strip()))
        for index, line in enumerate(lines)
        if line.strip().startswith("Expected packaged files:")
    ]
    if len(headers) != 1 or headers[0][1] is None:
        raise ValueError("FILE_INVENTORY.txt must contain one valid expected-file count")
    header_index, count_match = headers[0]
    assert count_match is not None
    separator = next((index for index in range(header_index + 1, len(lines)) if not lines[index].strip()), None)
    if separator is None:
        raise ValueError("FILE_INVENTORY.txt is missing the file-list separator")
    names = [line.strip() for line in lines[separator + 1 :] if line.strip()]
    expected_count = int(count_match.group(1))
    if len(names) != expected_count:
        raise ValueError(f"FILE_INVENTORY.txt count says {expected_count}, but lists {len(names)} files")

    result: set[str] = set()
    normalized_names: set[str] = set()
    casefolded_names: set[str] = set()
    for number, name in enumerate(names, start=1):
        parts = name.split("/")
        normalized = unicodedata.normalize("NFC", name)
        if (
            not name
            or name.startswith("/")
            or "\\" in name
            or ":" in name
            or any(ord(character) < 32 or ord(character) == 127 for character in name)
            or any(part in {"", ".", ".."} or part.endswith((" ", ".")) for part in parts)
            or PurePosixPath(name).is_absolute()
        ):
            raise ValueError(f"FILE_INVENTORY.txt entry {number} has an unsafe path")
        if name in result or normalized in normalized_names or normalized.casefold() in casefolded_names:
            raise ValueError(f"FILE_INVENTORY.txt entry {number} collides with another path")
        result.add(name)
        normalized_names.add(normalized)
        casefolded_names.add(normalized.casefold())
    return result


def _check_clean_package(root: Path, snapshot: TreeSnapshot | None = None) -> Check:
    """Validate a text-only release tree against the declared package inventory."""
    tree = snapshot or _snapshot_tree(root)
    findings = list(tree.unsafe_entries)
    try:
        expected_files = _parse_file_inventory(root)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        expected_files = set()
        findings.append(str(exc))

    actual_files = {path.relative_to(root).as_posix() for path in tree.files}
    expected_directories: set[str] = set()
    for name in expected_files:
        parts = name.split("/")[:-1]
        for index in range(1, len(parts) + 1):
            expected_directories.add("/".join(parts[:index]))
    actual_directories = set(tree.directories)
    missing = sorted(expected_files - actual_files)
    extra = sorted(actual_files - expected_files)
    missing_directories = sorted(expected_directories - actual_directories)
    extra_directories = sorted(actual_directories - expected_directories)
    if missing:
        findings.append(f"inventory files missing: {missing[:8]}")
    if extra:
        findings.append(f"files outside inventory: {extra[:8]}")
    if missing_directories:
        findings.append(f"inventory directories missing: {missing_directories[:8]}")
    if extra_directories:
        findings.append(f"directories outside inventory: {extra_directories[:8]}")

    try:
        manifest_paths = set(_parse_manifest(root / MANIFEST_FILENAME))
        manifest_dynamic = {MANIFEST_FILENAME, KILL_SWITCH_FILENAME, "logs/.gitkeep", "runtime/.gitkeep"}
        if expected_files and expected_files != manifest_paths | manifest_dynamic:
            findings.append("FILE_INVENTORY.txt does not reconcile with MANIFEST.sha256 and dynamic placeholders")
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        findings.append(f"manifest inventory could not be reconciled: {exc}")

    for directory in tree.directories:
        if any(part.casefold() in _CLEAN_FORBIDDEN_DIRS for part in directory.split("/")):
            findings.append(f"cache or environment directory is packaged: {directory}")

    total_bytes = 0
    binary_magics = (
        b"MZ",
        b"\x7fELF",
        b"PK\x03\x04",
        b"PK\x05\x06",
        b"PK\x07\x08",
        b"\x1f\x8b",
        b"7z\xbc\xaf\x27\x1c",
        b"Rar!\x1a\x07",
        b"%PDF-",
        b"\x89PNG\r\n\x1a\n",
        b"\xff\xd8\xff",
        b"GIF87a",
        b"GIF89a",
        b"SQLite format 3\x00",
    )
    for path in tree.files:
        relative = path.relative_to(root).as_posix()
        lower_relative = relative.casefold()
        lower_name = path.name.casefold()
        suffix = path.suffix.casefold()
        if lower_name.startswith(".env") and relative != ".env.example":
            findings.append(f"environment file is packaged: {relative}")
        if lower_name in _CLEAN_GENERATED_NAMES:
            findings.append(f"generated verification artifact is packaged: {relative}")
        if suffix in _CLEAN_BINARY_EXTENSIONS:
            findings.append(f"bytecode or native binary is packaged: {relative}")
        if suffix in _CLEAN_ARCHIVE_EXTENSIONS or lower_relative.endswith(".tar.gz"):
            findings.append(f"nested archive or package is packaged: {relative}")
        if relative.startswith(("logs/", "runtime/")) and relative not in {
            "logs/.gitkeep",
            "runtime/.gitkeep",
        }:
            findings.append(f"runtime or log content is packaged: {relative}")
        try:
            data = path.read_bytes()
        except OSError as exc:
            findings.append(f"packaged file is unreadable: {relative} ({type(exc).__name__})")
            continue
        total_bytes += len(data)
        if len(data) > _CLEAN_MAX_FILE_BYTES:
            findings.append(f"packaged file exceeds {_CLEAN_MAX_FILE_BYTES} bytes: {relative}")
        if relative in {"logs/.gitkeep", "runtime/.gitkeep"} and data:
            findings.append(f"runtime placeholder must be empty: {relative}")
        if b"\x00" in data or any(data.startswith(magic) for magic in binary_magics):
            findings.append(f"binary content is packaged: {relative}")
            continue
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            findings.append(f"packaged file is not UTF-8 text: {relative}")
    if total_bytes > _CLEAN_MAX_TOTAL_BYTES:
        findings.append(f"package exceeds {_CLEAN_MAX_TOTAL_BYTES} total bytes")

    if findings:
        return Check("Clean package layout", "FAIL", "; ".join(dict.fromkeys(findings))[:4000])
    return Check(
        "Clean package layout",
        "PASS",
        f"exactly {len(actual_files)} declared UTF-8 text files and only expected directories are present",
    )


def _placeholder_credential_value(raw: str) -> bool:
    value = raw.strip().rstrip(",").strip().strip("\"'").strip()
    upper = value.upper()
    return (
        not value
        or (value.startswith("<") and value.endswith(">"))
        or upper.startswith("YOUR_")
        or upper in {"PLACEHOLDER", "REDACTED", "CHANGEME"}
        or value.startswith("/absolute/path/")
        or value == "11111111-2222-3333-4444-555555555555"
        or bool(re.fullmatch(r"0+", value.replace("-", "")))
    )


def _check_secrets(
    root: Path,
    *,
    snapshot: TreeSnapshot | None = None,
    package_mode: bool = False,
) -> Check:
    """Scan regular files outside explicitly excluded root-level development directories."""
    tree = snapshot or _snapshot_tree(
        root,
        skip_directories=frozenset(_SECRET_SCAN_IGNORED_DIRS),
    )
    findings = list(tree.unsafe_entries)
    private_key_header = re.compile(
        br"-----BEGIN (?:ENCRYPTED |RSA |DSA |EC |OPENSSH |PGP )?PRIVATE KEY(?: BLOCK)?-----"
    )
    env_assignment = re.compile(
        r"^\s*([A-Z][A-Z0-9_]*"
        r"(?:(?:API|ACCESS|PRIVATE)_?KEY|CLIENT_?SECRET|SECRET|TOKEN|PASSWORD|CREDENTIAL)"
        r"[A-Z0-9_]*)\s*=\s*(.*?)\s*$"
    )
    structured_assignment = re.compile(
        r"^\s*(?:[\"']([^\"']+)[\"']|"
        r"(api[_-]?key|access[_-]?key|client[_-]?secret|private[_-]?key|secret|token|password|credential))"
        r"\s*[:=]\s*(.*?)\s*$",
        re.IGNORECASE,
    )
    provider_patterns = {
        "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
        "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
        "OpenAI-style token": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
        "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
        "JWT": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    }
    credential_terms = re.compile(
        r"(?:api[_-]?key|access[_-]?key|client[_-]?secret|private[_-]?key|secret|token|password|credential)",
        re.IGNORECASE,
    )
    root_env_exemptions = {"KALSHI_API_KEY_ID", "KALSHI_PRIVATE_KEY_PATH"}
    putty_private_marker = b"PuTTY-" + b"User-Key-File-"
    age_private_marker = b"AGE-SECRET-" + b"KEY-1"
    for path in tree.files:
        relative = path.relative_to(root).as_posix()
        lower_name = path.name.casefold()
        if path.suffix.casefold() in _KEY_EXTENSIONS or lower_name in {
            "id_dsa",
            "id_ecdsa",
            "id_ed25519",
            "id_rsa",
        }:
            findings.append(f"private-key-like file: {relative}")
        try:
            data = path.read_bytes()
        except OSError as exc:
            findings.append(f"unreadable file during secret scan: {relative} ({type(exc).__name__})")
            continue
        if b"\x00" not in data and (
            private_key_header.search(data) or putty_private_marker in data or age_private_marker in data
        ):
            findings.append(f"embedded private-key material: {relative}")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            env_match = env_assignment.match(line)
            structured_match = structured_assignment.match(line)
            key = ""
            value = ""
            if env_match:
                key, value = env_match.groups()
            elif structured_match:
                quoted_key, plain_key, value = structured_match.groups()
                key = quoted_key or plain_key or ""
                if not credential_terms.search(key):
                    key = ""
                elif path.suffix.casefold() in {".py", ".pyi"} and not value.lstrip().startswith(("\"", "'")):
                    # In Python source, only literal credential values are findings;
                    # annotations and runtime expressions are not embedded secrets.
                    key = ""
            if (
                key
                and not _placeholder_credential_value(value)
                and not (
                    not package_mode
                    and relative == ".env"
                    and key.upper().replace("-", "_") in root_env_exemptions
                )
            ):
                findings.append(f"credential-like assignment: {relative}:{line_number}")
            for category, pattern in provider_patterns.items():
                if pattern.search(line):
                    findings.append(f"{category} pattern: {relative}:{line_number}")
    if findings:
        return Check("Secret and private-key scan", "FAIL", "; ".join(dict.fromkeys(findings))[:4000])
    return Check(
        "Secret and private-key scan",
        "PASS",
        "all regular files outside root-level development/cache directories were scanned "
        "without finding private keys or credential-like values",
    )


def _call_name(node: ast.Call) -> str:
    target = node.func
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        parts: list[str] = [target.attr]
        value = target.value
        while isinstance(value, ast.Attribute):
            parts.append(value.attr)
            value = value.value
        if isinstance(value, ast.Name):
            parts.append(value.id)
        return ".".join(reversed(parts))
    return ""


def _check_python_safety(root: Path) -> Check:
    findings: list[str] = []
    forbidden_calls = {"eval", "exec", "os.system", "pickle.load", "pickle.loads", "marshal.load", "marshal.loads"}
    runtime_files = [root / "run_bot.py", *sorted((root / "kalshi_public").glob("*.py"))]
    for path in runtime_files:
        if not path.is_file():
            findings.append(f"missing runtime source: {path.name}")
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError) as exc:
            findings.append(f"could not parse {path.relative_to(root)}: {exc}")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            if name in forbidden_calls:
                findings.append(f"{path.relative_to(root)}:{node.lineno} uses {name}")
            for keyword in node.keywords:
                if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                    findings.append(f"{path.relative_to(root)}:{node.lineno} uses shell=True")
                if keyword.arg == "verify" and isinstance(keyword.value, ast.Constant) and keyword.value.value is False:
                    findings.append(f"{path.relative_to(root)}:{node.lineno} disables TLS verification")
    if findings:
        return Check("Dangerous-code scan", "FAIL", "; ".join(findings[:12]))
    return Check(
        "Dangerous-code scan", "PASS", "no eval/exec, shell execution, unsafe deserialization, or disabled TLS found"
    )


def _check_network_origins(root: Path) -> Check:
    findings: list[str] = []
    url_re = re.compile(r"https?://[^\s\"']+")
    approved = tuple(urlparse(base) for base in APPROVED_REST_URLS)
    for path in [root / "run_bot.py", *sorted((root / "kalshi_public").glob("*.py"))]:
        text = path.read_text(encoding="utf-8")
        for url in url_re.findall(text):
            cleaned = url.rstrip(").,;]")
            parsed = urlparse(cleaned)
            allowed = any(
                parsed.scheme == base.scheme
                and parsed.netloc == base.netloc
                and (parsed.path == base.path or parsed.path.startswith(base.path + "/"))
                for base in approved
            )
            if not allowed:
                findings.append(f"{path.relative_to(root)} contains unapproved origin {cleaned}")
    batch_route = "/portfolio/events/orders/" + "batched"
    if batch_route in "\n".join(
        path.read_text(encoding="utf-8")
        for path in [root / "run_bot.py", *sorted((root / "kalshi_public").glob("*.py"))]
    ):
        findings.append("batch order route is present in runtime source")
    if findings:
        return Check("Network-origin and route allowlist", "FAIL", "; ".join(findings[:10]))
    return Check(
        "Network-origin and route allowlist",
        "PASS",
        "Python network origins are Kalshi-only; no batch mutation route exists",
    )


def _check_defaults(root: Path) -> Check:
    failures: list[str] = []
    expected = {
        "PUBLIC_RUN_MODE": "dry-run",
        "PUBLIC_ORDER_WRITES_ENABLED": "0",
        "LIVE_TRADING": "0",
        "DRY_RUN": "1",
        "KALSHI_DRY_RUN": "1",
        "PAPER_MODE": "1",
        "PAPER_TRADE": "1",
        "SIMULATION_MODE": "1",
        "ALLOW_PRODUCTION_TRADING": "0",
    }
    for key, value in expected.items():
        if SAFE_DEFAULTS.get(key) != value:
            failures.append(f"internal safe default mismatch for {key}")
    switch_path = root / KILL_SWITCH_FILENAME
    if switch_path.is_symlink() or not switch_path.is_file():
        failures.append("tracked TRADING_DISABLED kill switch is missing or unsafe")
    example_path = root / ".env.example"
    if not example_path.is_file():
        failures.append(".env.example is missing")
    else:
        try:
            parsed, unknown = parse_env_text(example_path.read_text(encoding="utf-8"))
            for key, value in expected.items():
                if parsed.get(key) != value:
                    failures.append(f".env.example {key} must be {value}")
            if unknown:
                failures.append(".env.example contains unsupported keys: " + ", ".join(unknown))
            if parsed.get("KALSHI_API_KEY_ID", ""):
                failures.append(".env.example contains a nonblank API key ID")
            if parsed.get("KALSHI_PRIVATE_KEY_PATH", ""):
                failures.append(".env.example contains a nonblank private-key path")
        except Exception as exc:
            failures.append(f".env.example could not be parsed: {exc}")
    if failures:
        return Check("Dry-run defaults", "FAIL", "; ".join(failures))
    return Check(
        "Dry-run defaults",
        "PASS",
        "internal defaults, .env.example, and tracked kill switch are write-disabled",
    )


def _check_invariants() -> Check:
    failures: list[str] = []
    if ORDER_COUNT != 10:
        failures.append("ORDER_COUNT is not 10")
    if Decimal("0.01") != ECONOMIC_BUY_PRICE:
        failures.append("economic buy price is not 1c")
    if SESSION_CONTRACT_CAP != 80:
        failures.append("session cap is not 80")
    if MAX_CREATE_ORDERS_PER_PROCESS != 8:
        failures.append("process order limit is not 8")
    if len(ALLOWED_SERIES) != 8 or len(set(ALLOWED_SERIES)) != 8:
        failures.append("approved series allowlist is not the expected eight unique entries")
    if failures:
        return Check("Immutable 10x1c profile", "FAIL", "; ".join(failures))
    return Check(
        "Immutable 10x1c profile", "PASS", "10 contracts, 1c, 80-contract session cap, eight-order process cap"
    )


def _requirements(root: Path) -> dict[str, str]:
    path = root / "requirements.txt"
    requirements: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+-]+)", line)
        if not match:
            raise ValueError(f"requirements.txt line {number} is not an exact pin")
        requirements[match.group(1).lower()] = match.group(2)
    return requirements


def _check_dependencies(root: Path) -> Check:
    try:
        requirements = _requirements(root)
    except (OSError, ValueError) as exc:
        return Check("Pinned dependencies", "FAIL", str(exc))
    mismatches: list[str] = []
    for package, expected in requirements.items():
        try:
            installed = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            mismatches.append(f"{package} is not installed")
            continue
        if installed != expected:
            mismatches.append(f"{package} installed={installed}, required={expected}")
    if mismatches:
        return Check("Pinned dependencies", "FAIL", "; ".join(mismatches))
    return Check("Pinned dependencies", "PASS", f"{len(requirements)} exact runtime pins are installed")


def _run_command(name: str, argv: list[str], root: Path, *, required: bool = True) -> Check:
    try:
        completed = subprocess.run(
            argv,
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=180,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(root)},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check(name, "FAIL" if required else "WARN", f"command could not complete: {type(exc).__name__}")
    output = "\n".join(completed.stdout.splitlines()[-12:]).strip()
    if completed.returncode != 0:
        return Check(name, "FAIL" if required else "WARN", output or f"exit code {completed.returncode}")
    return Check(name, "PASS", output or "completed successfully")


def _check_compile(root: Path) -> Check:
    failures: list[str] = []
    for path in [
        root / "run_bot.py",
        *sorted((root / "kalshi_public").glob("*.py")),
        *sorted((root / "scripts").glob("*.py")),
        *sorted((root / "tests").glob("*.py")),
    ]:
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            failures.append(f"{path.relative_to(root)}: {exc}")
    if failures:
        return Check("Python compilation", "FAIL", "; ".join(failures[:8]))
    return Check("Python compilation", "PASS", "all Python files compile in memory")


def _write_report(root: Path, checks: list[Check], passed: bool, *, ci: bool) -> Path:
    report = root / "VERIFICATION_REPORT.md"
    lines = [
        "# Verification Report",
        "",
        f"- Build: `{BUILD_ID}`",
        f"- Verified UTC: `{datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}`",
        f"- Mode: `{'CI/strict' if ci else 'standard'}`",
        f"- Result: **{'PASS' if passed else 'FAIL'}**",
        "",
        "| Check | Result | Detail |",
        "|---|---:|---|",
    ]
    for check in checks:
        detail = " ".join(check.detail.replace("|", "\\|").split())
        lines.append(f"| {check.name} | **{check.status}** | {detail} |")
    lines.extend(
        [
            "",
            (
                "A PASS is evidence that the packaged controls and tests behaved as designed at verification time. "
                "It is not a warranty, penetration test, profitability finding, or permission to trade."
            ),
        ]
    )
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def verify_release(root: Path, *, ci: bool = False, clean_package: bool = False) -> VerificationResult:
    if ci and clean_package:
        raise ValueError("--ci and --clean-package are mutually exclusive")
    if clean_package:
        snapshot = _snapshot_tree(root)
        checks = [
            _check_clean_package(root, snapshot),
            _check_manifest(root),
            _check_secrets(root, snapshot=snapshot, package_mode=True),
        ]
        passed = not any(check.status == "FAIL" for check in checks)
        return VerificationResult(passed, tuple(checks), None)

    strict_key = _strict_root_key(root)
    if not ci:
        _STRICT_PASSES.pop(strict_key, None)

    checks: list[Check] = []
    checks.append(Check("Python version", "PASS" if sys.version_info >= (3, 10) else "FAIL", sys.version.split()[0]))
    checks.extend(
        [
            _check_manifest(root),
            _check_secrets(root),
            _check_python_safety(root),
            _check_network_origins(root),
            _check_defaults(root),
            _check_invariants(),
            _check_dependencies(root),
            _check_compile(root),
        ]
    )
    checks.append(
        _run_command(
            "Unit and security regression tests",
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
            root,
        )
    )
    checks.append(_run_command("Dependency consistency", [sys.executable, "-m", "pip", "check"], root))

    if importlib.util.find_spec("ruff") is not None:
        checks.append(
            _run_command(
                "Ruff static analysis",
                [
                    sys.executable,
                    "-m",
                    "ruff",
                    "check",
                    "--no-cache",
                    "run_bot.py",
                    "kalshi_public",
                    "scripts",
                    "tests",
                ],
                root,
            )
        )
    else:
        checks.append(
            Check(
                "Ruff static analysis", "FAIL" if ci else "WARN", "ruff is not installed; install requirements-dev.txt"
            )
        )

    if ci:
        if importlib.util.find_spec("pip_audit") is not None:
            checks.append(
                _run_command(
                    "Known-vulnerability audit",
                    [sys.executable, "-m", "pip_audit", "-r", "requirements.txt", "--progress-spinner", "off"],
                    root,
                )
            )
        else:
            checks.append(Check("Known-vulnerability audit", "FAIL", "pip-audit is not installed"))
    else:
        checks.append(Check("Known-vulnerability audit", "WARN", "not run in standard mode; use verify --ci"))

    passed = not any(check.status == "FAIL" for check in checks)
    report = _write_report(root, checks, passed, ci=ci)
    if passed:
        attestation = {
            "schema_version": 1,
            "build_id": BUILD_ID,
            "result": "PASS",
            "verified_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "manifest_digest": hashlib.sha256((root / MANIFEST_FILENAME).read_bytes()).hexdigest(),
            "python": sys.version.split()[0],
            "ci": ci,
            "checks": len(checks),
        }
        (root / ATTESTATION_FILENAME).write_text(
            json.dumps(attestation, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if os.name != "nt":
            (root / ATTESTATION_FILENAME).chmod(0o600)
        if ci:
            _STRICT_PASSES[strict_key] = (
                hashlib.sha256((root / MANIFEST_FILENAME).read_bytes()).hexdigest(),
                sys.version.split()[0],
                time.monotonic(),
            )
    else:
        _STRICT_PASSES.pop(strict_key, None)
        (root / ATTESTATION_FILENAME).unlink(missing_ok=True)
    return VerificationResult(passed, tuple(checks), report)
