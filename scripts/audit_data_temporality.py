#!/usr/bin/env python3
"""Audit timestamp coverage and historical-comparison evidence for one run."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
from typing import Any, Dict, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.source_health.evidence_ledger import load_evidence_ledger  # noqa: E402
from src.source_health.provider_ledger import load_provider_ledger  # noqa: E402


def audit_data_temporality(docs_dir: str | Path, run_date: str) -> Dict[str, Any]:
    docs = Path(docs_dir)
    run_dir = docs / "run_status" / run_date
    providers = load_provider_ledger(run_dir / "provider_runs.jsonl")
    evidence = load_evidence_ledger(run_dir / "evidence_ledger.jsonl")
    artifact = _read_json(docs / "reports" / f"{run_date}.artifact.json")

    provider_missing_observed = [row for row in providers if not row.get("observed_at")]
    evidence_missing_as_of = [row for row in evidence if not (row.get("as_of") or row.get("asOf"))]
    exact_source_time = [
        row for row in evidence
        if row.get("event_time") or row.get("published_at") or row.get("fetched_at")
    ]
    generated_at = str((((artifact.get("readerV3") or {}).get("timing") or {}).get("generatedAt") or ""))
    future_evidence = _future_rows(evidence, run_date, generated_at=generated_at)
    metrics = {str(row.get("metric") or "") for row in evidence}
    comparison_status = {
        "price": "price_history_comparison" in metrics and "universe_price_comparison" in metrics,
        "macro": any(metric.endswith("_history_comparison") for metric in metrics),
        "intelligence": "intelligence_recency_comparison" in metrics,
    }
    timing = ((artifact.get("readerV3") or {}).get("timing") or {}) if isinstance(artifact, Mapping) else {}
    errors = []
    if provider_missing_observed:
        errors.append(f"provider rows missing observed_at: {len(provider_missing_observed)}")
    if evidence_missing_as_of:
        errors.append(f"evidence rows missing as_of: {len(evidence_missing_as_of)}")
    if future_evidence:
        errors.append(f"evidence source times after run window: {len(future_evidence)}")
    if not comparison_status["price"]:
        errors.append("price historical comparison evidence missing")
    if not comparison_status["macro"]:
        errors.append("macro historical comparison evidence missing")
    if not timing.get("dataAsOf"):
        errors.append("Reader timing.dataAsOf missing")

    result = {
        "schema": "data_temporality_audit_v1",
        "runDate": run_date,
        "ok": not errors,
        "providerRuns": len(providers),
        "providerObservedAtCoverage": _ratio(len(providers) - len(provider_missing_observed), len(providers)),
        "evidenceFacts": len(evidence),
        "evidenceAsOfCoverage": _ratio(len(evidence) - len(evidence_missing_as_of), len(evidence)),
        "evidenceExactTimeCoverage": _ratio(len(exact_source_time), len(evidence)),
        "futureEvidenceCount": len(future_evidence),
        "comparisonStatus": comparison_status,
        "readerTiming": dict(timing),
        "errors": errors,
    }
    out_dir = docs / "local_acceptance" / run_date
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "data_temporality_audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "data_temporality_audit.md").write_text(_markdown(result), encoding="utf-8")
    return result


def _future_rows(
    rows: Iterable[Mapping[str, Any]],
    run_date: str,
    *,
    generated_at: str = "",
) -> list[Mapping[str, Any]]:
    try:
        latest = date.fromisoformat(run_date) + timedelta(days=1)
    except ValueError:
        return []
    generated = _parse_timestamp(generated_at) or datetime.now(timezone.utc)
    exact_limit = generated + timedelta(minutes=5)
    out = []
    for row in rows:
        is_future = False
        for key in ("event_time", "published_at", "fetched_at"):
            text = str(row.get(key) or "").strip()
            if not text:
                continue
            observed_at = _parse_timestamp(text)
            if observed_at is None:
                continue
            if observed_at > exact_limit:
                out.append(row)
                is_future = True
                break
        if is_future:
            continue
        text = str(row.get("as_of") or "")[:10]
        if not text:
            continue
        try:
            observed = date.fromisoformat(text)
        except ValueError:
            continue
        if observed > latest:
            out.append(row)
    return out


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text or len(text) <= 10:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _markdown(result: Mapping[str, Any]) -> str:
    comparisons = result.get("comparisonStatus") if isinstance(result.get("comparisonStatus"), Mapping) else {}
    errors = result.get("errors") or []
    return "\n".join([
        f"# Data Temporality Audit — {result.get('runDate')}",
        "",
        f"- 状态：{'PASS' if result.get('ok') else 'FAIL'}",
        f"- Provider observed_at 覆盖：{result.get('providerObservedAtCoverage')}",
        f"- Evidence as_of 覆盖：{result.get('evidenceAsOfCoverage')}",
        f"- Evidence 精确时间覆盖：{result.get('evidenceExactTimeCoverage')}",
        f"- 未来时间异常：{result.get('futureEvidenceCount')}",
        f"- 价格历史对比：{comparisons.get('price')}",
        f"- 宏观历史对比：{comparisons.get('macro')}",
        f"- 情报时效对比：{comparisons.get('intelligence')}",
        "",
        "## Errors",
        *(f"- {item}" for item in errors),
        "" if errors else "- None",
        "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit evidence timing and historical comparisons")
    parser.add_argument("--date", required=True)
    parser.add_argument("--docs-dir", default="docs")
    parser.add_argument("--fail-on-error", action="store_true")
    args = parser.parse_args()
    result = audit_data_temporality(args.docs_dir, args.date)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if args.fail_on_error and not result.get("ok") else 0


if __name__ == "__main__":
    raise SystemExit(main())
