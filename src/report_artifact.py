# -*- coding: utf-8 -*-
"""ReportArtifact v1 contract helpers.

One contract feeds both the Web/App report view and the static ``docs/``
publisher.  Keep this file framework-light so renderers, API endpoints and
tests can share the same validation rules.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


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
    agent_counts = _agent_origin_counts(docs_path, run_date)

    source_health = _daily_source_health(health)
    candidate_count = len(queue.get("candidates") or []) if isinstance(queue, dict) else 0
    auto_governed_count = len(queue.get("auto_governed_candidates") or []) if isinstance(queue, dict) else 0
    blocked_count = sum(1 for row in governed_rows if _is_blocked_governed_row(row))
    macro_status = _first_text(macro.get("status"), health.get("macro_status"), default="未提供")
    trade_usability = _first_text(health.get("trade_review_usability"), default="未提供")
    regime = _first_text(strategy.get("regime"), default="未提供")
    headline = _first_text((strategy.get("strategy") or {}).get("headline") if isinstance(strategy.get("strategy"), dict) else None, macro.get("headline"), default="今日报告已生成。")

    if governed_rows and blocked_count == len(governed_rows):
        one_line = "今日 governed 标的全部被门控阻断；最终动作是不操作。"
    elif governed_rows:
        one_line = "今日存在 governed 标的；按门控结果逐只复核，不自动交易。"
    else:
        one_line = "今日无 completed governed 个股报告；仅保留市场观察和候选池。"
    if _is_limited_source_health(source_health):
        one_line += " 数据源降级，只可观察，不可作为满血交易依据。"

    key_facts = [
        f"运行日期：{run_date}",
        f"宏观状态：{macro_status}",
        f"市场状态：{regime}",
        f"交易审查可用性：{trade_usability}",
        f"深评候选：{candidate_count}；自动 governed：{auto_governed_count}",
        f"governed 完成：{len(governed_rows)}；阻断：{blocked_count}",
        f"Agent 来源：真实 {agent_counts.get('RAW_AGENT', 0)}；回填 {agent_counts.get('DERIVED_FROM_ARTIFACT', 0)}；缺失 {agent_counts.get('MISSING', 0)}",
    ]

    governed_lines = _governed_summary_lines(governed_rows)
    source_lines = _source_health_lines(health)
    candidate_lines = _candidate_lines(queue)
    missing_files = _missing_daily_source_files(docs_path, run_date)
    decision = _daily_decision(governed_rows)

    sections = [
        {
            "key": "source",
            "title": "数据源",
            "kind": "source",
            "contentMarkdown": "\n".join(source_lines) or "- 未提供数据源健康明细",
            "sourceRefs": _existing_source_refs(docs_path, run_date),
            "confidence": "medium" if source_lines else "low",
        },
        {
            "key": "facts",
            "title": "关键数据",
            "kind": "facts",
            "contentMarkdown": "\n".join(f"- {item}" for item in key_facts),
            "confidence": "medium",
        },
        {
            "key": "analysis",
            "title": "推论",
            "kind": "analysis",
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
            "contentMarkdown": "\n".join(
                [
                    "- 先读总报告，再看源健康和 Agent 卷宗。",
                    "- 宏观源降级时，只做观察和候选筛选。",
                    "- blocked / 低分标的不交易；补公告、业绩、估值和催化剂后再审。",
                ]
            ),
            "confidence": "medium",
        },
    ]

    artifact = {
        "schemaVersion": SCHEMA_VERSION,
        "artifactId": f"daily:{run_date}",
        "runDate": run_date,
        "generatedAt": _now_iso(),
        "artifactType": "daily",
        "audience": "reader",
        "title": f"{run_date} 投研日报",
        "summary": {
            "oneLine": _safe_reader_text(one_line),
            "keyFacts": [_safe_reader_text(item) for item in key_facts],
            "analysis": _safe_reader_text(headline),
            "finalConclusion": _safe_reader_text("；".join(line.lstrip("- ") for line in governed_lines) if governed_lines else "维持观察，不自动交易。"),
            "nextSteps": [
                "先读源健康，确认数据缺口。",
                "候选只做观察，不直接交易。",
                "如需交易，另跑 evidence pack、红蓝对抗和评分门控。",
            ],
        },
        "sections": sections,
        "sourceHealth": source_health,
        "decision": decision,
        "agentOrigins": {
            "raw": agent_counts.get("RAW_AGENT", 0),
            "derived": agent_counts.get("DERIVED_FROM_ARTIFACT", 0),
            "missing": agent_counts.get("MISSING", 0),
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
            "completeness": "partial" if missing_files or _is_limited_source_health(source_health) else "complete",
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
    out = docs_path / "reports" / f"{run_date}.artifact.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return artifact


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
        score = _safe_float(row.get("score"))
        trade_plan = row.get("trade_plan") if isinstance(row.get("trade_plan"), dict) else {}
        blocked = _is_blocked_governed_row(row)
        action = "阻断 / 不操作 / 0%" if blocked else _human_action(trade_plan.get("action"))
        target = 0 if blocked else _safe_float(_first_present(trade_plan.get("target_pct"), trade_plan.get("target_position_pct"), None))
        target_text = f"{target:g}%" if target is not None else "未提供"
        score_text = f"{score:g}/10" if score is not None else "未提供"
        headline = _first_text(row.get("headline"), default="未提供")
        lines.append(f"- {name}({code})：{action}；评分 {score_text}；目标仓位 {target_text}；{headline}")
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
    score = _safe_float(row.get("score"))
    status_text = f"{row.get('cio_status', '')} {row.get('gate', '')}".upper()
    trade_plan = row.get("trade_plan") if isinstance(row.get("trade_plan"), dict) else {}
    action = str(trade_plan.get("action") or "").lower()
    return "BLOCKED" in status_text or "FATAL" in status_text or action == "no_action" or (score is not None and score < 6)


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
        "BLOCKED_BY_FATAL": "治理层阻断",
        "RAW_AGENT": "真实 Agent",
        "DERIVED_FROM_ARTIFACT": "回填审计",
        "MISSING agent": "未运行 Agent",
        "no_action": "不操作",
        "N/A": "未提供",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    return value


def _safe_float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
