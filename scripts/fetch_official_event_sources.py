#!/usr/bin/env python3
"""Fetch free-first official/event source evidence into docs staging."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.source_health.official_event_sources import (  # noqa: E402
    OfficialEventSourceClient,
    write_official_event_sources_payload,
)
from src.source_health.smoke_symbols import full_review_smoke_symbols  # noqa: E402
from src.source_health.run_matrix import sha256_file, upsert_run_matrix_stage  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch SEC/GDELT/CNINFO evidence")
    parser.add_argument("--date", required=True)
    parser.add_argument("--docs-dir", default="docs")
    parser.add_argument("--symbols", default="", help="Comma-separated symbols. Defaults to governed results and STOCK_LIST-like docs.")
    parser.add_argument("--query", default="", help="Optional broad event/news query terms, comma-separated.")
    parser.add_argument("--smoke-profile", choices=["full-review"], default="", help="Use fixed local smoke symbols for A/HK/US official source checks.")
    parser.add_argument("--output", default="")
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args(argv)

    docs = Path(args.docs_dir)
    if args.smoke_profile == "full-review":
        symbols = _symbols(args.symbols) or full_review_smoke_symbols()
    else:
        symbols = _symbols(args.symbols) or _symbols_from_docs(docs, args.date)
    query_terms = _symbols(args.query) or _query_terms_from_docs(docs, args.date, symbols)
    out = Path(args.output) if args.output else docs / "official_events" / f"{args.date}.json"

    source_scope = "source_smoke" if args.smoke_profile else "subject_evidence"
    result = OfficialEventSourceClient(timeout_s=args.timeout).fetch(
        symbols=symbols,
        query_terms=query_terms,
        run_date=args.date,
    )
    payload = write_official_event_sources_payload(out, result, source_scope=source_scope)
    upsert_run_matrix_stage(
        docs,
        args.date,
        {
            "name": "source_smoke" if source_scope == "source_smoke" else "subject_evidence",
            "status": "success" if payload.get("providerRuns") else "partial",
            "blocking": False,
            "outputs": [str(out.relative_to(docs)) if out.is_relative_to(docs) else str(out)],
            "sha256": sha256_file(out),
        },
        symbols=symbols,
    )
    print(json.dumps({
        "schema": "official_event_sources_fetch_v1",
        "runDate": args.date,
        "symbols": symbols,
        "queryTerms": query_terms,
        "sourceScope": source_scope,
        "output": str(out),
        "providerRuns": len(payload.get("providerRuns") or []),
        "evidenceFacts": len(payload.get("evidenceFacts") or []),
    }, ensure_ascii=False, indent=2))
    return 0


def _symbols(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _symbols_from_docs(docs: Path, run_date: str) -> list[str]:
    out: list[str] = []
    universe = _read_json(docs / "run_status" / run_date / "daily_universe.json")
    if isinstance(universe, dict):
        out.extend(str(item) for item in universe.get("subjectSymbols") or [])
        for group in universe.get("groups") or []:
            if isinstance(group, dict):
                out.extend(str(item) for item in group.get("symbols") or [])
    governed = _read_json(docs / "governed_results.json")
    if isinstance(governed, list):
        for row in governed:
            if isinstance(row, dict) and str(row.get("run_date") or run_date) == run_date:
                symbol = str(row.get("code") or row.get("symbol") or "").strip()
                if symbol:
                    out.append(symbol)
    stock_list = _read_text(docs / "governed_stock_list.txt")
    out.extend(_symbols(stock_list.replace("\n", ",")))
    return _dedupe(out)


def _query_terms_from_docs(docs: Path, run_date: str, symbols: list[str]) -> list[str]:
    terms = list(symbols)
    # A daily geo/news scan needs a geopolitical universe of its own. Stock
    # tickers alone cannot establish whether sanctions, conflict, trade or
    # shipping risks changed.
    terms.extend([
        "global sanctions export controls",
        "armed conflict escalation",
        "trade restrictions tariffs",
        "energy supply disruption",
        "Red Sea shipping disruption",
        "Taiwan Strait tensions",
        "Middle East conflict",
        "Ukraine conflict",
    ])
    queue = _read_json(docs / "market_cycle" / run_date / "11_deep_review_queue.json")
    if isinstance(queue, dict):
        for row in queue.get("candidates") or []:
            if isinstance(row, dict):
                for key in ("symbol", "name"):
                    value = str(row.get(key) or "").strip()
                    if value:
                        terms.append(value)
    return _dedupe(terms)[:16]


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.upper()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


if __name__ == "__main__":
    raise SystemExit(main())
