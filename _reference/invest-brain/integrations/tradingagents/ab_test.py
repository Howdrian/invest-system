from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
import argparse
import hashlib
import json

try:
    from schemas import (
        PROJECT_ROOT,
        PROTECTED_PATHS,
        RESEARCH_ARCHIVE,
        archive_slug,
        assert_safe_output_path,
        validate_ticker,
        write_json_safe,
        write_text_safe,
    )
except ImportError:  # pragma: no cover
    from .schemas import (
        PROJECT_ROOT,
        PROTECTED_PATHS,
        RESEARCH_ARCHIVE,
        archive_slug,
        assert_safe_output_path,
        validate_ticker,
        write_json_safe,
        write_text_safe,
    )


DIMENSIONS = {
    "fact_verifiability": 25,
    "risk_coverage": 20,
    "catalyst_clarity": 15,
    "decision_discipline": 20,
    "incremental_information": 10,
    "actionability": 10,
}

SAMPLE_POOL = [
    {"ticker": "NVDA", "type": "us_equity", "purpose": "高关注科技成长股"},
    {"ticker": "SPY", "type": "us_etf", "purpose": "broad beta"},
    {"ticker": "GLD", "type": "commodity_etf", "purpose": "避险/宏观"},
    {"ticker": "CCJ", "type": "commodity_equity", "purpose": "铀主线"},
    {"ticker": "URA", "type": "commodity_etf", "purpose": "铀 basket"},
    {"ticker": "COPX", "type": "commodity_etf", "purpose": "铜主线"},
    {"ticker": "0700.HK", "type": "hk_equity", "purpose": "港股质量资产"},
    {"ticker": "1211.HK", "type": "hk_equity", "purpose": "港股强势制造/新能源"},
    {"ticker": "300750.SZ", "type": "cn_equity", "purpose": "A 股强势成长"},
    {"ticker": "601899.SS", "type": "cn_equity", "purpose": "黄金/资源股"},
]
REQUIRED_SAMPLE_TICKERS = {sample["ticker"].upper() for sample in SAMPLE_POOL}


class ABTestError(RuntimeError):
    pass


@dataclass
class AggregateResult:
    verdict: str
    sample_count: int
    final_sample_count: int
    duplicate_tickers: list[str]
    missing_required_tickers: list[str]
    average_delta: float
    incremental_count: int
    factual_error_count: int
    gate_bypass_count: int
    writeback_violation_count: int
    protected_audit_count: int
    protected_audit_changed_files: list[str]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "sample_count": self.sample_count,
            "final_sample_count": self.final_sample_count,
            "duplicate_tickers": self.duplicate_tickers,
            "missing_required_tickers": self.missing_required_tickers,
            "average_delta": self.average_delta,
            "incremental_count": self.incremental_count,
            "factual_error_count": self.factual_error_count,
            "gate_bypass_count": self.gate_bypass_count,
            "writeback_violation_count": self.writeback_violation_count,
            "protected_audit_count": self.protected_audit_count,
            "protected_audit_changed_files": self.protected_audit_changed_files,
            "notes": self.notes,
        }


def ab_dir_for(ticker: str, analysis_date: str, archive_root: Path | None = None) -> Path:
    root = archive_root or RESEARCH_ARCHIVE
    directory = root / f"{analysis_date}-abtest-{archive_slug(ticker)}"
    assert_safe_output_path(directory)
    return directory


def empty_scores() -> dict[str, int]:
    return {key: 0 for key in DIMENSIONS}


def grading_template(ticker: str, analysis_date: str) -> dict[str, Any]:
    return {
        "ticker": validate_ticker(ticker),
        "analysis_date": analysis_date,
        "status": "draft",
        "scores": {
            "a_old_flow": empty_scores(),
            "b_with_tradingagents": empty_scores(),
        },
        "has_incremental_information": False,
        "factual_error_count_b": 0,
        "local_gate_bypassed": False,
        "writeback_violation": False,
        "changed_final_action": False,
        "notes": {
            "b_added": [],
            "b_errors": [],
            "decision_change_reason": "",
            "gate_check": "",
        },
    }


def score_total(scores: dict[str, Any]) -> int:
    total = 0
    for key, weight in DIMENSIONS.items():
        value = int(scores.get(key, 0))
        if value < 0 or value > weight:
            raise ABTestError(f"Score {key}={value} is outside 0-{weight}")
        total += value
    return total


