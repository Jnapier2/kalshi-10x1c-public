from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = [ROOT / 'kalshi_public_buy', ROOT / 'run_buy_planner.py']
PROHIBITED_IMPORT_ROOTS = {
    'requests', 'httpx', 'urllib', 'socket', 'websockets', 'cryptography',
    'ssl', 'ftplib', 'smtplib', 'telnetlib',
}
PROHIBITED_SOURCE_TERMS = {
    'create_order', 'cancel_order', 'amend_order', 'decrease_order',
    'private_key', 'api_key', 'authorization_header', 'bearer_token',
}


class PublicBoundaryTests(unittest.TestCase):
    def test_trading_disabled_marker_is_present(self) -> None:
        self.assertTrue((ROOT / 'TRADING_DISABLED').is_file())

    def test_runtime_source_has_no_network_or_credential_imports(self) -> None:
        paths = []
        for source in SOURCE_PATHS:
            paths.extend(source.rglob('*.py') if source.is_dir() else [source])
        for path in paths:
            tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
            roots = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots.update(alias.name.split('.')[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    roots.add(node.module.split('.')[0])
            self.assertFalse(roots & PROHIBITED_IMPORT_ROOTS, (path, roots))

    def test_runtime_source_has_no_mutation_or_credential_symbols(self) -> None:
        paths = []
        for source in SOURCE_PATHS:
            paths.extend(source.rglob('*.py') if source.is_dir() else [source])
        for path in paths:
            text = path.read_text(encoding='utf-8').lower()
            for term in PROHIBITED_SOURCE_TERMS:
                self.assertNotIn(term, text, (path, term))


if __name__ == '__main__':
    unittest.main()
