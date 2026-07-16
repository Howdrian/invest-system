#!/usr/bin/env python3
"""Stage, validate, then publish a daily Pages bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.validate_pages_bundle import validate_pages_bundle  # noqa: E402
from src.pages_publication import publish_pages_bundle, stage_pages_bundle  # noqa: E402


def _governed_rows(docs_dir: Path, run_date: str) -> list[dict]:
    path = docs_dir / "governed_results.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(payload, list):
        return [
            item
            for item in payload
            if isinstance(item, dict) and str(item.get("run_date") or run_date) == run_date
        ]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage/gate/publish Pages bundle")
    parser.add_argument("--date", required=True)
    parser.add_argument("--stage-from", required=True, help="Runtime/publish source dir")
    parser.add_argument("--staging-dir", required=True)
    parser.add_argument("--docs-dir", required=True)
    parser.add_argument("--validation-output", default="")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--fail-on-error", action="store_true")
    args = parser.parse_args(argv)

    source_dir = Path(args.stage_from)
    staging_dir = Path(args.staging_dir)
    docs_dir = Path(args.docs_dir)
    source_rows = _governed_rows(source_dir, args.date)

    staging = stage_pages_bundle(source_dir, staging_dir, args.date, source_rows)
    validation = validate_pages_bundle(args.date, staging_dir)
    published = {"copied": [], "missing": []}
    if validation.ok and args.publish:
        stage_rows = _governed_rows(staging_dir, args.date)
        published = publish_pages_bundle(staging_dir, docs_dir, args.date, stage_rows)

    payload = {
        "schema": "pages_bundle_publish_v1",
        "runDate": args.date,
        "staging": staging,
        "validation": validation.to_dict(),
        "published": published,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.validation_output:
        out = Path(args.validation_output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    print(text, end="")
    if args.fail_on_error and not validation.ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