def validate_grading(payload: dict[str, Any]) -> dict[str, Any]:
    scores = payload.get("scores") or {}
    a = scores.get("a_old_flow") or {}
    b = scores.get("b_with_tradingagents") or {}
    a_total = score_total(a)
    b_total = score_total(b)
    payload["a_total"] = a_total
    payload["b_total"] = b_total
    payload["delta"] = b_total - a_total
    return payload


def render_grading_md(payload: dict[str, Any]) -> str:
    payload = validate_grading(payload)
    notes = payload.get("notes") or {}
    b_added = notes.get("b_added") or []
    b_errors = notes.get("b_errors") or []
    added_text = "\n".join(f"- {item}" for item in b_added) if b_added else "- TODO"
    errors_text = "\n".join(f"- {item}" for item in b_errors) if b_errors else "- TODO"

    rows = []
    for key, weight in DIMENSIONS.items():
        a_value = payload["scores"]["a_old_flow"].get(key, 0)
        b_value = payload["scores"]["b_with_tradingagents"].get(key, 0)
        rows.append(f"| {key} | {weight} | {a_value} | {b_value} | {b_value - a_value} |")

    return f"""# A/B Grading

## Context

- Ticker: `{payload.get("ticker")}`
- Analysis date: `{payload.get("analysis_date")}`
- Status: `{payload.get("status")}`

## Scores

| Dimension | Weight | A old flow | B with TradingAgents | Delta |
|---|---:|---:|---:|---:|
{chr(10).join(rows)}
| **Total** | **100** | **{payload["a_total"]}** | **{payload["b_total"]}** | **{payload["delta"]}** |

## Gate Checks

- B has incremental information: `{payload.get("has_incremental_information")}`
- B factual error count: `{payload.get("factual_error_count_b")}`
- Local gate bypassed: `{payload.get("local_gate_bypassed")}`
- Writeback violation: `{payload.get("writeback_violation")}`
- Changed final action: `{payload.get("changed_final_action")}`

## B Added

{added_text}

## B Errors

{errors_text}

## Decision Change Reason

{notes.get("decision_change_reason") or "TODO"}

## Gate Check Detail

{notes.get("gate_check") or "TODO"}
"""


def render_summary_md(payload: dict[str, Any]) -> str:
    payload = validate_grading(payload)
    return f"""# A/B Summary

- Ticker: `{payload.get("ticker")}`
- A old flow score: `{payload["a_total"]}/100`
- B with TradingAgents score: `{payload["b_total"]}/100`
- Delta: `{payload["delta"]}`
- Local gate bypassed: `{payload.get("local_gate_bypassed")}`
- Writeback violation: `{payload.get("writeback_violation")}`

This summary is not a trading decision. Final action still depends on the local red-blue protocol, scoring-card, and position sizing.
"""


def init_sample(ticker: str, analysis_date: str, archive_root: Path | None = None, force: bool = False) -> Path:
    safe_ticker = validate_ticker(ticker)
    out_dir = ab_dir_for(safe_ticker, analysis_date, archive_root)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = {
        "a_old_flow.md": "# A Old Flow\n\nTODO: paste or generate the local-only invest-brain analysis.\n",
        "b_with_tradingagents.md": "# B With TradingAgents\n\nTODO: paste or generate the local flow with TradingAgents sidecar evidence and local challenge.\n",
    }
    for filename, content in files.items():
        path = out_dir / filename
        if force or not path.exists():
            write_text_safe(path, content)

    grading = grading_template(safe_ticker, analysis_date)
    json_path = out_dir / "ab_grading.json"
    if force or not json_path.exists():
        write_json_safe(json_path, grading)

    grading_path = out_dir / "grading.md"
    if force or not grading_path.exists():
        write_text_safe(grading_path, render_grading_md(grading))

    summary_path = out_dir / "summary.md"
    if force or not summary_path.exists():
        write_text_safe(summary_path, render_summary_md(grading))

    return out_dir


def load_gradings(paths: list[Path]) -> list[dict[str, Any]]:
    gradings = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        gradings.append(validate_grading(payload))
    return gradings


