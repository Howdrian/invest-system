# -*- coding: utf-8 -*-
"""ReportArtifact v1 contract helpers.

One contract feeds both the Web/App report view and the static ``docs/``
publisher.  Keep this file framework-light so renderers, API endpoints and
tests can share the same validation rules.
"""

from __future__ import annotations

import ast
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from src.source_health.evidence_ledger import load_evidence_ledger, normalize_evidence_fact
from src.source_health.policy import build_source_health_v2
from src.source_health.provider_ledger import load_provider_ledger
from src.source_health.run_matrix import build_snapshot_refs, load_run_matrix, write_run_matrix
from src.source_health.temporal import iso_timestamp
from src.source_health.daily_universe import load_daily_universe
from src.report_policy import is_blocked_governed_row
from src.department_data_profiles import build_department_inputs
from src.original_analysis_adapter import load_original_analysis, load_original_analysis_refs
from src.research_core import build_challenge_verdicts, build_research_reliability, build_scenario_adjudication


SCHEMA_VERSION = "report_artifact_v1"

ARTIFACT_TYPES = {
    "daily",
    "market_summary",
    "macro_review",
    "source_health",
    "screening_funnel",
    "deep_review_queue",
    "preliminary_review",
    "market_strategy",
    "stock_governed",
    "agent_memo",
    "run_status",
}

AUDIENCES = {"reader", "audit", "machine", "run_status"}
SECTION_KINDS = {
    "source",
    "facts",
    "analysis",
    "final_conclusion",
    "next_steps",
    "risk",
    "evidence",
    "raw",
}

READER_REQUIRED_SECTION_KINDS = {
    "source",
    "facts",
    "analysis",
    "final_conclusion",
    "next_steps",
}

_MISSING = object()


