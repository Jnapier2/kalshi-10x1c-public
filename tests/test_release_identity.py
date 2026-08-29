from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.verify_release import verify_project

ROOT = Path(__file__).resolve().parents[1]


def _copy_project(destination: Path) -> Path:
    target = destination / 'project'
    shutil.copytree(
        ROOT,
        target,
        ignore=shutil.ignore_patterns('.git', '__pycache__', '*.pyc', '*.pyo'),
    )
    return target


class ReleaseIdentityTests(unittest.TestCase):
    def test_release_identity_passes(self) -> None:
        ok, errors = verify_project()
        self.assertTrue(ok, errors)

    def test_release_identity_rejects_unlisted_shadow_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            candidate = _copy_project(Path(temp))
            (candidate / 'argparse.py').write_text('raise RuntimeError("shadow")\n', encoding='utf-8')
            ok, errors = verify_project(candidate)
            self.assertFalse(ok)
            self.assertIn('unexpected_file:argparse.py', errors)

    def test_release_identity_rejects_non_object_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            candidate = _copy_project(Path(temp))
            (candidate / 'PACKAGE_METADATA.json').write_text('[]\n', encoding='utf-8')
            ok, errors = verify_project(candidate)
            self.assertFalse(ok)
            self.assertIn('metadata_not_object', errors)

    def test_release_identity_rejects_non_object_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            candidate = _copy_project(Path(temp))
            (candidate / 'MANIFEST.json').write_text('[]\n', encoding='utf-8')
            ok, errors = verify_project(candidate)
            self.assertFalse(ok)
            self.assertIn('manifest_not_object', errors)


if __name__ == '__main__':
    unittest.main()
