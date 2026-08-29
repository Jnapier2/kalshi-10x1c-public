from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {'.bat', '.json', '.md', '.py', '.txt', '.yml', '.yaml'}
TEXT_NAMES = {'LICENSE', 'TRADING_DISABLED'}


def canonical_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    if path.suffix.lower() in TEXT_SUFFIXES or path.name in TEXT_NAMES:
        text = data.decode('utf-8', errors='strict')
        return text.replace('\r\n', '\n').replace('\r', '\n').encode('utf-8')
    return data


def verify_project(root: Path = ROOT) -> tuple[bool, list[str]]:
    errors: list[str] = []
    manifest_path = root / 'MANIFEST.json'
    metadata_path = root / 'PACKAGE_METADATA.json'
    version_path = root / 'VERSION.txt'
    disabled_path = root / 'TRADING_DISABLED'

    for required in (manifest_path, metadata_path, version_path, disabled_path):
        if not required.is_file() or required.is_symlink():
            errors.append(f'missing_or_unsafe:{required.name}')
    if errors:
        return False, errors

    try:
        manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding='utf-8'))
        metadata: dict[str, Any] = json.loads(metadata_path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return False, [f'metadata_parse_error:{type(exc).__name__}']

    version = version_path.read_text(encoding='utf-8').strip()
    expected_pairs = (
        ('version', manifest.get('version'), version),
        ('metadata_version', metadata.get('display_version'), version),
        ('package_id', manifest.get('package_id'), metadata.get('package_id')),
        ('project', manifest.get('project'), metadata.get('project')),
        ('build_id', manifest.get('build_id'), metadata.get('build_id')),
        ('execution_namespace', manifest.get('execution_namespace'), metadata.get('execution_namespace')),
        ('canonical_entrypoint', manifest.get('canonical_entrypoint'), metadata.get('canonical_entrypoint')),
    )
    for label, observed, expected in expected_pairs:
        if observed != expected:
            errors.append(f'{label}_mismatch')

    if manifest.get('schema_version') != 'gateway-public-manifest-v1.2':
        errors.append('manifest_schema_mismatch')
    if metadata.get('schema_version') != 'gateway-public-package-v1':
        errors.append('metadata_schema_mismatch')
    if metadata.get('backend_target') != metadata.get('canonical_entrypoint'):
        errors.append('backend_target_mismatch')
    aliases = metadata.get('approved_entrypoint_aliases')
    if not isinstance(aliases, list) or aliases != [metadata.get('windows_convenience_shim')]:
        errors.append('entrypoint_alias_contract_mismatch')
    if metadata.get('network_access') is not False:
        errors.append('network_boundary_mismatch')
    if metadata.get('credential_support') is not False:
        errors.append('credential_boundary_mismatch')
    if metadata.get('live_write_capability') is not False:
        errors.append('mutation_boundary_mismatch')
    if metadata.get('execution_mode') != 'offline-read-only':
        errors.append('execution_mode_mismatch')
    output_policy = metadata.get('output_policy')
    if not isinstance(output_policy, dict) or output_policy.get('implicit_filesystem_writes') is not False:
        errors.append('output_policy_mismatch')

    canonical_entrypoint = metadata.get('canonical_entrypoint')
    launcher = metadata.get('windows_convenience_shim')
    for rel in (canonical_entrypoint, launcher):
        if not isinstance(rel, str):
            errors.append('entrypoint_invalid')
            continue
        target = root / rel
        if not target.is_file() or target.is_symlink():
            errors.append(f'missing_or_unsafe_entrypoint:{rel}')

    entries = manifest.get('files')
    if not isinstance(entries, list):
        return False, errors + ['manifest_files_invalid']
    if manifest.get('file_count') != len(entries):
        errors.append('manifest_file_count_mismatch')

    seen: set[str] = set()
    casefolded: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append('manifest_entry_invalid')
            continue
        if entry.get('package_managed') is not True:
            errors.append('unmanaged_manifest_entry')
            continue
        rel = entry.get('path')
        if not isinstance(rel, str):
            errors.append('manifest_path_invalid')
            continue
        pure = PurePosixPath(rel)
        if pure.is_absolute() or '..' in pure.parts or '\\' in rel:
            errors.append(f'unsafe_path:{rel}')
            continue
        if rel in seen:
            errors.append(f'duplicate_path:{rel}')
            continue
        seen.add(rel)
        folded = rel.casefold()
        if folded in casefolded:
            errors.append(f'case_collision:{rel}')
            continue
        casefolded.add(folded)

        target = root.joinpath(*pure.parts)
        try:
            resolved = target.resolve(strict=True)
        except OSError:
            errors.append(f'missing:{rel}')
            continue
        if root.resolve() not in resolved.parents:
            errors.append(f'outside_root:{rel}')
            continue
        if target.is_symlink() or not target.is_file():
            errors.append(f'unsafe_file:{rel}')
            continue
        try:
            data = canonical_bytes(target)
        except (OSError, UnicodeError) as exc:
            errors.append(f'read_error:{rel}:{type(exc).__name__}')
            continue
        if len(data) != entry.get('canonical_size'):
            errors.append(f'size_mismatch:{rel}')
        digest = hashlib.sha256(data).hexdigest()
        if digest != entry.get('sha256'):
            errors.append(f'hash_mismatch:{rel}')

    required_managed = {
        'PACKAGE_METADATA.json', 'SBOM.cdx.json', 'VERSION.txt', 'TRADING_DISABLED',
        str(metadata.get('canonical_entrypoint')), str(metadata.get('windows_convenience_shim')),
    }
    missing_managed = sorted(required_managed - seen)
    errors.extend(f'missing_managed_contract:{item}' for item in missing_managed)

    return not errors, errors


def main() -> int:
    ok, errors = verify_project()
    if ok:
        print('PUBLIC_RELEASE_IDENTITY: PASS')
        return 0
    print('PUBLIC_RELEASE_IDENTITY: FAIL')
    for error in errors:
        print(error)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
