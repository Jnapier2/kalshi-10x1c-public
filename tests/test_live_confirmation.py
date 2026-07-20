from __future__ import annotations

import unittest
from argparse import Namespace
from types import SimpleNamespace
from unittest.mock import Mock, patch

import run_bot
from kalshi_public.constants import LIVE_LAUNCH_ACK
from kalshi_public.safety import SafetyError


class LiveConfirmationTests(unittest.TestCase):
    @patch("run_bot.load_settings")
    def test_live_launch_requires_interactive_terminal(self, load_settings: Mock) -> None:
        load_settings.return_value = Mock(direction_policy="cheapest")
        with (
            patch("run_bot.sys.stdin.isatty", return_value=False),
            self.assertRaisesRegex(SafetyError, "interactive terminal"),
        ):
            run_bot.command_write(Namespace(command="live", continuous=False))

    @patch("run_bot.authorization_failures", return_value=["expected downstream stop"])
    @patch("run_bot.verify_release")
    @patch("run_bot.load_settings")
    def test_exact_fresh_confirmation_reaches_normal_authorization_gates(
        self,
        load_settings: Mock,
        verify_release: Mock,
        authorization_failures: Mock,
    ) -> None:
        load_settings.return_value = Mock(direction_policy="cheapest")
        verify_release.return_value = Mock(passed=True, checks=())
        with (
            patch("run_bot.sys.stdin.isatty", return_value=True),
            patch("builtins.input", return_value=LIVE_LAUNCH_ACK),
            self.assertRaisesRegex(SafetyError, "expected downstream stop"),
        ):
            run_bot.command_write(Namespace(command="live", continuous=False))
        authorization_failures.assert_called_once()

    @patch("run_bot.verify_release")
    @patch("run_bot.load_settings")
    def test_wrong_confirmation_creates_no_authorization(self, load_settings: Mock, verify_release: Mock) -> None:
        load_settings.return_value = Mock(direction_policy="cheapest")
        verify_release.return_value = Mock(passed=True, checks=())
        with (
            patch("run_bot.sys.stdin.isatty", return_value=True),
            patch("builtins.input", return_value="no"),
            patch("run_bot.authorize_write") as authorize_write,
            self.assertRaisesRegex(SafetyError, "did not match"),
        ):
            run_bot.command_write(Namespace(command="live", continuous=True))
        authorize_write.assert_not_called()

    @patch("run_bot.verify_release")
    @patch("run_bot.load_settings")
    def test_failed_strict_verification_blocks_before_prompt(self, load_settings: Mock, verify_release: Mock) -> None:
        load_settings.return_value = Mock(direction_policy="cheapest")
        verify_release.return_value = Mock(
            passed=False,
            checks=(SimpleNamespace(status="FAIL", name="Known-vulnerability audit"),),
        )
        with (
            patch("run_bot.sys.stdin.isatty", return_value=True),
            patch("builtins.input") as prompt,
            self.assertRaisesRegex(SafetyError, "Known-vulnerability audit"),
        ):
            run_bot.command_write(Namespace(command="live", continuous=False))
        prompt.assert_not_called()


if __name__ == "__main__":
    unittest.main()
