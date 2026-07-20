from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kalshi_public.env import SAFE_DEFAULTS, EnvError, load_settings, parse_env_text


class EnvTests(unittest.TestCase):
    def test_safe_defaults_are_write_disabled(self) -> None:
        self.assertEqual(SAFE_DEFAULTS["PUBLIC_ORDER_WRITES_ENABLED"], "0")
        self.assertEqual(SAFE_DEFAULTS["LIVE_TRADING"], "0")
        self.assertEqual(SAFE_DEFAULTS["DRY_RUN"], "1")

    def test_parse_basic_values(self) -> None:
        values, unknown = parse_env_text("PUBLIC_RUN_MODE=dry-run\nPUBLIC_DIRECTION_POLICY='yes'\n")
        self.assertEqual(values["PUBLIC_RUN_MODE"], "dry-run")
        self.assertEqual(values["PUBLIC_DIRECTION_POLICY"], "yes")
        self.assertEqual(unknown, ())

    def test_unknown_keys_are_reported_not_loaded(self) -> None:
        values, unknown = parse_env_text("UNKNOWN_SECRET=abc\nDRY_RUN=1\n")
        self.assertNotIn("UNKNOWN_SECRET", values)
        self.assertEqual(unknown, ("UNKNOWN_SECRET",))

    def test_duplicate_key_is_rejected(self) -> None:
        with self.assertRaises(EnvError):
            parse_env_text("DRY_RUN=1\nDRY_RUN=0\n")

    def test_command_substitution_is_rejected(self) -> None:
        for text in ("KALSHI_PRIVATE_KEY_PATH=$(whoami)", "KALSHI_PRIVATE_KEY_PATH=`whoami`"):
            with self.subTest(text=text), self.assertRaises(EnvError):
                parse_env_text(text)

    def test_unterminated_quote_is_rejected(self) -> None:
        with self.assertRaises(EnvError):
            parse_env_text("PUBLIC_RUN_MODE='dry-run")

    def test_ambient_process_environment_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"LIVE_TRADING": "1"}, clear=False):
            settings = load_settings(Path(folder))
            self.assertEqual(settings.values["LIVE_TRADING"], "0")

    def test_only_root_dotenv_is_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / ".env.local").write_text("LIVE_TRADING=1\n", encoding="utf-8")
            settings = load_settings(root)
            self.assertFalse(settings.source_exists)
            self.assertEqual(settings.values["LIVE_TRADING"], "0")

    def test_runtime_numeric_settings_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / ".env").write_text(
                "PUBLIC_SCAN_INTERVAL_SECONDS=1\nPUBLIC_MIN_SECONDS_TO_CLOSE=99999\nPUBLIC_HTTP_TIMEOUT_SECONDS=0\n",
                encoding="utf-8",
            )
            settings = load_settings(root)
            self.assertEqual(settings.scan_interval_seconds, 5)
            self.assertEqual(settings.min_seconds_to_close, 3600)
            self.assertEqual(settings.http_timeout_seconds, 1.0)

    @unittest.skipIf(os.name == "nt", "symlink creation may require elevated privileges on Windows")
    def test_dotenv_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / "real.env"
            target.write_text("LIVE_TRADING=1\n", encoding="utf-8")
            (root / ".env").symlink_to(target)
            with self.assertRaises(EnvError):
                load_settings(root)

    def test_oversized_dotenv_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / ".env").write_text("#" + ("x" * (64 * 1024)) + "\n", encoding="utf-8")
            with self.assertRaises(EnvError):
                load_settings(root)


if __name__ == "__main__":
    unittest.main()
