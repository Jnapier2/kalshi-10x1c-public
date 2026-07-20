from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from kalshi_public.instance_lock import InstanceLock, unlock
from kalshi_public.safety import SafetyError, create_kill_switch
from kalshi_public.verify import (
    _check_clean_package,
    _check_defaults,
    _check_manifest,
    _check_secrets,
    generate_manifest,
    immutable_files,
    verify_release,
)
from tests.helpers import TempPublicRoot


def _make_clean_fixture(root: Path) -> None:
    (root / "logs").mkdir()
    (root / "runtime").mkdir()
    (root / "logs/.gitkeep").write_bytes(b"")
    (root / "runtime/.gitkeep").write_bytes(b"")
    (root / "TRADING_DISABLED").write_text("Trading disabled.\n", encoding="utf-8")
    (root / "code.py").write_text("value = 1\n", encoding="utf-8")
    files = (
        "FILE_INVENTORY.txt",
        "MANIFEST.sha256",
        "TRADING_DISABLED",
        "code.py",
        "logs/.gitkeep",
        "runtime/.gitkeep",
    )
    (root / "FILE_INVENTORY.txt").write_text(
        "Test package\n\n"
        f"Expected packaged files: {len(files)}\n"
        "Generated state is not packaged.\n\n"
        + "\n".join(files)
        + "\n",
        encoding="utf-8",
    )
    generate_manifest(root)


class InstanceLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TempPublicRoot()

    def tearDown(self) -> None:
        self.temp.close()

    def test_second_writer_is_blocked(self) -> None:
        first = InstanceLock(self.temp.root)
        with first, self.assertRaises(SafetyError), InstanceLock(self.temp.root):
            pass

    def test_lock_is_removed_on_clean_exit(self) -> None:
        path = self.temp.root / "runtime/live_instance.lock"
        with InstanceLock(self.temp.root):
            self.assertTrue(path.exists())
        self.assertFalse(path.exists())

    def test_unlock_requires_kill_switch(self) -> None:
        (self.temp.root / "runtime").mkdir()
        (self.temp.root / "runtime/live_instance.lock").write_text("{}", encoding="utf-8")
        with self.assertRaises(SafetyError):
            unlock(self.temp.root, "I_CONFIRM_NO_OTHER_BOT_INSTANCE_IS_RUNNING")

    def test_unlock_requires_exact_ack(self) -> None:
        (self.temp.root / "runtime").mkdir()
        path = self.temp.root / "runtime/live_instance.lock"
        path.write_text("{}", encoding="utf-8")
        create_kill_switch(self.temp.root)
        with self.assertRaises(SafetyError):
            unlock(self.temp.root, "yes")
        self.assertTrue(path.exists())

    def test_unlock_removes_stale_lock_with_all_gates(self) -> None:
        (self.temp.root / "runtime").mkdir()
        path = self.temp.root / "runtime/live_instance.lock"
        path.write_text("{}", encoding="utf-8")
        create_kill_switch(self.temp.root)
        unlock(self.temp.root, "I_CONFIRM_NO_OTHER_BOT_INSTANCE_IS_RUNNING")
        self.assertFalse(path.exists())


