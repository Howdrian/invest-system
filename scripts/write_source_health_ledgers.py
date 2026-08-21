#!/usr/bin/env python3
"""Write daily provider/evidence ledgers from local report artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.source_health.daily_ledgers import write_daily_source_health_ledgers  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write daily source health ledgers")
    parser.add_argument("--date", required=True, help="Run date YYYY-MM-DD")
    parser.add_argument("--docs-dir", default="docs")
    parser.add_argument("--output", default="")
    parser.add_argument(
        "--preserve-runtime-enrichment",
        action="store_true",
        help="Preserve current-run CIO enrichment while refreshing publication health.",
    )
    parser.add_argument(
        "--include-pages-validation",
        action="store_true",
        help="Include the completed Pages validator result in final publication health.",
    )
    args = parser.parse_args(argv)

    result = write_daily_source_health_ledgers(
        Path(args.docs_dir),
        args.date,
        preserve_runtime_enrichment=args.preserve_runtime_enrichment,
        include_pages_validation=args.include_pages_validation,
    )
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