def file_fingerprint(path: Path, root: Path = PROJECT_ROOT) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "relative_path": str(path.relative_to(root)) if path.is_absolute() and path.is_relative_to(root) else str(path),
            "exists": False,
            "sha256": None,
            "size": None,
        }
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    stat = path.stat()
    return {
        "path": str(path),
        "relative_path": str(path.relative_to(root)) if path.is_absolute() and path.is_relative_to(root) else str(path),
        "exists": True,
        "sha256": digest,
        "size": stat.st_size,
    }


def protected_snapshot(paths: list[Path] | None = None) -> dict[str, Any]:
    selected_paths = sorted(paths or list(PROTECTED_PATHS), key=lambda p: str(p))
    files = {}
    for path in selected_paths:
        fingerprint = file_fingerprint(path)
        files[fingerprint["relative_path"]] = fingerprint
    return {
        "schema": "protected_file_snapshot_v1",
        "project_root": str(PROJECT_ROOT),
        "files": files,
    }


def compare_protected_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_files = before.get("files") or {}
    after_files = after.get("files") or {}
    changed_files: list[str] = []
    for path in sorted(set(before_files) | set(after_files)):
        before_item = before_files.get(path)
        after_item = after_files.get(path)
        if before_item != after_item:
            changed_files.append(path)
    return {
        "schema": "protected_file_audit_v1",
        "writeback_violation": bool(changed_files),
        "changed_files": changed_files,
        "before_project_root": before.get("project_root"),
        "after_project_root": after.get("project_root"),
    }


def load_protected_audits(paths: list[Path]) -> list[dict[str, Any]]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def aggregate_gradings(
    gradings: list[dict[str, Any]],
    protected_audits: list[dict[str, Any]] | None = None,
) -> AggregateResult:
    if not gradings:
        raise ABTestError("No grading files provided")

    sample_count = len(gradings)
    final_sample_count = sum(1 for g in gradings if str(g.get("status", "")).lower() == "final")
    tickers = [str(g.get("ticker", "")).upper() for g in gradings]
    duplicate_tickers = sorted({ticker for ticker in tickers if tickers.count(ticker) > 1})
    missing_required_tickers = sorted(REQUIRED_SAMPLE_TICKERS - set(tickers))
    average_delta = sum(g["delta"] for g in gradings) / sample_count
    incremental_count = sum(1 for g in gradings if bool(g.get("has_incremental_information")))
    factual_error_count = sum(int(g.get("factual_error_count_b", 0)) for g in gradings)
    gate_bypass_count = sum(1 for g in gradings if bool(g.get("local_gate_bypassed")))
    writeback_violation_count = sum(1 for g in gradings if bool(g.get("writeback_violation")))
    protected_audit_count = len(protected_audits or [])
    protected_audit_changed_files = sorted({
        changed
        for audit in protected_audits or []
        if bool(audit.get("writeback_violation"))
        for changed in audit.get("changed_files", [])
    })
    if protected_audit_changed_files:
        writeback_violation_count += 1

    notes: list[str] = []
    if sample_count < 10:
        notes.append("Needs 10 samples before PASS is possible.")
    if duplicate_tickers:
        notes.append("A/B sample pool contains duplicate tickers.")
    if missing_required_tickers:
        notes.append("A/B sample pool is missing required rubric tickers.")
    if final_sample_count < sample_count:
        notes.append("All grading samples must be status=final before PASS is possible.")
    if average_delta < 8:
        notes.append("Average B-A delta is below +8.")
    if incremental_count < 7:
        notes.append("Fewer than 7 samples have clear incremental information.")
    if factual_error_count > 2:
        notes.append("B factual errors exceed 2 total.")
    if gate_bypass_count:
        notes.append("At least one sample bypassed the local score gate.")
    if writeback_violation_count:
        notes.append("At least one sample wrote or attempted to write protected state.")
    if protected_audit_count == 0:
        notes.append("Protected file audit is required before PASS is possible.")
    if protected_audit_changed_files:
        notes.append("Protected file audit detected changes.")

    if sample_count >= 10 and not notes:
        verdict = "PASS"
    elif average_delta > 0 and gate_bypass_count == 0 and writeback_violation_count == 0:
        verdict = "PARTIAL"
    else:
        verdict = "FAIL"

    return AggregateResult(
        verdict=verdict,
        sample_count=sample_count,
        final_sample_count=final_sample_count,
        duplicate_tickers=duplicate_tickers,
        missing_required_tickers=missing_required_tickers,
        average_delta=round(average_delta, 2),
        incremental_count=incremental_count,
        factual_error_count=factual_error_count,
        gate_bypass_count=gate_bypass_count,
        writeback_violation_count=writeback_violation_count,
        protected_audit_count=protected_audit_count,
        protected_audit_changed_files=protected_audit_changed_files,
        notes=notes,
    )


