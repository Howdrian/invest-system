#!/usr/bin/env python3
"""Export same-day original-system AnalysisResult rows for research agents."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.original_analysis_adapter import export_original_analysis_snapshot  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--docs-dir", default="docs")
    parser.add_argument("--symbols", default="")
    args = parser.parse_args()
    symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
    payload = export_original_analysis_snapshot(
        args.docs_dir,
        args.date,
        symbols=symbols,
    )
    print(
        "original_analysis_snapshot: "
        f"date={payload['runDate']} records={payload['recordCount']} sha256={payload['sha256'][:12]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
