#!/usr/bin/env python3
"""Build docs/run_status/{date}/daily_universe.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.source_health.daily_universe import write_daily_universe  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build daily universe")
    parser.add_argument("--date", required=True, help="Run date YYYY-MM-DD")
    parser.add_argument("--docs-dir", default="docs")
    parser.add_argument("--symbols", default="", help="Comma-separated local override")
    parser.add_argument("--market", default="")
    args = parser.parse_args(argv)

    symbols = [item.strip() for item in args.symbols.replace("，", ",").split(",") if item.strip()] if args.symbols else None
    payload = write_daily_universe(args.docs_dir, args.date, symbols=symbols, market=args.market or None)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
