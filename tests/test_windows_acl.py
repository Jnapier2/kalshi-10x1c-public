from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from kalshi_public.auth import _windows_acl_failures


class WindowsAclTests(unittest.TestCase):
    def _result(self, rules: list[dict[str, object]], *, owner: str = "S-1-5-21-1000") -> Mock:
        payload = {
            "CurrentSid": "S-1-5-21-1000",
            "OwnerSid": owner,
            "Rules": rules,
        }
        return Mock(returncode=0, stdout=json.dumps(payload), stderr="")

    @patch("kalshi_public.auth.Path.is_file", return_value=True)
    @patch("kalshi_public.auth.subprocess.run")
    def test_owner_system_and_administrators_acl_passes(self, run: Mock, _is_file: Mock) -> None:
        run.return_value = self._result(
            [
                {"Sid": "S-1-5-21-1000", "Type": "Allow", "Rights": 2032127, "Inherited": False},
                {"Sid": "S-1-5-18", "Type": "Allow", "Rights": 2032127, "Inherited": False},
                {"Sid": "S-1-5-32-544", "Type": "Allow", "Rights": 2032127, "Inherited": False},
            ]
        )
        self.assertEqual(_windows_acl_failures(Path("C:/secure/key.pem")), [])
        self.assertIsInstance(run.call_args.args[0], list)
        self.assertNotIn("C:/secure/key.pem", " ".join(run.call_args.args[0]))

    @patch("kalshi_public.auth.Path.is_file", return_value=True)
    @patch("kalshi_public.auth.subprocess.run")
    def test_authenticated_users_access_fails_closed(self, run: Mock, _is_file: Mock) -> None:
        run.return_value = self._result(
            [
                {"Sid": "S-1-5-21-1000", "Type": "Allow", "Rights": 131209, "Inherited": False},
                {"Sid": "S-1-5-11", "Type": "Allow", "Rights": 131209, "Inherited": True},
            ]
        )
        failures = _windows_acl_failures(Path("C:/secure/key.pem"))
        self.assertTrue(any("broader Windows principal" in item for item in failures))

    @patch("kalshi_public.auth.Path.is_file", return_value=True)
    @patch("kalshi_public.auth.subprocess.run")
    def test_acl_probe_error_fails_closed_without_echoing_details(self, run: Mock, _is_file: Mock) -> None:
        run.return_value = Mock(returncode=1, stdout="", stderr="sensitive diagnostic")
        self.assertEqual(
            _windows_acl_failures(Path("C:/secure/key.pem")),
            ["Windows ACL verification did not complete successfully"],
        )


if __name__ == "__main__":
    unittest.main()