def write_aggregate_report(result: AggregateResult, out: Path) -> None:
    body = f"""# TradingAgents A/B Aggregate Result

- Verdict: `{result.verdict}`
- Sample count: `{result.sample_count}`
- Final sample count: `{result.final_sample_count}`
- Duplicate tickers: `{", ".join(result.duplicate_tickers) if result.duplicate_tickers else "none"}`
- Missing required tickers: `{", ".join(result.missing_required_tickers) if result.missing_required_tickers else "none"}`
- Average B-A delta: `{result.average_delta}`
- Incremental info count: `{result.incremental_count}`
- B factual error count: `{result.factual_error_count}`
- Local gate bypass count: `{result.gate_bypass_count}`
- Writeback violation count: `{result.writeback_violation_count}`
- Protected audit count: `{result.protected_audit_count}`

## Notes

{chr(10).join(f"- {note}" for note in result.notes) if result.notes else "- All pass criteria met."}

## Protected File Audit

{chr(10).join(f"- {path}" for path in result.protected_audit_changed_files) if result.protected_audit_changed_files else "- No protected file changes supplied or detected."}
"""
    write_text_safe(out, body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create and aggregate TradingAgents A/B tests.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-sample")
    init_parser.add_argument("--ticker", required=True)
    init_parser.add_argument("--analysis-date", default=date.today().isoformat())
    init_parser.add_argument("--force", action="store_true")

    init_pool_parser = subparsers.add_parser("init-pool")
    init_pool_parser.add_argument("--analysis-date", default=date.today().isoformat())
    init_pool_parser.add_argument("--force", action="store_true")

    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("--grading-json", type=Path, required=True)

    aggregate_parser = subparsers.add_parser("aggregate")
    aggregate_parser.add_argument("--grading-json", type=Path, nargs="+", required=True)
    aggregate_parser.add_argument("--protected-audit-json", type=Path, nargs="*", default=[])
    aggregate_parser.add_argument("--out", type=Path, required=True)

    snapshot_parser = subparsers.add_parser("snapshot-protected")
    snapshot_parser.add_argument("--out", type=Path, required=True)

    audit_parser = subparsers.add_parser("audit-protected")
    audit_parser.add_argument("--before", type=Path, required=True)
    audit_parser.add_argument("--after", type=Path, required=True)
    audit_parser.add_argument("--out", type=Path, required=True)

    args = parser.parse_args(argv)

    if args.command == "init-sample":
        print(init_sample(args.ticker, args.analysis_date, force=args.force))
        return 0

    if args.command == "init-pool":
        for sample in SAMPLE_POOL:
            print(init_sample(sample["ticker"], args.analysis_date, force=args.force))
        return 0

    if args.command == "render":
        payload = json.loads(args.grading_json.read_text(encoding="utf-8"))
        payload = validate_grading(payload)
        directory = args.grading_json.parent
        write_text_safe(directory / "grading.md", render_grading_md(payload))
        write_text_safe(directory / "summary.md", render_summary_md(payload))
        print(directory)
        return 0

    if args.command == "aggregate":
        result = aggregate_gradings(
            load_gradings(args.grading_json),
            protected_audits=load_protected_audits(args.protected_audit_json),
        )
        write_aggregate_report(result, args.out)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "snapshot-protected":
        snapshot = protected_snapshot()
        write_json_safe(args.out, snapshot)
        print(args.out)
        return 0

    if args.command == "audit-protected":
        before = json.loads(args.before.read_text(encoding="utf-8"))
        after = json.loads(args.after.read_text(encoding="utf-8"))
        audit = compare_protected_snapshots(before, after)
        write_json_safe(args.out, audit)
        print(json.dumps(audit, ensure_ascii=False, indent=2))
        return 0

    raise ABTestError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