class ManifestTests(unittest.TestCase):
    def test_manifest_round_trip_and_tamper_detection(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "a.txt").write_text("alpha", encoding="utf-8")
            (root / "b.py").write_text("x = 1\n", encoding="utf-8")
            generate_manifest(root)
            self.assertEqual(_check_manifest(root).status, "PASS")
            (root / "a.txt").write_text("changed", encoding="utf-8")
            self.assertEqual(_check_manifest(root).status, "FAIL")

    def test_dynamic_runtime_files_are_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "code.py").write_text("x=1", encoding="utf-8")
            (root / ".env").write_text("SECRET=x", encoding="utf-8")
            (root / "runtime").mkdir()
            (root / "runtime/state.json").write_text("{}", encoding="utf-8")
            names = {path.relative_to(root).as_posix() for path in immutable_files(root)}
            self.assertEqual(names, {"code.py"})

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            _make_clean_fixture(root)
            before = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(_check_clean_package(root).status, "PASS")
            result = verify_release(root, clean_package=True)
            self.assertTrue(result.passed)
            self.assertIsNone(result.report_path)
            self.assertFalse((root / "VERIFICATION_REPORT.md").exists())
            self.assertFalse((root / ".public_verify_attestation.json").exists())
            after = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before, "clean-package checking must be read-only")

        def add_file(relative: str, data: bytes = b"extra\n") -> None:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        adversarial = (
            (".env", b"SAFE=0\n"),
            (".env.local", b"SAFE=0\n"),
            ("nested/.env.example", b"SAFE=0\n"),
            ("kalshi_public/cache.pyc", b"bytecode"),
            ("native.DLL", b"MZpayload"),
            ("nested/archive.ZIP", b"PK\x05\x06"),
            ("renamed.txt", b"PK\x03\x04payload"),
            ("VERIFICATION_REPORT.md", b"generated\n"),
            (".public_verify_attestation.json", b"{}\n"),
            ("runtime/state.json", b"{}\n"),
            ("logs/orders.jsonl", b"{}\n"),
        )
        for relative, data in adversarial:
            with self.subTest(forbidden=relative), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                _make_clean_fixture(root)
                add_file(relative, data)
                self.assertEqual(_check_clean_package(root).status, "FAIL")
        for directory in ("__pycache__", ".pytest_cache", ".venv", "nested/node_modules"):
            with self.subTest(forbidden_directory=directory), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                _make_clean_fixture(root)
                (root / directory).mkdir(parents=True)
                self.assertEqual(_check_clean_package(root).status, "FAIL")
        for placeholder in ("logs/.gitkeep", "runtime/.gitkeep"):
            with self.subTest(nonempty_placeholder=placeholder), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                _make_clean_fixture(root)
                (root / placeholder).write_text("state\n", encoding="utf-8")
                self.assertEqual(_check_clean_package(root).status, "FAIL")

    @unittest.skipIf(os.name == "nt", "symlink behavior differs on Windows")
    def test_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "real.txt").write_text("x", encoding="utf-8")
            (root / "link.txt").symlink_to(root / "real.txt")
            with self.assertRaises(ValueError):
                immutable_files(root)

    def test_private_key_file_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "oops.key").write_text("not-even-a-key", encoding="utf-8")
            self.assertEqual(_check_secrets(root).status, "FAIL")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / ".env").write_text(
                "KALSHI_API_KEY_ID=8fb950b6-7ec2-4abd-8e7d-96d3a1e0176e\n"
                "KALSHI_PRIVATE_KEY_PATH=/keys/private.key\n",
                encoding="utf-8",
            )
            self.assertEqual(_check_secrets(root).status, "PASS")
            (root / ".env.local").write_text("API_TOKEN=actual-value-not-a-placeholder\n", encoding="utf-8")
            result = _check_secrets(root)
            self.assertEqual(result.status, "FAIL")
            self.assertNotIn("actual-value-not-a-placeholder", result.detail)
        for relative, line in (
            ("runtime/debug.trace", "PASSWORD=runtime-leak-value\n"),
            ("logs/output.log", '"api_key": "log-leak-value"\n'),
            ("VERIFICATION_REPORT.md", "CLIENT_SECRET=report-leak-value\n"),
            ("runtime/provider.dat", "AK" + "IA1234567890ABCDEF\n"),
        ):
            with self.subTest(dynamic_secret=relative), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(line, encoding="utf-8")
                self.assertEqual(_check_secrets(root).status, "FAIL")

    def test_verifier_requires_tracked_kill_switch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".env.example").write_text(
                "PUBLIC_RUN_MODE=dry-run\n"
                "PUBLIC_ORDER_WRITES_ENABLED=0\n"
                "LIVE_TRADING=0\n"
                "DRY_RUN=1\n"
                "KALSHI_DRY_RUN=1\n"
                "PAPER_MODE=1\n"
                "PAPER_TRADE=1\n"
                "SIMULATION_MODE=1\n"
                "ALLOW_PRODUCTION_TRADING=0\n",
                encoding="utf-8",
            )
            self.assertEqual(_check_defaults(root).status, "FAIL")
            (root / "TRADING_DISABLED").write_text("Trading disabled.\n", encoding="utf-8")
            self.assertEqual(_check_defaults(root).status, "PASS")

    def test_embedded_private_key_header_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "oops.txt").write_text("-----BEGIN " + "PRIVATE KEY-----\n", encoding="utf-8")
            self.assertEqual(_check_secrets(root).status, "FAIL")
        for relative, kind in (("runtime/debug.trace", "ENCRYPTED "), ("logs/output.log", "DSA ")):
            with self.subTest(dynamic_key=relative), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                path = root / relative
                path.parent.mkdir(parents=True)
                path.write_text("-----BEGIN " + kind + "PRIVATE KEY-----\n", encoding="utf-8")
                self.assertEqual(_check_secrets(root).status, "FAIL")


if __name__ == "__main__":
    unittest.main()
