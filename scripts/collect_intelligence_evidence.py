#!/usr/bin/env python3
"""Fetch configured IntelligenceService sources into research ledgers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.source_health.intelligence_evidence import collect_intelligence_evidence  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect upstream intelligence evidence")
    parser.add_argument("--date", required=True)
    parser.add_argument("--docs-dir", default="docs")
    parser.add_argument("--no-bootstrap", action="store_true")
    args = parser.parse_args()
    result = collect_intelligence_evidence(
        args.docs_dir,
        args.date,
        bootstrap_safe_sources=not args.no_bootstrap,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
