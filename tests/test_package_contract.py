from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PackageContractTests(unittest.TestCase):
    def test_identity_and_manifest_agree(self) -> None:
        version = (ROOT / 'VERSION.txt').read_text(encoding='utf-8').strip()
        metadata = json.loads((ROOT / 'PACKAGE_METADATA.json').read_text(encoding='utf-8'))
        manifest = json.loads((ROOT / 'MANIFEST.json').read_text(encoding='utf-8'))
        self.assertEqual(metadata['display_version'], version)
        self.assertEqual(manifest['version'], version)
        self.assertEqual(metadata['package_id'], manifest['package_id'])
        self.assertEqual(metadata['project'], manifest['project'])
        self.assertEqual(metadata['build_id'], manifest['build_id'])
        self.assertEqual(metadata['execution_namespace'], manifest['execution_namespace'])
        self.assertEqual(metadata['canonical_entrypoint'], manifest['canonical_entrypoint'])
        self.assertEqual(metadata['backend_target'], metadata['canonical_entrypoint'])
        self.assertEqual(manifest['schema_version'], 'gateway-public-manifest-v1.2')
        self.assertEqual(manifest['file_count'], len(manifest['files']))
        self.assertFalse(metadata['network_access'])
        self.assertFalse(metadata['credential_support'])
        self.assertFalse(metadata['live_write_capability'])
        self.assertEqual(metadata['execution_mode'], 'offline-read-only')
        self.assertEqual(metadata['execution_namespace'], 'KALSHI10X1C_PUBLIC')
        self.assertEqual(metadata['runtime_dependencies'], [])
        self.assertFalse(metadata['output_policy']['implicit_filesystem_writes'])

    def test_manifest_paths_are_unique_safe_and_managed(self) -> None:
        manifest = json.loads((ROOT / 'MANIFEST.json').read_text(encoding='utf-8'))
        paths = [entry['path'] for entry in manifest['files']]
        self.assertEqual(len(paths), len(set(paths)))
        folded = {item.casefold() for item in paths}
        self.assertEqual(len(paths), len(folded))
        for entry in manifest['files']:
            self.assertTrue(entry['package_managed'])
            path = entry['path']
            pure = PurePosixPath(path)
            self.assertFalse(pure.is_absolute())
            self.assertNotIn('..', pure.parts)
            self.assertNotIn('\\', path)

    def test_one_bat_launcher_delegates_to_canonical_entrypoint(self) -> None:
        metadata = json.loads((ROOT / 'PACKAGE_METADATA.json').read_text(encoding='utf-8'))
        bat_files = sorted(ROOT.glob('*.bat'))
        self.assertEqual([path.name for path in bat_files], [metadata['windows_convenience_shim']])
        self.assertEqual(metadata['approved_entrypoint_aliases'], [metadata['windows_convenience_shim']])
        text = bat_files[0].read_text(encoding='utf-8')
        self.assertIn(metadata['canonical_entrypoint'], text)
        self.assertNotIn('ExecutionPolicy', text)

    def test_no_unlocked_build_dependency_surface(self) -> None:
        self.assertFalse((ROOT / 'pyproject.toml').exists())
        self.assertFalse((ROOT / 'requirements.txt').exists())
        sbom = json.loads((ROOT / 'SBOM.cdx.json').read_text(encoding='utf-8'))
        self.assertEqual(sbom['components'], [])


if __name__ == '__main__':
    unittest.main()
