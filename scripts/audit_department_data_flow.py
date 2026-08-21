#!/usr/bin/env python3
"""Write department data-flow audit for a daily research run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.source_health.department_data_audit import write_department_data_audit  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit provider → evidence → Agent → Reader data flow")
    parser.add_argument("--date", required=True)
    parser.add_argument("--docs-dir", default="docs")
    args = parser.parse_args(argv)
    result = write_department_data_audit(Path(args.docs_dir), args.date)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
