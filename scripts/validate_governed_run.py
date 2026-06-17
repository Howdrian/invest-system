# -*- coding: utf-8 -*-
"""Validate date-scoped governed stock-analysis outputs.

This script is intentionally small and filesystem-based so GitHub Actions can
run it after ``main.py`` even when the Python process exits 0 after swallowing a
top-level exception. It writes structured run status used by the daily publisher.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, List


TERMINAL_OK = {"success", "skipped_market_only"}


def normalize_symbol(symbol: str) -> str:
    value = str(symbol or "").strip().replace(" ", "")
    value = re.sub(r"^(SH|SZ|BJ)(?=\d{6}$)", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\.(SH|SZ|BJ)$", "", value, flags=re.IGNORECASE)
    return value.upper() if not value.isdigit() else value


def split_symbols(raw: str) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for part in str(raw or "").split(","):
        symbol = normalize_symbol(part)
        if symbol and symbol not in seen:
            seen.add(symbol)
            result.append(symbol)
    return result


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_governed_results(reports_dir: Path, run_date: str) -> List[dict[str, Any]]:
    payload = _read_json(reports_dir / "governed_results.json")
    if not isinstance(payload, list):
        return []
    rows: List[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        item_date = str(item.get("run_date") or "").strip()
        if item_date and item_date != run_date:
            continue
        code = normalize_symbol(str(item.get("code") or item.get("symbol") or ""))
        if not code:
            continue
        copied = dict(item)
        copied["code"] = code
        rows.append(copied)
    return rows


def evaluate_governed_run(
    *,
    run_date: str,
    mode: str,
    expected_symbols: Iterable[str],
    reports_dir: Path,
    main_exit_code: int = 0,
) -> dict[str, Any]:
    expected = [s for s in (normalize_symbol(x) for x in expected_symbols) if s]
    compact = run_date.replace("-", "")
    today_report = reports_dir / f"report_{compact}.md"
    governed_results = load_governed_results(reports_dir, run_date)
    completed = sorted({normalize_symbol(str(x.get("code") or "")) for x in governed_results if x.get("code")})
    missing = [s for s in expected if s not in completed]
    stale_reports = [
        p.name
        for p in sorted(reports_dir.glob("report_*.md"))
        if compact not in p.name
    ]
    reasons: List[str] = []

    if mode == "market-only":
        status = "skipped_market_only"
    else:
        if main_exit_code != 0:
            reasons.append(f"main_exit_code_{main_exit_code}")
        if not today_report.exists():
            reasons.append("missing_today_report")
        if not governed_results:
            reasons.append("missing_governed_results")
        if expected and missing:
            reasons.append("incomplete_governed_symbols")

        if today_report.exists() and governed_results and not missing and main_exit_code == 0:
            status = "success"
        elif today_report.exists() or governed_results:
            status = "partial"
        else:
            status = "failed"

    return {
        "schema": "governed_run_status_v1",
        "run_date": run_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "status": status,
        "main_exit_code": main_exit_code,
        "expected_symbols": expected,
        "completed_symbols": completed,
        "missing_symbols": [] if mode == "market-only" else missing,
        "today_report": str(today_report),
        "today_report_exists": today_report.exists(),
        "governed_results_path": str(reports_dir / "governed_results.json"),
        "governed_results_count": len(governed_results),
        "stale_reports_ignored": stale_reports,
        "reasons": reasons,
    }


def write_status(summary: dict[str, Any], status_dir: Path) -> None:
    status_dir.mkdir(parents=True, exist_ok=True)
    (status_dir / "stock_analysis_status.txt").write_text(str(summary["status"]), encoding="utf-8")
    (status_dir / "governed_result_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if summary.get("reasons"):
        (status_dir / "stock_analysis_failure_reason.txt").write_text(
            "\n".join(str(x) for x in summary["reasons"]),
            encoding="utf-8",
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate governed run outputs")
    parser.add_argument("--run-date", required=True)
    parser.add_argument("--mode", default="full")
    parser.add_argument("--expected-symbols", default="")
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--status-dir", default="reports/run_status")
    parser.add_argument("--main-exit-code", type=int, default=0)
    parser.add_argument("--fail-on-non-success", action="store_true")
    args = parser.parse_args(argv)

    summary = evaluate_governed_run(
        run_date=args.run_date,
        mode=args.mode,
        expected_symbols=split_symbols(args.expected_symbols),
        reports_dir=Path(args.reports_dir),
        main_exit_code=args.main_exit_code,
    )
    write_status(summary, Path(args.status_dir))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.fail_on_non_success and str(summary["status"]) not in TERMINAL_OK:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
