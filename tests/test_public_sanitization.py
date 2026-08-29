from __future__ import annotations

import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {'.bat', '.json', '.md', '.py', '.txt', '.yml', '.yaml'}
PATTERNS = {
    'openai_key': re.compile(r'\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b'),
    'github_token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b'),
    'gitlab_token': re.compile(r'\bglpat-[A-Za-z0-9_-]{20,}\b'),
    'aws_key': re.compile(r'\b(?:AKIA|ASIA)[0-9A-Z]{16}\b'),
    'google_api_key': re.compile(r'\bAIza[0-9A-Za-z_-]{35}\b'),
    'slack_token': re.compile(r'\b(?:xox[a-z]|xapp)-[A-Za-z0-9-]{10,}\b'),
    'npm_token': re.compile(r'\bnpm_[A-Za-z0-9]{20,}\b'),
    'pypi_token': re.compile(r'\bpypi-[A-Za-z0-9_-]{40,}\b'),
    'stripe_secret': re.compile(r'\b(?:sk|rk)_live_[A-Za-z0-9]{16,}\b'),
    'huggingface_token': re.compile(r'\bhf_[A-Za-z0-9]{20,}\b'),
    'private_key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'windows_user_path': re.compile(r'[A-Za-z]:\\Users\\[^\\\s]+', re.IGNORECASE),
    'unix_home_path': re.compile(r'/home/[A-Za-z0-9._-]+', re.IGNORECASE),
    'drive_url': re.compile(r'https://(?:drive|docs)\.google\.com/', re.IGNORECASE),
    'internal_project_id': re.compile(r'\bg-p-[a-f0-9]{12,}\b', re.IGNORECASE),
    'private_digest': re.compile(r'\b[a-fA-F0-9]{64}\b'),
    'secret_assignment': re.compile(
        r'(?i)\b(?:api[_ -]?key|api[_ -]?secret|private[_ -]?key|wallet|password|token|'
        r'aws[_ -]?(?:access[_ -]?key[_ -]?id|secret[_ -]?access[_ -]?key|session[_ -]?token)|'
        r'github[_ -]?token|gitlab[_ -]?token|openai[_ -]?api[_ -]?key|'
        r'slack[_ -]?(?:app[_ -]?token|bot[_ -]?token|user[_ -]?token)|'
        r'npm[_ -]?token|pypi[_ -]?token)\b\s*[:=]\s*[\"\']?[^\s\"\']{8,}'
    ),
}


class PublicSanitizationTests(unittest.TestCase):
    def test_high_value_token_fixtures_are_detected(self) -> None:
        fixtures = {
            'openai_key': ('sk-proj-' + 'A' * 24,),
            'github_token': ('ghp_' + 'A' * 30, 'github_pat_' + 'A' * 30),
            'gitlab_token': ('glpat-' + 'A' * 24,),
            'aws_key': ('AKIA' + 'ABCDEFGHIJKLMNOP', 'ASIA' + 'QRSTUVWXYZABCDEF'),
            'google_api_key': ('AIza' + 'A' * 35,),
            'slack_token': ('xoxb-' + '1234567890-ABCDEFGHIJK', 'xapp-' + '1-ABCDEFGHIJK-1234567890', 'xoxe-' + '1-ABCDEFGHIJK-1234567890'),
            'npm_token': ('npm_' + 'A' * 36,),
            'pypi_token': ('pypi-' + 'A' * 48,),
            'stripe_secret': ('sk_live_' + 'A' * 24,),
            'huggingface_token': ('hf_' + 'A' * 32,),
            'private_key': ('-----BEGIN ' + 'PRIVATE KEY-----',),
            'secret_assignment': ('AWS_SECRET_ACCESS_KEY=' + 'A' * 40, 'SLACK_APP_TOKEN=' + 'A' * 24),
        }
        for label, values in fixtures.items():
            for value in values:
                with self.subTest(pattern=label, prefix=value[:12]):
                    self.assertIsNotNone(PATTERNS[label].search(value))

    def test_public_tree_contains_no_sensitive_residue(self) -> None:
        excluded = {'MANIFEST.json'}
        for path in ROOT.rglob('*'):
            if not path.is_file() or path.name in excluded or '__pycache__' in path.parts:
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {'LICENSE', 'TRADING_DISABLED'}:
                continue
            text = path.read_text(encoding='utf-8')
            for label, pattern in PATTERNS.items():
                with self.subTest(path=path.relative_to(ROOT), pattern=label):
                    self.assertIsNone(pattern.search(text))

    def test_public_boundary_has_no_network_or_mutation_override(self) -> None:
        combined = '\n'.join(
            path.read_text(encoding='utf-8')
            for path in ROOT.rglob('*.py')
            if 'tests' not in path.parts and '__pycache__' not in path.parts
        ).lower()
        for token in (
            'requests.', 'httpx.', 'urlopen(', 'socket.', 'websocket',
            'create_order(', 'cancel_order(', 'amend_order(', 'decrease_order(',
            'load_private_key', 'live_trading = true', 'authorization:',
        ):
            self.assertNotIn(token, combined)


if __name__ == '__main__':
    unittest.main()