def validate_report_artifact(artifact: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Return ``(ok, errors)`` for a ReportArtifact v1 payload."""

    errors: List[str] = []
    if not isinstance(artifact, dict):
        return False, ["artifact must be an object"]

    required_top = [
        "schemaVersion",
        "artifactId",
        "runDate",
        "generatedAt",
        "artifactType",
        "audience",
        "title",
        "summary",
        "sections",
        "provenance",
        "publish",
        "quality",
    ]
    for key in required_top:
        if key not in artifact:
            errors.append(f"missing top-level field: {key}")

    if artifact.get("schemaVersion") != SCHEMA_VERSION:
        errors.append("schemaVersion must be report_artifact_v1")
    if artifact.get("artifactType") not in ARTIFACT_TYPES:
        errors.append("artifactType invalid")
    if artifact.get("audience") not in AUDIENCES:
        errors.append("audience invalid")

    summary = artifact.get("summary")
    if not isinstance(summary, dict):
        errors.append("summary must be an object")
    else:
        for key in ("oneLine", "keyFacts", "analysis", "finalConclusion", "nextSteps"):
            value = summary.get(key)
            if value is None or value == "" or value == []:
                errors.append(f"summary.{key} missing")

    sections = artifact.get("sections")
    if not isinstance(sections, list):
        errors.append("sections must be a list")
    else:
        kinds = set()
        for idx, section in enumerate(sections):
            if not isinstance(section, dict):
                errors.append(f"sections[{idx}] must be an object")
                continue
            kind = section.get("kind")
            if kind not in SECTION_KINDS:
                errors.append(f"sections[{idx}].kind invalid")
            else:
                kinds.add(kind)
            for key in ("key", "title"):
                if not section.get(key):
                    errors.append(f"sections[{idx}].{key} missing")
        if artifact.get("audience") == "reader":
            missing_kinds = sorted(READER_REQUIRED_SECTION_KINDS - kinds)
            for kind in missing_kinds:
                errors.append(f"reader artifact missing section kind: {kind}")

    provenance = artifact.get("provenance")
    if not isinstance(provenance, dict):
        errors.append("provenance must be an object")
    else:
        for key in ("origin", "sourceFiles", "generatedBy"):
            if key not in provenance:
                errors.append(f"provenance.{key} missing")

    quality = artifact.get("quality")
    if not isinstance(quality, dict):
        errors.append("quality must be an object")
    else:
        for key in ("completeness", "missingFields", "validationErrors"):
            if key not in quality:
                errors.append(f"quality.{key} missing")

    if "snapshotRefs" in artifact and not isinstance(artifact.get("snapshotRefs"), dict):
        errors.append("snapshotRefs must be an object")
    if "researchReliability" in artifact:
        reliability = artifact.get("researchReliability")
        if not isinstance(reliability, dict):
            errors.append("researchReliability must be an object")
        elif reliability.get("schema") != "research_reliability_v1":
            errors.append("researchReliability.schema must be research_reliability_v1")
    if "runMatrix" in artifact:
        run_matrix = artifact.get("runMatrix")
        if not isinstance(run_matrix, dict):
            errors.append("runMatrix must be an object")
        elif run_matrix.get("runDate") and run_matrix.get("runDate") != artifact.get("runDate"):
            errors.append("runMatrix.runDate must match artifact.runDate")

    return not errors, errors


def build_daily_report_artifact(docs_dir: str | Path, run_date: str) -> Dict[str, Any]:
    """Build the canonical daily ReportArtifact from published docs artifacts."""

    docs_path = Path(docs_dir)
    compact = run_date.replace("-", "")
    market_cycle = docs_path / "market_cycle" / run_date

    macro = _read_json(market_cycle / "01_macro_review.json") or {}
    health = _read_json(market_cycle / "13_source_health.json") or {}
    queue = _read_json(market_cycle / "11_deep_review_queue.json") or {}
    strategy = _read_json(market_cycle / "14_market_strategy.json") or {}
    governed = _read_json(docs_path / "governed_results.json")
    governed_rows = [
        row
        for row in (governed if isinstance(governed, list) else [])
        if isinstance(row, dict) and str(row.get("run_date") or "") == run_date
    ]
    universe = load_daily_universe(docs_path, run_date)
    universe_subjects = [str(item) for item in universe.get("subjectSymbols") or [] if str(item)]
    universe_mode = str(universe.get("mode") or "")
    agent_counts = _agent_origin_counts(docs_path, run_date)
    agent_runtime_counts = _agent_runtime_counts(docs_path, run_date)
    cio_enrichment = _load_cio_enrichment(docs_path, run_date)
    agent_model_selection = _read_json(docs_path / "run_status" / run_date / "agent_model_selection.json") or {}
    original_analysis = load_original_analysis(docs_path, run_date)
    original_analysis_refs = load_original_analysis_refs(docs_path, run_date)

    source_health = _daily_source_health(health)
    evidence_facts = _load_daily_evidence_facts(docs_path, run_date, health, source_health)
    source_health_v2 = _load_daily_source_health_v2_snapshot(docs_path, run_date) or build_source_health_v2(
        health,
        provider_runs=_load_daily_provider_runs(docs_path, run_date),
        evidence_facts=evidence_facts,
        agent_origin_counts=agent_counts,
    )
    department_reports = _department_reports(docs_path, run_date)
    _apply_daily_reader_scope(department_reports, universe)
    source_health_v2 = _align_source_health_with_agent_outputs(
        source_health_v2,
        department_reports=department_reports,
        has_governed_rows=bool(governed_rows),
        daily_universe_mode=universe_mode,
        daily_subject_count=len(universe_subjects),
    )
    research_reliability = build_research_reliability(department_reports)
    scenario_adjudication = build_scenario_adjudication(department_reports)
    candidate_count = len(queue.get("candidates") or []) if isinstance(queue, dict) else 0
    auto_governed_count = len(queue.get("auto_governed_candidates") or []) if isinstance(queue, dict) else 0
    blocked_count = sum(1 for row in governed_rows if _is_blocked_governed_row(row))
    macro_status = _first_text(macro.get("status"), health.get("macro_status"), default="未提供")
    trade_usability = _first_text(health.get("trade_review_usability"), default="未提供")
    regime = _first_text(strategy.get("regime"), default="未提供")
    headline = _first_text((strategy.get("strategy") or {}).get("headline") if isinstance(strategy.get("strategy"), dict) else None, macro.get("headline"), default="今日报告已生成。")

    if universe_subjects:
        one_line = f"今日覆盖 {len(universe_subjects)} 个观察标的，按市场、行业、候选和个股分层复核。"
    elif universe_mode == "market_and_candidates":
        one_line = "今日自选股为空；生成市场观察和候选池日报，不回退单只 600519。"
    elif governed_rows and blocked_count == len(governed_rows):
        one_line = "今日 governed 标的全部被门控阻断；最终动作是不操作。"
    elif governed_rows:
        one_line = "今日存在 governed 标的；按门控结果逐只复核，不自动交易。"
    else:
        one_line = "今日无 completed governed 个股报告；仅保留市场观察和候选池。"
    analysis_mode = str(source_health_v2.get("overallMode") or "BLOCKED")
    if analysis_mode != "FULL_REVIEW" and _is_limited_source_health(source_health):
        one_line += " 数据源有缺口，需要带限制阅读。"
    evidence_stats = source_health_v2.get("evidenceStats") if isinstance(source_health_v2.get("evidenceStats"), dict) else {"schema": "evidence_stats_v1"}
    one_line = f"{analysis_mode}：{one_line}"

    key_facts = [
        f"报告模式：{analysis_mode}",
        f"运行日期：{run_date}",
        f"宏观状态：{macro_status}",
        f"市场状态：{regime}",
        f"交易审查可用性：{trade_usability}",
        f"深评候选：{candidate_count}；自动 governed：{auto_governed_count}",
        f"日报 universe：{len(universe_subjects)} 个观察标的；模式：{universe_mode or '未提供'}",
        f"governed 完成：{len(governed_rows)}；阻断：{blocked_count}",
        f"Agent 来源：真实 {agent_counts.get('RAW_AGENT', 0)}；回填 {agent_counts.get('DERIVED_FROM_ARTIFACT', 0)}；缺失 {agent_counts.get('MISSING', 0)}",
        f"CIO 补数：请求 {cio_enrichment.get('requestCount', 0)}；成功 {cio_enrichment.get('successCount', 0)}；失败 {cio_enrichment.get('failedCount', 0)}",
        f"证据统计：verified {evidence_stats.get('verifiedFacts', 0)}；discovery {evidence_stats.get('discoveryItems', 0)}；missing critical {evidence_stats.get('missingCriticalFacts', 0)}",
    ]

    governed_lines = _governed_summary_lines(governed_rows)
    source_lines = _source_health_lines(health)
    candidate_lines = _candidate_lines(queue)
    missing_files = _missing_daily_source_files(docs_path, run_date)
    decision = _apply_claim_policy_to_decision(_daily_decision(governed_rows), source_health_v2)
    reader_brief = _build_reader_brief(
        run_date=run_date,
        mode=analysis_mode,
        headline=headline,
        governed_lines=governed_lines,
        candidate_lines=candidate_lines,
        source_health_v2=source_health_v2,
        evidence_stats=evidence_stats,
        decision=decision,
        department_reports=department_reports,
        universe=universe,
    )
    department_inputs = build_department_inputs(department_reports, original_refs=original_analysis_refs)
    preferred_evidence_ids = [
        str(evidence_id)
        for report in department_reports
        for evidence_id in report.get("evidenceIds") or []
        if str(evidence_id)
    ]
    evidence_items = _evidence_items(evidence_facts, preferred_ids=preferred_evidence_ids)
    reader_v2 = _build_reader_v2(
        run_date=run_date,
        reader_brief=reader_brief,
        department_reports=department_reports,
        department_inputs=department_inputs,
        original_analysis_refs=original_analysis_refs,
        evidence_items=evidence_items,
        source_health_v2=source_health_v2,
    )
    generated_at = _now_iso()
    reader_v3 = _build_reader_v3(
        run_date=run_date,
        generated_at=generated_at,
        data_as_of=_latest_evidence_time(evidence_facts, fallback=run_date),
        reader_brief=reader_brief,
        department_reports=department_reports,
        department_inputs=department_inputs,
        evidence_items=evidence_items,
        source_health_v2=source_health_v2,
        evidence_stats=evidence_stats,
        decision=decision,
        research_reliability=research_reliability,
        scenario_adjudication=scenario_adjudication,
        universe=universe,
    )
    data_coverage = {
        "mode": analysis_mode,
        "label": _reader_mode_label(analysis_mode),
        "score": source_health_v2.get("overallScore"),
        "missingCriticalFacts": int(evidence_stats.get("missingCriticalFacts") or 0),
    }
    conclusion_confidence = {
        "label": str(research_reliability.get("label") or "结论不足"),
        "headlineSafe": bool(research_reliability.get("headlineSafe")),
        "supportedClaims": int(research_reliability.get("supportedClaims") or 0),
        "hypothesisClaims": int(research_reliability.get("hypothesisClaims") or 0),
        "rejectedClaims": int(research_reliability.get("rejectedClaims") or 0),
    }

    sections = [
        {
            "key": "source",
            "title": "数据源",
            "kind": "source",
            "readerVisible": False,
            "contentMarkdown": "\n".join(source_lines) or "- 未提供数据源健康明细",
            "sourceRefs": _existing_source_refs(docs_path, run_date),
            "confidence": "medium" if source_lines else "low",
        },
        {
            "key": "facts",
            "title": "关键数据",
            "kind": "facts",
            "readerVisible": False,
            "contentMarkdown": "\n".join(f"- {item}" for item in key_facts),
            "confidence": "medium",
        },
        {
            "key": "analysis",
            "title": "推论",
            "kind": "analysis",
            "readerVisible": False,
            "contentMarkdown": _safe_reader_text(
                "\n".join(
                    [
                        headline,
                        "宏观和源健康只决定风险温度与阅读置信度，不能单独触发交易。",
                        "候选池用于发现机会；只有证据链、红蓝对抗、评分卡和 CIO 门控通过后才可进入交易前复核。",
                        "\n".join(candidate_lines),
                    ]
                )
            ),
            "confidence": "medium" if not _is_limited_source_health(source_health) else "low",
        },
        {
            "key": "final_conclusion",
            "title": "总结论",
            "kind": "final_conclusion",
            "readerVisible": False,
            "contentMarkdown": _safe_reader_text(
                "\n".join(
                    governed_lines
                    or ["- 今日没有 completed governed 个股；维持观察，不自动交易。"]
                )
            ),
            "confidence": "medium",
            "blocking": decision.get("gateStatus") == "blocked",
        },
        {
            "key": "next_steps",
            "title": "下一步",
            "kind": "next_steps",
            "readerVisible": False,
            "contentMarkdown": "\n".join(
                [
                    "- 先读总报告，再看源健康和 Agent 卷宗。",
                    "- 宏观源降级时，只做观察和候选筛选。",
                    "- blocked / 低分标的不交易；补公告、业绩、估值和催化剂后再审。",
                ]
            ),
            "confidence": "medium",
        },
        {
            "key": "department_summary",
            "title": "分部门摘要",
            "kind": "analysis",
            "readerVisible": False,
            "contentMarkdown": "\n".join(f"- {row['label']}：{row['summaryForReader']}" for row in _reader_department_reports(department_reports)[:8]) or "- 本轮未记录到分部门结论。",
            "confidence": "medium" if department_reports else "low",
        },
    ]

    run_matrix = load_run_matrix(docs_path, run_date)
    snapshot_refs = build_snapshot_refs(docs_path, run_date, agent_run_id=str(run_matrix.get("runId") or run_date))

    artifact = {
        "schemaVersion": SCHEMA_VERSION,
        "artifactId": f"daily:{run_date}",
        "runDate": run_date,
        "generatedAt": generated_at,
        "artifactType": "daily",
        "audience": "reader",
        "title": f"{run_date} 投研日报",
        "summary": {
            "oneLine": _safe_reader_text(reader_brief["oneLine"]),
            "keyFacts": [_safe_reader_text(item) for item in reader_brief["why"]],
            "analysis": _safe_reader_text(reader_brief["analysis"]),
            "finalConclusion": _safe_reader_text(reader_brief["finalConclusion"]),
            "nextSteps": [_safe_reader_text(item) for item in reader_brief["nextSteps"]],
        },
        "readerBrief": reader_brief,
        "dailyUniverse": universe,
        "sections": sections,
        "sourceHealth": source_health,
        "sourceHealthV2": source_health_v2,
        "analysisMode": analysis_mode,
        "dataCoverage": data_coverage,
        "conclusionConfidence": conclusion_confidence,
        "claimPolicy": source_health_v2.get("claimPolicy") if isinstance(source_health_v2.get("claimPolicy"), dict) else {},
        "claimEvidence": source_health_v2.get("claimEvidence") if isinstance(source_health_v2.get("claimEvidence"), dict) else {},
        "evidenceStats": evidence_stats,
        "evidenceItems": evidence_items,
        "runMatrix": {
            "runId": run_matrix.get("runId") or snapshot_refs.get("agentRunId") or run_date,
            "runDate": run_matrix.get("runDate") or run_date,
        },
        "snapshotRefs": snapshot_refs,
        "decision": decision,
        "cioEnrichment": cio_enrichment,
        "agentModelSelection": agent_model_selection,
        "originalAnalysis": _artifact_original_analysis(original_analysis, run_date),
        "departmentInputs": department_inputs,
        "readerV2": reader_v2,
        "readerV3": reader_v3,
        "researchReliability": research_reliability,
        "departmentReports": department_reports,
        "agentOrigins": {
            "raw": agent_counts.get("RAW_AGENT", 0),
            "derived": agent_counts.get("DERIVED_FROM_ARTIFACT", 0),
            "missing": agent_counts.get("MISSING", 0),
        },
        "agentRuntimeSummary": {
            "llm": agent_runtime_counts.get("LLM", 0),
            "rule": agent_runtime_counts.get("RULE", 0),
            "ruleFallback": agent_runtime_counts.get("RULE_FALLBACK", 0),
            "derivedDiagnostic": agent_runtime_counts.get("DERIVED_DIAGNOSTIC", 0),
            "unknown": agent_runtime_counts.get("unknown", 0),
        },
        "provenance": {
            "origin": "invest-system.static",
            "sourceFiles": _existing_source_refs(docs_path, run_date),
            "generatedBy": "src.report_artifact.build_daily_report_artifact",
            "runId": run_date,
        },
        "publish": {
            "docsPath": f"docs/reports/{run_date}.html",
            "jsonPath": f"docs/reports/{run_date}.artifact.json",
            "htmlPath": f"reports/{run_date}.html",
            "markdownPath": f"daily/{run_date}.md",
            "webPath": f"/reports/{run_date}",
        },
        "quality": {
            "completeness": _daily_completeness(missing_files, source_health, source_health_v2),
            "missingFields": missing_files,
            "validationErrors": [],
        },
    }
    ok, errors = validate_report_artifact(artifact)
    artifact["quality"]["validationErrors"] = errors
    if not ok:
        artifact["quality"]["completeness"] = "failed"
    return artifact


def write_daily_report_artifact(docs_dir: str | Path, run_date: str) -> Dict[str, Any]:
    """Build and persist ``docs/reports/{date}.artifact.json``."""

    docs_path = Path(docs_dir)
    artifact = build_daily_report_artifact(docs_path, run_date)
    _ensure_daily_snapshot_files(docs_path, run_date, artifact)
    artifact = build_daily_report_artifact(docs_path, run_date)
    out = docs_path / "reports" / f"{run_date}.artifact.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return artifact


def _ensure_daily_snapshot_files(docs_path: Path, run_date: str, artifact: Dict[str, Any]) -> None:
    """Persist the snapshot files needed for a publishable daily artifact.

    ``build_daily_report_artifact`` stays side-effect free so API/Web callers can
    inspect artifacts without mutating ``docs/``.  Publishing calls this helper
    before the final build so snapshot hashes are stable.
    """

    run_status_path = docs_path / "run_status" / run_date
    run_status_path.mkdir(parents=True, exist_ok=True)
    for ledger_name in ("provider_runs.jsonl", "evidence_ledger.jsonl"):
        ledger_path = run_status_path / ledger_name
        if not ledger_path.exists():
            ledger_path.write_text("", encoding="utf-8")

    source_health_v2 = artifact.get("sourceHealthV2") if isinstance(artifact.get("sourceHealthV2"), dict) else {}
    source_health_snapshot_path = run_status_path / "source_health_v2.json"
    source_health_snapshot_path.write_text(
        json.dumps(source_health_v2, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not (run_status_path / "run_matrix.json").exists():
        write_run_matrix(
            docs_path,
            run_date,
            stages=[
                {
                    "name": "report_artifact",
                    "status": "partial",
                    "blocking": True,
                    "outputs": [f"reports/{run_date}.artifact.json"],
                }
            ],
        )


def build_stock_artifact_from_history_detail(detail: Dict[str, Any]) -> Dict[str, Any]:
    """Build a reader-facing stock governed artifact from a history detail dict."""

    record_id = detail.get("id")
    query_id = detail.get("query_id") or ""
    stock_code = detail.get("stock_code") or ""
    stock_name = detail.get("stock_name") or stock_code or "未知标的"
    created_at = detail.get("created_at") or _now_iso()
    run_date = str(created_at)[:10] if created_at else _now_iso()[:10]
    raw_result = detail.get("raw_result") if isinstance(detail.get("raw_result"), dict) else {}
    dashboard = raw_result.get("dashboard") if isinstance(raw_result.get("dashboard"), dict) else raw_result
    governance = dashboard.get("governance") if isinstance(dashboard, dict) and isinstance(dashboard.get("governance"), dict) else {}
    trade_plan = governance.get("trade_plan") if isinstance(governance.get("trade_plan"), dict) else {}

    source_refs = _source_refs_from_detail(detail)
    score_value = _first_present(governance.get("score"), detail.get("sentiment_score"), "未知")
    key_facts = [
        f"标的：{stock_name}({stock_code})",
        f"趋势：{detail.get('trend_prediction') or '未给出'}",
        f"评分：{score_value}",
        f"门控：{governance.get('cio_status') or governance.get('gate') or '未给出'}",
    ]
    analysis = detail.get("analysis_summary") or "报告缺少可读分析摘要，需要回看原始记录。"
    operation = detail.get("operation_advice") or "未给出"
    final_conclusion = f"{operation}；最终动作：{trade_plan.get('action') or '需人工复核'}。"
    next_steps = _next_steps(governance, detail)

    artifact = {
        "schemaVersion": SCHEMA_VERSION,
        "artifactId": f"history:{record_id}" if record_id is not None else f"query:{query_id}",
        "runDate": run_date,
        "generatedAt": _now_iso(),
        "artifactType": "stock_governed",
        "audience": "reader",
        "title": f"{stock_name}({stock_code}) governed 报告",
        "summary": {
            "oneLine": str(operation),
            "keyFacts": key_facts,
            "analysis": str(analysis),
            "finalConclusion": final_conclusion,
            "nextSteps": next_steps,
        },
        "sections": [
            {
                "key": "sources",
                "title": "数据源",
                "kind": "source",
                "contentMarkdown": "\n".join(f"- {item}" for item in source_refs) or "- 来源未记录",
                "sourceRefs": source_refs,
                "confidence": "medium" if source_refs else "low",
            },
            {
                "key": "facts",
                "title": "关键数据",
                "kind": "facts",
                "contentMarkdown": "\n".join(f"- {item}" for item in key_facts),
            },
            {
                "key": "analysis",
                "title": "推论",
                "kind": "analysis",
                "contentMarkdown": str(analysis),
            },
            {
                "key": "final_conclusion",
                "title": "总结论",
                "kind": "final_conclusion",
                "contentMarkdown": final_conclusion,
                "blocking": _is_blocked(governance, operation),
            },
            {
                "key": "next_steps",
                "title": "下一步",
                "kind": "next_steps",
                "contentMarkdown": "\n".join(f"- {item}" for item in next_steps),
            },
        ],
        "decision": _decision_from_governance(governance, operation),
        "provenance": {
            "origin": "invest-system.history",
            "sourceFiles": [],
            "generatedBy": "src.report_artifact.build_stock_artifact_from_history_detail",
            "recordId": str(record_id) if record_id is not None else None,
            "queryId": query_id,
        },
        "publish": {},
        "quality": {
            "completeness": "partial" if not source_refs else "complete",
            "missingFields": [] if source_refs else ["sourceRefs"],
            "validationErrors": [],
        },
    }
    ok, errors = validate_report_artifact(artifact)
    artifact["quality"]["validationErrors"] = errors
    if not ok:
        artifact["quality"]["completeness"] = "failed"
    return artifact


def _source_refs_from_detail(detail: Dict[str, Any]) -> List[str]:
    refs: List[str] = []
    if detail.get("news_content"):
        refs.append("history.news_content")
    if detail.get("context_snapshot"):
        refs.append("history.context_snapshot")
    raw_result = detail.get("raw_result")
    if raw_result:
        refs.append("history.raw_result")
    return refs


def _decision_from_governance(governance: Dict[str, Any], operation: Any) -> Dict[str, Any]:
    trade_plan = governance.get("trade_plan") if isinstance(governance.get("trade_plan"), dict) else {}
    action = str(_first_present(trade_plan.get("action"), "")).strip().lower() or _operation_to_action(operation)
    blocked = _is_blocked(governance, operation)
    score_value = _first_present(governance.get("score"), governance.get("total_score"), None)
    target_value = _first_present(trade_plan.get("target_pct"), trade_plan.get("target_position_pct"), None)
    return {
        "action": "no_action" if blocked else action,
        "gateStatus": "blocked" if blocked else ("watch" if action in {"watch", "wait", "hold"} else "passed"),
        "score": _safe_float(score_value),
        "targetPct": 0 if blocked else _safe_float(target_value),
        "blockedReasons": list(governance.get("blocked_reasons") or []) if blocked else [],
    }


def _apply_claim_policy_to_decision(decision: Dict[str, Any], source_health_v2: Dict[str, Any]) -> Dict[str, Any]:
    """Attach evidence caveats without replacing the upstream decision.

    Source health describes how strongly a recommendation is supported.  It is
    not a second trading engine and must not silently turn an upstream
    recommendation into ``no_action`` or erase a suggested range.
    """

    policy = source_health_v2.get("claimPolicy") if isinstance(source_health_v2.get("claimPolicy"), dict) else {}
    out = dict(decision)
    caveats: List[str] = []
    if policy.get("canActionableAdvice") is False:
        caveats.append("actionable_advice_evidence_limited")
    if policy.get("canPositionSizing") is False:
        caveats.append("position_sizing_evidence_limited")
    out["advisoryCaveats"] = caveats
    return out


_AGENT_GAP_DOMAIN_KEYWORDS = {
    "price": (
        "历史日线",
        "ohclv",
        "ohlcv",
        "成交量",
        "技术指标",
        "支撑位",
        "压力位",
        "市场宽度",
        "涨跌家数",
        "成交额",
        "资金流",
        "资金面",
        "capital_flow",
        "market_stats",
        "main_indices",
    ),
    "fundamentals": (
        "财务",
        "财报",
        "估值",
        "基本面",
        "市盈率",
        "成长性",
        "收入增长",
        "腾讯控股",
        "平安银行",
    ),
    "filings_events": (
        "公告",
        "深交所",
        "港交所",
        "hkex",
        "szse",
        "form 4",
        "交易所",
    ),
    "macro": (
        "pmi",
        "社融",
        "cpi",
        "ppi",
        "中国本土关键宏观",
        "宏观经济指标",
    ),
    "news_sentiment": (
        "新闻",
        "舆情",
        "gdelt",
        "媒体叙事",
        "搜索",
    ),
    "portfolio": (
        "持仓",
        "组合",
        "portfolio holdings",
        "风险暴露",
        "集中度",
    ),
}

def _align_source_health_with_agent_outputs(
    source_health_v2: Dict[str, Any],
    *,
    department_reports: List[Dict[str, Any]],
    has_governed_rows: bool,
    daily_universe_mode: str = "",
    daily_subject_count: int = 0,
) -> Dict[str, Any]:
    """Attach department observations without rewriting data health.

    SourceHealth is a measurement of providers/evidence.  Agent uncertainty is
    a conclusion-quality signal and belongs to ``researchReliability``.  Older
    code mixed the two and could turn an Agent phrase into a fake provider
    outage.  Keep this compatibility seam, but make the dependency one-way.
    """

    health = json.loads(json.dumps(source_health_v2, ensure_ascii=False))
    reported_gap_domains = _agent_reported_gap_domains(department_reports)
    no_governed_blocks = not has_governed_rows and not _daily_can_use_department_report(daily_universe_mode, daily_subject_count)
    health["departmentObservations"] = {
        "reportedGapDomains": reported_gap_domains,
        "noCompletedGovernedReport": no_governed_blocks,
        "agentsRecommendNoDecision": _agents_say_no_decision(department_reports),
    }
    return health


def _agent_reported_gap_domains(department_reports: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    domains: Dict[str, List[str]] = {}
    for row in department_reports:
        texts = []
        texts.extend(str(item) for item in (row.get("dataGaps") or []) if str(item))
        texts.extend(str(item) for item in (row.get("counterpoints") or []) if str(item))
        agent = str(row.get("agent") or "")
        if agent in {"RiskAgent", "RiskPositionAgent", "RedTeamAgent", "RedBlueAgent", "CIOAgent", "DecisionReportAgent"}:
            texts.append(str(row.get("summaryForReader") or ""))
        blob = "\n".join(texts).lower()
        if not blob:
            continue
        for domain, keywords in _AGENT_GAP_DOMAIN_KEYWORDS.items():
            if any(keyword.lower() in blob for keyword in keywords):
                reason = _first_gap_reason(texts, keywords)
                domains.setdefault(domain, [])
                if reason and reason not in domains[domain]:
                    domains[domain].append(reason)
    return domains


def _daily_can_use_department_report(mode: str, subject_count: int) -> bool:
    return str(mode or "") in {"multi_subject_daily", "market_and_candidates"} or int(subject_count or 0) > 1


def _first_gap_reason(texts: List[str], keywords: tuple[str, ...]) -> str:
    lowered_keywords = [keyword.lower() for keyword in keywords]
    for text in texts:
        cleaned = str(text or "").strip()
        if cleaned and any(keyword in cleaned.lower() for keyword in lowered_keywords):
            return cleaned[:120]
    for text in texts:
        cleaned = str(text or "").strip()
        if cleaned:
            return cleaned[:120]
    return "Agent 报告存在数据缺口。"


def _agents_say_no_decision(department_reports: List[Dict[str, Any]]) -> bool:
    for row in department_reports:
        if str(row.get("agent") or "") not in {"RiskAgent", "RiskPositionAgent", "RedTeamAgent", "RedBlueAgent", "CIOAgent", "DecisionReportAgent"}:
            continue
        blob = "\n".join(
            [str(row.get("summaryForReader") or "")]
            + [str(item) for item in (row.get("counterpoints") or [])]
            + [str(item) for item in (row.get("dataGaps") or [])]
        )
        if any(token in blob for token in ("无法决策", "信息不足", "盲目下注", "等同于赌博", "无法评估任何潜在操作")):
            return True
    return False


def _operation_to_action(operation: Any) -> str:
    text = str(operation or "").lower()
    if "阻断" in text or "no_action" in text:
        return "no_action"
    if "买" in text or "buy" in text:
        return "buy"
    if "卖" in text or "减" in text or "sell" in text or "reduce" in text:
        return "sell"
    return "watch"


def _is_blocked(governance: Dict[str, Any], operation: Any) -> bool:
    status = str(governance.get("cio_status") or "").upper()
    gate = str(governance.get("gate") or governance.get("gate_result") or "").upper()
    score = _safe_float(_first_present(governance.get("score"), governance.get("total_score"), None))
    action = _operation_to_action(operation)
    return status in {"BLOCKED_BY_FATAL", "NEEDS_EVIDENCE"} or gate == "BLOCKED" or (score is not None and score < 6) or action == "no_action"


def _next_steps(governance: Dict[str, Any], detail: Dict[str, Any]) -> List[str]:
    if _is_blocked(governance, detail.get("operation_advice")):
        return ["补齐阻断证据", "重新运行 governed 审查", "人工复核持仓风险"]
    return ["人工复核数据源", "确认入场条件", "保持无自动交易"]


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _existing_source_refs(docs_dir: Path, run_date: str) -> List[str]:
    compact = run_date.replace("-", "")
    rels = [
        f"daily/{run_date}.md",
        f"governed_results.json",
        f"report_{compact}.md",
        f"market_cycle/{run_date}/01_macro_review.json",
        f"market_cycle/{run_date}/11_deep_review_queue.json",
        f"market_cycle/{run_date}/13_source_health.json",
        f"market_cycle/{run_date}/14_market_strategy.json",
        f"official_events/{run_date}.json",
        f"agent_memos/{run_date}/index.json",
    ]
    return [rel for rel in rels if (docs_dir / rel).exists()]


def _missing_daily_source_files(docs_dir: Path, run_date: str) -> List[str]:
    required = [
        f"daily/{run_date}.md",
        f"market_cycle/{run_date}/13_source_health.json",
        f"market_cycle/{run_date}/14_market_strategy.json",
    ]
    return [rel for rel in required if not (docs_dir / rel).exists()]


def _agent_origin_counts(docs_dir: Path, run_date: str) -> Dict[str, int]:
    counts = {"RAW_AGENT": 0, "DERIVED_FROM_ARTIFACT": 0, "MISSING": 0}
    base = docs_dir / "agent_memos" / run_date
    if not base.exists():
        return counts
    for path in base.rglob("*.json"):
        payload = _read_json(path)
        if not isinstance(payload, dict) or payload.get("schema") != "agent_memo_v1":
            continue
        origin = str(payload.get("origin") or "DERIVED_FROM_ARTIFACT")
        counts[origin] = counts.get(origin, 0) + 1
    return counts


def _agent_runtime_counts(docs_dir: Path, run_date: str) -> Dict[str, int]:
    counts = {"LLM": 0, "RULE": 0, "RULE_FALLBACK": 0, "DERIVED_DIAGNOSTIC": 0, "unknown": 0}
    base = docs_dir / "agent_memos" / run_date
    if not base.exists():
        return counts
    for path in base.rglob("*.json"):
        payload = _read_json(path)
        if not isinstance(payload, dict) or payload.get("schema") != "agent_memo_v1":
            continue
        runtime = str(payload.get("agentRuntime") or payload.get("agent_runtime") or "unknown").strip() or "unknown"
        counts[runtime] = counts.get(runtime, 0) + 1
    return counts


def _load_cio_enrichment(docs_dir: Path, run_date: str) -> Dict[str, Any]:
    payload = _read_json(docs_dir / "run_status" / run_date / "cio_data_requests.json")
    summary = payload.get("summary") if isinstance(payload, dict) and isinstance(payload.get("summary"), dict) else {}
    if not summary:
        return {
            "requested": False,
            "requestCount": 0,
            "successCount": 0,
            "failedCount": 0,
            "addedEvidenceIds": [],
            "remainingGaps": [],
        }
    return {
        "requested": bool(summary.get("requested")),
        "requestCount": int(summary.get("requestCount") or 0),
        "successCount": int(summary.get("successCount") or 0),
        "failedCount": int(summary.get("failedCount") or 0),
        "addedEvidenceIds": list(summary.get("addedEvidenceIds") or []),
        "remainingGaps": list(summary.get("remainingGaps") or []),
    }


def _artifact_original_analysis(original: Dict[str, Any], run_date: str) -> Dict[str, Any]:
    if not isinstance(original, dict) or original.get("schema") != "original_analysis_v1":
        return {
            "runDate": run_date,
            "marketContextAvailable": False,
            "marketReviewAvailable": False,
            "stockContextCount": 0,
            "stockAnalysisCount": 0,
            "decisionSignalCount": 0,
            "portfolioSnapshotAvailable": False,
            "structuredSnapshotAvailable": False,
            "refsPath": f"docs/run_status/{run_date}/original_analysis_refs.jsonl",
        }
    return {
        "runDate": original.get("runDate") or run_date,
        "marketContextAvailable": bool(original.get("marketContextAvailable")),
        "marketReviewAvailable": bool(original.get("marketReviewAvailable")),
        "stockContextCount": int(original.get("stockContextCount") or 0),
        "stockAnalysisCount": int(original.get("stockAnalysisCount") or 0),
        "decisionSignalCount": int(original.get("decisionSignalCount") or 0),
        "portfolioSnapshotAvailable": bool(original.get("portfolioSnapshotAvailable")),
        "structuredSnapshotAvailable": bool(original.get("structuredSnapshotAvailable")),
        "structuredSnapshotPath": original.get("structuredSnapshotPath"),
        "structuredSnapshotSha256": original.get("structuredSnapshotSha256"),
        "refsPath": original.get("refsPath") or f"docs/run_status/{run_date}/original_analysis_refs.jsonl",
        "refCount": int(original.get("refCount") or 0),
        "availableKinds": list(original.get("availableKinds") or []),
        "notes": list(original.get("notes") or [])[:4],
    }


def _build_reader_v2(
    *,
    run_date: str,
    reader_brief: Dict[str, Any],
    department_reports: List[Dict[str, Any]],
    department_inputs: List[Dict[str, Any]],
    original_analysis_refs: List[Dict[str, Any]],
    evidence_items: List[Dict[str, Any]],
    source_health_v2: Dict[str, Any],
) -> Dict[str, Any]:
    visible = _reader_department_reports(department_reports)
    cards = [_reader_v2_department_card(row, department_inputs, evidence_items) for row in visible]
    geo = _first_department(visible, {"GeoPolicyAgent"})
    market = _first_department(visible, {"MarketAgent", "MarketStrategyAgent"})
    risk = _first_department(visible, {"RiskAgent", "RiskPositionAgent", "RedTeamAgent", "RedBlueAgent"})
    evidence_stats = source_health_v2.get("evidenceStats") if isinstance(source_health_v2.get("evidenceStats"), dict) else {}
    risk_bullets = [_safe_reader_text(item) for item in (reader_brief.get("risks") or [])[:5]]
    if not risk_bullets and risk:
        risk_bullets = [_safe_reader_text(risk.get("summaryForReader"))]
    sections = [
        {
            "key": "today",
            "title": "今日总判断",
            "body": _safe_reader_text(reader_brief.get("finalConclusion") or reader_brief.get("oneLine") or "本轮未生成总判断。"),
        },
        {
            "key": "why",
            "title": "核心理由",
            "bullets": [_safe_reader_text(item) for item in (reader_brief.get("why") or [])[:5]],
        },
        {
            "key": "risk",
            "title": "最大风险 / 反证",
            "bullets": risk_bullets,
        },
        {
            "key": "market_geo",
            "title": "市场与地缘状态",
            "bullets": [
                _safe_reader_text(market.get("summaryForReader")) if market else "",
                _safe_reader_text(geo.get("summaryForReader")) if geo else "",
            ],
        },
        {
            "key": "next",
            "title": "下一步",
            "bullets": [_safe_reader_text(item) for item in (reader_brief.get("nextSteps") or [])[:5]],
        },
        {
            "key": "data_confidence",
            "title": "数据可信度",
            "body": _safe_reader_text(reader_brief.get("dataConfidence") or _reader_data_confidence(source_health_v2, evidence_stats)),
        },
    ]
    return {
        "schema": "reader_v2_v1",
        "runDate": run_date,
        "sections": _clean_reader_v2_sections(sections),
        "departmentCards": cards,
        "supportDrawers": _reader_v2_support_drawers(cards, original_analysis_refs, evidence_items),
    }


def _build_reader_v3(
    *,
    run_date: str,
    generated_at: str = "",
    data_as_of: str = "",
    reader_brief: Dict[str, Any],
    department_reports: List[Dict[str, Any]],
    department_inputs: List[Dict[str, Any]],
    evidence_items: List[Dict[str, Any]],
    source_health_v2: Dict[str, Any],
    evidence_stats: Dict[str, Any],
    decision: Dict[str, Any],
    research_reliability: Optional[Dict[str, Any]] = None,
    scenario_adjudication: Optional[Dict[str, Any]] = None,
    universe: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    reliability_provided = research_reliability is not None
    research_reliability = research_reliability or build_research_reliability(department_reports)
    scenario_adjudication = scenario_adjudication or build_scenario_adjudication(department_reports)
    visible = _reader_department_reports(department_reports)
    cards = [_reader_v3_department_card(row, department_inputs, evidence_items) for row in visible]
    challenge_verdicts = build_challenge_verdicts(visible)
    _apply_challenge_verdicts(cards, challenge_verdicts)
    cio = _first_department(visible, {"CIOAgent", "DecisionReportAgent"})
    risk = _first_department(visible, {"RiskAgent", "RiskPositionAgent"})
    red_team = _first_department(visible, {"RedTeamAgent", "RedBlueAgent"})
    market = _first_department(visible, {"MarketAgent", "MarketStrategyAgent"})
    geo = _first_department(visible, {"GeoPolicyAgent"})

    total_gap_count = sum(len(card.get("dataGaps") or []) for card in cards)
    critical_gap_count = int(evidence_stats.get("missingCriticalFacts") or 0)
    if reliability_provided:
        confidence_label = str(research_reliability.get("label") or "结论不足")
    else:
        score = _safe_float(source_health_v2.get("overallScore"))
        confidence_label = "高可信" if score is not None and score >= 0.85 else "中等可信" if score is not None and score >= 0.6 else "低可信"
        if critical_gap_count:
            confidence_label = f"{confidence_label}，带限制"
        elif total_gap_count:
            confidence_label = f"{confidence_label}，含待确认项"

    action_label = _reader_action_label(decision)
    one_line = _reader_cio_headline(
        scenario_adjudication.get("judgment")
        or (cio or {}).get("summaryForReader")
        or reader_brief.get("finalConclusion")
        or reader_brief.get("oneLine")
        or "本轮未生成总判断。"
    )
    if research_reliability.get("audited") and not research_reliability.get("headlineSafe"):
        one_line = "本轮核心裁决未通过证据相关性检查；只保留已验证事实和条件化情景。"
    supported_cio_claims, hypothesis_cio_claims = _reader_claims_by_semantic_status(cio or {})
    key_reasons = _dedupe_nonempty(
        [
            *_product_list(scenario_adjudication.get("sharedFacts"), limit=2),
            *_product_list(supported_cio_claims, limit=2),
            *[f"基准解释：{item}" for item in _product_list(hypothesis_cio_claims, limit=1)],
            *_product_list(reader_brief.get("why"), limit=2),
        ],
        limit=3,
    )
    risk_items = _dedupe_nonempty(
        [
            *_product_list((red_team or {}).get("counterpoints"), limit=2),
            *(
                [f"竞争情景：{_product_copy(scenario_adjudication.get('strongestAlternative'))}"]
                if scenario_adjudication.get("strongestAlternative")
                else []
            ),
            *[
                f"翻转信号：{item}"
                for item in _product_list(scenario_adjudication.get("invalidationTriggers"), limit=1)
            ],
        ],
        limit=3,
    )
    next_steps = _reader_next_steps(
        (cio or {}).get("nextAction"),
        [
            *[
                f"下次复核什么：{item}"
                for item in _dedupe_nonempty(
                    [
                        gap
                        for raw_gap in (cio or {}).get("dataGaps") or []
                        for gap in [_reader_gap_text(raw_gap)]
                        if gap
                    ],
                    limit=3,
                )
            ],
            (risk or {}).get("nextAction"),
            (red_team or {}).get("nextAction"),
            *_product_list(reader_brief.get("nextSteps"), limit=3),
        ],
    )
    max_limitation = _max_reader_limitation(cards, source_health_v2, evidence_stats)
    card_by_agent = {str(card.get("agent") or ""): card for card in cards}
    market_geo = _dedupe_nonempty(
        [
            _product_copy((card_by_agent.get("MarketAgent") or {}).get("conclusion") or ""),
            _product_copy((card_by_agent.get("GeoPolicyAgent") or {}).get("conclusion") or ""),
        ],
        limit=2,
    )
    report_sections = _reader_v3_report_sections(cards, source_health_v2, evidence_stats)
    if not cards:
        legacy_stock_summary = _product_copy(
            reader_brief.get("finalConclusion") or reader_brief.get("analysis")
        )
        if legacy_stock_summary:
            for section in report_sections:
                if section.get("key") == "stocks":
                    section["body"] = legacy_stock_summary
                    break
    public_cards = [_public_reader_v3_department_card(card) for card in cards]

    return {
        "schema": "reader_v3_v1",
        "runDate": run_date,
        "timing": {
            "reportDate": run_date,
            "generatedAt": generated_at,
            "dataAsOf": data_as_of or run_date,
        },
        "hero": {
            "action": action_label,
            "status": _reader_mode_label(str(source_health_v2.get("overallMode") or "")),
            "confidence": confidence_label,
            "oneLine": one_line,
            "maxLimitation": max_limitation,
            "coverage": _reader_market_coverage(universe or {}),
        },
        "assessment": {
            "dataCoverage": _reader_mode_label(str(source_health_v2.get("overallMode") or "")),
            "conclusionConfidence": confidence_label,
        },
        "keyReasons": key_reasons,
        "counterpoints": risk_items,
        "nextSteps": next_steps or ["等待下一次数据刷新后复核。"],
        "marketGeo": market_geo,
        "adjudication": {
            "sharedFacts": _product_list(scenario_adjudication.get("sharedFacts"), limit=3),
            "baseCase": _product_copy(scenario_adjudication.get("baseCase")),
            "strongestAlternative": _product_copy(scenario_adjudication.get("strongestAlternative")),
            "judgment": _reader_adjudication_judgment(scenario_adjudication.get("judgment")),
            "why": _product_copy(scenario_adjudication.get("why")),
            "invalidationTriggers": _product_list(scenario_adjudication.get("invalidationTriggers"), limit=3),
        },
        "challengeVerdicts": [_public_challenge_verdict(row) for row in challenge_verdicts],
        "reliability": {
            "label": confidence_label,
            "headlineSafe": bool(research_reliability.get("headlineSafe")),
            "warnings": _product_list(research_reliability.get("warnings"), limit=3),
            "supportedClaims": research_reliability.get("supportedClaims", 0),
            "hypothesisClaims": research_reliability.get("hypothesisClaims", 0),
            "rejectedClaims": research_reliability.get("rejectedClaims", 0),
        },
        "reportSections": report_sections,
        "dataConfidence": _reader_v3_confidence_copy(
            confidence_label,
            critical_gap_count=critical_gap_count,
            department_gap_count=total_gap_count,
        ),
        "evidenceSummary": {
            "verifiedFacts": evidence_stats.get("verifiedFacts", 0),
            "derivedFacts": evidence_stats.get("derivedFacts", 0),
            "discoveryItems": evidence_stats.get("discoveryItems", 0),
            "missingCriticalFacts": evidence_stats.get("missingCriticalFacts", 0),
            "departmentGapItems": total_gap_count,
        },
        "departmentCards": public_cards,
        "diagnosticsPath": f"reports/{run_date}.diagnostics.html",
    }


def _reader_market_coverage(universe: Mapping[str, Any]) -> str:
    counts = {"A股": 0, "港股": 0, "美股/ETF": 0}
    for raw in universe.get("subjectSymbols") or []:
        symbol = str(raw or "").strip().upper()
        if not symbol:
            continue
        if re.fullmatch(r"HK\d{4,5}", symbol):
            counts["港股"] += 1
        elif re.fullmatch(r"(?:SH|SZ|BJ)?\d{6}", symbol):
            counts["A股"] += 1
        else:
            counts["美股/ETF"] += 1
    parts = [f"{label} {count}" for label, count in counts.items() if count]
    return "覆盖范围：" + "、".join(parts) if parts else ""


def _public_reader_v3_department_card(card: Dict[str, Any]) -> Dict[str, Any]:
    """Remove internal Agent identifiers from the product-facing Reader v3."""

    row = dict(card)
    agent_key = str(card.get("agent") or "")
    label = _DEPARTMENT_LABELS.get(agent_key) or str(card.get("label") or "")
    if not label:
        label = re.sub(r"Agent$", "", agent_key) or "分析部门"
    row["agent"] = _product_copy(label)
    row["label"] = _product_copy(label)
    return row


def _apply_challenge_verdicts(cards: List[Dict[str, Any]], verdicts: List[Dict[str, Any]]) -> None:
    cards_by_agent = {str(card.get("agent") or ""): card for card in cards}
    for verdict in verdicts:
        if str(verdict.get("verdict") or "") != "challenged":
            continue
        card = cards_by_agent.get(str(verdict.get("department") or ""))
        if not card:
            continue
        claim = _product_copy(verdict.get("claim"))
        claims = list(card.get("keyClaims") or [])
        if claim in claims:
            claims.remove(claim)
        else:
            match = re.search(r":(\d+)$", str(verdict.get("targetClaimId") or ""))
            index = int(match.group(1)) - 1 if match else -1
            if 0 <= index < len(claims):
                claim = claims.pop(index)
        card["keyClaims"] = claims
        challenged = list(card.get("challengedClaims") or [])
        challenged.append({
            "claim": claim,
            "status": "存在有效反证，未作为确定依据",
            "opposingScenario": _product_copy(verdict.get("opposingScenario")),
            "falsifier": _product_copy(verdict.get("falsifier")),
        })
        card["challengedClaims"] = challenged


def _public_challenge_verdict(value: Dict[str, Any]) -> Dict[str, Any]:
    department = str(value.get("department") or "")
    return {
        "department": _product_copy(_DEPARTMENT_LABELS.get(department) or re.sub(r"Agent$", "", department)),
        "claim": _product_copy(value.get("claim")),
        "status": "原结论已撤回" if value.get("verdict") == "withdrawn" else "存在有效反证，待裁决",
        "opposingScenario": _product_copy(value.get("opposingScenario")),
        "falsifier": _product_copy(value.get("falsifier")),
    }


def _reader_v3_department_card(row: Dict[str, Any], department_inputs: List[Dict[str, Any]], evidence_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    card = _reader_v2_department_card(row, department_inputs, evidence_items)
    return {
        "agent": card.get("agent"),
        "label": _product_copy(card.get("label")),
        "conclusion": _reader_department_conclusion(row, card.get("conclusion")),
        "keyClaims": _reader_department_claims(row, card.get("keyClaims")),
        "counterpoints": _product_list(card.get("counterpoints"), limit=2),
        "dataGaps": _product_list(card.get("dataGaps"), limit=2),
        "nextAction": _product_copy(card.get("nextAction")),
        "nextActions": [
            _concise_numbered_step(item)
            for item in _split_reader_steps(card.get("nextAction"))
        ][:3],
        "confidence": card.get("confidence") or "medium",
        "supportSignals": _product_list(card.get("supportSignals"), limit=3),
        "evidenceSamples": [
            _reader_v3_evidence_sample(item)
            for item in card.get("evidenceSamples") or []
            if isinstance(item, dict)
        ],
    }


def _reader_department_conclusion(row: Dict[str, Any], value: Any) -> str:
    text = _product_copy(value)
    text = re.sub(
        r"前序部门关于[“\"]防御板块价格表现相对抗跌；是否属于主动资金抱团仍待资金流与市场宽度验证、"
        r"跨市场联动减弱[”\"]的基准判断存在严重的[‘']单股污染[’']与[‘']时效错配[’']",
        "前序部门把少数防御样本的相对抗跌解释为资金抱团，并据此判断跨市场联动减弱；"
        "该结论存在单股污染与时效错配",
        text,
    )
    semantic = row.get("semanticValidation") if isinstance(row.get("semanticValidation"), dict) else {}
    summary = semantic.get("summary") if isinstance(semantic.get("summary"), dict) else {}
    status = str(summary.get("status") or "").lower()
    if status in {"hypothesis", "disputed"} and text and not text.startswith("部门判断："):
        return f"部门判断：{text}"
    return text


def _reader_department_claims(row: Dict[str, Any], fallback: Any) -> List[str]:
    claims: List[str] = []
    for item in row.get("claimEvidence") or []:
        if not isinstance(item, dict):
            continue
        text = _product_copy(item.get("claim") or item.get("text"))
        status = str(item.get("semanticStatus") or item.get("status") or "").lower()
        if not text or status == "rejected" or text.endswith(("：", ":")):
            continue
        if status in {"hypothesis", "disputed"} and not text.startswith("解释性判断："):
            text = f"解释性判断：{text}"
        claims.append(text)
    return _dedupe_nonempty(claims, limit=3) or _product_list(fallback, limit=3)


def _reader_v3_evidence_sample(item: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(item)
    if str(item.get("metric") or "") == "main_indices" and isinstance(item.get("measurements"), dict):
        row["label"] = _main_indices_measurement_label(item.get("measurements") or {})
    else:
        row["label"] = _reader_evidence_label(item.get("label") or "")
    row["provider"] = {
        "DataFetcherManager": "原系统数据聚合",
        "YfinanceFundamentalAdapter": "公开财务数据",
        "TushareFetcher": "Tushare 行情",
        "SEC_EDGAR": "SEC 官方披露",
        "CNINFO": "巨潮资讯官方公告",
    }.get(str(item.get("provider") or ""), _product_copy(item.get("provider") or ""))
    row["factType"] = {
        "verified_fact": "已验证事实",
        "derived_fact": "推导事实",
        "discovery": "发现线索",
        "agent_opinion": "部门判断",
        "final_claim": "最终判断",
    }.get(str(item.get("factType") or ""), _product_copy(item.get("factType") or ""))
    return row


def _reader_v3_confidence_copy(
    confidence_label: str,
    *,
    critical_gap_count: int,
    department_gap_count: int,
) -> str:
    if critical_gap_count:
        return f"{confidence_label}；仍有 {critical_gap_count} 个关键证据缺口，结论需带限制阅读。"
    if department_gap_count:
        return (
            f"{confidence_label}；核心证据链完整，"
            f"另有 {department_gap_count} 个部门待确认项影响细分判断。"
        )
    return f"{confidence_label}；核心证据链完整。"


def _reader_evidence_label(value: Any) -> str:
    """Turn ledger payloads into concise reader copy.

    Raw field names and complete provider payloads stay available in
    Diagnostics.  Reader evidence is a short, human-readable citation.
    """
    text = _product_copy(value)
    if not text:
        return ""

    if "main_indices records=" in text or text.startswith("主要指数行情"):
        items = _name_change_items(text, limit=6)
        return f"主要指数：{'、'.join(items)}" if items else "主要指数行情快照"
    if "行业强弱排行 records=" in text:
        items = _name_change_items(text, limit=5)
        return f"行业强弱：{'、'.join(items)}" if items else "行业强弱排行快照"
    if "热门标的列表 records=" in text:
        items = _name_change_items(text, limit=6)
        return f"热门标的：{'、'.join(items)}" if items else "热门标的快照"
    if (
        "market_stats records=" in text
        or text.startswith("市场统计 records=")
        or text.startswith("市场宽度")
    ):
        fields = _named_number_fields(text)
        labels = (
            ("up_count", "上涨"),
            ("down_count", "下跌"),
            ("flat_count", "平盘"),
            ("limit_up_count", "涨停"),
            ("limit_down_count", "跌停"),
        )
        parts = [f"{label} {int(fields[key])}" for key, label in labels if key in fields]
        return f"市场宽度：{'，'.join(parts)}" if parts else "市场宽度快照"
    if text.startswith("growth available:") or text.startswith("增长 available:"):
        fields = _named_number_fields(text)
        labels = (
            ("revenue_yoy", "营收同比"),
            ("net_profit_yoy", "净利润同比"),
            ("roe", "ROE"),
            ("gross_margin", "毛利率"),
        )
        parts = [f"{label} {_format_percent(fields[key])}" for key, label in labels if key in fields]
        return f"基本面增长：{'，'.join(parts)}" if parts else "基本面增长快照"
    if text.startswith("earnings available:") or text.startswith("财报 available:"):
        date = _regex_group(text, r"report_date=([^,\]]+)")
        currency = _regex_group(text, r"currency=([^,\]]+)")
        fields = _named_number_fields(text)
        parts = []
        if date:
            parts.append(f"报告期 {date}")
        for key, label in (
            ("revenue", "营收"),
            ("net_profit_parent", "归母净利润"),
            ("operating_cash_flow", "经营现金流"),
        ):
            if key in fields:
                parts.append(f"{label} {_format_amount(fields[key], currency)}")
        if "roe" in fields:
            parts.append(f"ROE {_format_percent(fields['roe'])}")
        return f"财报快照：{'，'.join(parts)}" if parts else "财报与分红快照"
    if text.startswith("quote ") or text.startswith("行情 "):
        fields = _named_number_fields(text)
        price = fields.get("行情") or fields.get("price") or fields.get("current")
        change = fields.get("change_pct")
        parts = []
        if price is not None:
            parts.append(f"现价 {price:g}")
        if change is not None:
            parts.append(f"涨跌幅 {_format_percent(change)}")
        return f"行情快照：{'，'.join(parts)}" if parts else "行情快照"
    if re.match(r"^4\s+\d{4}-\d{2}-\d{2}\s+", text):
        date = _regex_group(text, r"^4\s+(\d{4}-\d{2}-\d{2})")
        return f"SEC Form 4 高管持股变动披露 · {date}" if date else "SEC Form 4 高管持股变动披露"
    if re.match(r"^[A-Z0-9]+=[^@]+@\s*\d{4}-\d{2}-\d{2}$", text):
        code = text.split("=", 1)[0]
        names = {
            "DGS10": "美国10年期国债收益率",
            "VIXCLS": "VIX 波动率指数",
            "BAMLH0A0HYM2": "美国高收益债利差",
        }
        return text.replace(code, names.get(code, code), 1)

    cleaned = re.sub(r"\brecords=\d+;?\s*", "", text)
    cleaned = re.sub(r"\b(code|change_pct|report_date)=", "", cleaned)
    return cleaned[:220].rstrip("；;，, ") + ("…" if len(cleaned) > 220 else "")


def _name_change_items(text: str, *, limit: int) -> List[str]:
    out: List[str] = []
    for chunk in text.split("|"):
        name = _regex_group(chunk, r"name=([^,|]+)")
        change = _regex_group(chunk, r"change_pct=(-?\d+(?:\.\d+)?)")
        if not name:
            continue
        out.append(f"{name.strip()} {_format_percent(float(change))}" if change else name.strip())
        if len(out) >= limit:
            break
    return out


def _named_number_fields(text: str) -> Dict[str, float]:
    return {
        key: float(raw)
        for key, raw in re.findall(r"([A-Za-z_\u4e00-\u9fff]+)=(-?\d+(?:\.\d+)?)", text)
    }


def _regex_group(text: str, pattern: str) -> str:
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""


def _format_percent(value: float) -> str:
    return f"{value:+.2f}%" if value != 0 else "0.00%"


def _main_indices_measurement_label(measurements: Dict[str, Any]) -> str:
    names = (
        ("index_sh000001_change_pct", "上证指数"),
        ("index_sz399001_change_pct", "深证成指"),
        ("index_sz399006_change_pct", "创业板指"),
        ("index_sh000688_change_pct", "科创50"),
        ("index_sh000016_change_pct", "上证50"),
        ("index_sh000300_change_pct", "沪深300"),
    )
    parts: List[str] = []
    for key, name in names:
        try:
            value = float(measurements[key])
        except (KeyError, TypeError, ValueError):
            continue
        parts.append(f"{name} {_format_percent(value)}")
    return f"主要指数：{'、'.join(parts)}" if parts else "主要指数行情快照"


def _format_amount(value: float, currency: str) -> str:
    unit = currency or ""
    if abs(value) >= 100_000_000:
        return f"{value / 100_000_000:.2f} 亿 {unit}".strip()
    if abs(value) >= 10_000:
        return f"{value / 10_000:.2f} 万 {unit}".strip()
    return f"{value:g} {unit}".strip()


def _reader_v3_report_sections(
    cards: List[Dict[str, Any]],
    source_health_v2: Dict[str, Any],
    evidence_stats: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Build the fixed product report structure for Web and static Reader.

    Department cards remain the detailed drawer.  These sections are the
    reader-facing outline the user asked for: market first, then macro/geo,
    sector, candidates, stocks, portfolio, risk, confidence and next action.
    """

    section_specs = [
        ("market_status", "市场状态", {"MarketAgent"}),
        ("macro_geo", "宏观与地缘", {"MacroAgent", "GeoPolicyAgent"}),
        ("sector_style", "行业/风格", {"SectorAgent"}),
        ("candidates", "候选观察", {"SectorAgent", "IntelAgent"}),
        ("stocks", "重点个股", {"FundamentalAgent", "TechnicalAgent"}),
        ("portfolio", "持仓影响", {"PortfolioAgent"}),
        ("risk", "风险和反证", {"RiskAgent", "RedTeamAgent"}),
    ]
    sections: List[Dict[str, Any]] = []
    for key, title, agents in section_specs:
        rows = _reader_cards_for_agents(cards, agents)
        sections.append(
            {
                "key": key,
                "title": title,
                "body": _section_body(rows, title),
                "bullets": _section_bullets(rows),
                "counterpoints": _section_counterpoints(rows),
                "nextActions": _section_next_actions(rows),
                "evidenceSamples": _section_evidence_samples(rows),
            }
        )
    critical = int(evidence_stats.get("missingCriticalFacts") or 0)
    sections.append(
        {
            "key": "data_confidence",
            "title": "数据可信度",
            "body": (
                "核心证据链完整；部门待确认项只作为人工复核提示。"
                if critical == 0
                else f"仍有 {critical} 个关键证据缺口，结论需要降级阅读。"
            ),
            "bullets": [
                f"已验证事实 {evidence_stats.get('verifiedFacts', 0)}",
                f"推导事实 {evidence_stats.get('derivedFacts', 0)}",
                f"发现线索 {evidence_stats.get('discoveryItems', 0)}",
                _reader_mode_label(str(source_health_v2.get("overallMode") or "")),
            ],
            "counterpoints": [],
            "nextActions": [],
            "evidenceSamples": [],
        }
    )
    return sections


def _reader_cards_for_agents(cards: List[Dict[str, Any]], agents: set[str]) -> List[Dict[str, Any]]:
    return [card for card in cards if str(card.get("agent") or "") in agents]


def _section_body(rows: List[Dict[str, Any]], fallback_title: str) -> str:
    conclusions = _dedupe_nonempty(
        [_product_copy(row.get("conclusion")) for row in rows],
        limit=2,
    )
    if conclusions:
        return " ".join(conclusions)
    return f"{fallback_title}本轮未形成独立结论。"


def _section_bullets(rows: List[Dict[str, Any]]) -> List[str]:
    values: List[str] = []
    for row in rows:
        values.extend(_product_list(row.get("keyClaims"), limit=3))
        values.extend(_product_list(row.get("supportSignals"), limit=2))
    return _dedupe_nonempty(values, limit=5)


def _section_counterpoints(rows: List[Dict[str, Any]]) -> List[str]:
    values: List[str] = []
    for row in rows:
        values.extend(_product_list(row.get("counterpoints"), limit=2))
        values.extend(_product_list(row.get("dataGaps"), limit=1))
    return _dedupe_nonempty(values, limit=4)


def _section_next_actions(rows: List[Dict[str, Any]]) -> List[str]:
    return _dedupe_nonempty(
        [_product_copy(row.get("nextAction")) for row in rows],
        limit=3,
    )


def _section_evidence_samples(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    samples: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        for item in row.get("evidenceSamples") or []:
            if not isinstance(item, dict):
                continue
            key = str(item.get("id") or item.get("label") or "")
            if key in seen:
                continue
            seen.add(key)
            samples.append(item)
            if len(samples) >= 5:
                return samples
    return samples


def _reader_action_label(decision: Dict[str, Any]) -> str:
    action = str(decision.get("action") or "watch").lower()
    gate = str(decision.get("gateStatus") or "").lower()
    if gate == "blocked" or action == "no_action":
        return "不操作"
    if action in {"buy", "sell", "hold"}:
        return _human_action(action)
    return "观察"


def _reader_mode_label(mode: str) -> str:
    return {
        "FULL_REVIEW": "完整复盘",
        "LIMITED_REVIEW": "有限复盘",
        "SCREEN_ONLY": "仅筛选观察",
        "OBSERVE_ONLY": "市场观察",
        "BLOCKED": "数据不足",
    }.get(str(mode or "").upper(), "投研复盘")


def _max_reader_limitation(cards: List[Dict[str, Any]], source_health_v2: Dict[str, Any], evidence_stats: Dict[str, Any]) -> str:
    critical = evidence_stats.get("missingCriticalFacts") or 0
    if critical:
        return f"仍有 {critical} 个关键证据缺口，结论需要降级阅读。"
    blockers = source_health_v2.get("blockingReasons") if isinstance(source_health_v2.get("blockingReasons"), list) else []
    mode = str(source_health_v2.get("overallMode") or "").upper()
    if blockers and mode != "FULL_REVIEW":
        return _product_copy(_human_blocking_reason(str(blockers[0])))
    department_gaps = sum(len(card.get("dataGaps") or []) for card in cards)
    if department_gaps:
        gaps = [str(gap) for card in cards for gap in card.get("dataGaps") or [] if str(gap).strip()]
        joined = " ".join(gaps)
        items: List[str] = []
        if any(token in joined for token in ("氦气", "霍尔木兹", "美伊", "商务部", "海关总署")):
            items.append("地缘与贸易传闻仍需官方原文核验")
        if any(token in joined for token in ("真实持仓", "持仓标的", "成本价", "total_aum")):
            items.append("未接入真实持仓快照")
        if not items:
            items.append(f"仍有 {department_gaps} 个部门待确认项影响细分判断")
        return f"核心证据链完整；{'；'.join(items)}。"
    return "核心证据链完整；结论仍需人工复核，不自动执行交易。"


def _split_reader_steps(value: Any) -> List[str]:
    if isinstance(value, str):
        raw = value.strip()
        if raw.startswith("{") and raw.endswith("}"):
            try:
                parsed = ast.literal_eval(raw)
            except (SyntaxError, ValueError):
                parsed = None
            if isinstance(parsed, dict):
                value = parsed
    if isinstance(value, dict):
        aliases = {
            "不做什么": ("不做什么", "不要做", "禁止操作", "操作纪律", "do_not", "avoid"),
            "看什么": (
                "看什么", "观察信号", "核心观察信号", "风险升级触发条件",
                "风险缓解触发条件", "风险升级信号", "风险解除信号", "watch", "signals",
            ),
            "下次复核什么": ("下次复核什么", "下次复核", "review", "next_review"),
        }
        rows: List[str] = []
        for label, keys in aliases.items():
            bodies = [_product_copy(value.get(key)) for key in keys if value.get(key)]
            clean = _clean_step_body("；".join(bodies))
            if clean:
                rows.append(f"{label}：{clean}")
        return rows[:3]
    text = _product_copy(value)
    if not text:
        return []
    text = re.sub(r"\s+", " ", text)
    marker_pattern = (
        r"(?:^|[\s；;*])(?:\d+[.)、]\s*)?"
        r"(操作纪律|禁止操作|不做之事|不做什么|不要做|核心观察信号|观察信号|风险升级触发条件|风险缓解触发条件|风险升级信号|风险解除信号|风险降级信号|看什么|数据修复后行动|数据恢复后行动|数据补齐后行动|下次复核什么|下次复核)"
        r"(?:（[^）]*）|\([^)]*\))?\s*[:：]"
    )
    parts = re.split(marker_pattern, text)
    if len(parts) > 1:
        grouped: Dict[str, List[str]] = {
            "不做什么": [],
            "看什么": [],
            "下次复核什么": [],
        }
        for idx in range(1, len(parts), 2):
            marker = (parts[idx] or "").strip()
            body = (parts[idx + 1] if idx + 1 < len(parts) else "").strip(" *；;")
            if not body:
                continue
            if marker in {"操作纪律", "禁止操作", "不做之事", "不做什么", "不要做"}:
                label = "不做什么"
            elif marker in {
                "核心观察信号",
                "观察信号",
                "风险升级触发条件",
                "风险缓解触发条件",
                "风险升级信号",
                "风险解除信号",
                "看什么",
            }:
                label = "看什么"
            else:
                label = "下次复核什么"
            grouped[label].append(_clean_step_body(_product_copy(body)))
        sections = [
            _product_copy(f"{label}：{_clean_step_body('；'.join(_dedupe_nonempty(grouped[label], limit=3)))}")
            for label in ("不做什么", "看什么", "下次复核什么")
            if grouped[label]
        ]
        if sections:
            return _dedupe_nonempty(sections, limit=3)
    parts = re.split(
        r"(?:\n+|\n\s*[-•]\s+|(?:^|[；;]\s*)\d+[.)、]\s*)",
        text,
    )
    rows = [part.strip(" -•；;") for part in parts if part and part.strip(" -•；;")]
    return _dedupe_nonempty(rows, limit=3) if rows else [text]


def _reader_next_steps(primary: Any, fallback: Any) -> List[str]:
    grouped: Dict[str, List[str]] = {
        "不做什么": [],
        "看什么": [],
        "下次复核什么": [],
    }
    for row in _split_reader_steps(primary):
        matched = False
        for label in grouped:
            prefix = f"{label}："
            if row.startswith(prefix):
                grouped[label].append(row[len(prefix):])
                matched = True
                break
        if not matched:
            grouped["看什么"].append(row)
    for row in _product_list(fallback, limit=3):
        matched = False
        for label in grouped:
            prefix = f"{label}："
            if row.startswith(prefix):
                if not grouped[label]:
                    grouped[label].append(row[len(prefix):])
                matched = True
                break
        if not matched:
            normalized = re.sub(r"^下次复核(?:什么)?\s*[:：]?\s*", "", row).strip()
            if not grouped["下次复核什么"]:
                grouped["下次复核什么"].append(normalized or row)
    if not grouped["不做什么"]:
        grouped["不做什么"].append("不要把单一标的或单日波动直接外推为全市场结论")
    return [
        _product_copy(f"{label}：{_clean_step_body(grouped[label][0])}")
        for label in ("不做什么", "看什么", "下次复核什么")
        if grouped[label]
    ][:3]


def _first_numbered_item(text: str) -> str:
    parts = [
        part.strip(" ；;。")
        for part in re.split(r"(?:^|\s+)\d+[.)、]\s*", str(text or ""))
        if part.strip(" ；;。")
    ]
    return parts[0] if parts else str(text or "").strip()


def _clean_step_body(text: str) -> str:
    value = re.sub(r"[；;]{2,}", "；", str(text or "")).strip(" ；;。")
    value = re.sub(r"(?:^|[；;])\s*(?:待验证情景|情景判断)\s*[:：]\s*", "；", value).strip(" ；;。")
    numbered = [
        part.strip(" ；;。")
        for part in re.split(r"(?:^|[；;\s])\d+[.)、]\s*", value)
        if part.strip(" ；;。")
    ]
    if len(numbered) > 1:
        return "；".join(_dedupe_nonempty(numbered, limit=2))
    clauses = [part.strip() for part in value.split("；") if part.strip()]
    return "；".join(_dedupe_nonempty(clauses, limit=3))


def _concise_numbered_step(text: str) -> str:
    value = str(text or "").strip()
    for label in ("不做什么", "看什么", "下次复核什么"):
        prefix = f"{label}："
        if value.startswith(prefix):
            return f"{prefix}{_first_numbered_item(value[len(prefix):])}"
    return _first_numbered_item(value)


def _reader_claims_by_semantic_status(card: Dict[str, Any]) -> tuple[List[str], List[str]]:
    """Keep facts/partial claims ahead of hypotheses in the executive summary."""

    supported: List[str] = []
    hypotheses: List[str] = []
    for row in card.get("claimEvidence") or []:
        if not isinstance(row, dict):
            continue
        claim = _product_copy(row.get("claim") or row.get("text"))
        status = str(row.get("semanticStatus") or row.get("status") or "").lower()
        if not claim:
            continue
        if status in {"supported", "partial"}:
            supported.append(claim)
        elif status in {"hypothesis", "disputed"}:
            hypotheses.append(claim)
    if not supported and not hypotheses:
        supported = _product_list(card.get("keyClaims"), limit=3)
    return _dedupe_nonempty(supported, limit=3), _dedupe_nonempty(hypotheses, limit=3)


def _product_list(value: Any, *, limit: int) -> List[str]:
    if isinstance(value, list):
        raw = value
    elif value:
        raw = [value]
    else:
        raw = []
    return _dedupe_nonempty([_product_copy(item) for item in raw], limit=limit)


def _dedupe_nonempty(items: List[str], *, limit: int) -> List[str]:
    out: List[str] = []
    for item in items:
        text = _product_copy(item)
        if not text or text in out:
            continue
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _product_value_to_text(value: Any) -> str:
    if isinstance(value, dict):
        parts: List[str] = []
        claim = value.get("claim") or value.get("point")
        basis = value.get("basis") or value.get("reason") or value.get("rationale")
        if claim:
            claim_text = _product_value_to_text(claim)
            basis_text = _product_value_to_text(basis) if basis else ""
            return f"{claim_text}。依据：{basis_text}" if basis_text else claim_text
        value_type = str(value.get("type") or "").strip()
        description = value.get("description") or value.get("summary") or value.get("message") or value.get("reason")
        if value_type and description:
            parts.append(f"{value_type}：{_product_value_to_text(description)}")
        elif description:
            parts.append(_product_value_to_text(description))
        elif value_type:
            parts.append(value_type)

        do_not = value.get("do_not") or value.get("avoid")
        if do_not:
            parts.append(f"不要做：{_product_value_to_text(do_not)}")

        conditions = value.get("conditions")
        if conditions:
            parts.append(f"触发条件：{_product_value_to_text(conditions)}")

        triggers = value.get("triggers")
        if isinstance(triggers, list):
            for trigger in triggers[:3]:
                trigger_text = _product_value_to_text(trigger)
                if trigger_text:
                    parts.append(trigger_text)

        if not parts:
            for key in ("value", "label", "title", "next_action", "next_step"):
                if value.get(key):
                    parts.append(_product_value_to_text(value.get(key)))
                    break
        if not parts:
            parts = [
                f"{key}：{_product_value_to_text(item)}"
                for key, item in value.items()
                if item not in (None, "", [])
            ][:4]
        return "；".join(part for part in parts if part)
    if isinstance(value, list):
        return "；".join(_product_value_to_text(item) for item in value if item not in (None, "", []))
    return str(value or "")


def _product_copy(value: Any) -> str:
    if isinstance(value, str):
        raw = value.strip()
        if raw and raw[0] in "{[" and raw[-1] in "}]":
            try:
                parsed = ast.literal_eval(raw)
            except (SyntaxError, ValueError):
                parsed = None
            if isinstance(parsed, (dict, list)):
                return _product_copy(parsed)
    text = _safe_reader_text(_product_value_to_text(value))
    replacements = {
        "RedTeamAgent": "红队",
        "RiskAgent": "风险部门",
        "MarketAgent": "市场部门",
        "SectorAgent": "行业部门",
        "TechnicalAgent": "技术部门",
        "FundamentalAgent": "基本面部门",
        "MacroAgent": "宏观部门",
        "GeoPolicyAgent": "地缘政策部门",
        "CIOAgent": "CIO",
        "capital_flow": "资金流",
        "concept_rankings": "概念主题排行",
        "sector_rankings": "行业强弱排行",
        "hot_stocks": "热门标的列表",
        "originalAnalysisRefs": "上游分析材料",
        "portfolio_snapshot": "持仓快照",
        "quantity": "持仓数量",
        "market_value": "持仓市值",
        "cost_basis": "成本价",
        "fundamental_context": "结构化基本面上下文",
        "subject_fundamental_depth_incomplete": "部分标的基本面深度不足",
        "realtime_quote": "实时行情",
        "daily_data": "日线数据",
        "not_supported": "暂未适配",
        "rate_limited": "限流",
        "auth_missing": "缺授权",
        "provider_run": "数据源记录",
        "record_count": "记录数",
        "sourceHealthV2": "数据健康",
        "providerMatrix": "数据源矩阵",
        "claimPolicy": "结论规则",
        "artifactId": "报告编号",
        "Tavily": "第三方搜索线索",
        "RAW_AGENT": "真实分析",
        "DERIVED_FROM_ARTIFACT": "历史材料整理",
        "FULL_REVIEW": "完整复盘",
        "LIMITED_REVIEW": "有限复盘",
        "verified_fact": "已验证事实",
        "verified fact": "已验证事实",
        "derived_fact": "推导事实",
        "discovery": "发现线索",
        "Discovery": "搜索线索",
        "main_indices": "主要指数行情",
        "market_stats": "市场宽度",
        "agent_opinion": "部门判断",
        "final_claim": "最终判断",
        "待验证情景：": "情景判断：",
        "关键数据缺失": "关键待确认项",
        "关键数据缺口": "关键待确认项",
        "关键待确认项修复前": "关键待确认项补齐前",
        "数据修复": "下次复核",
        "数据恢复后": "下次复核后",
        "数据缺口": "待确认项",
        "指数崩塌": "指数大幅下跌",
        "崩塌式下跌": "大幅下跌",
        "暴跌": "大幅下跌",
        "高位科技股在结构性多头踩踏": "高位科技股出现结构性多头踩踏",
        "个股虚涨": "个股上涨持续性存疑",
        "虚假繁荣": "上涨持续性存疑",
        "高危": "高风险",
        "禁止追涨": "不要追涨",
        "禁止基于": "不应仅基于",
        "不能再将": "不宜继续将",
        "法批公告": "法披公告",
        "原系统市场分析层：主要指数行情 ；市场宽度": "已纳入主要指数与市场宽度",
        "第三方搜索线索 网页抓取的媒体传闻": "媒体报道线索",
        "第三方搜索线索 媒体发现线索": "媒体线索",
        "第三方搜索线索 发现线索": "媒体线索",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    if text.startswith("情景判断："):
        text = "情景判断：" + text[len("情景判断："):].replace("情景判断：", "")
    text = re.sub(
        r"\s*[（(][^（）()]{0,240}(?:subject|fred|sec|cninfo|intelligence):[^（）()]{0,240}[）)]",
        "",
        text,
        flags=re.I,
    )
    text = _strip_reader_raw_fields(text)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = text.replace("*", "")
    text = text.replace("`", "")
    text = re.sub(r"\bpartial\b", "部分可用", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(success|failed|empty)\s*\(\d+\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+-\s+", "；", text)
    text = re.sub(r"^\s*[-•]\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -•；;")
    return text


def _reader_cio_headline(value: Any) -> str:
    """Keep the hero decisive, short and explicitly framed as adjudication."""

    text = _reader_adjudication_judgment(value)
    if not text:
        return "当前基准判断：本轮未生成总判断。"
    first = next(
        (item.strip() for item in re.split(r"(?<=[。！？!?])", text) if item.strip()),
        text,
    )
    first = first.rstrip("。！？!?") + "。"
    if first.startswith(("当前基准判断：", "当前判断：", "今日结论：")):
        return first
    return f"当前基准判断：{first}"


def _reader_adjudication_judgment(value: Any) -> str:
    """Render a decision, not an alarmist summary of both sides."""

    text = _product_copy(value)
    if not text:
        return ""
    match = re.search(
        r"(?:当前)?裁决偏向基准情景(?:，即)?[“\"]?([^”\"，。；]+)[”\"]?"
        r"，但必须对最强竞争情景[（(]([^）)]+)[）)]保持高度警惕",
        text,
    )
    if match:
        return (
            f"当前基准判断：{match.group(1).strip()}；"
            f"{match.group(2).strip()}仅作为竞争情景，出现翻转信号时再切换判断"
        )
    return text.replace("最强相反情景", "最强竞争情景")


def _strip_reader_raw_fields(text: str) -> str:
    value = str(text or "")
    claim_match = re.search(r"(?:^|[；;]\s*)(?:claim|point|主张|观点)[:：]\s*(.*?)(?=[；;]\s*(?:basis|依据|evidence_ids|证据|$)|$)", value, flags=re.I)
    basis_match = re.search(r"(?:^|[；;]\s*)(?:basis|依据)[:：]\s*(.*?)(?=[；;]\s*(?:evidence_ids|证据|$)|$)", value, flags=re.I)
    if claim_match:
        claim = claim_match.group(1).strip(" ；;")
        basis = basis_match.group(1).strip(" ；;") if basis_match else ""
        value = f"{claim}。依据：{basis}" if basis else claim
    value = re.sub(r"(?:^|[；;]\s*)(?:evidence_ids|证据\s*id|证据ID|source_refs)[:：]\s*[^。]*", "", value, flags=re.I)
    value = re.sub(r"\b(?:memo|subject|tavily|fred|sec|cninfo|official|cio):[^\s，。；;、]+", "", value, flags=re.I)
    value = re.sub(r"\bproviderSummary\b|\boriginalAnalysisSummary\b", "", value)
    value = re.sub(r"\s*；\s*；+", "；", value)
    value = re.sub(r"([\u4e00-\u9fffA-Za-z]+)[(（]\1[)）]", r"\1", value)
    value = re.sub(r"(?<=[和、，,])-\s*", "", value)
    value = value.replace("。。依据", "。依据")
    value = value.replace("。。", "。")
    value = value.replace("。；", "；")
    value = re.sub(r"\s+", " ", value)
    return value.strip(" ；;。")


def _reader_v2_department_card(row: Dict[str, Any], department_inputs: List[Dict[str, Any]], evidence_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    agent = str(row.get("agent") or "")
    profile = next((item for item in department_inputs if item.get("agent") == agent), {})
    evidence_ids = [str(item) for item in row.get("evidenceIds") or [] if str(item)]
    samples = _evidence_samples(evidence_items, evidence_ids, limit=3)
    support_signals = [
        signal
        for ref in profile.get("originalAnalysisRefs") or []
        if isinstance(ref, dict)
        for signal in [_reader_support_signal(ref)]
        if signal
    ][:4]
    return {
        "agent": agent,
        "label": _safe_reader_text(row.get("label") or agent),
        "conclusion": _safe_reader_text(row.get("summaryForReader") or "本部门未给出可读结论。"),
        "keyClaims": [_safe_reader_text(item) for item in (row.get("keyClaims") or [])[:5]],
        "counterpoints": [_safe_reader_text(item) for item in (row.get("counterpoints") or [])[:4]],
        "dataGaps": [_reader_gap_text(item) for item in (row.get("dataGaps") or [])[:4] if _reader_gap_text(item)],
        "nextAction": _safe_reader_text(row.get("nextAction") or ""),
        "confidence": row.get("confidence") or "medium",
        "supportSignals": support_signals,
        "evidenceIds": evidence_ids[:8],
        "evidenceSamples": samples,
    }


def _reader_support_signal(ref: Dict[str, Any]) -> str:
    kind = str(ref.get("kind") or "")
    summary = str(ref.get("summary") or "")
    symbols = [str(item) for item in ref.get("symbols") or [] if str(item)]
    symbol_text = "、".join(symbols[:4])
    if kind == "market_review":
        return "已纳入主要指数与市场统计，用于判断大盘结构。"
    if kind == "screening":
        if "concept_rankings empty" in summary:
            return "已纳入行业排行和热股候选；概念主题本轮无结果，只作限制。"
        return "已纳入行业排行、概念排行和热股候选。"
    if kind == "technical_context":
        return f"{symbol_text or '重点标的'} 已纳入行情与 K 线结构。"
    if kind == "fundamental_context":
        match = re.search(r"公告/法披\s*(\d+)\s*条", summary)
        count = match.group(1) if match else ""
        if count and count != "0":
            return f"{symbol_text or '重点标的'} 已纳入 {count} 条公告/法披证据。"
        return f"{symbol_text or '重点标的'} 结构化基本面已纳入；公告/法披仍需补强。"
    if kind == "stock_analysis_context":
        return f"{symbol_text or '重点标的'} 已纳入原系统个股行情、K 线和基本面上下文。"
    if kind == "portfolio_snapshot":
        return "已纳入持仓/自选股快照；真实持仓为空时只判断观察池。"
    if kind == "watchlist_snapshot":
        return f"已纳入自选观察池：{symbol_text}。"
    if kind == "geo_policy_seed":
        return "已纳入利率、能源、信用风险和新闻线索，用于地缘政策传导判断。"
    if kind == "decision_signals":
        return "原系统结构化决策信号本轮为空；不作为默认结论来源。"
    if kind == "history_summary":
        return "已纳入本轮标的范围内的历史报告约束。"
    return _safe_reader_text(summary or kind)


def _reader_gap_text(value: Any) -> str:
    text = _product_copy(value)
    if not text:
        return ""
    if _is_no_gap_text(text):
        return ""
    replacements = {
        "capital_flow": "资金流",
        "concept_rankings": "概念主题排行",
        "fundamental_context": "结构化基本面上下文",
        "subject_fundamental_depth_incomplete": "部分标的基本面深度不足",
        "provider_run": "数据源记录",
        "record_count": "记录数",
        "not_supported": "暂未适配",
        "rate_limited": "限流",
        "auth_missing": "缺授权",
        "关键数据缺口": "关键待确认项",
        "数据缺口": "待确认项",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"\b(success|failed|empty)\s*\(\d+\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" ；;。")
    return text


def _is_no_gap_text(value: str) -> bool:
    normalized = re.sub(r"[\s。.!！；;，,、]+", "", str(value or "")).lower()
    return normalized in {
        "无",
        "暂无",
        "没有",
        "无缺口",
        "无数据缺口",
        "无关键缺口",
        "无关键数据缺口",
        "无待确认项",
        "none",
        "n/a",
        "na",
    }


def _reader_v2_support_drawers(cards: List[Dict[str, Any]], original_refs: List[Dict[str, Any]], evidence_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for card in cards:
        evidence_ids = [str(item) for item in card.get("evidenceIds") or [] if str(item)]
        agent = str(card.get("agent") or "")
        used_refs = [
            _safe_reader_text(str(ref.get("summary") or ref.get("kind") or ""))
            for ref in original_refs
            if isinstance(ref, dict) and agent in [str(item) for item in ref.get("agentTargets") or []]
        ][:6]
        out.append({
            "agent": agent,
            "title": f"{card.get('label') or agent}支撑",
            "originalAnalysis": used_refs,
            "evidence": _evidence_samples(evidence_items, evidence_ids, limit=6),
        })
    return out


def _evidence_samples(evidence_items: List[Dict[str, Any]], evidence_ids: List[str], *, limit: int) -> List[Dict[str, Any]]:
    by_id = {str(item.get("id") or ""): item for item in evidence_items if isinstance(item, dict)}
    out: List[Dict[str, Any]] = []
    for evidence_id in evidence_ids:
        item = by_id.get(evidence_id)
        if not item:
            continue
        out.append({
            "id": item.get("id"),
            "label": _safe_reader_text(item.get("value") or item.get("id") or ""),
            "provider": item.get("provider") or "",
            "factType": item.get("factType") or "",
            "metric": item.get("metric") or "",
            "measurements": item.get("measurements") if isinstance(item.get("measurements"), dict) else {},
            "sourceUrl": item.get("sourceUrl") or "",
        })
        if len(out) >= limit:
            break
    return out


def _clean_reader_v2_sections(sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cleaned: List[Dict[str, Any]] = []
    for section in sections:
        row = dict(section)
        row["body"] = _safe_reader_text(row.get("body") or "")
        row["bullets"] = [_safe_reader_text(item) for item in row.get("bullets") or [] if str(item).strip()]
        cleaned.append(row)
    return cleaned


_DEPARTMENT_LABELS = {
    "MacroAgent": "宏观部门",
    "MacroGeopoliticsAgent": "宏观部门",
    "GeoPolicyAgent": "地缘政策部门",
    "MarketAgent": "市场部门",
    "MarketStrategyAgent": "市场策略部门",
    "SectorAgent": "行业/风格部门",
    "CandidateReviewAgent": "候选池部门",
    "TechnicalAgent": "技术面部门",
    "IntelAgent": "新闻情报部门",
    "IntelCatalystAgent": "新闻情报部门",
    "SourceReviewAgent": "数据源复核",
    "FundamentalAgent": "基本面部门",
    "FundamentalReportsAgent": "基本面部门",
    "PortfolioReviewAgent": "持仓复核部门",
    "PortfolioAgent": "持仓复核部门",
    "RiskPositionAgent": "风险部门",
    "RiskAgent": "风险部门",
    "RedBlueAgent": "红队反证",
    "RedTeamAgent": "红队反证",
    "EvidenceGate": "证据门控",
    "ScoringAgent": "评分部门",
    "TradeDecisionGate": "CIO 门控",
    "DecisionReportAgent": "CIO 报告",
    "CIOAgent": "CIO 报告",
}

_READER_VISIBLE_AGENTS = {
    "MacroAgent",
    "MacroGeopoliticsAgent",
    "GeoPolicyAgent",
    "MarketAgent",
    "MarketStrategyAgent",
    "SectorAgent",
    "CandidateReviewAgent",
    "FundamentalAgent",
    "FundamentalReportsAgent",
    "TechnicalAgent",
    "IntelAgent",
    "IntelCatalystAgent",
    "PortfolioAgent",
    "PortfolioReviewAgent",
    "RiskAgent",
    "RiskPositionAgent",
    "RedBlueAgent",
    "RedTeamAgent",
    "DecisionReportAgent",
    "CIOAgent",
}

_DEPARTMENT_ORDER = {
    "DecisionReportAgent": 0,
    "CIOAgent": 0,
    "RedBlueAgent": 10,
    "RiskAgent": 20,
    "RiskPositionAgent": 20,
    "TechnicalAgent": 30,
    "IntelAgent": 40,
    "IntelCatalystAgent": 40,
    "FundamentalAgent": 50,
    "FundamentalReportsAgent": 50,
    "MacroAgent": 60,
    "MacroGeopoliticsAgent": 60,
    "GeoPolicyAgent": 65,
    "MarketStrategyAgent": 70,
    "MarketAgent": 70,
    "SectorAgent": 75,
    "CandidateReviewAgent": 80,
    "PortfolioAgent": 90,
    "PortfolioReviewAgent": 90,
}


def _department_reports(docs_dir: Path, run_date: str) -> List[Dict[str, Any]]:
    base = docs_dir / "agent_memos" / run_date
    if not base.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for path in sorted(base.rglob("*.json")):
        memo = _read_json(path)
        if not isinstance(memo, dict) or memo.get("schema") != "agent_memo_v1":
            continue
        agent = str(memo.get("agent") or "Agent")
        summary = _localized_department_summary(
            agent,
            _first_text(memo.get("summary_for_reader"), memo.get("readable_summary"), memo.get("conclusion"), default="本部门未给出可读结论。"),
        )
        claims = [str(item) for item in (memo.get("key_claims") or memo.get("facts") or []) if str(item)]
        evidence_ids = [str(item) for item in (memo.get("evidence_ids") or memo.get("source_refs") or []) if str(item)]
        counterpoints = [str(item) for item in (memo.get("counterpoints") or memo.get("missing_data") or []) if str(item)]
        data_gaps = memo.get("data_gaps") if "data_gaps" in memo else memo.get("missing_data") or []
        rows.append({
            "agent": agent,
            "label": _DEPARTMENT_LABELS.get(agent, agent.replace("Agent", "")),
            "subject": memo.get("subject") or memo.get("symbol") or memo.get("scope") or "",
            "origin": memo.get("origin") or "DERIVED_FROM_ARTIFACT",
            "agentRuntime": memo.get("agentRuntime") or memo.get("agent_runtime") or "unknown",
            "runtimeKind": memo.get("runtime_kind") or memo.get("runtimeKind") or "",
            "llmStatus": memo.get("llm_status") or "",
            "readerVisible": agent in _READER_VISIBLE_AGENTS,
            "summaryForReader": _safe_reader_text(summary),
            "keyClaims": [_safe_reader_text(item) for item in claims[:5]],
            "evidenceIds": evidence_ids[:8],
            "counterpoints": [_safe_reader_text(item) for item in counterpoints[:5]],
            "dataGaps": [str(item) for item in data_gaps if str(item)][:5],
            "confidence": memo.get("confidence") or "medium",
            "nextAction": _safe_reader_text(memo.get("next_action") or memo.get("next_step") or ""),
            "claimEvidence": [dict(item) for item in memo.get("claim_evidence") or [] if isinstance(item, dict)],
            "semanticValidation": dict(memo.get("semantic_validation") or {}) if isinstance(memo.get("semantic_validation"), dict) else {},
            "semanticWarnings": [str(item) for item in memo.get("semantic_warnings") or [] if str(item)][:8],
            "challenges": [dict(item) for item in memo.get("challenges") or [] if isinstance(item, dict)][:5],
            "adjudication": dict(memo.get("adjudication") or {}) if isinstance(memo.get("adjudication"), dict) else {},
        })
    return sorted(rows, key=lambda row: (_DEPARTMENT_ORDER.get(str(row.get("agent")), 999), str(row.get("agent") or "")))


def _reader_department_reports(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [row for row in rows if row.get("readerVisible") is not False]


def _apply_daily_reader_scope(rows: List[Dict[str, Any]], universe: Dict[str, Any]) -> None:
    if not isinstance(universe, dict):
        return
    subject_count = len(universe.get("subjectSymbols") or [])
    mode = str(universe.get("mode") or "")
    if mode != "market_and_candidates" and subject_count <= 1:
        return
    for row in rows:
        if not _is_daily_scope_department(row):
            row["readerVisible"] = False
            row["readerScope"] = "stock_drilldown"


def _daily_scope_department_reports(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [row for row in rows if _is_daily_scope_department(row)]


def _is_daily_scope_department(row: Dict[str, Any]) -> bool:
    subject = str(row.get("subject") or "").strip().lower()
    return subject in {"", "daily", "market", "portfolio"}


def _daily_final_text(rows: List[Dict[str, Any]], fallback: str) -> str:
    parts: List[str] = []
    for agents in [
        {"CIOAgent", "DecisionReportAgent"},
        {"MarketAgent", "MarketStrategyAgent"},
        {"SectorAgent"},
        {"MacroAgent", "MacroGeopoliticsAgent"},
        {"GeoPolicyAgent"},
        {"RiskAgent", "RiskPositionAgent"},
        {"RedTeamAgent", "RedBlueAgent"},
        {"PortfolioAgent", "PortfolioReviewAgent"},
    ]:
        row = _first_department(rows, agents)
        if row and row.get("summaryForReader"):
            parts.append(str(row.get("summaryForReader")))
    return "；".join(parts[:3]) if parts else fallback


def _legacy_daily_final_text(rows: List[Dict[str, Any]], fallback: str) -> str:
    parts: List[str] = []
    for agents in [
        {"MarketStrategyAgent"},
        {"CandidateReviewAgent"},
        {"MacroGeopoliticsAgent"},
        {"PortfolioReviewAgent"},
    ]:
        row = _first_department(rows, agents)
        if row and row.get("summaryForReader"):
            parts.append(str(row.get("summaryForReader")))
    return "；".join(parts[:3]) if parts else fallback


def _localized_department_summary(agent: str, summary: str) -> str:
    text = str(summary or "")
    if agent == "TechnicalAgent" and "bearish MA alignment" in text:
        return "技术面偏弱：均线空头排列，MACD 指向下行；今日虽反弹但量能不足，暂不追涨。"
    return text


def _build_reader_brief(
    *,
    run_date: str,
    mode: str,
    headline: str,
    governed_lines: List[str],
    candidate_lines: List[str],
    source_health_v2: Dict[str, Any],
    evidence_stats: Dict[str, Any],
    decision: Dict[str, Any],
    department_reports: List[Dict[str, Any]],
    universe: Dict[str, Any],
) -> Dict[str, Any]:
    action = str(decision.get("action") or "watch")
    blocked = decision.get("gateStatus") == "blocked" or action == "no_action"
    subject_count = len(universe.get("subjectSymbols") or []) if isinstance(universe, dict) else 0
    universe_mode = str(universe.get("mode") or "") if isinstance(universe, dict) else ""
    if universe_mode == "market_and_candidates":
        one_line = "今日结论：自选股为空，先做市场观察和候选跟踪。"
    elif subject_count > 1:
        one_line = f"今日结论：覆盖 {subject_count} 个观察标的，先看市场/行业，再看重点个股。"
    elif blocked:
        one_line = "今日结论：暂不行动，等待证据补齐和风险复核。"
    elif mode == "FULL_REVIEW":
        one_line = "今日结论：证据链可读，可进入人工交易前复核。"
    else:
        one_line = "今日结论：有限复盘，以观察和候选跟踪为主。"

    is_multi_scope_daily = universe_mode == "market_and_candidates" or subject_count > 1
    visible_departments = _reader_department_reports(department_reports)
    daily_departments = _daily_scope_department_reports(visible_departments) if is_multi_scope_daily else visible_departments
    cio_report = _first_department(daily_departments, {"DecisionReportAgent", "CIOAgent"})
    final_text = (
        str(cio_report.get("summaryForReader") or "")
        if cio_report
        else _daily_final_text(daily_departments, one_line)
        if is_multi_scope_daily
        else ("；".join(line.lstrip("- ") for line in governed_lines) if governed_lines else one_line)
    )

    why: List[str] = []
    universe_summary = _universe_summary_line(universe)
    if universe_summary:
        why.append(universe_summary)
    for agents in [
        {"CIOAgent", "DecisionReportAgent"},
        {"MacroAgent", "MacroGeopoliticsAgent"},
        {"GeoPolicyAgent"},
        {"MarketAgent", "MarketStrategyAgent"},
        {"SectorAgent"},
        {"FundamentalAgent", "FundamentalReportsAgent"},
        {"TechnicalAgent"},
        {"IntelAgent", "IntelCatalystAgent"},
        {"RiskAgent", "RiskPositionAgent"},
        {"RedTeamAgent", "RedBlueAgent"},
    ]:
        row = _first_department(daily_departments, agents)
        if row and row.get("summaryForReader"):
            why.append(str(row.get("summaryForReader")))
    if not why and headline:
        why.append(str(headline))
    if not why:
        why.append("本轮缺少足够分部门结论，只能保留观察。")

    risks: List[str] = []
    risk_report = _first_department(daily_departments, {"RiskAgent", "RiskPositionAgent", "RedTeamAgent", "RedBlueAgent"})
    if risk_report and risk_report.get("summaryForReader"):
        risks.append(str(risk_report.get("summaryForReader")))
    for reason in source_health_v2.get("blockingReasons") or []:
        risks.append(_human_blocking_reason(str(reason)))
    if evidence_stats.get("missingCriticalFacts"):
        risks.append(f"关键证据缺口：{evidence_stats.get('missingCriticalFacts')}")
    for row in daily_departments:
        risks.extend(_human_blocking_reason(str(item)) for item in row.get("counterpoints") or [] if str(item))
        if len(risks) >= 5:
            break

    watchlist = [_safe_reader_text(str(item).lstrip("- ")) for item in candidate_lines[:5]]
    data_confidence = _reader_data_confidence(source_health_v2, evidence_stats)
    next_steps = [
        "先看 CIO 结论和分部门摘要，不直接按单一信号行动。",
        "候选清单只做观察，等待证据和价格条件共振。",
        "日报先判断市场和行业，再下钻重点个股；不要让单一股票覆盖全局结论。",
        "只把搜索/新闻当线索，关键事实回跳公告、SEC、交易所或公司 IR。",
    ]
    if cio_report and cio_report.get("nextAction"):
        next_steps.insert(0, str(cio_report.get("nextAction")))

    universe_payload = {
        "mode": universe_mode,
        "subjectCount": subject_count,
        "subjects": [str(item) for item in (universe.get("subjectSymbols") or [])[:12]] if isinstance(universe, dict) else [],
    }

    return {
        "schema": "reader_brief_v1",
        "runDate": run_date,
        "mode": mode,
        "oneLine": _safe_reader_text(one_line),
        "analysis": _safe_reader_text(final_text),
        "finalConclusion": _safe_reader_text(final_text),
        "why": [_safe_reader_text(item) for item in list(dict.fromkeys(why))[:6]],
        "risks": [_safe_reader_text(item) for item in list(dict.fromkeys(risks))[:6]],
        "watchlist": watchlist,
        "universe": universe_payload,
        "dataConfidence": data_confidence,
        "nextSteps": [_safe_reader_text(item) for item in list(dict.fromkeys(next_steps))[:6]],
    }


def _universe_summary_line(universe: Dict[str, Any]) -> str:
    if not isinstance(universe, dict):
        return ""
    groups = universe.get("groups") if isinstance(universe.get("groups"), list) else []
    parts: List[str] = []
    for name in ("watchlist", "portfolio", "candidates", "market", "macro"):
        row = next((item for item in groups if isinstance(item, dict) and item.get("name") == name), None)
        if not row:
            continue
        if name == "market":
            parts.append("市场已纳入")
            continue
        if name == "macro":
            parts.append("宏观已纳入")
            continue
        symbols = row.get("symbols") if isinstance(row.get("symbols"), list) else []
        parts.append(f"{_universe_group_label(name)} {len(symbols)}")
    return "日报范围：" + "；".join(parts) if parts else ""


def _universe_group_label(name: str) -> str:
    return {
        "watchlist": "自选股",
        "portfolio": "持仓",
        "candidates": "候选",
        "market": "市场",
        "macro": "宏观",
    }.get(name, name)


def _first_department(rows: List[Dict[str, Any]], agents: set[str]) -> Dict[str, Any] | None:
    for row in rows:
        if str(row.get("agent") or "") in agents:
            return row
    return None


def _human_blocking_reason(reason: str) -> str:
    text = str(reason or "")
    if text.endswith(":agent_reported_data_gap"):
        domain = text.split(":", 1)[0]
        labels = {
            "price": "行情、资金流或市场宽度仍有缺口。",
            "fundamentals": "基本面证据仍有缺口。",
            "filings_events": "公告/事件证据仍有缺口。",
            "macro": "宏观证据仍有缺口。",
            "news_sentiment": "新闻/舆情线索仍需补强。",
            "portfolio": "持仓/组合数据仍有缺口。",
        }
        return labels.get(domain, "部门复核指出关键数据仍有缺口。")
    if text == "governance:no_completed_governed_report":
        return "本轮没有完成可行动个股深评。"
    mapping = {
        "fundamentals:subject_coverage_incomplete": "部分观察标的仍缺少结构化基本面，相关个股结论需谨慎。",
        "fundamentals:subject_fundamental_depth_incomplete": "部分观察标的只有浅层估值，缺少财务质量和增长数据；相关个股结论需谨慎。",
        "price:subject_coverage_incomplete": "部分观察标的仍缺少行情/K线，相关个股结论需谨慎。",
        "publish_bundle:not_observed": "报告发布包尚未完成最终校验。",
        "fundamentals:failed": "基本面证据不足：当前标的没有拿到可追源财务事实。",
        "fundamentals:missing": "基本面证据不足：当前标的缺少财务事实。",
        "price:missing": "行情证据不足：当前标的价格/K线未形成可用快照。",
        "macro:degraded": "宏观数据降级：宏观只能作为背景参考。",
        "news_sentiment:search_only_discovery": "新闻只属于发现线索，不能直接当事实。",
        "search_provider": "搜索源结果只作线索，需要回跳权威来源。",
        "official_announcements": "公告/交易所原文仍需补强。",
        "a_share_quote": "A 股行情快照需继续核对。",
        "a_share_quote_fallback": "A 股行情走了备用源，需要人工复核。",
        "no_auto_governed_candidates": "没有自动进入深评的候选，先观察。",
        "financial_statement_refs": "财报原文引用不足。",
        "valuation_peer_refs": "同业估值引用不足。",
    }
    return _safe_reader_text(mapping.get(text, text))


def _reader_data_confidence(source_health_v2: Dict[str, Any], evidence_stats: Dict[str, Any]) -> str:
    mode = str(source_health_v2.get("overallMode") or "OBSERVE_ONLY")
    score = source_health_v2.get("overallScore")
    try:
        score_value = float(score)
    except Exception:
        score_value = 0.0
    missing = evidence_stats.get("missingCriticalFacts") or 0
    if mode == "FULL_REVIEW" and score_value >= 0.85 and not missing:
        return "核心证据链完整；数据可信度高，结论仍需人工复核。"
    if score_value >= 0.55:
        return "数据可信度中等；可读结论，但必须看限制。"
    return "数据可信度低；本轮主要用于诊断和观察。"


def _daily_source_health(health: Dict[str, Any]) -> Dict[str, Any]:
    status = _first_text(health.get("usability_verdict"), health.get("macro_status"), default="unknown")
    trade = _first_text(health.get("trade_review_usability"), default="unknown")
    normalized = f"{status} {trade}".lower()
    limited = any(token in normalized for token in ("degraded", "partial", "limited", "unknown"))
    failed = any(token in normalized for token in ("failed", "unavailable", "blocked"))
    rows = health.get("rows") if isinstance(health.get("rows"), list) else []
    available_rows = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_status = str(row.get("status") or "").upper()
        if row_status in {"AVAILABLE", "OK", "REFRESHED"}:
            available_rows += 1
    coverage = round(available_rows / len(rows), 4) if rows else None
    return {
        "status": status,
        "verdict": trade,
        "canScore": not failed,
        "canTradeReview": not limited and not failed,
        "coverageScore": coverage,
        "freshnessStatus": _first_text(health.get("freshness_status"), default="未提供"),
        "fallbackUsed": _first_text(health.get("fallback_used"), default="未提供"),
        "failureReason": _first_text(health.get("failure_reason"), default="未提供"),
        "decisionImpact": "数据源降级，可观察，不可作为满血交易依据" if limited or failed else "数据源可用于常规审查",
        "rows": rows,
    }


def _daily_completeness(missing_files: List[str], source_health: Dict[str, Any], source_health_v2: Dict[str, Any]) -> str:
    mode = str(source_health_v2.get("overallMode") or "").upper()
    if missing_files:
        return "partial"
    if mode != "FULL_REVIEW":
        return "partial"
    return "complete"


def _load_daily_source_health_v2_snapshot(docs_dir: Path, run_date: str) -> Dict[str, Any]:
    payload = _read_json(docs_dir / "run_status" / run_date / "source_health_v2.json")
    return dict(payload) if isinstance(payload, dict) and payload.get("schema") == "source_health_v2" else {}


def _load_daily_provider_runs(docs_dir: Path, run_date: str) -> List[Dict[str, Any]]:
    candidates = [
        docs_dir / "run_status" / run_date / "provider_runs.jsonl",
        docs_dir / "run_status" / "provider_runs.jsonl",
        docs_dir / "reports" / run_date / "provider_runs.jsonl",
        docs_dir / "reports" / "provider_runs.jsonl",
        docs_dir / "provider_runs.jsonl",
    ]
    rows: List[Dict[str, Any]] = []
    for path in candidates:
        rows.extend(load_provider_ledger(path))
    return rows


def _load_daily_evidence_facts(docs_dir: Path, run_date: str, health: Dict[str, Any], source_health: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates = [
        docs_dir / "run_status" / run_date / "evidence_ledger.jsonl",
        docs_dir / "run_status" / "evidence_ledger.jsonl",
        docs_dir / "reports" / run_date / "evidence_ledger.jsonl",
        docs_dir / "reports" / "evidence_ledger.jsonl",
        docs_dir / "evidence_ledger.jsonl",
    ]
    facts: List[Dict[str, Any]] = []
    for path in candidates:
        facts.extend(load_evidence_ledger(path))
    facts.extend(_daily_evidence_facts(health, source_health))
    return facts


def _daily_evidence_facts(health: Dict[str, Any], source_health: Dict[str, Any]) -> List[Dict[str, Any]]:
    facts: List[Dict[str, Any]] = []
    rows = health.get("rows") if isinstance(health.get("rows"), list) else []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        domain = _source_health_row_domain(row)
        status = str(row.get("status") or row.get("usability") or "").lower()
        evidence_refs = row.get("evidence_refs") if isinstance(row.get("evidence_refs"), list) else []
        if evidence_refs:
            facts.append({
                "id": f"derived:source_health:{idx}",
                "domain": domain,
                "fact_type": "derived_fact",
                "provider": row.get("source") or "source_health_v1",
                "confidence": "medium",
            })
        elif any(token in status for token in ("unavailable", "failed", "missing")):
            facts.append({
                "id": f"missing:source_health:{idx}",
                "domain": domain,
                "fact_type": "missing",
                "provider": row.get("source") or "source_health_v1",
                "confidence": "low",
            })
    text = f"{source_health.get('status', '')} {source_health.get('verdict', '')}".lower()
    if any(token in text for token in ("degraded", "limited", "unknown")) and not facts:
        facts.append({
            "id": "missing:source_health:limited",
            "domain": "macro",
            "fact_type": "missing",
            "provider": "source_health_v1",
            "confidence": "low",
        })
    return facts


def _evidence_items(
    facts: List[Dict[str, Any]],
    *,
    preferred_ids: Optional[List[str]] = None,
    limit: int = 80,
) -> List[Dict[str, Any]]:
    priority = {"verified_fact": 0, "discovery": 1, "derived_fact": 2, "missing": 3}
    preferred_rank = {
        evidence_id: index
        for index, evidence_id in enumerate(dict.fromkeys(preferred_ids or []))
    }
    normalized = [normalize_evidence_fact(fact) for fact in facts]
    normalized.sort(
        key=lambda item: (
            0 if str(item.get("id") or "") in preferred_rank else 1,
            preferred_rank.get(str(item.get("id") or ""), 9999),
            priority.get(str(item.get("fact_type")), 9),
            str(item.get("domain") or ""),
            str(item.get("id") or ""),
        )
    )
    out: List[Dict[str, Any]] = []
    for fact in normalized[:limit]:
        out.append({
            "id": fact.get("id"),
            "domain": fact.get("domain"),
            "factType": fact.get("fact_type"),
            "provider": fact.get("provider"),
            "symbol": fact.get("symbol") or "",
            "metric": fact.get("metric") or "",
            "value": fact.get("value") or "",
            "measurements": dict(fact.get("measurements") or {}),
            "unit": fact.get("unit") or "",
            "asOf": fact.get("as_of") or fact.get("asOf") or "",
            "eventTime": fact.get("event_time") or fact.get("eventTime") or "",
            "publishedAt": fact.get("published_at") or fact.get("publishedAt") or "",
            "fetchedAt": fact.get("fetched_at") or fact.get("fetchedAt") or "",
            "sourceUrl": fact.get("source_url") or fact.get("sourceUrl") or "",
            "rawPath": fact.get("raw_path") or fact.get("rawPath") or "",
            "confidence": fact.get("confidence"),
            "evidenceScope": fact.get("evidence_scope") or "subject_evidence",
        })
    return out


def _source_health_row_domain(row: Dict[str, Any]) -> str:
    component = str(row.get("component") or row.get("source") or "").lower()
    if "macro" in component:
        return "macro"
    if "portfolio" in component:
        return "portfolio"
    if "governed" in component or "report" in component:
        return "publish_bundle"
    if "prediction" in component or "news" in component:
        return "news_sentiment"
    return "price"


def _is_limited_source_health(source_health: Dict[str, Any]) -> bool:
    text = f"{source_health.get('status', '')} {source_health.get('verdict', '')} {source_health.get('decisionImpact', '')}".lower()
    return any(token in text for token in ("degraded", "partial", "limited", "unknown", "不可作为满血"))


def _source_health_lines(health: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    rows = health.get("rows") if isinstance(health.get("rows"), list) else []
    if rows:
        for row in rows[:12]:
            if not isinstance(row, dict):
                continue
            name = _first_text(row.get("component"), row.get("source"), default="未命名来源")
            status = _first_text(row.get("status"), default="未提供")
            warning = _join_text(row.get("warnings") or row.get("warning") or [])
            suffix = f"；提示：{warning}" if warning else ""
            lines.append(f"- {name}：{status}{suffix}")
    else:
        status = _first_text(health.get("usability_verdict"), health.get("macro_status"), default="未提供")
        lines.append(f"- 源健康：{status}")
    return [_safe_reader_text(line) for line in lines]


def _candidate_lines(queue: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    candidates = queue.get("candidates") if isinstance(queue, dict) else []
    for row in (candidates or [])[:6]:
        if not isinstance(row, dict):
            continue
        symbol = _first_text(row.get("symbol"), default="")
        name = _first_text(row.get("name"), default=symbol or "未命名")
        verdict = _first_text(row.get("verdict"), default="待复核")
        risk = _first_text(row.get("price_risk"), default="未提供")
        lines.append(f"- {name}({symbol})：{verdict}；价格风险：{risk}")
    return [_safe_reader_text(line) for line in lines]


def _governed_summary_lines(rows: List[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    for row in rows:
        code = _first_text(row.get("code"), row.get("symbol"), default="")
        name = _first_text(row.get("name"), default=code or "未命名")
        trade_plan = row.get("trade_plan") if isinstance(row.get("trade_plan"), dict) else {}
        blocked = _is_blocked_governed_row(row)
        action = "暂不行动" if blocked else _human_action(trade_plan.get("action"))
        headline = _first_text(row.get("headline"), default="未提供")
        lines.append(f"- {name}({code})：{action}。原因：{headline}")
    return [_safe_reader_text(line) for line in lines]


def _daily_decision(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {
            "action": "watch",
            "gateStatus": "watch",
            "score": None,
            "targetPct": 0,
            "blockedReasons": ["no_completed_governed_report"],
        }
    scores = [_safe_float(row.get("score")) for row in rows]
    scores = [score for score in scores if score is not None]
    blocked_rows = [row for row in rows if _is_blocked_governed_row(row)]
    all_blocked = len(blocked_rows) == len(rows)
    return {
        "action": "no_action" if all_blocked else "watch",
        "gateStatus": "blocked" if all_blocked else "watch",
        "score": min(scores) if scores else None,
        "targetPct": 0,
        "blockedReasons": _blocked_reasons(blocked_rows) if all_blocked else [],
    }


def _blocked_reasons(rows: List[Dict[str, Any]]) -> List[str]:
    reasons: List[str] = []
    for row in rows:
        code = _first_text(row.get("code"), row.get("symbol"), default="unknown")
        status = _first_text(row.get("cio_status"), row.get("gate"), default="blocked")
        reasons.append(f"{code}:{status}")
    return reasons[:12]


def _is_blocked_governed_row(row: Dict[str, Any]) -> bool:
    return is_blocked_governed_row(row)


def _human_action(action: Any) -> str:
    value = str(action or "").strip().lower()
    if value == "no_action":
        return "不操作"
    if value == "buy":
        return "买入候选"
    if value == "sell":
        return "卖出候选"
    if value == "hold":
        return "持有/复核"
    if value == "watch":
        return "观察"
    if value == "wait":
        return "等待观察"
    return "未生成动作"


def _join_text(value: Any) -> str:
    if isinstance(value, list):
        return "；".join(str(item) for item in value if str(item))
    return str(value or "").strip()


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is _MISSING:
            continue
        if value is None:
            continue
        if isinstance(value, str) and value == "":
            continue
        return value
    return None


def _first_text(*values: Any, default: str = "未知") -> str:
    value = _first_present(*values)
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _safe_reader_text(text: Any) -> str:
    value = str(text or "")
    replacements = {
        "FULL_REVIEW": "完整复盘",
        "LIMITED_REVIEW": "有限复盘",
        "SCREEN_ONLY": "仅筛选观察",
        "OBSERVE_ONLY": "仅市场观察",
        "BLOCKED_BY_FATAL": "暂不行动",
        "BLOCKED": "暂不行动",
        "RAW_AGENT": "真实 Agent",
        "DERIVED_FROM_ARTIFACT": "历史材料整理",
        "回填审计：": "",
        "有限信息结论：": "",
        "source health": "数据健康",
        "source_health": "数据健康",
        "price / fundamentals / filings / macro": "行情、基本面、公告、宏观",
        "price": "行情",
        "fundamentals": "基本面",
        "filings": "公告",
        "macro": "宏观",
        "DEEP_REVIEW_WAIT_ENTRY": "等待深评入场条件",
        "OVERHEATED_WAIT_ENTRY": "短线过热，等待承接",
        "gate=暂不行动": "未通过",
        "ScoringAgent": "评分复核",
        "TradeDecisionGate": "交易前复核",
        "EvidenceGate": "证据复核",
        "FundamentalAgent": "基本面部门",
        "sector_rankings": "行业强弱排行",
        "hot_stocks": "热门标的列表",
        "originalAnalysisRefs": "上游分析材料",
        "portfolio_snapshot": "持仓快照",
        "quantity": "持仓数量",
        "market_value": "持仓市值",
        "cost_basis": "成本价",
        "评分复核未通过（总分4.0/10）": "综合判断偏弱，暂不支持行动",
        "评分门控未通过（总分4.0/10）": "综合判断偏弱，暂不支持行动",
        "MISSING agent": "未运行 Agent",
        "no_action": "不操作",
        "N/A": "未提供",
        "关键数据缺口": "关键待确认项",
        "数据缺口": "待确认项",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    return value


def _safe_float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _latest_evidence_time(facts: List[Dict[str, Any]], *, fallback: str) -> str:
    values: List[str] = []
    for fact in facts:
        value = iso_timestamp(
            fact.get("event_time")
            or fact.get("eventTime")
            or fact.get("published_at")
            or fact.get("publishedAt")
            or fact.get("as_of")
            or fact.get("asOf")
        )
        if value:
            values.append(value)
    return max(values, default=fallback)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
