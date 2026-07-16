#!/usr/bin/env python3
"""Collect subject evidence through the upstream DataFetcherManager."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.source_health.subject_evidence import collect_subject_evidence  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect subject evidence")
    parser.add_argument("--date", required=True, help="Run date YYYY-MM-DD")
    parser.add_argument("--docs-dir", default="docs")
    parser.add_argument("--symbols", default="", help="Comma-separated local override")
    parser.add_argument("--market", default="")
    parser.add_argument("--max-symbols", type=int, default=None)
    args = parser.parse_args(argv)

    symbols = [item.strip() for item in args.symbols.replace("，", ",").split(",") if item.strip()] if args.symbols else None
    summary = collect_subject_evidence(
        args.docs_dir,
        args.date,
        symbols=symbols,
        market=args.market or None,
        max_symbols=args.max_symbols,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
