#!/usr/bin/env python3
"""Release-owner tool: regenerate MANIFEST.sha256 after intentional changes."""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kalshi_public.verify import generate_manifest  # noqa: E402

if __name__ == "__main__":
    print(generate_manifest(ROOT))
