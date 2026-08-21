# -*- coding: utf-8 -*-
"""Build report-only Agent memo dossiers from existing daily artifacts.

This module does not run LLMs and does not trade.  It normalizes the current
market-cycle and governed artifacts into a stable, human-readable dossier tree
so Pages can show the planned Agent flow even when raw per-agent transcripts
are not yet persisted by the runtime.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evidence_pack import build_evidence_pack, source_attempts_from_tool_calls
from src.core.run_context import resolve_analysis_run_date
from src.report_markdown import CSS, markdown_to_html


AGENT_MEMO_SCHEMA = "agent_memo_v1"
SOURCE_STATUS_SCHEMA = "source_status_v1"

AGENT_ORIGINS = {"RAW_AGENT", "DERIVED_FROM_ARTIFACT", "MISSING"}

RUNTIME_STAGE_MEMOS = {
    "macro": ("MacroAgent", "02_macro_memo"),
    "technical": ("TechnicalAgent", "04_technical_memo"),
    "intel": ("IntelCatalystAgent", "05_intel_catalyst_memo"),
    "risk": ("RiskPositionAgent", "06_risk_position_memo"),
    "evidence_gate": ("EvidenceGate", "07_evidence_gate"),
    "red_blue": ("RedBlueAgent", "08_red_blue"),
    "scoring": ("ScoringAgent", "09_scoring"),
    "cio": ("TradeDecisionGate", "10_trade_decision_gate"),
    "decision": ("DecisionReportAgent", "11_decision_report"),
}

SOURCE_DOMAIN_LABELS = {
    "macro": "宏观",
    "geo": "地缘",
    "a_share": "A股",
    "us_stock": "美股",
    "news": "新闻研报",
    "reports": "新闻研报",
    "portfolio": "持仓",
    "crypto": "Crypto",
    "options": "Options",
}


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _html_page(title: str, markdown: str) -> str:
    return (
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{_esc(title)}</title>{CSS}</head><body><main>"
        f"{markdown_to_html(markdown)}"
        "<p class='footer'>Agent memo dossier · report-only · no trade execution</p>"
        "</main></body></html>"
    )


def _esc(value: Any) -> str:
    import html

    return html.escape(str(value), quote=True)


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _text(value: Any, default: str = "UNKNOWN") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _status_from_blockers(*, fatal: bool = False, blocked: bool = False, warn: bool = False) -> str:
    if fatal or blocked:
        return "BLOCKED"
    if warn:
        return "WARN"
    return "PASS"


def _memo(
    *,
    agent: str,
    scope: str,
    status: str = "PASS",
    symbol: str = "",
    facts: Optional[List[str]] = None,
    reasoning: Optional[List[str]] = None,
    conclusion: str = "",
    missing_data: Optional[List[str]] = None,
    source_refs: Optional[List[str]] = None,
    fatal_objection: bool = False,
    next_step: str = "",
    origin: str = "DERIVED_FROM_ARTIFACT",
    readable_summary: str = "",
    evidence_blocks: Optional[List[Dict[str, str]]] = None,
    audit_detail: Optional[Dict[str, Any]] = None,
    evidence_level: str = "",
    source_attempts: Optional[List[Dict[str, Any]]] = None,
    limited_report: Optional[bool] = None,
    evidence_pack: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    normalized_status = status if status in {"PASS", "WARN", "BLOCKED", "SKIPPED"} else "WARN"
    normalized_origin = origin if origin in AGENT_ORIGINS else "DERIVED_FROM_ARTIFACT"
    normalized_facts = [str(item) for item in (facts or []) if str(item)]
    normalized_reasoning = [str(item) for item in (reasoning or []) if str(item)]
    normalized_refs = [str(item) for item in (source_refs or []) if str(item)]
    blocks = evidence_blocks or _default_evidence_blocks(normalized_facts, normalized_reasoning, normalized_refs)
    normalized_missing = [str(item) for item in (missing_data or []) if str(item)]
    attempts = [item for item in (source_attempts or []) if isinstance(item, dict)]
    pack = evidence_pack
    if pack is None and (attempts or evidence_level):
        pack = build_evidence_pack(
            scope=scope,
            symbol=symbol,
            source_attempts=attempts,
            evidence_items=blocks,
            missing_evidence=normalized_missing,
            critical_missing=normalized_status == "BLOCKED" and bool(fatal_objection),
        )
    payload = {
        "schema": AGENT_MEMO_SCHEMA,
        "agent": agent,
        "scope": scope,
        "subject": symbol or scope,
        "symbol": symbol,
        "status": normalized_status,
        "origin": normalized_origin,
        "origin_label": _origin_label(normalized_origin, bool(limited_report) or (isinstance(pack, dict) and bool(pack.get("limited_report")))),
        "facts": normalized_facts,
        "reasoning": normalized_reasoning,
        "conclusion": conclusion,
        "missing_data": normalized_missing,
        "source_refs": normalized_refs,
        "fatal_objection": bool(fatal_objection),
        "next_step": next_step,
        "summary_for_reader": readable_summary or _readable_summary(normalized_origin, normalized_status, conclusion, bool(limited_report) or (isinstance(pack, dict) and bool(pack.get("limited_report")))),
        "key_claims": [str(block.get("claim")) for block in blocks if isinstance(block, dict) and block.get("claim")],
        "evidence_ids": _memo_evidence_ids(normalized_refs, blocks),
        "counterpoints": normalized_missing[:3] if normalized_missing else ([] if normalized_status == "PASS" else [conclusion or "需要反证复核"]),
        "data_gaps": normalized_missing,
        "next_action": next_step,
        "claims": _memo_claims(blocks, normalized_refs, normalized_missing),
        "decision": {
            "action": "block" if normalized_status == "BLOCKED" else ("review" if normalized_status == "PASS" else "observe"),
            "can_score": normalized_status != "BLOCKED",
            "can_position_sizing": False,
        },
        "readable_summary": readable_summary or _readable_summary(normalized_origin, normalized_status, conclusion, bool(limited_report) or (isinstance(pack, dict) and bool(pack.get("limited_report")))),
        "evidence_blocks": blocks,
        "audit_detail": audit_detail
        or {
            "schema": AGENT_MEMO_SCHEMA,
            "origin": normalized_origin,
            "status": normalized_status,
            "source_refs": normalized_refs,
            "fatal_objection": bool(fatal_objection),
        },
        "no_trade_execution": True,
    }
    if pack is not None:
        payload["evidence_pack"] = pack
        payload["evidence_level"] = str(pack.get("evidence_level") or evidence_level or "LIMITED")
        payload["source_attempts"] = list(pack.get("source_attempts") or attempts)
        payload["limited_report"] = bool(pack.get("limited_report"))
        payload["confidence"] = str(pack.get("confidence") or "low")
    elif evidence_level:
        payload["evidence_level"] = evidence_level
        payload["source_attempts"] = attempts
        payload["limited_report"] = bool(limited_report)
    return payload


def _memo_evidence_ids(refs: List[str], blocks: List[Dict[str, Any]]) -> List[str]:
    ids: List[str] = []
    for ref in refs:
        if ref and ref not in ids:
            ids.append(ref)
    for block in blocks:
        if not isinstance(block, dict):
            continue
        value = str(block.get("id") or block.get("evidence_id") or block.get("source") or "").strip()
        if value and value != "UNKNOWN" and value not in ids:
            ids.append(value)
    return ids[:12]


def _memo_claims(blocks: List[Dict[str, Any]], refs: List[str], gaps: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    default_refs = refs[:3]
    for block in blocks:
        if not isinstance(block, dict):
            continue
        claim = str(block.get("claim") or "").strip()
        if not claim:
            continue
        evidence_id = str(block.get("id") or block.get("evidence_id") or block.get("source") or "").strip()
        evidence_ids = [evidence_id] if evidence_id and evidence_id != "UNKNOWN" else default_refs
        out.append({
            "claim": claim,
            "claim_type": "observation",
            "evidence_ids": evidence_ids,
            "allowed_fact_types": ["verified_fact", "derived_fact"],
            "confidence": "medium" if evidence_ids else "low",
            "missing_domains": gaps,
            "blockers": ["missing_evidence"] if not evidence_ids else [],
        })
    return out[:8]


def _origin_label(origin: str, limited: bool = False) -> str:
    if limited and origin == "RAW_AGENT":
        return "有限证据 Agent 输出"
    return {
        "RAW_AGENT": "真实 Agent 输出",
        "DERIVED_FROM_ARTIFACT": "回填审计",
        "MISSING": "本轮未运行",
    }.get(origin, "回填审计")


def _readable_summary(origin: str, status: str, conclusion: str, limited: bool = False) -> str:
    prefix = _origin_label(origin, limited)
    conclusion_text = conclusion or "等待下一轮报告。"
    if status == "BLOCKED":
        return f"阻断：{prefix}。{conclusion_text}"
    if limited:
        return f"有限信息结论：{conclusion_text}"
    return f"{prefix}：{conclusion_text}"


def _default_evidence_blocks(facts: List[str], reasoning: List[str], refs: List[str]) -> List[Dict[str, str]]:
    return [
        {
            "claim": facts[0] if facts else "本轮没有足够结构化事实。",
            "data": "；".join(facts[:3]) if facts else "UNKNOWN",
            "source": refs[0] if refs else "UNKNOWN",
            "inference": reasoning[0] if reasoning else "缺少独立推理链。",
        }
    ]


def _memo_markdown(memo: Dict[str, Any]) -> str:
    audit = memo.get("audit_detail") or {}
    attempts = memo.get("source_attempts") or []
    lines = [
        f"# {memo.get('agent')} — {memo.get('symbol') or memo.get('scope')}",
        "",
        f"- 输出来源：{memo.get('origin_label') or _origin_label(str(memo.get('origin') or 'DERIVED_FROM_ARTIFACT'), bool(memo.get('limited_report')))}",
        f"- 当前状态：{_reader_status(str(memo.get('status') or ''))}",
        f"- 证据等级：{memo.get('evidence_level', '未标注')}",
        "",
        "## 一句话结论",
        memo.get("readable_summary") or memo.get("conclusion") or "UNKNOWN",
        "",
        "## 我搜了什么",
        *_attempt_lines(attempts),
        "",
        "## 搜到什么",
        *_evidence_block_lines(memo.get("evidence_blocks") or []),
        "",
        "## 搜不到什么",
        *_bullets(memo.get("missing_data") or ["无明确缺口"]),
        "",
        "## 有限信息结论",
        _limited_conclusion(memo),
        "",
        "## 我看了什么",
        *_bullets(memo.get("source_refs") or ["UNKNOWN"]),
        "",
        "## 事实",
        *_bullets(memo.get("facts") or ["UNKNOWN"]),
        "",
        "## 我的推理",
        *_bullets(memo.get("reasoning") or ["UNKNOWN"]),
        "",
        "## 我的结论",
        memo.get("conclusion") or "UNKNOWN",
        "",
        "## 下一步谁补",
        memo.get("next_step") or "等待下一轮报告。",
        "",
        "## 审计详情",
        *_bullets(
            [
                f"schema={audit.get('schema') or memo.get('schema')}",
                f"origin={audit.get('origin') or memo.get('origin')}",
                f"scope={memo.get('scope')}",
                f"status={audit.get('status') or memo.get('status')}",
                f"fatal={audit.get('fatal_objection') if 'fatal_objection' in audit else memo.get('fatal_objection')}",
                f"no_trade_execution={memo.get('no_trade_execution')}",
            ]
        ),
    ]
    return _sanitize_memo_markdown("\n".join(lines), blocked=_is_blocked_memo(memo))


def _evidence_block_lines(blocks: List[Dict[str, Any]]) -> List[str]:
    if not blocks:
        return ["- UNKNOWN"]
    lines: List[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        lines.append(
            "- "
            + "；".join(
                [
                    f"主张：{block.get('claim', 'UNKNOWN')}",
                    f"数据：{block.get('data', 'UNKNOWN')}",
                    f"来源：{block.get('source', 'UNKNOWN')}",
                    f"推论：{block.get('inference', 'UNKNOWN')}",
                ]
            )
        )
    return lines or ["- UNKNOWN"]


def _bullets(items: Iterable[Any]) -> List[str]:
    return [f"- {item}" for item in items]




def _attempt_lines(attempts: Iterable[Any]) -> List[str]:
    rows = [item for item in attempts if isinstance(item, dict)]
    if not rows:
        return ["- 本轮没有记录到主动搜索；只能使用已有上下文。"]
    lines = []
    for item in rows:
        status = _reader_status(str(item.get("status") or ""))
        query = item.get("query") or item.get("tool") or item.get("source") or "UNKNOWN"
        detail = f"{item.get('source') or item.get('tool')}: {query} -> {status}"
        if item.get("failure_reason"):
            detail += f"（{_reader_failure_reason(str(item.get('failure_reason')))}）"
        if item.get("results_count") is not None:
            detail += f"，返回 {item.get('results_count')} 条"
        lines.append(f"- {detail}")
    return lines


def _limited_conclusion(memo: Dict[str, Any]) -> str:
    if memo.get("limited_report"):
        return memo.get("conclusion") or "证据不足，只能作为有限信息背景参考；不得作为交易动作依据。"
    return memo.get("conclusion") or "证据覆盖可读。"


def _is_blocked_memo(memo: Dict[str, Any]) -> bool:
    text = " ".join(str(memo.get(k) or "") for k in ["status", "conclusion", "readable_summary"]).upper()
    return bool(memo.get("fatal_objection")) or "BLOCKED" in text or "FATAL" in text


def _reader_status(value: str) -> str:
    return {
        "RAW_AGENT": "真实 Agent",
        "DERIVED_FROM_ARTIFACT": "回填审计",
        "BLOCKED_BY_FATAL": "治理层阻断",
        "NO_ACTION": "不操作",
        "REFRESHED": "可用",
        "FAILED": "失败",
        "DEGRADED": "降级",
        "BLOCKED": "阻断",
        "PASS": "通过",
        "WARN": "警告",
    }.get(value.upper(), value)


def _reader_failure_reason(value: str) -> str:
    return {
        "rate_limited": "限流/额度不足",
        "missing_key": "缺 key",
        "permission_limited": "权限不足",
        "timeout": "超时",
        "anti_bot": "反爬",
        "parse_error": "解析失败",
        "no_matching_market": "无匹配市场",
        "endpoint_changed": "接口异常",
        "unknown": "未知原因",
    }.get(value, value)


def _sanitize_memo_markdown(markdown: str, *, blocked: bool = False) -> str:
    text = markdown
    replacements = {
        "BLOCKED_BY_FATAL": "治理层阻断",
        "no_action": "不操作",
        "RAW_AGENT": "真实 Agent",
        "DERIVED_FROM_ARTIFACT": "回填审计",
        "强烈买入信号": "技术强势信号",
        "买入信号": "技术信号",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    if blocked:
        blocked_replacements = {
            "建议立即减仓或清仓止损": "如已持仓，仅做人工风险复核，不执行自动交易",
            "立即减仓": "人工风险复核",
            "清仓止损": "人工风险复核",
            "清仓": "人工风险复核",
            "止损": "风险复核",
            "强烈买入": "技术强势",
            "买入": "关注",
            "卖出": "风险复核",
            "减仓": "风险复核",
        }
        for old, new in blocked_replacements.items():
            text = text.replace(old, new)
        if "阻断 / 不操作 / 0%" not in text:
            text += "\n\n> 最终门控：阻断 / 不操作 / 0%。"
    return text




def _ensure_memo_evidence_fields(memo: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(memo, dict):
        return memo
    if memo.get("evidence_pack") and memo.get("evidence_level"):
        return memo
    upgraded = dict(memo)
    attempts = upgraded.get("source_attempts") if isinstance(upgraded.get("source_attempts"), list) else []
    audit = upgraded.get("audit_detail") if isinstance(upgraded.get("audit_detail"), dict) else {}
    if not attempts:
        attempts = source_attempts_from_tool_calls(audit.get("tool_calls_log") or [])
    agent = str(upgraded.get("agent") or "")
    symbol = str(upgraded.get("symbol") or "")
    if not attempts and agent in {"StockSourceAgent", "FundamentalReportsAgent", "IntelCatalystAgent", "SourceReviewAgent", "MacroGeopoliticsAgent", "CandidateReviewAgent"}:
        attempts = _stock_source_attempts(symbol, "", kind="fundamental" if agent == "FundamentalReportsAgent" else "source") if symbol else []
    missing = [str(item) for item in (upgraded.get("missing_data") or []) if str(item)]
    critical_missing = bool(upgraded.get("fatal_objection")) or (agent in {"StockSourceAgent", "FundamentalReportsAgent", "IntelCatalystAgent"} and bool(attempts))
    pack = build_evidence_pack(
        scope=str(upgraded.get("scope") or "stock"),
        symbol=symbol,
        source_attempts=attempts,
        evidence_items=upgraded.get("evidence_blocks") or upgraded.get("facts") or [],
        missing_evidence=missing,
        critical_missing=critical_missing,
    )
    upgraded["evidence_pack"] = pack
    upgraded["evidence_level"] = pack.get("evidence_level")
    upgraded["source_attempts"] = pack.get("source_attempts") or []
    upgraded["limited_report"] = bool(pack.get("limited_report"))
    upgraded["confidence"] = pack.get("confidence")
    if upgraded.get("limited_report") and upgraded.get("origin") == "RAW_AGENT":
        upgraded["origin_label"] = _origin_label("RAW_AGENT", True)
        upgraded["readable_summary"] = _readable_summary("RAW_AGENT", str(upgraded.get("status") or "WARN"), str(upgraded.get("conclusion") or ""), True)
    return upgraded


def _existing_raw_memo(root: Path, rel: str) -> Optional[Dict[str, Any]]:
    existing = _read_json(root / f"{rel}.json")
    if isinstance(existing, dict) and existing.get("schema") == AGENT_MEMO_SCHEMA and existing.get("origin") == "RAW_AGENT":
        return existing
    return None


def _write_memo_triplet(root: Path, rel: str, memo: Dict[str, Any], *, preserve_raw: bool = True) -> List[str]:
    if preserve_raw:
        raw = _existing_raw_memo(root, rel)
        if raw is not None:
            memo = raw
    memo = _ensure_memo_evidence_fields(memo)
    json_path = root / f"{rel}.json"
    md_path = root / f"{rel}.md"
    html_path = root / f"{rel}.html"
    md = _memo_markdown(memo)
    _write_json(json_path, memo)
    _write_text(md_path, md)
    _write_text(html_path, _html_page(str(memo.get("agent") or rel), md))
    return [f"{rel}.json", f"{rel}.md", f"{rel}.html"]


def write_runtime_context_pack(ctx: Any, *, output_dir: Path | str, run_date: str) -> List[str]:
    """Write the raw ContextPack for a governed stock run.

    This is called before governed agents run. It is not an agent memo, but it
    is the evidence bundle every per-stock Agent memo links back to.
    """
    out = Path(output_dir)
    symbol = str(getattr(ctx, "stock_code", "") or "").strip()
    if not symbol:
        return []
    rel = f"stocks/{symbol}/00_context_pack"
    payload = {
        "schema": "context_pack_v1",
        "origin": "RAW_AGENT",
        "run_date": run_date,
        "symbol": symbol,
        "name": getattr(ctx, "stock_name", ""),
        "facts": _context_pack_facts(ctx),
        "data_keys": sorted((getattr(ctx, "data", {}) or {}).keys()),
        "source_refs": _source_refs_for_stage("context_pack", run_date),
        "macro_status": _nested_get(ctx.get_data("macro_review") or {}, "status"),
        "portfolio_context": ctx.get_data("portfolio_context"),
        "no_trade_execution": True,
    }
    _write_json(out / f"{rel}.json", payload)
    md = "\n".join(
        [
            f"# ContextPack — {symbol}",
            "",
            "## 一句话结论",
            "这是 governed 个股分析的运行时共享证据包；所有后续 Agent 只能在这些证据基础上推理。",
            "",
            "## 我看了什么",
            *_bullets(payload["source_refs"]),
            "",
            "## 关键数据",
            *_bullets(payload["facts"] or ["UNKNOWN"]),
            "",
            "## 审计详情",
            "```json",
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            "```",
        ]
    )
    _write_text(out / f"{rel}.md", md)
    _write_text(out / f"{rel}.html", _html_page(f"ContextPack {symbol}", md))
    return [f"{rel}.json", f"{rel}.md", f"{rel}.html"]


def write_runtime_stage_memo(
    ctx: Any,
    stage_result: Any,
    *,
    output_dir: Path | str,
    run_date: str = "",
) -> List[str]:
    """Persist one governed stage as a RAW_AGENT memo."""
    stage_name = str(getattr(stage_result, "stage_name", "") or "")
    mapping = RUNTIME_STAGE_MEMOS.get(stage_name)
    if mapping is None:
        return []
    status_value = str(getattr(getattr(stage_result, "status", ""), "value", getattr(stage_result, "status", "")))
    if status_value != "completed":
        return []

    display_agent, file_name = mapping
    symbol = str(getattr(ctx, "stock_code", "") or "").strip()
    if not symbol:
        return []

    opinion = getattr(stage_result, "opinion", None) or _latest_opinion(ctx, stage_name)
    raw_data = getattr(opinion, "raw_data", None) if opinion is not None else None
    if not isinstance(raw_data, dict):
        raw_data = _parse_raw_text((getattr(stage_result, "meta", {}) or {}).get("raw_text"))

    facts = _runtime_facts(stage_name, raw_data, opinion, ctx)
    reasoning = _runtime_reasoning(stage_name, raw_data, opinion)
    conclusion = _runtime_conclusion(stage_name, raw_data, opinion)
    missing_data = _runtime_missing_data(stage_name, raw_data)
    fatal = _runtime_fatal(stage_name, raw_data)
    status = _runtime_status(stage_name, raw_data, fatal)
    refs = _source_refs_for_stage(stage_name, run_date)
    tool_calls_log = (getattr(stage_result, "meta", {}) or {}).get("tool_calls_log") or []
    attempts = source_attempts_from_tool_calls(tool_calls_log)
    pack = build_evidence_pack(
        scope="stock",
        symbol=symbol,
        source_attempts=attempts,
        evidence_items=facts,
        missing_evidence=missing_data,
        critical_missing=fatal and stage_name in {"evidence_gate", "scoring", "cio", "decision"},
    )
    rel = f"stocks/{symbol}/{file_name}"
    memo = _memo(
        agent=display_agent,
        scope="stock",
        symbol=symbol,
        status=status,
        facts=facts,
        reasoning=reasoning,
        conclusion=conclusion,
        missing_data=missing_data,
        source_refs=refs,
        fatal_objection=fatal,
        next_step=_runtime_next_step(stage_name, raw_data, fatal),
        origin="RAW_AGENT",
        readable_summary=conclusion,
        evidence_blocks=[
            {
                "claim": conclusion or f"{display_agent} 已完成",
                "data": "；".join(facts[:4]) if facts else "RAW_AGENT completed",
                "source": "；".join(refs[:3]) if refs else "runtime_context",
                "inference": "；".join(reasoning[:2]) if reasoning else "见审计详情。",
            }
        ],
        audit_detail={
            "schema": AGENT_MEMO_SCHEMA,
            "origin": "RAW_AGENT",
            "stage_name": stage_name,
            "status": status,
            "raw_untrusted": True,
            "raw_data": raw_data,
            "raw_text": (getattr(stage_result, "meta", {}) or {}).get("raw_text"),
            "tokens_used": getattr(stage_result, "tokens_used", 0),
            "tool_calls_count": getattr(stage_result, "tool_calls_count", 0),
            "models_used": (getattr(stage_result, "meta", {}) or {}).get("models_used", []),
        },
        evidence_level=pack.get("evidence_level", ""),
        source_attempts=attempts,
        limited_report=bool(pack.get("limited_report")),
        evidence_pack=pack,
    )
    return _write_memo_triplet(Path(output_dir), rel, memo, preserve_raw=False)


def _latest_opinion(ctx: Any, stage_name: str) -> Any:
    opinions = list(getattr(ctx, "opinions", []) or [])
    for opinion in reversed(opinions):
        if getattr(opinion, "agent_name", "") == stage_name:
            return opinion
    return None


def _parse_raw_text(raw_text: Any) -> Dict[str, Any]:
    if not isinstance(raw_text, str) or not raw_text.strip():
        return {}
    try:
        return json.loads(raw_text)
    except Exception:
        return {"raw_text": raw_text.strip()[:4000]}


def _context_pack_facts(ctx: Any) -> List[str]:
    data = getattr(ctx, "data", {}) or {}
    facts = [
        f"data_keys={','.join(sorted(data.keys())) or 'none'}",
        f"has_macro_review={bool(data.get('macro_review'))}",
        f"has_market_heat_context={bool(data.get('market_heat_context'))}",
        f"has_event_context={bool(data.get('event_context'))}",
        f"has_portfolio_context={bool(data.get('portfolio_context'))}",
    ]
    quote = data.get("realtime_quote")
    if isinstance(quote, dict):
        facts.append(f"price={quote.get('price', 'UNKNOWN')}")
        facts.append(f"quote_source={quote.get('source', 'UNKNOWN')}")
    return facts


def _runtime_facts(stage_name: str, raw_data: Dict[str, Any], opinion: Any, ctx: Any) -> List[str]:
    facts: List[str] = []
    if opinion is not None:
        facts.append(f"signal={getattr(opinion, 'signal', '')}")
        facts.append(f"confidence={getattr(opinion, 'confidence', '')}")
    for key in _fact_keys_for_stage(stage_name):
        if key in raw_data:
            facts.append(f"{key}={_short_value(raw_data.get(key))}")
    if stage_name == "evidence_gate":
        facts.extend(str(item) for item in raw_data.get("facts") or [])
    if stage_name == "cio":
        trade_plan = raw_data.get("trade_plan")
        if isinstance(trade_plan, dict):
            facts.append(f"action={trade_plan.get('action')}")
            facts.append(f"position={trade_plan.get('target_position_pct')}%")
    if stage_name == "decision":
        governance = raw_data.get("governance")
        if isinstance(governance, dict):
            facts.append(f"cio_status={governance.get('cio_status')}")
            facts.append(f"score={governance.get('score')}")
    return [item for item in facts if item and item != "confidence="] or ["RAW_AGENT completed"]


def _fact_keys_for_stage(stage_name: str) -> List[str]:
    return {
        "macro": ["status", "risk_state", "market_regime", "confidence", "key_macro_drivers", "data_gaps"],
        "technical": ["trend_score", "ma_alignment", "volume_status", "pattern", "key_levels"],
        "intel": ["sentiment_label", "capital_flow_signal", "positive_catalysts", "risk_alerts", "key_news"],
        "risk": ["risk_level", "risk_score", "flags", "veto_buy", "signal_adjustment"],
        "evidence_gate": ["status", "missing_evidence", "warnings", "fatal_objection"],
        "red_blue": ["arbitration", "emotion_injection_detected"],
        "scoring": ["total_score", "gate_result", "position_size_range", "cannot_trade_reasons"],
        "cio": ["status", "headline", "confidence", "cannot_proceed_reasons", "fatal_objections"],
        "decision": ["decision_type", "sentiment_score", "analysis_summary", "operation_advice"],
    }.get(stage_name, [])


def _runtime_reasoning(stage_name: str, raw_data: Dict[str, Any], opinion: Any) -> List[str]:
    reasoning: List[str] = []
    if opinion is not None and getattr(opinion, "reasoning", ""):
        reasoning.append(str(getattr(opinion, "reasoning")))
    value = raw_data.get("reasoning")
    if isinstance(value, list):
        reasoning.extend(str(item) for item in value)
    elif value:
        reasoning.append(str(value))
    if stage_name == "red_blue":
        arb = raw_data.get("arbitration") if isinstance(raw_data.get("arbitration"), dict) else {}
        if arb.get("verdict"):
            reasoning.append(str(arb.get("verdict")))
    if stage_name == "scoring":
        reasoning.append("评分 < 6.0 时强制 no_action / 0%。")
    if stage_name == "cio":
        reasoning.append("TradeDecisionGate 只做门控，不执行交易。")
    return list(dict.fromkeys(item for item in reasoning if item)) or ["见 RAW_AGENT 审计详情。"]


def _runtime_conclusion(stage_name: str, raw_data: Dict[str, Any], opinion: Any) -> str:
    if stage_name == "evidence_gate" and raw_data.get("conclusion"):
        return str(raw_data.get("conclusion"))
    if stage_name == "scoring":
        score = _score_float(raw_data.get("total_score"))
        gate = str(raw_data.get("gate_result") or "UNKNOWN")
        return f"评分 {score}/10，gate={gate}；{'阻断交易动作' if score < 6 else '可进入 TradeDecisionGate'}。"
    if stage_name == "cio":
        status = str(raw_data.get("status") or "UNKNOWN")
        trade_plan = raw_data.get("trade_plan") if isinstance(raw_data.get("trade_plan"), dict) else {}
        action = trade_plan.get("action", "UNKNOWN")
        pct = trade_plan.get("target_position_pct", "UNKNOWN")
        return f"TradeDecisionGate={status}；action={action}；position={pct}% 。"
    if stage_name == "decision":
        return str(raw_data.get("analysis_summary") or raw_data.get("operation_advice") or "最终报告已生成。")
    if opinion is not None and getattr(opinion, "reasoning", ""):
        return str(getattr(opinion, "reasoning"))
    return "RAW_AGENT 已完成，详见审计详情。"


def _runtime_missing_data(stage_name: str, raw_data: Dict[str, Any]) -> List[str]:
    for key in ("missing_data", "missing_evidence", "data_gaps", "cannot_trade_reasons"):
        value = raw_data.get(key)
        if isinstance(value, list):
            return [str(item) for item in value if str(item)]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
    return []


def _runtime_fatal(stage_name: str, raw_data: Dict[str, Any]) -> bool:
    if bool(raw_data.get("fatal_objection")):
        return True
    if stage_name == "scoring":
        return str(raw_data.get("gate_result") or "").upper() == "BLOCKED" or _score_float(raw_data.get("total_score")) < 6
    if stage_name == "cio":
        return str(raw_data.get("status") or "").upper() == "BLOCKED_BY_FATAL"
    if stage_name == "risk":
        return bool(raw_data.get("veto_buy")) or str(raw_data.get("risk_level") or "").lower() == "high"
    return False


def _runtime_status(stage_name: str, raw_data: Dict[str, Any], fatal: bool) -> str:
    if fatal:
        return "BLOCKED"
    if stage_name == "evidence_gate" and str(raw_data.get("status") or "").upper() == "NEEDS_EVIDENCE":
        return "WARN"
    if stage_name == "cio" and str(raw_data.get("status") or "").upper() == "NEEDS_EVIDENCE":
        return "WARN"
    if _runtime_missing_data(stage_name, raw_data):
        return "WARN"
    return "PASS"


def _runtime_next_step(stage_name: str, raw_data: Dict[str, Any], fatal: bool) -> str:
    if fatal:
        return "不执行交易动作；先解决阻断原因后重新审查。"
    return {
        "macro": "把宏观约束交给技术/情报/风险 Agent 使用。",
        "technical": "用技术关键位验证是否追高或等待承接。",
        "intel": "继续补公告/新闻/研报原文，确认催化剂质量。",
        "risk": "把高严重度风险传给红蓝和评分。",
        "evidence_gate": "证据可进入红蓝；缺口由后续治理层保守处理。",
        "red_blue": "将红蓝仲裁交给 ScoringAgent 量化。",
        "scoring": "将评分门控交给 TradeDecisionGate。",
        "cio": "最终 action/position 以 TradeDecisionGate 为准。",
        "decision": "在 Pages 展示门控后的最终报告。",
    }.get(stage_name, "等待下一阶段。")


def _source_refs_for_stage(stage_name: str, run_date: str) -> List[str]:
    compact = (run_date or "").replace("-", "")
    common = [f"stocks/{{symbol}}/00_context_pack.json"]
    refs = {
        "context_pack": [f"market_cycle/{run_date}/01_macro_review.json", f"market_cycle/{run_date}/13_source_health.json", f"market_cycle/{run_date}/11_deep_review_queue.json"],
        "macro": [f"market_cycle/{run_date}/01_macro_review.json", "data/macro_cache/macro_context_latest.json"],
        "technical": ["runtime:realtime_quote", "runtime:daily_history", "runtime:trend_result"],
        "intel": [f"market_heat/latest_market_heat.json", "runtime:news_context", f"market_cycle/{run_date}/11_deep_review_queue.json"],
        "risk": ["runtime:event_context", "runtime:news_context", f"market_cycle/{run_date}/13_source_health.json"],
        "evidence_gate": ["runtime:agent_opinions", "runtime:risk_flags", f"market_cycle/{run_date}/13_source_health.json"],
        "red_blue": ["runtime:evidence_gate_result", "runtime:agent_opinions"],
        "scoring": ["runtime:red_blue_result", "runtime:agent_opinions"],
        "cio": ["runtime:scoring_result", "runtime:red_blue_result", "runtime:portfolio_context"],
        "decision": ["runtime:cio_result", f"report_{compact}.md" if compact else "runtime:final_dashboard"],
    }
    return refs.get(stage_name, common)


def _short_value(value: Any, limit: int = 280) -> str:
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, default=str)
    else:
        text = str(value)
    return text if len(text) <= limit else text[:limit] + "..."


def _nested_get(payload: Dict[str, Any], key: str) -> Any:
    return payload.get(key) if isinstance(payload, dict) else None


PUBLIC_SOURCE_DEFAULTS = [
    {"source": "Tavily", "component": "search_provider", "domain": "news", "status": "DEGRADED", "failure_reason": "unknown", "criticality": "supporting", "manual_action": "检查 Tavily key/额度；额度耗尽时走 SearXNG/Google News/GDELT fallback。"},
    {"source": "SearXNG", "component": "search_provider", "domain": "news", "status": "DEGRADED", "failure_reason": "rate_limited", "criticality": "supporting", "manual_action": "优先配置自建 SearXNG；公共实例 429/403 只作降级 fallback。"},
    {"source": "CNINFO", "component": "official_announcements", "domain": "a_share", "status": "DEGRADED", "failure_reason": "unknown", "criticality": "supporting", "manual_action": "补公告查询 adapter 或检查公告任务输出。"},
    {"source": "Eastmoney", "component": "a_share_quote", "domain": "a_share", "status": "DEGRADED", "failure_reason": "endpoint_changed", "criticality": "supporting", "manual_action": "保留 AKShare/Sina fallback，记录 Eastmoney 断连。"},
    {"source": "AKShare", "component": "a_share_quote_fallback", "domain": "a_share", "status": "DEGRADED", "failure_reason": "unknown", "criticality": "supporting", "manual_action": "确认 AKShare/Sina fallback 成功率和字段覆盖。"},
    {"source": "Tushare", "component": "a_share_financials", "domain": "a_share", "status": "DEGRADED", "failure_reason": "permission_limited", "criticality": "supporting", "manual_action": "若无权限，不把 Tushare 当 critical；用公开公告/财报 fallback。"},
    {"source": "Polymarket", "component": "prediction_market", "domain": "geo", "status": "DEGRADED", "failure_reason": "no_matching_market", "criticality": "optional", "manual_action": "补地缘场景关键词映射和流动性过滤。"},
]


def _append_required_public_sources(inventory: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    existing_sources = {str(row.get("source") or "").lower() for row in inventory}
    geo_status = next((row.get("status") for row in inventory if row.get("domain") == "geo"), "")
    appended = list(inventory)
    for default in PUBLIC_SOURCE_DEFAULTS:
        if str(default["source"]).lower() in existing_sources:
            continue
        row = {
            "schema": SOURCE_STATUS_SCHEMA,
            "source": default["source"],
            "component": default["component"],
            "domain": default["domain"],
            "status": default["status"],
            "failure_reason": default["failure_reason"],
            "criticality": default["criticality"],
            "impact_scope": _infer_impact_scope(default),
            "fallback_used": "待确认",
            "next_retry": "next_daily_run",
            "manual_action": default["manual_action"],
        }
        if default["source"] == "Polymarket" and geo_status == "AVAILABLE_NO_MATCHING_MARKET":
            row["status"] = "AVAILABLE_NO_MATCHING_MARKET"
            row["failure_reason"] = "no_matching_market"
        appended.append(row)
    return appended


def _source_attempts_from_inventory(inventory: List[Dict[str, Any]], *, domains: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    domain_set = set(domains or [])
    attempts = []
    for row in inventory:
        if not isinstance(row, dict):
            continue
        if domain_set and row.get("domain") not in domain_set:
            continue
        status = str(row.get("status") or "DEGRADED")
        attempts.append({
            "schema": "source_attempt_v1",
            "source": row.get("source") or row.get("component") or "unknown",
            "tool": row.get("component") or row.get("source") or "unknown",
            "domain": row.get("domain") or "system",
            "query": f"source health check: {row.get('source') or row.get('component')}",
            "status": status,
            "failure_reason": row.get("failure_reason") or "",
            "error": row.get("manual_action") or "",
            "results_count": 1 if status == "REFRESHED" else 0,
            "impact_scope": row.get("impact_scope") or ["system"],
        })
    return attempts


def _stock_source_attempts(symbol: str, name: str, *, kind: str) -> List[Dict[str, Any]]:
    base = [
        ("CNINFO", "official_announcements", "公告/监管原文"),
        ("Eastmoney", "a_share_quote", "行情/估值/热度"),
        ("AKShare", "a_share_quote_fallback", "行情 fallback"),
        ("Tushare", "a_share_financials", "财务字段"),
        ("Tavily", "search_provider", "新闻/研报搜索"),
        ("SearXNG", "search_provider", "搜索 fallback"),
    ]
    attempts = []
    for source, tool, purpose in base:
        attempts.append({
            "schema": "source_attempt_v1",
            "source": source,
            "tool": tool,
            "domain": "reports" if kind == "fundamental" else "a_share",
            "query": f"{name} {symbol} {purpose}".strip(),
            "status": "DEGRADED",
            "failure_reason": "unknown" if source not in {"Tushare"} else "permission_limited",
            "error": "artifact-only evidence; raw source transcript not available",
            "results_count": 0,
            "stock_code": symbol,
            "stock_name": name,
            "impact_scope": ["stock_source", "fundamental", "evidence_gate"],
        })
    return attempts


def _limited_evidence_pack(scope: str, symbol: str, attempts: List[Dict[str, Any]], missing: List[str]) -> Dict[str, Any]:
    return build_evidence_pack(
        scope=scope,
        symbol=symbol,
        source_attempts=attempts,
        evidence_items=[],
        missing_evidence=missing,
        critical_missing=True,
    )

def build_source_inventory(health: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = health.get("rows") or health.get("components") or []
    inventory: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_status = str(row.get("status") or "").upper()
        warnings = [str(item) for item in (row.get("warnings") or [])]
        status = _normalize_source_status(raw_status, warnings)
        inventory.append(
            {
                "schema": SOURCE_STATUS_SCHEMA,
                "source": row.get("source") or row.get("component") or "unknown",
                "component": row.get("component") or "unknown",
                "domain": _infer_domain(row),
                "status": status,
                "failure_reason": _infer_failure_reason(raw_status, warnings),
                "criticality": row.get("criticality") or "supporting",
                "impact_scope": _infer_impact_scope(row),
                "fallback_used": row.get("fallback_used") or row.get("fallback") or "",
                "next_retry": row.get("next_retry") or "next_daily_run",
                "manual_action": _manual_action(row, status, warnings),
            }
        )
    return _append_required_public_sources(inventory)


def _health_with_macro_signal(health: Dict[str, Any], macro: Dict[str, Any]) -> Dict[str, Any]:
    if not _prediction_market_available_without_match(macro):
        return health
    cloned = dict(health)
    rows = []
    for row in health.get("rows") or health.get("components") or []:
        if not isinstance(row, dict):
            rows.append(row)
            continue
        item = dict(row)
        source_text = f"{item.get('component', '')} {item.get('source', '')}".lower()
        if "prediction" in source_text or "polymarket" in source_text:
            warnings = list(item.get("warnings") or [])
            if "no_matching_market" not in warnings:
                warnings.append("no_matching_market")
            item["warnings"] = warnings
        rows.append(item)
    cloned["rows"] = rows
    return cloned


def _prediction_market_available_without_match(macro: Dict[str, Any]) -> bool:
    if str(macro.get("prediction_market_status") or "").lower() not in {"available", "refreshed"}:
        return False
    scenarios = macro.get("geopolitical_scenarios") or []
    if not scenarios:
        return False
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue
        if scenario.get("market_probability") is not None:
            return False
        try:
            if float(scenario.get("fusion_weight") or 0) > 0:
                return False
        except (TypeError, ValueError):
            pass
    return True


def _normalize_source_status(raw_status: str, warnings: Optional[List[str]] = None) -> str:
    joined = " ".join(warnings or []).lower()
    if raw_status in {"AVAILABLE", "REFRESHED", "OK", "SUCCESS"} and (
        "no_matching_market" in joined or "no matching" in joined
    ):
        return "AVAILABLE_NO_MATCHING_MARKET"
    if raw_status in {"AVAILABLE", "REFRESHED", "OK", "SUCCESS"}:
        return "REFRESHED"
    if raw_status in {"DISABLED", "SKIPPED"}:
        return "DISABLED"
    if raw_status in {"FAILED", "UNAVAILABLE", "ERROR", "MISSING"}:
        return "FAILED"
    return "DEGRADED" if raw_status == "DEGRADED" else "DEGRADED"


def _infer_failure_reason(raw_status: str, warnings: List[str]) -> str:
    joined = " ".join(warnings).lower()
    if raw_status in {"AVAILABLE", "REFRESHED", "OK", "SUCCESS"} and not warnings:
        return ""
    if "missing_key" in joined or "fred_key_missing" in joined or "fmp_unavailable" in joined or "needs_key" in joined:
        return "missing_key"
    if "permission" in joined or "402" in joined or "403" in joined:
        return "permission_limited"
    if "429" in joined or "rate" in joined:
        return "rate_limited"
    if "anti" in joined or "captcha" in joined:
        return "anti_bot"
    if "parse" in joined:
        return "parse_error"
    if "stale" in joined or "cache" in joined:
        return "stale_cache"
    if "no_matching" in joined or "no matching" in joined:
        return "no_matching_market"
    return "unknown"


def _infer_domain(row: Dict[str, Any]) -> str:
    text = f"{row.get('component', '')} {row.get('source', '')}".lower()
    if any(token in text for token in ["macro", "fmp", "fred", "bea", "eia", "treasury", "bls", "fed"]):
        return "macro"
    if any(token in text for token in ["polymarket", "prediction", "geo"]):
        return "geo"
    if any(token in text for token in ["portfolio", "holding"]):
        return "portfolio"
    if any(token in text for token in ["market_heat", "eastmoney", "cninfo", "a_share"]):
        return "a_share"
    if any(token in text for token in ["sec", "yahoo", "nasdaq", "us_stock"]):
        return "us_stock"
    if any(token in text for token in ["news", "tavily", "gdelt"]):
        return "news"
    if "crypto" in text:
        return "crypto"
    if "option" in text:
        return "options"
    return "reports"


def _infer_impact_scope(row: Dict[str, Any]) -> List[str]:
    component = str(row.get("component") or "").lower()
    criticality = str(row.get("criticality") or "").lower()
    scope = set()
    if "macro" in component:
        scope.update(["market", "trade_review"])
    if "portfolio" in component:
        scope.update(["portfolio", "trade_review"])
    if "queue" in component or "screening" in component:
        scope.update(["opportunity", "trade_review"])
    if "governed" in component:
        scope.update(["evidence", "trade_review"])
    if criticality == "critical":
        scope.add("trade_review")
    return sorted(scope or {"system"})


def _manual_action(row: Dict[str, Any], status: str, warnings: List[str]) -> str:
    if status == "REFRESHED":
        return "none"
    reason = _infer_failure_reason(str(row.get("status") or "").upper(), warnings)
    if reason == "missing_key":
        return "检查对应 GitHub Secret / 本地 .env 是否配置并有效。"
    if reason == "permission_limited":
        return "确认当前 API plan 是否支持该 endpoint，必要时启用免费官方 fallback。"
    if reason == "rate_limited":
        return "降低并发、启用缓存、等待下一轮重试。"
    if reason == "no_matching_market":
        return "补市场关键词映射，确认是否有足够流动性和清晰结算规则。"
    return "查看 source gap plan，补源或接受降级。"


def _source_gap_plan(inventory: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    plan = []
    for item in inventory:
        if item.get("status") == "REFRESHED":
            continue
        plan.append(
            {
                "source": item.get("source"),
                "component": item.get("component"),
                "domain": item.get("domain"),
                "status": item.get("status"),
                "failure_reason": item.get("failure_reason"),
                "criticality": item.get("criticality"),
                "impact_scope": item.get("impact_scope"),
                "fallback_used": item.get("fallback_used"),
                "where_to_collect": _where_to_collect(str(item.get("domain") or "")),
                "manual_action": item.get("manual_action"),
            }
        )
    return plan


def _where_to_collect(domain: str) -> List[str]:
    mapping = {
        "macro": ["FRED", "BEA", "EIA", "Treasury", "NY Fed", "BLS"],
        "geo": ["Polymarket Gamma/Data/CLOB"],
        "a_share": ["Eastmoney", "CNINFO", "SSE/SZSE", "Gov.cn", "CSRC", "NDRC", "PBOC", "Tushare", "AKShare", "efinance"],
        "us_stock": ["SEC EDGAR APIs", "SEC Company Facts", "Yahoo", "Nasdaq"],
        "news": ["Google News RSS", "GDELT", "Tavily", "Company IR"],
        "reports": ["Google News RSS", "Tavily", "Company IR", "公开研报页面"],
        "portfolio": ["invest-system DB", "PORTFOLIO_HOLDINGS", "持仓导出文件"],
        "crypto": ["CoinGecko", "Binance public"],
        "options": ["Yahoo fallback", "Tradier", "Polygon", "Alpaca", "IBKR"],
    }
    return mapping.get(domain, ["source inventory"])


def _probe_tasks() -> List[Dict[str, Any]]:
    return [
        {"task": "macro_probe", "goal": "验证 FRED/BEA/EIA/Treasury 能否生成增长、通胀、利率、美元、能源、信用六因子。", "sources": _where_to_collect("macro")},
        {"task": "a_share_probe", "goal": "验证 Eastmoney/CNINFO/Tushare/AKShare/efinance 的行情、公告、财务字段。", "sources": _where_to_collect("a_share")},
        {"task": "us_stock_probe", "goal": "验证 SEC submissions、company facts、Yahoo 财务快照。", "sources": _where_to_collect("us_stock")},
        {"task": "news_report_probe", "goal": "验证 Tavily/Google News/GDELT/IR 的新闻、研报、公告原文链接。", "sources": _where_to_collect("news")},
        {"task": "polymarket_probe", "goal": "把地缘四场景映射到可用市场，输出质量分和权重。", "sources": _where_to_collect("geo")},
        {"task": "portfolio_probe", "goal": "验证持仓行情、成本、浮盈亏、公告、板块联动。", "sources": _where_to_collect("portfolio")},
        {"task": "source_gap_plan", "goal": "每日列出缺什么源、去哪拿、是否要 key、是否阻断交易审查。", "sources": ["source_status_v1"]},
    ]


def _write_table_report(root: Path, rel: str, title: str, rows: List[Dict[str, Any]], *, intro: str = "") -> List[str]:
    json_path = root / f"{rel}.json"
    md_path = root / f"{rel}.md"
    html_path = root / f"{rel}.html"
    _write_json(json_path, rows)
    if rel.startswith("sources/"):
        md_lines = _source_narrative_markdown(title, rows, intro=intro)
    else:
        headers = sorted({key for row in rows for key in row.keys()})
        md_lines = [f"# {title}", "", intro, ""]
        if rows:
            md_lines.append("| " + " | ".join(headers) + " |")
            md_lines.append("|" + "|".join("---" for _ in headers) + "|")
            for row in rows:
                md_lines.append("| " + " | ".join(_cell(row.get(key)) for key in headers) + " |")
        else:
            md_lines.append("无缺口。")
    md = "\n".join(md_lines)
    _write_text(md_path, md)
    _write_text(html_path, _html_page(title, md))
    return [f"{rel}.json", f"{rel}.md", f"{rel}.html"]


def _source_narrative_markdown(title: str, rows: List[Dict[str, Any]], *, intro: str = "") -> List[str]:
    md_lines = [f"# {title}", "", intro, ""]
    if not rows:
        md_lines.append("无缺口。")
        return md_lines

    if title == "Source Gap Plan":
        md_lines.extend(
            [
                "## 先读结论",
                "宏观只可背景参考，不是满血 regime；critical 源不可用才阻断交易审查，optional 源失败只降权。",
                "",
            ]
        )

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        domain = str(row.get("domain") or _infer_domain(row))
        grouped.setdefault(domain, []).append(row)

    ordered_domains = ["macro", "geo", "a_share", "us_stock", "news", "reports", "portfolio", "crypto", "options"]
    for domain in ordered_domains:
        items = grouped.pop(domain, [])
        if not items:
            continue
        label = SOURCE_DOMAIN_LABELS.get(domain, domain)
        md_lines.extend([f"## {label}", ""])
        md_lines.append(
            "| 数据源 | 今天状态 | 失败原因 | 影响哪个分析结论 | 是否阻断交易审查 | fallback 是否启用 | 下一步怎么修 |"
        )
        md_lines.append("|---|---|---|---|---|---|---|")
        for item in items:
            md_lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(item.get("source") or item.get("component")),
                        _cell(item.get("status")),
                        _source_failure_text(item),
                        _source_impact_text(item),
                        _source_blocking_text(item),
                        _cell(item.get("fallback_used") or "未启用"),
                        _source_manual_action_text(item),
                    ]
                )
                + " |"
            )
        md_lines.append("")

    for domain, items in sorted(grouped.items()):
        label = SOURCE_DOMAIN_LABELS.get(domain, domain)
        md_lines.extend([f"## {label}", ""])
        for item in items:
            md_lines.append(f"- {_cell(item.get('source'))}: {_cell(item.get('status'))}")
        md_lines.append("")
    return md_lines


def _source_failure_text(item: Dict[str, Any]) -> str:
    reason = str(item.get("failure_reason") or "")
    status = str(item.get("status") or "")
    if status == "AVAILABLE_NO_MATCHING_MARKET":
        return "API 可用，但未匹配到可用场景市场"
    if not reason:
        return "无"
    return {
        "missing_key": "缺 key 或 key 不可用",
        "permission_limited": "权限/套餐不足",
        "rate_limited": "限流",
        "endpoint_changed": "接口变化",
        "anti_bot": "反爬限制",
        "parse_error": "解析失败",
        "stale_cache": "缓存过期",
        "no_matching_market": "API 可用，但未匹配到可用场景市场",
        "unknown": "未知",
    }.get(reason, reason)


def _source_impact_text(item: Dict[str, Any]) -> str:
    domain = str(item.get("domain") or "")
    status = str(item.get("status") or "")
    if domain == "macro":
        return "影响宏观/地缘、六因子 regime 和交易审查置信度"
    if domain == "geo":
        if status == "AVAILABLE_NO_MATCHING_MARKET":
            return "影响 Polymarket 概率融合；本轮只能用内部场景概率"
        return "影响地缘概率校准"
    if domain == "a_share":
        return "影响 A股热榜、公告、候选池和深评队列"
    if domain == "us_stock":
        return "影响美股行情、SEC 事实和个股基本面"
    if domain in {"news", "reports"}:
        return "影响新闻、研报、公告原文和催化剂判断"
    if domain == "portfolio":
        return "影响持仓轻量复核、浮盈亏和是否进入 governed"
    if domain == "crypto":
        return "影响风险偏好温度计"
    if domain == "options":
        return "影响期权候选，不影响股票日报生成"
    return "影响系统审计和报告完整性"


def _source_blocking_text(item: Dict[str, Any]) -> str:
    status = str(item.get("status") or "")
    criticality = str(item.get("criticality") or "")
    if criticality == "critical" and status == "FAILED":
        return "阻断交易审查"
    if criticality == "critical" and status in {"DEGRADED", "AVAILABLE_NO_MATCHING_MARKET"}:
        return "不阻断日报，但交易审查降级"
    return "不阻断，只降权"


def _source_manual_action_text(item: Dict[str, Any]) -> str:
    status = str(item.get("status") or "")
    if status == "AVAILABLE_NO_MATCHING_MARKET":
        return "补市场关键词映射，确认是否有足够流动性和清晰结算规则"
    action = str(item.get("manual_action") or "").strip()
    if action and action != "none":
        return action
    return "保持监控，下一轮自动复查"


def _cell(value: Any) -> str:
    if isinstance(value, list):
        return "；".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value or "")


def _market_memos(
    run_date: str,
    health: Dict[str, Any],
    source_health_v2: Dict[str, Any],
    macro: Dict[str, Any],
    queue: Dict[str, Any],
    strategy: Dict[str, Any],
    governed_rows: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    inventory = build_source_inventory(health)
    source_attempts = _source_attempts_from_inventory(inventory)
    macro_attempts = _source_attempts_from_inventory(inventory, domains=["macro", "geo"])
    source_mode = str(source_health_v2.get("overallMode") or "")
    source_score = source_health_v2.get("overallScore")
    source_domains = source_health_v2.get("domains") if isinstance(source_health_v2.get("domains"), dict) else {}
    macro_domain = source_domains.get("macro") if isinstance(source_domains.get("macro"), dict) else {}
    macro_domain_status = str(macro_domain.get("status") or "").lower()
    source_blockers = [str(item) for item in (source_health_v2.get("blockingReasons") or []) if str(item)]
    candidates = queue.get("candidates") or []
    auto = queue.get("auto_governed_candidates") or []
    portfolio = next((row for row in (health.get("rows") or []) if isinstance(row, dict) and row.get("component") == "portfolio_holdings"), {})
    source_warn = (
        source_mode != "FULL_REVIEW"
        if source_mode
        else str(health.get("usability_verdict") or "").lower() not in {"usable", "available"}
    )
    macro_warn = macro_domain_status in {"missing", "degraded", "blocked"} or (not macro_domain_status and str(macro.get("status") or "").upper() != "REFRESHED")
    source_missing = source_blockers or [item["component"] for item in inventory if item.get("status") != "REFRESHED"]
    macro_missing = list(macro_domain.get("blockers") or []) or list(macro.get("data_gaps") or []) or [item["source"] for item in inventory if item.get("domain") in {"macro", "geo"} and item.get("status") != "REFRESHED"]
    candidate_missing = [] if auto else ["no_auto_governed_candidates", "non_hot_rank_evidence_required"]
    source_pack = build_evidence_pack(scope="market", source_attempts=source_attempts, evidence_items=[f"source_count={len(inventory)}"], missing_evidence=source_missing, critical_missing=source_warn)
    macro_pack = build_evidence_pack(scope="market", source_attempts=macro_attempts, evidence_items=[macro.get("headline") or "macro review"], missing_evidence=macro_missing, critical_missing=macro_warn)
    candidate_attempts = [
        {
            "schema": "source_attempt_v1",
            "source": "screening_funnel",
            "tool": "deep_review_queue",
            "domain": "candidate",
            "query": "candidate evidence cross-check",
            "status": "DEGRADED" if candidate_missing else "REFRESHED",
            "failure_reason": "unknown" if candidate_missing else "",
            "results_count": len(candidates),
            "impact_scope": ["candidate", "governed_selection"],
        }
    ]
    candidate_pack = build_evidence_pack(scope="market", source_attempts=candidate_attempts, evidence_items=candidates, missing_evidence=candidate_missing, critical_missing=bool(candidate_missing))
    return {
        "market/01_source_review": _memo(
            agent="SourceReviewAgent",
            scope="market",
            status=_status_from_blockers(warn=source_warn),
            facts=[
                f"source_health={health.get('usability_verdict', 'UNKNOWN')}",
                f"trade_review_usability={health.get('trade_review_usability', 'UNKNOWN')}",
                f"source_health_v2={source_mode or 'UNKNOWN'}",
                f"overall_score={source_score if source_score is not None else 'UNKNOWN'}",
                f"source_count={len(inventory)}",
            ],
            reasoning=["critical unavailable 才阻断交易审查；optional/supporting failure 只降权。"],
            conclusion="本轮源状态可支撑完整复盘。" if source_mode == "FULL_REVIEW" and not source_warn else "本轮可读但需按 source health 降权。",
            missing_data=[item["component"] for item in inventory if item.get("status") != "REFRESHED"],
            source_refs=["market_cycle/%s/13_source_health.json" % run_date, "run_status/%s/source_health_v2.json" % run_date],
            next_step="查看 sources/01_source_gap_plan，优先修 critical 或 macro 降级源。",
            origin="DERIVED_FROM_ARTIFACT",
            source_attempts=source_attempts,
            limited_report=bool(source_pack.get("limited_report")),
            evidence_pack=source_pack,
        ),
        "market/02_macro_geopolitics": _memo(
            agent="MacroGeopoliticsAgent",
            scope="market",
            status=_status_from_blockers(warn=macro_warn),
            facts=[
                f"macro_status={macro.get('status', 'UNKNOWN')}",
                f"source_health_macro={macro_domain_status or 'UNKNOWN'}",
                f"confidence={macro.get('confidence', 'UNKNOWN')}",
                f"headline={macro.get('headline', 'UNKNOWN')}",
                f"prediction_market_status={macro.get('prediction_market_status', 'UNKNOWN')}",
            ],
            reasoning=["宏观/地缘只做背景约束；Polymarket 只做概率校准，不能单独触发交易。"],
            conclusion="宏观证据已进入证据池，可作为市场背景。" if not macro_warn else "宏观降级，维持观察。",
            missing_data=list(macro.get("data_gaps") or []),
            source_refs=["market_cycle/%s/01_macro_review.json" % run_date, "run_status/%s/source_health_v2.json" % run_date],
            next_step="补 FRED/BEA/EIA/Treasury 与六因子缺项，再提高宏观置信度。",
            origin="DERIVED_FROM_ARTIFACT",
            source_attempts=macro_attempts,
            limited_report=bool(macro_pack.get("limited_report")),
            evidence_pack=macro_pack,
        ),
        "market/03_market_strategy": _memo(
            agent="MarketStrategyAgent",
            scope="market",
            status="PASS",
            facts=[
                f"regime={strategy.get('regime', 'UNKNOWN')}",
                f"confidence={strategy.get('confidence', 'UNKNOWN')}",
                f"headline={(strategy.get('strategy') or {}).get('headline', 'UNKNOWN')}",
            ],
            reasoning=["市场策略只决定观察/候选路由，不产生交易动作。"],
            conclusion=(strategy.get("strategy") or {}).get("headline") or "等待价格和证据共振。",
            missing_data=[],
            source_refs=["market_cycle/%s/14_market_strategy.json" % run_date],
            next_step="把市场热度转为候选条件；交易仍走个股 governed。",
        ),
        "market/04_candidate_review": _memo(
            agent="CandidateReviewAgent",
            scope="market",
            status="PASS",
            facts=[
                f"candidate_count={len(candidates)}",
                f"auto_governed_count={len(auto)}",
                "top_candidates=" + "；".join(
                    f"{row.get('name') or row.get('symbol')}:{row.get('verdict')}" for row in candidates[:6] if isinstance(row, dict)
                ),
            ],
            reasoning=["候选池用于筛选，不等于交易池；热榜证据必须经公告/研报/基本面/技术承接复核。"],
            conclusion="本轮候选多数处于观察或等待承接。",
            missing_data=[] if auto else ["no_auto_governed_candidates"],
            source_refs=["market_cycle/%s/11_deep_review_queue.json" % run_date],
            next_step="只让 DEEP_REVIEW_NOW 或持仓异常进入个股 governed 深评。",
            origin="DERIVED_FROM_ARTIFACT",
            source_attempts=candidate_attempts,
            limited_report=bool(candidate_pack.get("limited_report")),
            evidence_pack=candidate_pack,
        ),
        "market/05_portfolio_review": _memo(
            agent="PortfolioReviewAgent",
            scope="portfolio",
            status="PASS" if portfolio else "WARN",
            facts=[
                f"holding_status={portfolio.get('holding_status') or portfolio.get('status') or 'UNKNOWN'}",
                f"selected_count={portfolio.get('selected_count', 0)}",
                f"governed_count={portfolio.get('governed_count', 0)}",
                f"governed_report_count={len(governed_rows)}",
            ],
            reasoning=["持仓每日轻量复核；只有异常、强触发或证据足够才进入 governed 深评。"],
            conclusion="持仓已进入日报摘要。" if portfolio else "未发现结构化持仓源。",
            missing_data=[] if portfolio else ["portfolio_holdings_context_missing"],
            source_refs=["market_cycle/%s/13_source_health.json" % run_date, "governed_results.json"],
            next_step="补持仓成本/当前价/浮盈亏/公告联动，生成持仓页。",
        ),
    }


def _stock_memos(run_date: str, row: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    symbol = _text(row.get("code") or row.get("symbol"), "")
    name = _text(row.get("name"), "")
    score = row.get("score")
    gate = _text(row.get("gate"), "")
    cio_status = _text(row.get("cio_status"), "")
    trade_plan = row.get("trade_plan") if isinstance(row.get("trade_plan"), dict) else {}
    action = trade_plan.get("action") or "unknown"
    pct = trade_plan.get("target_pct", trade_plan.get("target_position_pct", ""))
    blocked = "BLOCKED" in gate.upper() or "BLOCKED" in cio_status.upper() or _score_float(score) < 6
    fatal = "FATAL" in cio_status.upper() or blocked
    common_refs = [f"governed_results.json#{symbol}", f"report_{run_date.replace('-', '')}.md"]
    stock_source_attempts = _stock_source_attempts(symbol, name, kind="source")
    fundamental_attempts = _stock_source_attempts(symbol, name, kind="fundamental")
    stock_source_missing = ["raw_stock_source_refs", "agent_tool_trace_memos", "announcement_refs"]
    fundamental_missing = ["financial_statement_refs", "valuation_peer_refs", "report_refs"]
    stock_source_pack = _limited_evidence_pack("stock", symbol, stock_source_attempts, stock_source_missing)
    fundamental_pack = _limited_evidence_pack("stock", symbol, fundamental_attempts, fundamental_missing)
    return {
        f"stocks/{symbol}/01_stock_source_memo": _memo(
            agent="StockSourceAgent",
            scope="stock",
            symbol=symbol,
            status="WARN",
            facts=[f"symbol={symbol}", f"name={name}", "source=governed_results summary"],
            reasoning=["当前公开 Pages 只有最终 governed 摘要；原始逐 Agent transcript 尚未完全持久化。"],
            conclusion="可审计最终门控；需补单股原始源引用。",
            missing_data=["raw_stock_source_refs", "agent_tool_trace_memos"],
            source_refs=common_refs,
            next_step="后续从 pipeline ctx.opinions/stage_results 直接持久化。",
            origin="DERIVED_FROM_ARTIFACT",
            source_attempts=stock_source_attempts,
            limited_report=True,
            evidence_pack=stock_source_pack,
        ),
        f"stocks/{symbol}/02_macro_memo": _memo(
            agent="MacroAgent",
            scope="stock",
            symbol=symbol,
            status="WARN",
            facts=[f"macro_used_for_symbol={symbol}"],
            reasoning=["宏观只作为个股背景约束，不单独改变交易门控。"],
            conclusion="等待完整 macro_review 刷新后增强。",
            missing_data=["per_stock_macro_opinion_raw"],
            source_refs=common_refs,
            next_step="把 MacroAgent raw_data 落到本路径。",
        ),
        f"stocks/{symbol}/03_fundamental_reports_memo": _memo(
            agent="FundamentalReportsAgent",
            scope="stock",
            symbol=symbol,
            status="WARN",
            facts=[f"score={score}", f"headline={row.get('headline', '')}"],
            reasoning=["基本面/估值缺口是当前个股 governed 的关键输入，但尚未独立成 Agent memo。"],
            conclusion="先按最终评分和报告摘要审计；需要补财报/公告/研报原文链。",
            missing_data=["financial_statement_refs", "valuation_peer_refs", "report_refs"],
            source_refs=common_refs,
            next_step="新增 FundamentalReportsAgent 或持久化现有基本面上下文。",
            origin="DERIVED_FROM_ARTIFACT",
            source_attempts=fundamental_attempts,
            limited_report=True,
            evidence_pack=fundamental_pack,
        ),
        f"stocks/{symbol}/04_technical_memo": _memo(
            agent="TechnicalAgent",
            scope="stock",
            symbol=symbol,
            status="PASS",
            facts=[f"headline={row.get('headline', '')}"],
            reasoning=["技术面只做证据；过热/乖离不能绕过治理门控。"],
            conclusion="技术证据已进入最终报告，但应落独立 memo。",
            missing_data=["technical_agent_raw_json"],
            source_refs=common_refs,
            next_step="持久化 TechnicalAgent raw_data。",
        ),
        f"stocks/{symbol}/05_intel_catalyst_memo": _memo(
            agent="IntelCatalystAgent",
            scope="stock",
            symbol=symbol,
            status="WARN",
            facts=[f"symbol={symbol}"],
            reasoning=["新闻/公告/催化剂必须回答 what/when/exposure/evidence；热度不是催化剂。"],
            conclusion="当前只可从最终报告推断，需补独立催化剂 memo。",
            missing_data=["announcement_refs", "catalyst_timeline", "price_in_assessment"],
            source_refs=common_refs,
            next_step="持久化 IntelAgent raw_data，并补政策/公告子类。",
        ),
        f"stocks/{symbol}/06_risk_position_memo": _memo(
            agent="RiskPositionAgent",
            scope="stock",
            symbol=symbol,
            status="BLOCKED" if blocked else "PASS",
            facts=[f"gate={gate}", f"cio_status={cio_status}", f"score={score}"],
            reasoning=["风险/仓位镜头负责阻断追高、估值异常、缺证据和持仓叠加风险。"],
            conclusion="存在阻断风险。" if blocked else "未见最终阻断。",
            missing_data=[],
            source_refs=common_refs,
            fatal_objection=fatal,
            next_step="风险未解除前不进入交易动作。",
        ),
        f"stocks/{symbol}/07_evidence_gate": _memo(
            agent="EvidenceGate",
            scope="stock",
            symbol=symbol,
            status="BLOCKED" if fatal else "PASS",
            facts=[f"score={score}", f"gate={gate}", f"cio_status={cio_status}"],
            reasoning=["Evidence Gate 是原 CIO 总审的红蓝前证据门；当前从最终治理结果回填审计。"],
            conclusion="BLOCKED_BY_FATAL 或低分，不应继续交易动作。" if fatal else "证据可进入后续门控。",
            missing_data=["pre_red_blue_cio_raw_memo"],
            source_refs=common_refs,
            fatal_objection=fatal,
            next_step="后续运行时在 RedBlue 前生成真实 EvidenceGate memo。",
        ),
        f"stocks/{symbol}/08_red_blue": _memo(
            agent="RedBlueAgent",
            scope="stock",
            symbol=symbol,
            status="BLOCKED" if fatal else "PASS",
            facts=[f"red_blue_verdict={row.get('red_blue_verdict', '')}", json.dumps(row.get("red_blue") or {}, ensure_ascii=False)[:600]],
            reasoning=["红蓝对抗负责暴露反方 fatal objection，不能被多数意见覆盖。"],
            conclusion="红队风险占优。" if fatal else "红蓝结论可供评分使用。",
            missing_data=[] if row.get("red_blue") else ["red_blue_payload_missing"],
            source_refs=common_refs,
            fatal_objection=fatal,
            next_step="把红蓝完整论点展示到个股卷宗。",
        ),
        f"stocks/{symbol}/09_scoring": _memo(
            agent="ScoringAgent",
            scope="stock",
            symbol=symbol,
            status="BLOCKED" if _score_float(score) < 6 else "PASS",
            facts=[f"score={score}", f"gate={gate}", json.dumps(row.get("scoring") or {}, ensure_ascii=False)[:600]],
            reasoning=["评分 < 6 是硬门控，不可协商。"],
            conclusion="score < 6，强制 no_action / 0%。" if _score_float(score) < 6 else "评分通过，仍需 TradeDecisionGate。",
            missing_data=[],
            source_refs=common_refs,
            fatal_objection=_score_float(score) < 6,
            next_step="评分不过线则停止交易动作。",
        ),
        f"stocks/{symbol}/10_trade_decision_gate": _memo(
            agent="TradeDecisionGate",
            scope="stock",
            symbol=symbol,
            status="BLOCKED" if blocked else "PASS",
            facts=[f"action={action}", f"position={pct if pct != '' else 'UNKNOWN'}%", f"cio_status={cio_status}", f"score={score}"],
            reasoning=["TradeDecisionGate 是评分后的最终门控，只保证 action/position 不绕过红蓝和评分。"],
            conclusion="最终 action=no_action，position=0%。" if blocked else f"最终 action={action}，仍需人工确认。",
            missing_data=[],
            source_refs=common_refs,
            fatal_objection=fatal,
            next_step="0% 仓位；不执行交易；补证据后重新跑 governed。" if blocked else "人工确认后才可执行。",
        ),
        f"stocks/{symbol}/11_decision_report": _memo(
            agent="DecisionReportAgent",
            scope="stock",
            symbol=symbol,
            status="BLOCKED" if blocked else "PASS",
            facts=[f"name={name}", f"headline={row.get('headline', '')}", f"action={action}", f"score={score}"],
            reasoning=["最终报告只展示门控后的结论，不能输出与 TradeDecisionGate 冲突的话术。"],
            conclusion="报告应显示 no_action / 0% / 人工复核。" if blocked else "报告可展示条件化结论。",
            missing_data=[],
            source_refs=common_refs,
            fatal_objection=fatal,
            next_step="Pages 展示本卷宗和最终报告。",
        ),
    }


def _score_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def generate_daily_agent_memos(
    run_date: str,
    *,
    reports_dir: Path | str = Path("reports"),
    output_dir: Path | str | None = None,
) -> List[str]:
    reports = Path(reports_dir)
    out = Path(output_dir) if output_dir is not None else reports / "daily" / run_date
    market_dir = reports / "market_cycle" / run_date
    health = _read_json(market_dir / "13_source_health.json") or {}
    macro = _read_json(market_dir / "01_macro_review.json") or {}
    source_health_v2 = _read_json(reports / "run_status" / run_date / "source_health_v2.json") or {}
    health_for_sources = _health_with_macro_signal(health, macro)
    queue = _read_json(market_dir / "11_deep_review_queue.json") or {}
    strategy = _read_json(market_dir / "14_market_strategy.json") or {}
    governed_payload = _read_json(reports / "governed_results.json")
    governed_rows = [
        row for row in (governed_payload if isinstance(governed_payload, list) else [])
        if isinstance(row, dict) and str(row.get("run_date") or run_date) == run_date
    ]
    current_symbols = {
        _text(row.get("code") or row.get("symbol"), "")
        for row in governed_rows
        if _text(row.get("code") or row.get("symbol"), "")
    }
    stocks_dir = out / "stocks"
    if stocks_dir.exists():
        for child in stocks_dir.iterdir():
            if child.is_dir() and child.name not in current_symbols:
                shutil.rmtree(child)

    generated: List[str] = []
    for rel, memo in _market_memos(run_date, health_for_sources, source_health_v2, macro, queue, strategy, governed_rows).items():
        generated.extend(_write_memo_triplet(out, rel, memo))

    inventory = build_source_inventory(health_for_sources)
    generated.extend(_write_table_report(out, "sources/00_source_inventory", "Source Inventory", inventory, intro="source_status_v1；用于说明每个数据源状态、失败原因、影响范围和下一步。"))
    generated.extend(_write_table_report(out, "sources/01_source_gap_plan", "Source Gap Plan", _source_gap_plan(inventory), intro="只列缺口源；优先 critical，再 supporting，optional 只降权。"))
    generated.extend(_write_table_report(out, "sources/02_source_probe_tasks", "Source Probe Tasks", _probe_tasks(), intro="数据搜集任务清单。"))

    for row in governed_rows:
        symbol = _text(row.get("code") or row.get("symbol"), "")
        if not symbol:
            continue
        context = {
            "schema": "context_pack_v1",
            "symbol": symbol,
            "name": row.get("name"),
            "run_date": run_date,
            "source_refs": [f"governed_results.json#{symbol}", f"market_cycle/{run_date}/13_source_health.json"],
            "governance": {
                "score": row.get("score"),
                "gate": row.get("gate"),
                "cio_status": row.get("cio_status"),
                "trade_plan": row.get("trade_plan"),
            },
            "no_trade_execution": True,
        }
        rel = f"stocks/{symbol}/00_context_pack"
        existing_context = _read_json(out / f"{rel}.json")
        if isinstance(existing_context, dict) and existing_context.get("schema") == "context_pack_v1" and existing_context.get("origin") == "RAW_AGENT":
            context = existing_context
        _write_json(out / f"{rel}.json", context)
        if context.get("origin") == "RAW_AGENT":
            context_md = "\n".join(
                [
                    f"# ContextPack — {symbol}",
                    "",
                    "## 一句话结论",
                    "这是 governed 个股分析的运行时共享证据包；所有后续 Agent 只能在这些证据基础上推理。",
                    "",
                    "## 关键数据",
                    *_bullets(context.get("facts") or ["UNKNOWN"]),
                    "",
                    "## 审计详情",
                    "```json",
                    json.dumps(context, ensure_ascii=False, indent=2, default=str),
                    "```",
                ]
            )
        else:
            context_md = "# ContextPack — %s\n\n```json\n%s\n```\n" % (
                symbol,
                json.dumps(context, ensure_ascii=False, indent=2),
            )
        _write_text(out / f"{rel}.md", context_md)
        _write_text(out / f"{rel}.html", _html_page(f"ContextPack {symbol}", context_md))
        generated.extend([f"{rel}.json", f"{rel}.md", f"{rel}.html"])

        for memo_rel, memo in _stock_memos(run_date, row).items():
            generated.extend(_write_memo_triplet(out, memo_rel, memo))

    index_md = _daily_index_markdown(run_date, generated, governed_rows, output_dir=out)
    _write_text(out / "index.md", index_md)
    _write_text(out / "index.html", _html_page(f"{run_date} Agent 卷宗", index_md))
    generated.extend(["index.md", "index.html"])
    return generated


def _daily_index_markdown(
    run_date: str,
    generated: List[str],
    governed_rows: List[Dict[str, Any]],
    *,
    output_dir: Optional[Path] = None,
) -> str:
    stock_symbols = [
        str(row.get("code") or row.get("symbol") or "").strip()
        for row in governed_rows
        if str(row.get("code") or row.get("symbol") or "").strip()
    ]
    sections = [
        ("总览页", "index.html", "八大展示板块入口"),
        ("宏观与地缘", "market/02_macro_geopolitics.html", "MacroGeopoliticsAgent memo"),
        ("数据源健康与补全", "sources/01_source_gap_plan.html", "source inventory / gap plan / probe tasks"),
        ("候选池 / 深评队列", "market/04_candidate_review.html", "CandidateReviewAgent memo"),
        ("持仓复核", "market/05_portfolio_review.html", "PortfolioReviewAgent memo"),
        ("个股 Governed", f"stocks/{stock_symbols[0]}/11_decision_report.html" if stock_symbols else "", "个股 Agent 卷宗入口"),
        ("哪些 Agent 真跑了", "index.html#agent-运行真实性", "RAW_AGENT / DERIVED_FROM_ARTIFACT / MISSING 真实性索引"),
        ("证据链 / 审计", f"stocks/{stock_symbols[0]}/00_context_pack.html" if stock_symbols else "sources/00_source_inventory.html", "ContextPack / source refs / JSON"),
    ]
    origin_counts = _origin_counts_for_output(output_dir) if output_dir is not None else {}
    lines = [
        f"# {run_date} Agent 卷宗 / 静态 Pages Dashboard",
        "",
        "> 这是 report-only 展示层；不自动交易，不写保护区。",
        "",
        "## 八大板块",
        "",
        "| 板块 | 入口 | 说明 |",
        "|---|---|---|",
    ]
    for label, href, note in sections:
        link = f"[{label}]({href})" if href else label
        lines.append(f"| {label} | {link} | {note} |")
    lines.extend(
        [
            "",
            "## Agent 运行真实性",
            "",
            f"- RAW_AGENT: {origin_counts.get('RAW_AGENT', 0)}",
            f"- DERIVED_FROM_ARTIFACT: {origin_counts.get('DERIVED_FROM_ARTIFACT', 0)}",
            f"- MISSING: {origin_counts.get('MISSING', 0)}",
            "",
            "## 个股卷宗",
            "",
        ]
    )
    if stock_symbols:
        for symbol in stock_symbols:
            lines.append(f"- [{symbol} 决策报告](stocks/{symbol}/11_decision_report.html)")
            lines.append(f"- [{symbol} Trade Decision Gate](stocks/{symbol}/10_trade_decision_gate.html)")
            lines.append(f"- [{symbol} Evidence Gate](stocks/{symbol}/07_evidence_gate.html)")
    else:
        lines.append("- 无 governed 个股卷宗。")
    lines.extend(
        [
            "",
            "## 生成文件数",
            "",
            f"- {len(generated)}",
        ]
    )
    return "\n".join(lines)


def _origin_counts_for_output(root: Path) -> Dict[str, int]:
    counts = {"RAW_AGENT": 0, "DERIVED_FROM_ARTIFACT": 0, "MISSING": 0}
    for path in root.rglob("*.json"):
        payload = _read_json(path)
        if not isinstance(payload, dict) or payload.get("schema") != AGENT_MEMO_SCHEMA:
            continue
        origin = str(payload.get("origin") or "DERIVED_FROM_ARTIFACT")
        counts[origin] = counts.get(origin, 0) + 1
    return counts


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate daily Agent memo dossiers from report artifacts")
    parser.add_argument("--date", default="", help="Run date YYYY-MM-DD")
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args(argv)

    run_date = resolve_analysis_run_date(args.date or None)
    output_dir = Path(args.output_dir) if args.output_dir else Path(args.reports_dir) / "daily" / run_date
    generated = generate_daily_agent_memos(run_date, reports_dir=Path(args.reports_dir), output_dir=output_dir)
    print(f"agent_memos: generated {len(generated)} files for {run_date}")
    print(f"agent_memos: output_dir={output_dir}")
    for rel in generated:
        print(f"- {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
