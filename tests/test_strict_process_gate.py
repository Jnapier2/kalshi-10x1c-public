from __future__ import annotations

import hashlib
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from kalshi_public import verify


class StrictProcessGateTests(unittest.TestCase):
    def test_forged_file_attestation_is_not_an_in_process_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "MANIFEST.sha256").write_text("forged\n", encoding="utf-8")
            self.assertTrue(any("in this process" in item for item in verify.strict_verification_failures(root)))

    def test_registered_pass_is_bound_to_manifest_runtime_and_age(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "MANIFEST.sha256"
            manifest.write_text("sealed\n", encoding="utf-8")
            key = verify._strict_root_key(root)
            verify._STRICT_PASSES[key] = (
                hashlib.sha256(manifest.read_bytes()).hexdigest(),
                verify.sys.version.split()[0],
                time.monotonic(),
            )
            self.assertEqual(verify.strict_verification_failures(root), [])
            manifest.write_text("changed\n", encoding="utf-8")
            self.assertTrue(any("manifest changed" in item for item in verify.strict_verification_failures(root)))

    def test_expired_process_pass_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "MANIFEST.sha256"
            manifest.write_text("sealed\n", encoding="utf-8")
            key = verify._strict_root_key(root)
            verify._STRICT_PASSES[key] = (
                hashlib.sha256(manifest.read_bytes()).hexdigest(),
                verify.sys.version.split()[0],
                time.monotonic() - 901,
            )
            with patch.object(verify, "_STRICT_PASS_MAX_AGE_SECONDS", 900):
                self.assertTrue(any("older than" in item for item in verify.strict_verification_failures(root)))


if __name__ == "__main__":
    unittest.main()
