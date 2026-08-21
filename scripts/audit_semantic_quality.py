#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit whether product conclusions survive the semantic trust boundary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping


FORBIDDEN_READER_TERMS = (
    "ReportArtifact",
    "sourceHealthV2",
    "providerMatrix",
    "RAW_AGENT",
    "DERIVED_FROM_ARTIFACT",
    "claimPolicy",
    "artifactId",
    "errorType",
    "fallbackTo",
    "recordCount",
    "runMatrix",
    "range_position_pct",
    "volume_vs_avg20",
)

CONFLICTING_READER_TERMS = (
    "采纳红队",
    "系统性走弱",
    "基本面失速",
    "业绩下修",
    "补跌概率更高",
    "主要受持续股份回购支撑",
)


def audit_semantic_quality(docs_dir: str | Path, run_date: str) -> Dict[str, Any]:
    docs = Path(docs_dir)
    artifact_path = docs / "reports" / f"{run_date}.artifact.json"
    artifact = _read_json(artifact_path)
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(artifact, Mapping):
        return {"ok": False, "errors": [f"artifact_missing:{artifact_path}"], "warnings": []}

    reliability = artifact.get("researchReliability")
    if not isinstance(reliability, Mapping):
        errors.append("research_reliability_missing")
        reliability = {}
    else:
        if not reliability.get("audited"):
            errors.append("semantic_validation_not_audited")
        if not reliability.get("headlineSafe"):
            errors.append("cio_headline_not_safe")

    reader = artifact.get("readerV3") if isinstance(artifact.get("readerV3"), Mapping) else {}
    reader_reliability = reader.get("reliability") if isinstance(reader.get("reliability"), Mapping) else {}
    if not reader_reliability:
        errors.append("reader_reliability_missing")
    elif not reader_reliability.get("headlineSafe"):
        errors.append("reader_final_headline_not_safe")
    elif not reader_reliability.get("headlineEvidenceSupported"):
        errors.append("reader_final_headline_without_evidence_closure")
    reader_text = json.dumps(reader, ensure_ascii=False)
    leaked = [term for term in FORBIDDEN_READER_TERMS if term in reader_text]
    if leaked:
        errors.append("reader_engineering_terms:" + ",".join(leaked))
    conflicting = [term for term in CONFLICTING_READER_TERMS if term in reader_text]
    if conflicting:
        errors.append("reader_unresolved_reasoning_terms:" + ",".join(conflicting))

    if "-21.28" in json.dumps(artifact.get("departmentReports") or [], ensure_ascii=False) and "21.28%" in reader_text and "-21.28%" not in reader_text:
        errors.append("reader_negative_sign_lost")

    adjudication = reader.get("adjudication") if isinstance(reader.get("adjudication"), Mapping) else {}
    for key in ("baseCase", "strongestAlternative", "judgment"):
        if not str(adjudication.get(key) or "").strip():
            errors.append(f"adjudication_missing:{key}")

    memo_count = 0
    llm_count = 0
    fallback_count = 0
    rejected_count = 0
    hypothesis_count = 0
    for path in sorted((docs / "agent_memos" / run_date).rglob("*.json")):
        memo = _read_json(path)
        if not isinstance(memo, Mapping) or memo.get("schema") != "agent_memo_v1":
            continue
        memo_count += 1
        runtime = str(memo.get("agentRuntime") or memo.get("agent_runtime") or "")
        if runtime == "LLM":
            llm_count += 1
        if runtime == "RULE_FALLBACK":
            fallback_count += 1
        semantic = memo.get("semantic_validation")
        if not isinstance(semantic, Mapping):
            errors.append(f"semantic_validation_missing:{memo.get('agent')}")
            continue
        for collection in ("claims", "counterpoints", "nextActions"):
            for row in semantic.get(collection) or []:
                if not isinstance(row, Mapping):
                    continue
                status = str(row.get("status") or "")
                original = str(row.get("text") or "").strip()
                safe = str(row.get("safeText") or "").strip()
                if status == "rejected":
                    rejected_count += 1
                    if original and original in reader_text:
                        errors.append(f"rejected_claim_leaked:{memo.get('agent')}:{row.get('claimId')}")
                elif status in {"hypothesis", "disputed"}:
                    hypothesis_count += 1
                    if not safe:
                        errors.append(f"hypothesis_text_missing:{memo.get('agent')}:{row.get('claimId')}")

    if memo_count < 11:
        warnings.append(f"department_memo_count={memo_count}; expected>=11")
    if fallback_count:
        errors.append(f"rule_fallback_count={fallback_count}")
    if llm_count < 11:
        warnings.append(f"llm_department_count={llm_count}; expected>=11")

    return {
        "ok": not errors,
        "runDate": run_date,
        "artifactPath": str(artifact_path),
        "memoCount": memo_count,
        "llmCount": llm_count,
        "fallbackCount": fallback_count,
        "rejectedClaims": rejected_count,
        "conditionalClaims": hypothesis_count,
        "reliabilityLabel": reliability.get("label"),
        "errors": errors,
        "warnings": warnings,
    }


def write_semantic_audit(docs_dir: str | Path, result: Mapping[str, Any]) -> Path:
    docs = Path(docs_dir)
    run_date = str(result.get("runDate") or "unknown")
    path = docs / "local_acceptance" / run_date / "semantic_quality_audit.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {run_date} 语义质量审计",
        "",
        f"- 结论：{'PASS' if result.get('ok') else 'FAIL'}",
        f"- 可靠性：{result.get('reliabilityLabel') or '未提供'}",
        f"- 部门 memo：{result.get('memoCount', 0)}",
        f"- LLM 部门：{result.get('llmCount', 0)}",
        f"- 规则 fallback：{result.get('fallbackCount', 0)}",
        f"- 已移除无支撑主张：{result.get('rejectedClaims', 0)}",
        f"- 解释性/情景主张：{result.get('conditionalClaims', 0)}",
        "",
        "## 错误",
        *([f"- {item}" for item in result.get("errors") or []] or ["- 无"]),
        "",
        "## 警告",
        *([f"- {item}" for item in result.get("warnings") or []] or ["- 无"]),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    parser.add_argument("--docs-dir", default="docs")
    parser.add_argument("--fail-on-error", action="store_true")
    args = parser.parse_args()
    result = audit_semantic_quality(args.docs_dir, args.date)
    path = write_semantic_audit(args.docs_dir, result)
    print(json.dumps({**result, "reportPath": str(path)}, ensure_ascii=False, indent=2))
    return 1 if args.fail_on_error and not result.get("ok") else 0


if __name__ == "__main__":
    raise SystemExit(main())
