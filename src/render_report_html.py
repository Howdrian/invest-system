# -*- coding: utf-8 -*-
"""Render published Markdown/JSON report artifacts into human-readable HTML.

This is a Pages presentation layer only.  It does not run analysis and does not
touch the Web dashboard app.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.report_artifact import write_daily_report_artifact
from src.report_markdown import CSS, esc as _esc, markdown_to_html
from src.core.run_context import resolve_analysis_run_date
from src.utils.sanitize import sanitize_public_http_url
from src.report_view_model import (
    agent_display_name as _agent_display_name,
    agent_role_label as _agent_role_label,
    macro_reader_copy as _macro_reader_copy,
    provider_repair_items as _provider_repair_items,
    reader_blockers as _reader_blockers,
    reader_confidence as _reader_confidence,
    reader_confidence_text as _reader_confidence_text,
    reader_regime as _reader_regime,
    reader_status as _reader_status,
    source_health_reader_copy as _source_health_reader_copy,
)


_READER_TIMEZONE = ZoneInfo("Asia/Shanghai")


def _reader_datetime(value: Any, *, time_only: bool = False) -> str:
    """Format stored ISO timestamps for readers without changing the artifact."""

    text = str(value or "").strip()
    if not text:
        return "未标"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    local = parsed.astimezone(_READER_TIMEZONE)
    return local.strftime("%H:%M") if time_only else local.strftime("%Y-%m-%d %H:%M（北京时间）")


def _valid_http_url(value: Any) -> str:
    return sanitize_public_http_url(value)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _html_page(title: str, body: str, *, subtitle: str = "") -> str:
    sub = f"<p class='muted'>{_esc(subtitle)}</p>" if subtitle else ""
    return (
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{_esc(title)}</title>{CSS}</head><body><main>"
        f"{sub}{body}<p class='footer'>本报告仅供投研复核，不自动执行交易</p>"
        "</main></body></html>"
    )


def _join_items(items: Iterable[Any], *, limit: int = 6) -> str:
    values = [str(item) for item in items if str(item)]
    if not values:
        return "无"
    shown = values[:limit]
    suffix = f"；另有 {len(values) - limit} 项" if len(values) > limit else ""
    return "；".join(shown) + suffix


def _first_nonempty(*values: Any, default: str = "未知") -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def _flow_card(
    title: str,
    *,
    source: str,
    facts: str,
    inference: str,
    conclusion: str,
    next_step: str,
    href: str = "",
) -> str:
    heading = f"<a href='{_esc(href)}'>{_esc(title)}</a>" if href else _esc(title)
    source_text = _sanitize_reader_markdown(str(source))
    facts_text = _sanitize_reader_markdown(str(facts))
    inference_text = _sanitize_reader_markdown(str(inference))
    conclusion_text = _sanitize_reader_markdown(str(conclusion))
    next_text = _sanitize_reader_markdown(str(next_step))
    return f"""
<article class="flow-card">
  <h3>{heading}</h3>
  <div class="flow-row"><span class="flow-label">信息源</span>{_esc(source_text)}</div>
  <div class="flow-row"><span class="flow-label">关键数据</span>{_esc(facts_text)}</div>
  <div class="flow-row"><span class="flow-label">推论</span>{_esc(inference_text)}</div>
  <div class="flow-row"><span class="flow-label">分析结论</span>{_esc(conclusion_text)}</div>
  <div class="flow-row"><span class="flow-label">下一步</span>{_esc(next_text)}</div>
</article>
"""

def _context(docs_dir: Path, run_date: str) -> Dict[str, Any]:
    base = docs_dir / "market_cycle" / run_date
    governed = _read_json(docs_dir / "governed_results.json")
    governed_rows = governed if isinstance(governed, list) else []
    return {
        "macro": _read_json(base / "01_macro_review.json") or {},
        "screening": _read_json(base / "09_screening_funnel.json") or {},
        "queue": _read_json(base / "11_deep_review_queue.json") or {},
        "health": _read_json(base / "13_source_health.json") or {},
        "strategy": _read_json(base / "14_market_strategy.json") or {},
        "governed_today": [
            row for row in governed_rows if isinstance(row, dict) and str(row.get("run_date") or "") == run_date
        ],
    }


def _source_names(health: Dict[str, Any]) -> str:
    rows = health.get("rows") or []
    names = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        source = row.get("source")
        status = row.get("status")
        if source:
            names.append(f"{source}({status})")
    return _join_items(names, limit=8)


def _top_candidates(queue: Dict[str, Any]) -> List[str]:
    labels: List[str] = []
    for row in (queue.get("candidates") or [])[:6]:
        if not isinstance(row, dict):
            continue
        symbol = _first_nonempty(row.get("symbol"), default="")
        name = _first_nonempty(row.get("name"), default="")
        verdict = _first_nonempty(row.get("verdict"), default="")
        risk = _first_nonempty(row.get("price_risk"), default="")
        labels.append(f"{name or symbol}({symbol})：{verdict}/{risk}")
    return labels


def _governed_labels(governed_today: List[Dict[str, Any]]) -> List[str]:
    labels: List[str] = []
    for row in governed_today:
        code = _first_nonempty(row.get("code"), row.get("symbol"), default="")
        name = _first_nonempty(row.get("name"), default="")
        action = ((row.get("trade_plan") or {}).get("action") if isinstance(row.get("trade_plan"), dict) else "") or ""
        blocked = _is_blocked_governed(row)
        if blocked:
            decision = "阻断 / 不操作 / 0%"
            state_label = "暂停行动"
        else:
            decision = _human_action(action)
            state_label = "可人工复核"
        labels.append(
            f"{name or code}({code})：{decision}，{state_label}，综合评分 {_format_score(row.get('score'))}，{_position_status(row)}"
        )
    return labels



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

def _is_blocked_governed(row: Dict[str, Any]) -> bool:
    score = row.get("score")
    try:
        score_float = float(score)
    except (TypeError, ValueError):
        score_float = 0.0
    status_text = f"{row.get('cio_status', '')} {row.get('gate', '')}".upper()
    return "BLOCKED" in status_text or "FATAL" in status_text or score_float < 6


def _format_score(score: Any) -> str:
    try:
        value = float(score)
    except (TypeError, ValueError):
        return "未知"
    return f"{value:g}/10"


def _score_band(score: Any) -> str:
    try:
        value = float(score)
    except (TypeError, ValueError):
        return "评分未标"
    if value >= 8:
        return "质量较高"
    if value >= 6:
        return "可复核"
    if value >= 4:
        return "质量偏低"
    return "质量很低"


def _short_text(value: Any, *, max_len: int = 180) -> str:
    text = _sanitize_reader_markdown(_reader_product_text(value).strip())
    replacements = {
        "signal=": "信号：",
        "confidence=": "置信度：",
        "decision_type=": "决策类型：",
        "sentiment_score=": "综合评分：",
        "analysis_summary=": "分析摘要：",
        "operation_advice=": "操作建议：",
        "source_health=": "数据健康：",
        "trade_review_usability=": "交易复核可用性：",
        "source_count=": "数据源数量：",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"\s+", " ", text)
    return text if len(text) <= max_len else text[: max_len - 1].rstrip() + "…"


def _reader_product_text(value: Any) -> str:
    if isinstance(value, str):
        raw = value.strip()
        if raw and raw[0] in "{[" and raw[-1] in "}]":
            try:
                parsed = ast.literal_eval(raw)
            except (SyntaxError, ValueError):
                parsed = None
            if isinstance(parsed, (dict, list)):
                return _reader_product_text(parsed)
        return raw
    if isinstance(value, dict):
        claim = value.get("claim") or value.get("point") or value.get("主张") or value.get("观点")
        basis = value.get("basis") or value.get("依据") or value.get("reason")
        if claim:
            claim_text = _reader_product_text(claim)
            basis_text = _reader_product_text(basis) if basis else ""
            return f"{claim_text}。依据：{basis_text}" if basis_text else claim_text
        for key in ("description", "summary", "message", "value", "label", "title"):
            if value.get(key):
                return _reader_product_text(value.get(key))
        return "；".join(_reader_product_text(item) for key, item in value.items() if key not in {"evidence_ids", "source_refs"} and item not in (None, "", []))
    if isinstance(value, list):
        return "；".join(_reader_product_text(item) for item in value if item not in (None, "", []))
    return str(value or "")


def _as_text_list(value: Any, *, limit: int = 5) -> List[str]:
    if isinstance(value, list):
        raw = value
    elif value:
        raw = [value]
    else:
        raw = []
    out: List[str] = []
    for item in raw:
        text = _short_text(item)
        if text:
            out.append(text)
    return out[:limit]


def _html_list(items: Iterable[Any], *, empty: str = "未提供") -> str:
    values = [_short_text(item) for item in items if _short_text(item)]
    if not values:
        return f"<li class='muted'>{_esc(empty)}</li>"
    return "".join(f"<li>{_esc(item)}</li>" for item in values)


def _position_status(row: Dict[str, Any]) -> str:
    plan = row.get("trade_plan") if isinstance(row.get("trade_plan"), dict) else {}
    target = plan.get("target_pct")
    blocked = _is_blocked_governed(row)
    if blocked or target in (0, "0", "0%"):
        return "未生成仓位建议"
    if target in (None, ""):
        return "仓位需人工确认"
    return f"目标仓位 {target}%"


def _reader_gate(row: Dict[str, Any]) -> str:
    if _is_blocked_governed(row):
        return "暂停行动"
    return "可进入人工复核"


def _stock_reasons(row: Dict[str, Any]) -> List[str]:
    reasons: List[str] = []
    headline = _short_text(row.get("headline"))
    if headline:
        reasons.append(headline)
    scoring = row.get("scoring") if isinstance(row.get("scoring"), dict) else {}
    dimensions = scoring.get("dimensions") if isinstance(scoring.get("dimensions"), dict) else {}
    ranked: List[Tuple[float, str]] = []
    for name, raw in dimensions.items():
        if not isinstance(raw, dict):
            continue
        try:
            value = float(raw.get("score"))
        except (TypeError, ValueError):
            value = 99.0
        rationale = _short_text(raw.get("rationale"), max_len=150)
        if rationale:
            ranked.append((value, rationale))
    for _score, text in sorted(ranked, key=lambda item: item[0])[:3]:
        if text not in reasons:
            reasons.append(text)
    red_blue = _short_text(row.get("red_blue_verdict"), max_len=170)
    if red_blue and red_blue not in reasons:
        reasons.append(red_blue)
    return reasons[:5]


def _stock_risks(row: Dict[str, Any]) -> List[str]:
    risks: List[str] = []
    if _is_blocked_governed(row):
        risks.append("决策复核已暂停行动，不能把候选观察解读为交易指令。")
    scoring = row.get("scoring") if isinstance(row.get("scoring"), dict) else {}
    dimensions = scoring.get("dimensions") if isinstance(scoring.get("dimensions"), dict) else {}
    for name in ("fundamental_strength", "timing", "risk_reward_ratio", "catalyst_clarity"):
        raw = dimensions.get(name)
        if not isinstance(raw, dict):
            continue
        try:
            value = float(raw.get("score"))
        except (TypeError, ValueError):
            value = 99.0
        if value <= 1.0:
            rationale = _short_text(raw.get("rationale"), max_len=160)
            if rationale:
                risks.append(rationale)
    return list(dict.fromkeys(risks))[:5]


def _stock_next_steps(row: Dict[str, Any]) -> List[str]:
    plan = row.get("trade_plan") if isinstance(row.get("trade_plan"), dict) else {}
    steps = _as_text_list(row.get("next_action"), limit=1)
    steps.extend(_as_text_list(plan.get("conditions"), limit=3))
    steps.extend(_as_text_list(plan.get("invalidations"), limit=2))
    if not steps:
        steps.append("等待下一次数据刷新后重新复核。")
    return list(dict.fromkeys(steps))[:5]


def _build_stock_reader(docs_dir: Path, run_date: str, title: str) -> str:
    rows = _context(docs_dir, run_date)["governed_today"]
    if not rows:
        return f"""
<section class="card">
  <h2>{_esc(title)}</h2>
  <p class="warn">今日没有完成 governed 个股深评。</p>
  <p class="muted">可以先看报告中心、候选池和数据源健康页；不要把候选池当交易建议。</p>
</section>
"""

    cards: List[str] = []
    for row in rows:
        code = _first_nonempty(row.get("code"), row.get("symbol"), default="")
        name = _first_nonempty(row.get("name"), default=code)
        action = _human_action((row.get("trade_plan") or {}).get("action") if isinstance(row.get("trade_plan"), dict) else "")
        if _is_blocked_governed(row):
            action = "阻断 / 不操作 / 0%"
        score_label = _format_score(row.get("score"))
        reasons = _html_list(_stock_reasons(row), empty="没有足够理由支撑行动。")
        risks = _html_list(_stock_risks(row), empty="未发现额外风险摘要。")
        next_steps = _html_list(_stock_next_steps(row), empty="等待下一次刷新。")
        conclusion = _short_text(row.get("headline") or row.get("next_action") or "未提供结论。", max_len=220)
        cards.append(
            f"""
<article class="flow-card">
  <h3>{_esc(name)}（{_esc(code)}）</h3>
  <p>
    <span class="pill">{_esc(action)}</span>
    <span class="pill">{_esc(_reader_gate(row))}</span>
    <span class="pill">{_esc(_score_band(row.get('score')))} · {_esc(score_label)}</span>
    <span class="pill">{_esc(_position_status(row))}</span>
  </p>
  <div class="flow-row"><span class="flow-label">信息源</span>行情、技术指标、基本面线索、红蓝反证、评分卡和决策复核</div>
  <div class="flow-row"><span class="flow-label">今日结论</span>{_esc(conclusion)}</div>
  <div class="grid">
    <div><h3>为什么</h3><ul>{reasons}</ul></div>
    <div><h3>风险和反证</h3><ul>{risks}</ul></div>
  </div>
  <div><h3>下一步</h3><ul>{next_steps}</ul></div>
</article>
"""
        )
    return f"""
<section class="card">
  <h2>个股投研结论</h2>
  <p class="muted">这是读者版结论。原始分析记录放在下方折叠区，只用于追溯。</p>
  <div class="flow-grid">{''.join(cards)}</div>
</section>
"""


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




def _contains_blocked_signal(text: str) -> bool:
    upper = text.upper()
    return "阻断" in text or "BLOCKED" in upper or "FATAL" in upper or "不操作" in text


def _sanitize_blocked_trade_phrases(text: str) -> str:
    sanitized = text
    common = {
        "强烈买入信号": "技术强势信号",
        "买入信号": "技术信号",
    }
    for old, new in common.items():
        sanitized = sanitized.replace(old, new)
    if _contains_blocked_signal(sanitized):
        blocked = {
            "建议立即减仓或清仓止损": "如已持仓，仅做人工风险复核，不执行自动交易",
            "立即减仓": "人工风险复核",
            "清仓止损": "人工风险复核",
            "清仓": "人工风险复核",
            "止损": "风险复核",
            "强烈买入": "技术强势",
            "建议减仓": "建议人工风险复核",
            "建议卖出": "建议人工风险复核",
        }
        for old, new in blocked.items():
            sanitized = sanitized.replace(old, new)
    return sanitized


def _sanitize_reader_markdown(markdown: str) -> str:
    """Remove raw enum / template-like wording from reader-facing HTML."""
    text = markdown
    text = re.sub(
        r"数据健康\s*中\s*(?:portfolio|持仓/组合)\s*域的覆盖率(?:（覆盖率）)?\s*为\s*[0-9.]+，状态为\s*(?:partial|部分可用).*?(?:未能成功加载或关联。|$)",
        "本次运行没有拿到可用于组合暴露分析的结构化持仓；如果系统里已有持仓，也没有被本次日报正确关联。",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"(?<![A-Za-z0-9])N/A(?![A-Za-z0-9])", "未提供", text)
    text = text.replace("原始报告（审计原文）", "模块正文")
    text = text.replace("关键数据缺失", "关键待确认项")
    text = text.replace("关键数据缺口", "关键待确认项")
    text = text.replace("数据修复", "下次复核")
    text = text.replace("数据缺口", "待确认项")
    text = text.replace("FULL_REVIEW", "完整复盘")
    text = text.replace("LIMITED_REVIEW", "有限复盘")
    text = text.replace("SCREEN_ONLY", "仅筛选观察")
    text = text.replace("OBSERVE_ONLY", "仅市场观察")
    text = text.replace("BLOCKED_BY_FATAL", "证据不足，暂停结论")
    text = re.sub(r"\bBLOCKED\b", "暂停结论", text)
    text = re.sub(r"\bscore\s*=\s*", "综合评分 ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bgate\s*=\s*", "状态 ", text, flags=re.IGNORECASE)
    text = text.replace("target_pct", "目标仓位")
    text = text.replace("no_action", "不操作")
    text = text.replace("signal=", "信号：")
    text = text.replace("confidence=", "置信度：")
    text = text.replace("decision_type=", "决策类型：")
    text = text.replace("sentiment_score=", "综合评分：")
    text = text.replace("analysis_summary=", "分析摘要：")
    text = text.replace("operation_advice=", "操作建议：")
    text = text.replace("source_health=", "数据健康：")
    text = text.replace("trade_review_usability=", "交易复核可用性：")
    text = text.replace("source_count=", "数据源数量：")
    text = text.replace("available_limited", "有限可用")
    text = text.replace("holding_status=UNKNOWN", "未发现结构化持仓")
    text = text.replace("selected_count=0", "入选持仓 0 个")
    text = text.replace("governed_count=0", "深评持仓 0 个")
    text = text.replace("governed_report_count=1", "相关深评报告 1 份")
    text = text.replace("portfolio_holdings_context_missing", "缺少持仓上下文")
    text = text.replace("filings_events", "公告/事件")
    text = text.replace("news_sentiment", "新闻/舆情")
    text = text.replace("fundamentals", "基本面")
    text = text.replace("公告_events", "公告/事件")
    text = text.replace("capital_flow", "资金流")
    text = text.replace("sector_rankings", "行业强弱排行")
    text = text.replace("hot_stocks", "热门标的列表")
    text = text.replace("originalAnalysisRefs", "上游分析材料")
    text = text.replace("portfolio_snapshot", "持仓快照")
    text = text.replace("quantity", "持仓数量")
    text = text.replace("market_value", "持仓市值")
    text = text.replace("cost_basis", "成本价")
    text = text.replace("rates_liquidity", "利率与流动性")
    text = text.replace("energy_commodities", "能源与商品")
    text = text.replace("risk_appetite", "风险偏好")
    text = text.replace("market_heat", "市场热度")
    text = text.replace("prediction_market", "预测市场")
    text = text.replace("usd_fx", "美元/汇率")
    text = text.replace("growth", "增长")
    text = text.replace("inflation", "通胀")
    text = text.replace("OVERHEATED_WAIT_ENTRY", "过热等待承接")
    text = text.replace("DEEP_REVIEW_WAIT_ENTRY", "等待深评入口")
    text = text.replace("NORMAL_RECHECK", "常规复核")
    text = text.replace("评分复核未通过（总分4.0/10）", "综合判断偏弱，暂不支持行动")
    text = text.replace("评分门控未通过（总分4.0/10）", "综合判断偏弱，暂不支持行动")
    text = text.replace("governed 个股", "深评个股")
    text = text.replace("governed 深评", "个股深评")
    text = text.replace("governed", "深评")
    text = re.sub(r"\bmissing\b", "缺失", text, flags=re.IGNORECASE)
    text = re.sub(r"\bstale\b", "已变旧", text, flags=re.IGNORECASE)
    text = re.sub(r"\bfailed\b", "失败", text, flags=re.IGNORECASE)
    text = re.sub(r"\bempty\b", "空结果", text, flags=re.IGNORECASE)
    text = text.replace("评分门控", "评分复核")
    text = text.replace("治理层阻止", "决策复核暂停")
    text = text.replace("治理层阻断", "证据不足，暂停结论")
    text = re.sub(r"：hold\b", "：持有/观察", text, flags=re.IGNORECASE)
    text = re.sub(r"：buy\b", "：买入候选", text, flags=re.IGNORECASE)
    text = re.sub(r"：sell\b", "：卖出候选", text, flags=re.IGNORECASE)
    text = re.sub(r"：watch\b", "：观察", text, flags=re.IGNORECASE)
    text = re.sub(r"：medium\b", "：中等", text, flags=re.IGNORECASE)
    text = re.sub(r"：high\b", "：高", text, flags=re.IGNORECASE)
    text = re.sub(r"：low\b", "：低", text, flags=re.IGNORECASE)
    text = text.replace("RAW_AGENT", "真实 Agent")
    text = text.replace("DERIVED_FROM_ARTIFACT", "历史材料整理")
    text = text.replace("回填审计：", "")
    text = text.replace("有限信息结论：", "")
    text = text.replace("source health", "数据健康")
    text = text.replace("source_health", "数据健康")
    text = text.replace("SourceHealth", "数据健康")
    text = text.replace("sourceHealth", "数据健康")
    text = text.replace("price / fundamentals / filings / macro", "行情、基本面、公告、宏观")
    text = text.replace("dailyUniverse", "日报标的池")
    text = text.replace("market_stats", "市场统计")
    text = text.replace("agent_reported_data_gap", "部门指出待确认项")
    text = re.sub(r"\bportfolio\b", "持仓/组合", text, flags=re.IGNORECASE)
    text = text.replace("MISSING agent", "未运行 Agent")
    text = text.replace("ReportArtifact JSON", "报告 JSON")
    text = text.replace("ReportArtifact", "报告数据包")
    text = text.replace("sourceHealthV2", "数据健康快照")
    text = text.replace("providerMatrix", "数据源矩阵")
    text = text.replace("claimPolicy", "结论规则")
    text = text.replace("artifactId", "报告编号")
    text = text.replace("Tavily", "第三方搜索线索")
    text = text.replace("verified_fact", "已验证事实")
    text = text.replace("derived_fact", "推导事实")
    text = text.replace("discovery", "发现线索")
    text = text.replace("agent_opinion", "部门判断")
    text = text.replace("final_claim", "最终判断")
    text = text.replace("关键数据缺失", "关键待确认项")
    text = text.replace("数据修复", "下次复核")
    text = re.sub(r"\bcoverage\b", "覆盖率", text, flags=re.IGNORECASE)
    text = re.sub(r"\bpartial\b", "部分可用", text, flags=re.IGNORECASE)
    text = re.sub(r"\bprovider\b", "数据源", text, flags=re.IGNORECASE)
    text = re.sub(r"\berrorType\b", "错误类型", text, flags=re.IGNORECASE)
    text = text.replace("provider ledger", "数据源记录")
    text = text.replace("evidence ledger", "证据记录")
    text = text.replace("JSON", "数据文件")
    text = text.replace("json", "数据文件")
    text = text.replace("门控", "复核")
    text = text.replace("ScoringAgent", "评分复核")
    text = text.replace("FundamentalAgent", "基本面部门")
    text = text.replace("TradeDecisionGate", "交易前复核")
    text = text.replace("EvidenceGate", "证据复核")
    text = text.replace("机器可读", "可追溯")
    text = text.replace("financial_statement_refs", "财报原文引用不足")
    text = text.replace("valuation_peer_refs", "同业估值引用不足")
    text = re.sub(
        r"数据健康\s*中\s*持仓/组合\s*域的覆盖率(?:（覆盖率）)?\s*为\s*[0-9.]+，状态为\s*部分可用.*?(?:未能成功加载或关联。|$)",
        "本次运行没有拿到可用于组合暴露分析的结构化持仓；如果系统里已有持仓，也没有被本次日报正确关联。",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = text.replace("**", "")
    text = re.sub(r"^\s*[-•]\s*", "", text)
    text = text.replace("`", "")
    text = re.sub(r"[；;]{2,}", "；", text)
    text = re.sub(r"；\s*待验证情景：(?=同时|并|再)", "；", text)
    return _sanitize_blocked_trade_phrases(text)


def _sanitize_stock_report_markdown(markdown: str) -> str:
    """Remove misleading legacy governed wording from published stock reports."""
    text = _sanitize_reader_markdown(markdown)
    text = re.sub(r"证据不足，暂停结论 \| 评分\s+50\b", "证据不足，暂停结论 | 评分 0.5/10", text)
    text = re.sub(r"评分\s+50\b", "评分 0.5/10", text)
    text = text.replace("观望 — 治理层阻断", "暂停行动 / 不操作 / 0% — 证据不足，暂停结论")
    text = text.replace("**⚪ 观望** |", "**⛔ 暂停行动 / 不操作 / 0%** |")
    return _sanitize_blocked_trade_phrases(text)


def _reading_digest(docs_dir: Path, run_date: str, *, link_prefix: str = "") -> str:
    ctx = _context(docs_dir, run_date)
    macro = ctx["macro"]
    health = ctx["health"]
    queue = ctx["queue"]
    strategy = ctx["strategy"]
    governed_today = ctx["governed_today"]

    six_factor = macro.get("six_factor_regime") or {}
    macro_headline = _first_nonempty(macro.get("headline"), (strategy.get("strategy") or {}).get("headline"))
    macro_facts = _join_items(
        [
            f"宏观状态={_reader_status(macro.get('status'))}",
            f"置信度={_first_nonempty(macro.get('confidence'))}",
            macro_headline,
            f"六因子缺项={_join_items(six_factor.get('missing_factors') or [], limit=5)}",
            f"待确认项={_join_items(macro.get('data_gaps') or [], limit=5)}",
        ],
        limit=5,
    )

    source_facts = _join_items(
        [
            f"总可用性={_reader_status(health.get('usability_verdict'))}",
            f"交易审查={_reader_status(health.get('trade_review_usability'))}",
            f"宏观源={_reader_status(health.get('macro_status'))}",
            f"组件={_source_names(health)}",
        ],
        limit=4,
    )
    macro_inference, macro_conclusion, macro_next = _macro_reader_copy(macro)
    source_inference, source_conclusion, source_next = _source_health_reader_copy(health)

    candidates = queue.get("candidates") or []
    auto_candidates = queue.get("auto_governed_candidates") or []
    candidate_facts = _join_items(
        [
            f"深评候选={len(candidates)}",
            f"自动进入 governed={len(auto_candidates)}",
            f"Top={_join_items(_top_candidates(queue), limit=6)}",
        ],
        limit=3,
    )

    strategy_block = strategy.get("strategy") or {}
    strategy_facts = _join_items(
        [
            f"市场状态={_reader_regime(strategy.get('regime'))}",
            f"置信度={_first_nonempty(strategy.get('confidence'))}",
            _first_nonempty(strategy_block.get("headline"), default=""),
            f"应做={_join_items(strategy_block.get('actions') or [], limit=3)}",
            f"避免={_join_items(strategy_block.get('avoid') or [], limit=3)}",
        ],
        limit=5,
    )

    stock_facts = _join_items(_governed_labels(governed_today), limit=4)
    if not governed_today:
        stock_inference = "今日没有完成 governed 个股深评；不能从候选池直接推出交易动作。"
        stock_conclusion = "仅保留市场观察和待补数据清单。"
        stock_next = "先补数据源和候选证据，再启动单股 governed 深评。"
    else:
        blocked_count = sum(1 for row in governed_today if _is_blocked_governed(row))
        if blocked_count == len(governed_today):
            stock_inference = "今日完成深评的标的全部未通过决策复核；风险或证据缺口压过行动理由。"
            stock_conclusion = "最终动作是不操作；不新增仓位。"
            stock_next = "补公告、业绩、催化剂、估值和技术承接证据后重新审。"
        else:
            stock_inference = "有标的通过初步决策复核，但仍需人工复核证据和风险。"
            stock_conclusion = "只把通过复核的标的列为人工复核候选。"
            stock_next = "进入个股报告，看风险反证和失效条件。"

    cards = [
        _flow_card(
            "宏观与地缘",
            href=f"{link_prefix}market_cycle/{run_date}/01_macro_review.html" if link_prefix else "",
            source="官方宏观入口 + 六因子 regime + Polymarket 只读概率 + 市场热度摘要",
            facts=macro_facts,
            inference=macro_inference,
            conclusion=macro_conclusion,
            next_step=macro_next,
        ),
        _flow_card(
            "数据源健康",
            href=f"{link_prefix}market_cycle/{run_date}/13_source_health.html" if link_prefix else "",
            source=_source_names(health),
            facts=source_facts,
            inference=source_inference,
            conclusion=source_conclusion,
            next_step=source_next,
        ),
        _flow_card(
            "筛选 / 深评队列",
            href=f"{link_prefix}market_cycle/{run_date}/11_deep_review_queue.html" if link_prefix else "",
            source="市场热榜 + watchlist + 筛选漏斗 + 深评队列",
            facts=candidate_facts,
            inference="热榜只能做发现，不能做交易理由；本轮 Top 候选证据主要是 hot_stock_rank，且价格风险偏过热。",
            conclusion="候选只进入等待承接/补证据，不自动进入 governed 深评。",
            next_step="对京东方Ａ、兆易创新等只读公告、研报、技术承接；没有承接前不追高。",
        ),
        _flow_card(
            "市场策略总控",
            href=f"{link_prefix}market_cycle/{run_date}/14_market_strategy.html" if link_prefix else "",
            source="宏观结论 + 源健康 + 深评队列 + 候选路由",
            facts=strategy_facts,
            inference="市场允许普通观察，但交易动作仍必须由 governed 个股、红蓝、评分和 CIO 逐层确认。",
            conclusion="中性观察：维持观察，等待价格和证据共振。",
            next_step="把热度转成等待条件；只让证据足够的标的进入 governed。",
        ),
        _flow_card(
            "个股 Governed",
            href=f"{link_prefix}report_{run_date.replace('-', '')}.html" if link_prefix else "",
            source="技术面 + 基本面估值 + 红蓝反证 + 评分卡 + 决策复核",
            facts=stock_facts,
            inference=stock_inference,
            conclusion=stock_conclusion,
            next_step=stock_next,
        ),
    ]
    return f"""
<section class="card">
  <h2>一页读懂</h2>
  <p class="muted">先看这里。每块按“信息源 → 关键数据 → 推论 → 分析结论 → 下一步”读；下方原始报告只保留作审计。</p>
  <div class="flow-grid">{''.join(cards)}</div>
</section>
"""


def _report_intro(docs_dir: Path, run_date: str, dst_rel: str, title: str) -> str:
    ctx = _context(docs_dir, run_date)
    macro = ctx["macro"]
    health = ctx["health"]
    queue = ctx["queue"]
    strategy = ctx["strategy"]
    governed_today = ctx["governed_today"]
    compact = run_date.replace("-", "")

    if dst_rel.endswith("01_macro_review.html"):
        macro_inference, macro_conclusion, macro_next = _macro_reader_copy(macro)
        return _flow_card(
            f"阅读摘要：{title}",
            source="官方宏观入口 + 六因子市场状态 + Polymarket 只读概率",
            facts=_join_items(
                [
                    f"状态={_reader_status(macro.get('status'))}",
                    f"置信={_first_nonempty(macro.get('confidence'))}",
                    _first_nonempty(macro.get("headline")),
                ]
            ),
            inference=macro_inference,
            conclusion=macro_conclusion,
            next_step=macro_next,
        )
    if dst_rel.endswith("13_source_health.html"):
        source_inference, source_conclusion, source_next = _source_health_reader_copy(health)
        return _flow_card(
            f"阅读摘要：{title}",
            source=_source_names(health),
            facts=f"源健康={_reader_status(health.get('usability_verdict'))}；交易审查={_reader_status(health.get('trade_review_usability'))}",
            inference=source_inference,
            conclusion=source_conclusion,
            next_step=source_next,
        )
    if dst_rel.endswith("09_screening_funnel.html") or dst_rel.endswith("11_deep_review_queue.html"):
        return _flow_card(
            f"阅读摘要：{title}",
            source="市场热榜 + watchlist + 候选筛选器",
            facts=f"深评候选={len(queue.get('candidates') or [])}；自动 governed={len(queue.get('auto_governed_candidates') or [])}；Top={_join_items(_top_candidates(queue), limit=6)}",
            inference="热榜只能做发现，不能做交易理由；本轮候选多数需要等承接。",
            conclusion="候选池不是交易池。",
            next_step="读公告/研报/技术承接；只有 DEEP_REVIEW_NOW 才自动进入 governed。",
        )
    if dst_rel.endswith("14_market_strategy.html"):
        strategy_block = strategy.get("strategy") or {}
        return _flow_card(
            f"阅读摘要：{title}",
            source="宏观 + 源健康 + 候选路由",
            facts=f"市场状态={_reader_regime(strategy.get('regime'))}；置信={_first_nonempty(strategy.get('confidence'))}；{_first_nonempty(strategy_block.get('headline'))}",
            inference="允许观察，不等于允许交易。",
            conclusion="维持观察，等待价格和证据共振。",
            next_step="把热度转成等待条件，保留评分和决策复核。",
        )
    if dst_rel == f"report_{compact}.html":
        return _build_stock_reader(docs_dir, run_date, title)
    if dst_rel.endswith(f"daily/{run_date}.html"):
        return _flow_card(
            f"阅读摘要：{title}",
            source="GitHub Actions 运行状态 + 已发布报告链接",
            facts=f"宏观={_reader_status(macro.get('status'))}；源健康={_reader_status(health.get('usability_verdict'))}；深评={len(governed_today)}",
            inference="日报是入口，不是完整分析正文。",
            conclusion="从报告中心进入各模块阅读。",
            next_step="先看一页读懂，再看个股和源健康。",
        )
    return ""


def render_markdown_file(
    src: Path,
    dst: Path,
    title: Optional[str] = None,
    *,
    intro_html: str = "",
    raw_summary: str = "查看模块正文",
) -> bool:
    if not src.exists():
        return False
    body = intro_html
    if intro_html:
        body += f"<details class='card raw-report'><summary>{_esc(raw_summary)}</summary>"
    original_markdown = _read_text(src)
    markdown = original_markdown
    if src.name.startswith("report_"):
        markdown = _sanitize_stock_report_markdown(markdown)
    else:
        markdown = _sanitize_reader_markdown(markdown)
    body += markdown_to_html(markdown)
    if intro_html:
        body += "</details>"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(_html_page(title or src.stem, body), encoding="utf-8")
    return True


def _agent_memo_intro(src: Path) -> str:
    payload = _read_json(src.with_suffix(".json"))
    if not isinstance(payload, dict) or payload.get("schema") != "agent_memo_v1":
        return ""
    agent = str(payload.get("agent") or src.stem.replace("_", " "))
    display_agent = _agent_display_name(agent)
    readable_summary = _short_text(payload.get("readable_summary") or payload.get("conclusion"), max_len=260)
    facts = _html_list(payload.get("facts") or [], empty="未提供关键事实。")
    reasoning = _html_list(payload.get("reasoning") or [], empty="未提供推论。")
    missing = _html_list(payload.get("missing_data") or [], empty="未列出关键缺口。")
    next_step = _short_text(payload.get("next_step") or "等待下一轮数据刷新。", max_len=180)
    confidence = _reader_confidence_text(payload.get("confidence"))
    origin = str(payload.get("origin") or "")
    origin_note = "由实际分析流程生成" if origin == "RAW_AGENT" else "由报告快照补全"
    return f"""
<section class="card">
  <h2>{_esc(display_agent)}读者摘要</h2>
  <p class="muted">{_esc(_agent_role_label(agent))}。{_esc(origin_note)}；置信度：{_esc(confidence)}。</p>
  <p>{_esc(readable_summary or '本模块没有生成可读摘要。')}</p>
  <div class="grid">
    <div><h3>关键事实</h3><ul>{facts}</ul></div>
    <div><h3>推论</h3><ul>{reasoning}</ul></div>
  </div>
  <div class="grid">
    <div><h3>缺口</h3><ul>{missing}</ul></div>
    <div><h3>下一步</h3><p>{_esc(next_step)}</p></div>
  </div>
</section>
"""


def _report_specs(run_date: str) -> List[Tuple[str, str, str, str]]:
    compact = run_date.replace("-", "")
    return [
        ("daily", f"daily/{run_date}.md", f"daily/{run_date}.html", "今日日报 / 运行状态"),
        ("audit", f"market_cycle/{run_date}/summary.md", f"market_cycle/{run_date}/summary.html", "运行状态"),
        ("market", f"market_cycle/{run_date}/01_macro_review.md", f"market_cycle/{run_date}/01_macro_review.html", "宏观与地缘融合"),
        ("market", f"market_cycle/{run_date}/09_screening_funnel.md", f"market_cycle/{run_date}/09_screening_funnel.html", "筛选漏斗"),
        ("market", f"market_cycle/{run_date}/11_deep_review_queue.md", f"market_cycle/{run_date}/11_deep_review_queue.html", "深评候选队列"),
        ("market", f"market_cycle/{run_date}/12_preliminary_deep_review.md", f"market_cycle/{run_date}/12_preliminary_deep_review.html", "初步深评摘要"),
        ("market", f"market_cycle/{run_date}/13_source_health.md", f"market_cycle/{run_date}/13_source_health.html", "数据源健康"),
        ("market", f"market_cycle/{run_date}/14_market_strategy.md", f"market_cycle/{run_date}/14_market_strategy.html", "市场策略总控"),
        ("heat", "market_heat/latest_market_heat.md", "market_heat/latest_market_heat.html", "市场热度"),
        ("stock", f"report_{compact}.md", f"report_{compact}.html", "个股 Governed 报告"),
    ]


def _relative_from_report_center(path: str) -> str:
    return "../" + path


def _link(path: str, label: str, exists: bool, *, note: str = "") -> str:
    if exists:
        title = f"<a href='{_esc(_relative_from_report_center(path))}'>{_esc(label)}</a>"
    else:
        title = f"<span class='muted'>{_esc(label)}（缺失）</span>"
    note_html = f"<div class='muted'>{_esc(note)}</div>" if note else ""
    return f"<li>{title}{note_html}</li>"


def _agent_memo_links(docs_dir: Path, run_date: str) -> Dict[str, str]:
    base = docs_dir / "agent_memos" / run_date
    first_stock = ""
    stocks_dir = base / "stocks"
    if stocks_dir.exists():
        stock_dirs = sorted(path for path in stocks_dir.iterdir() if path.is_dir())
        if stock_dirs:
            first_stock = stock_dirs[0].name
    evidence_rel = (
        f"agent_memos/{run_date}/stocks/{first_stock}/00_context_pack.html"
        if first_stock
        else f"agent_memos/{run_date}/sources/00_source_inventory.html"
    )
    if not (docs_dir / evidence_rel).exists():
        evidence_rel = f"reports/{run_date}.diagnostics.html"
    source_review_rel = f"agent_memos/{run_date}/market/01_source_review.html"
    if not (docs_dir / source_review_rel).exists():
        source_review_rel = f"reports/{run_date}.diagnostics.html"
    return {
        "overview": f"agent_memos/{run_date}/index.html",
        "macro": f"agent_memos/{run_date}/market/02_macro_geopolitics.html",
        "geo": f"agent_memos/{run_date}/market/03_geo_policy.html",
        "sources": f"agent_memos/{run_date}/sources/01_source_gap_plan.html",
        "candidates": f"agent_memos/{run_date}/market/04_candidate_review.html",
        "portfolio": f"agent_memos/{run_date}/market/05_portfolio_review.html",
        "stock": f"agent_memos/{run_date}/stocks/{first_stock}/11_decision_report.html" if first_stock else "",
        "evidence": evidence_rel,
        "source_review": source_review_rel,
    }


def _section_report_aliases(run_date: str) -> Dict[str, str]:
    return {
        "macro": f"reports/{run_date}/macro.html",
        "geo": f"reports/{run_date}/geo.html",
        "market": f"reports/{run_date}/market.html",
        "sectors": f"reports/{run_date}/sectors.html",
        "candidates": f"reports/{run_date}/candidates.html",
        "news": f"reports/{run_date}/news.html",
        "stocks": f"reports/{run_date}/stocks.html",
        "portfolio": f"reports/{run_date}/portfolio.html",
        "risk": f"reports/{run_date}/risk.html",
    }


def _artifact_sections(docs_dir: Path, run_date: str) -> str:
    section_links = _section_report_aliases(run_date)
    return f"""
<section class="card">
  <h2>分报告下钻</h2>
  <p class="muted">需要细看时进入对应分报告；默认先读上方总判断和部门摘要。</p>
    <div class="flow-grid">
    {_section_card("宏观", section_links["macro"], "宏观、利率和流动性背景。")}
    {_section_card("地缘政策", section_links["geo"], "贸易、制裁、冲突、政策事件和市场传导。")}
    {_section_card("市场 / 板块", section_links["market"], "指数、热度、筛选漏斗和市场策略。")}
    {_section_card("行业 / 风格", section_links["sectors"], "行业强弱、风格轮动和持续性判断。")}
    {_section_card("候选观察", section_links["candidates"], "候选池、纳入原因和待验证条件。")}
    {_section_card("新闻情报", section_links["news"], "新闻发现、事件线索和舆情只读摘要。")}
    {_section_card("个股深挖", section_links["stocks"], "个股深评、反证复核和行动状态。")}
    {_section_card("持仓复核", section_links["portfolio"], "持仓轻量复核；异常才进入个股深评。")}
    {_section_card("风险 / 反证", section_links["risk"], "待确认项、反证和暂停理由。")}
  </div>
</section>
"""


def _section_card(title: str, href: str, note: str) -> str:
    return (
        "<article class='flow-card'>"
        f"<h3><a href='{_esc(_relative_from_report_center(href))}'>{_esc(title)}</a></h3>"
        f"<p>{_esc(note)}</p>"
        "<span class='pill'>已生成</span>"
        "</article>"
    )


def _claim_evidence_cards(claim_evidence: Dict[str, Any]) -> str:
    claims = claim_evidence.get("claims") if isinstance(claim_evidence.get("claims"), dict) else {}
    if not claims:
        return "<p class='muted'>未提供 claimEvidence。</p>"
    cards: List[str] = []
    for key, row in claims.items():
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "missing")
        status_class = "good" if status == "supported" else "warn"
        missing = _join_items(row.get("missingDomains") or [], limit=6)
        blockers = _join_items(row.get("blockers") or [], limit=6)
        cards.append(
            "<article class='flow-card'>"
            f"<h3>{_esc(row.get('label') or key)} <span class='{status_class}'>{_esc(status)}</span></h3>"
            f"<p>evidence：{_esc(row.get('evidenceCount', 0))}</p>"
            f"<p class='muted'>missing domains：{_esc(missing)}</p>"
            f"<p class='muted'>blockers：{_esc(blockers)}</p>"
            "</article>"
        )
    return "".join(cards) or "<p class='muted'>未提供 claimEvidence。</p>"


def _artifact_contract_html(artifact: Dict[str, Any]) -> str:
    reader_v3 = artifact.get("readerV3") if isinstance(artifact.get("readerV3"), dict) else {}
    if reader_v3:
        return _reader_v3_html(artifact, reader_v3)

    summary = artifact.get("summary") if isinstance(artifact.get("summary"), dict) else {}
    source_health_v2 = artifact.get("sourceHealthV2") if isinstance(artifact.get("sourceHealthV2"), dict) else {}
    claim_policy = artifact.get("claimPolicy") if isinstance(artifact.get("claimPolicy"), dict) else source_health_v2.get("claimPolicy") if isinstance(source_health_v2.get("claimPolicy"), dict) else {}
    evidence_stats = artifact.get("evidenceStats") if isinstance(artifact.get("evidenceStats"), dict) else source_health_v2.get("evidenceStats") if isinstance(source_health_v2.get("evidenceStats"), dict) else {}
    decision = artifact.get("decision") if isinstance(artifact.get("decision"), dict) else {}
    evidence_items = artifact.get("evidenceItems") if isinstance(artifact.get("evidenceItems"), list) else []
    runtime_summary = artifact.get("agentRuntimeSummary") if isinstance(artifact.get("agentRuntimeSummary"), dict) else {}

    mode = str(artifact.get("analysisMode") or source_health_v2.get("overallMode") or "OBSERVE_ONLY")
    mode_label = {
        "FULL_REVIEW": "完整复盘",
        "LIMITED_REVIEW": "有限复盘",
        "SCREEN_ONLY": "仅筛选观察",
        "OBSERVE_ONLY": "仅市场观察",
        "BLOCKED": "数据不足，暂停结论",
    }.get(mode, "仅市场观察")
    confidence_label = _reader_confidence(source_health_v2.get("overallScore"))
    action_label = _human_action(decision.get("action"))
    gate_label = "暂停结论" if decision.get("gateStatus") == "blocked" else ("观察等待" if decision.get("gateStatus") == "watch" else "可进入人工复核")
    source_note = ""
    if claim_policy.get("mustShowCaveat") and mode != "FULL_REVIEW":
        source_note = "数据仍有投研限制，结论需要人工复核。"
    rule_fallback_count = int(runtime_summary.get("ruleFallback") or 0)
    llm_count = int(runtime_summary.get("llm") or 0)
    if rule_fallback_count:
        source_note = (
            (source_note + " " if source_note else "")
            + f"分析部门未全部在线：{rule_fallback_count} 个部门使用规则层兜底。"
        )
    elif llm_count:
        source_note = (source_note + " " if source_note else "") + f"分析部门在线：{llm_count} 个部门完成分析。"

    key_facts = list(summary.get("keyFacts") or [])[:6]
    next_steps = list(summary.get("nextSteps") or [])[:5]
    brief = artifact.get("readerBrief") if isinstance(artifact.get("readerBrief"), dict) else {}
    reader_v2 = artifact.get("readerV2") if isinstance(artifact.get("readerV2"), dict) else {}
    reader_v2_sections = reader_v2.get("sections") if isinstance(reader_v2.get("sections"), list) else []
    v2_today = _reader_v2_section(reader_v2_sections, "today")
    v2_why = _reader_v2_section(reader_v2_sections, "why")
    v2_risk = _reader_v2_section(reader_v2_sections, "risk")
    v2_market_geo = _reader_v2_section(reader_v2_sections, "market_geo")
    v2_next = _reader_v2_section(reader_v2_sections, "next")
    v2_data_confidence = _reader_v2_section(reader_v2_sections, "data_confidence")
    why_source = v2_why.get("bullets") if isinstance(v2_why.get("bullets"), list) and v2_why.get("bullets") else brief.get("why") if isinstance(brief.get("why"), list) and brief.get("why") else key_facts
    why = [_sanitize_reader_markdown(str(item)) for item in (why_source[:5] or [summary.get("analysis") or "今日报告缺少关键依据摘要。"])]
    if isinstance(v2_next.get("bullets"), list) and v2_next.get("bullets"):
        next_steps = list(v2_next.get("bullets") or [])[:5]
    elif isinstance(brief.get("nextSteps"), list) and brief.get("nextSteps"):
        next_steps = list(brief.get("nextSteps") or [])[:5]
    blockers = []
    if isinstance(v2_risk.get("bullets"), list) and v2_risk.get("bullets"):
        blockers = list(dict.fromkeys([*_sanitize_list(v2_risk.get("bullets") or []), *blockers]))[:6]
    elif isinstance(brief.get("risks"), list):
        blockers = list(dict.fromkeys([*_sanitize_list(brief.get("risks") or []), *blockers]))[:6]
    cio_enrichment = artifact.get("cioEnrichment") if isinstance(artifact.get("cioEnrichment"), dict) else {}
    if cio_enrichment.get("remainingGaps"):
        blockers = list(dict.fromkeys([*blockers, *[f"CIO 补数后仍缺：{item}" for item in cio_enrichment.get("remainingGaps") or []]]))[:6]

    evidence_cards = []
    for item in evidence_items[:8]:
        if not isinstance(item, dict):
            continue
        if str(item.get("evidenceScope") or "subject_evidence") == "source_smoke":
            continue
        fact_type = str(item.get("factType") or "")
        fact_label = {"verified_fact": "已验证事实", "derived_fact": "推导事实", "discovery": "发现线索", "missing": "缺失项"}.get(fact_type, "证据")
        source_url = _valid_http_url(item.get("sourceUrl"))
        source_label = _reader_evidence_source(item, source_url)
        source_html = _esc(source_label)
        if source_url:
            source_html = f"<a href='{_esc(source_url)}' target='_blank' rel='noreferrer'>{source_html}</a>"
        evidence_cards.append(
            "<article class='flow-card'>"
            f"<h3>{_esc(fact_label)}</h3>"
            f"<p>{_esc(_reader_evidence_text(item))}</p>"
            f"<p class='muted'>{source_html} · {_esc(_reader_evidence_time(item))}</p>"
            "</article>"
        )

    why_html = "".join(f"<li>{_esc(item)}</li>" for item in why)
    blockers_html = "".join(f"<li>{_esc(item)}</li>" for item in blockers) or "<li>暂无额外主风险。</li>"
    next_html = "".join(f"<li>{_esc(_sanitize_reader_markdown(str(item)))}</li>" for item in next_steps) or "<li>等待下一次数据刷新后复核。</li>"
    v2_cards = reader_v2.get("departmentCards") if isinstance(reader_v2.get("departmentCards"), list) else []
    dept_cards = _department_cards(v2_cards)
    final_conclusion = _sanitize_reader_markdown(str(v2_today.get("body") or brief.get("finalConclusion") or summary.get("finalConclusion") or "未提供 CIO 总结。"))
    source_warning = f"<p class='warn'>{_esc(source_note)}</p>" if source_note else ""
    market_geo_html = ""
    if isinstance(v2_market_geo.get("bullets"), list) and v2_market_geo.get("bullets"):
        market_geo_html = (
            "<section class='card'>"
            f"<h2>{_esc(str(v2_market_geo.get('title') or '市场与地缘'))}</h2>"
            "<ul>"
            + "".join(f"<li>{_esc(_sanitize_reader_markdown(str(item)))}</li>" for item in v2_market_geo.get("bullets") or [] if str(item).strip())
            + "</ul></section>"
        )
    data_confidence = _sanitize_reader_markdown(str(v2_data_confidence.get("body") or brief.get("dataConfidence") or ""))
    return f"""
<section class="card">
  <h2>今日投研结论</h2>
  <p><span class="pill">{_esc(mode_label)}</span> <span class="pill">{_esc(confidence_label)}</span> <span class="pill">{_esc(action_label)} · {_esc(gate_label)}</span></p>
  <p>{_esc(_sanitize_reader_markdown(str(v2_today.get('body') or brief.get('oneLine') or summary.get('oneLine') or '未提供今日结论。')))}</p>
  {source_warning}
  <div class="grid3">
    <div><h3>当前动作</h3><p>{_esc(action_label)}；{_esc(gate_label)}</p></div>
    <div><h3>可信度</h3><p>{_esc(confidence_label)}</p></div>
    <div><h3>证据状态</h3><p>已验证 {_esc(evidence_stats.get('verifiedFacts', 0))}；发现线索 {_esc(evidence_stats.get('discoveryItems', 0))}；关键缺口 {_esc(evidence_stats.get('missingCriticalFacts', 0))}</p></div>
  </div>
  <div><h3>CIO 总结</h3><p>{_esc(final_conclusion)}</p></div>
  <div class="grid">
    <div><h3>为什么</h3><ul>{why_html}</ul></div>
    <div><h3>风险和反证</h3><ul>{blockers_html}</ul></div>
  </div>
  <div><h3>下一步</h3><ul>{next_html}</ul></div>
</section>
{market_geo_html}
<section class="card">
  <h2>分部门摘要</h2>
  <p class="muted">每个部门只展示结论、依据、反证、下一步和可展开证据；工程排障在高级诊断。</p>
  <div class="flow-grid">{dept_cards or '<p class="muted">本轮未记录到分部门结论。</p>'}</div>
</section>
<section class="card">
  <h2>数据可信度</h2>
  <p>{_esc(data_confidence or '本轮数据可用于投研复核，仍需人工判断。')}</p>
  <div class="flow-grid">{''.join(evidence_cards) or '<p class="muted">未提供证据摘要。</p>'}</div>
</section>
"""


def _reader_market_matrix_html(rows: Iterable[Any]) -> str:
    body: List[str] = []
    cards: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        scope_type = "市场数据" if row.get("scopeType") == "market" else "观察样本"
        scope_label = str(row.get("scopeLabel") or row.get("market") or "市场")
        state = _sanitize_reader_markdown(str(row.get("state") or "待观察"))
        headline = _sanitize_reader_markdown(str(row.get("headline") or "未提供"))
        scope_note = _sanitize_reader_markdown(str(row.get("scopeNote") or ""))
        body.append(
            "<tr>"
            f"<td><strong>{_esc(scope_label)}</strong><br><span class='scope-tag'>{_esc(scope_type)}</span></td>"
            f"<td>{_esc(state)}</td>"
            f"<td>{_esc(headline)}</td>"
            f"<td class='muted'>{_esc(scope_note)}</td>"
            "</tr>"
        )
        cards.append(
            "<article class='matrix-card'>"
            f"<div class='matrix-card-heading'><strong>{_esc(scope_label)}</strong><span class='scope-tag'>{_esc(scope_type)}</span></div>"
            f"<dl><div><dt>状态</dt><dd>{_esc(state)}</dd></div>"
            f"<div><dt>关键表现</dt><dd>{_esc(headline)}</dd></div>"
            f"<div><dt>如何解读</dt><dd>{_esc(scope_note or '未提供')}</dd></div></dl>"
            "</article>"
        )
    if not body:
        return ""
    return (
        "<section class='research-section'><div class='section-heading'><p class='eyebrow'>市场范围</p>"
        "<h2>市场范围与样本表现</h2></div>"
        "<div class='table-wrap reader-matrix-table'><table class='research-table'><thead><tr>"
        "<th>范围</th><th>状态</th><th>关键表现</th><th>如何解读</th>"
        f"</tr></thead><tbody>{''.join(body)}</tbody></table></div>"
        f"<div class='reader-matrix-cards'>{''.join(cards)}</div></section>"
    )


def _reader_stock_matrix_html(rows: Iterable[Any]) -> str:
    body: List[str] = []
    cards: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        price = row.get("lastPrice")
        price_text = f"{float(price):.2f} {row.get('currency') or ''}" if isinstance(price, (int, float)) else "待更新"
        returns = []
        for key, label in (("return1dPct", "1日"), ("return20dPct", "20日")):
            value = row.get(key)
            if isinstance(value, (int, float)):
                returns.append(f"{label} {float(value):+.2f}%")
        event = _sanitize_reader_markdown(str(row.get("latestEvent") or "暂无近期官方事件摘要"))
        event_url = str(row.get("eventUrl") or "")
        event_html = _esc(event)
        valid_event_url = _valid_http_url(event_url)
        if valid_event_url:
            event_html = f"<a href='{_esc(valid_event_url)}' target='_blank' rel='noreferrer'>{event_html}</a>"
        if row.get("eventDate"):
            event_html += f"<br><span class='muted'>{_esc(row.get('eventDate'))}</span>"
        name = str(row.get("name") or row.get("symbol") or "标的")
        symbol = str(row.get("symbol") or "")
        returns_text = " / ".join(returns) or "阶段表现待更新"
        trend = str(row.get("trend") or "趋势待确认")
        watch_levels = str(row.get("watchLevels") or "")
        fundamental = _sanitize_reader_markdown(str(row.get("fundamental") or "结构化基本面待补强"))
        valuation = _sanitize_reader_markdown(str(row.get("valuation") or "当前估值与历史样本待补"))
        stance = str(row.get("stance") or "观察")
        body.append(
            "<tr>"
            f"<td><strong>{_esc(name)}</strong><br><span class='muted'>{_esc(symbol)}</span></td>"
            f"<td>{_esc(price_text)}<br><span class='muted'>{_esc(returns_text)}</span></td>"
            f"<td>{_esc(trend)}<br><span class='muted'>{_esc(watch_levels)}</span></td>"
            f"<td>{_esc(fundamental)}</td>"
            f"<td>{_esc(valuation)}</td>"
            f"<td>{event_html}</td>"
            f"<td><span class='stance'>{_esc(stance)}</span></td>"
            "</tr>"
        )
        cards.append(
            "<article class='matrix-card stock-matrix-card'>"
            f"<div class='matrix-card-heading'><span><strong>{_esc(name)}</strong><small>{_esc(symbol)}</small></span><span class='stance'>{_esc(stance)}</span></div>"
            f"<dl><div><dt>价格 / 阶段表现</dt><dd>{_esc(price_text)}<br><span class='muted'>{_esc(returns_text)}</span></dd></div>"
            f"<div><dt>趋势 / 观察位</dt><dd>{_esc(trend)}<br><span class='muted'>{_esc(watch_levels)}</span></dd></div>"
            f"<div><dt>基本面</dt><dd>{_esc(fundamental)}</dd></div>"
            f"<div><dt>估值</dt><dd>{_esc(valuation)}</dd></div>"
            f"<div><dt>最新官方事件</dt><dd>{event_html}</dd></div></dl>"
            "</article>"
        )
    if not body:
        return ""
    return (
        "<section class='research-section'><div class='section-heading'><p class='eyebrow'>标的跟踪</p>"
        "<h2>重点标的跟踪</h2><p class='muted'>价格与指标来自同轮证据；定位是研究观察，不代表自动交易指令。</p></div>"
        "<div class='table-wrap reader-matrix-table'><table class='research-table stock-table'><thead><tr>"
        "<th>标的</th><th>价格 / 阶段表现</th><th>趋势 / 观察位</th><th>基本面</th><th>估值</th><th>最新官方事件</th><th>定位</th>"
        f"</tr></thead><tbody>{''.join(body)}</tbody></table></div>"
        f"<div class='reader-matrix-cards'>{''.join(cards)}</div></section>"
    )


def _hero_additive_fields_html(hero: Dict[str, Any]) -> str:
    primary_fields = (
        ("marketStance", "研究立场"),
        ("portfolioAction", "组合动作"),
    )
    meta_fields = (
        ("confidence", "可信度"),
        ("validity", "时效"),
        ("dataCoverage", "覆盖"),
    )
    primary: List[str] = []
    for key, label in primary_fields:
        value = _sanitize_reader_markdown(_reader_product_text(hero.get(key)))
        if not value:
            continue
        primary.append(
            "<div class='hero-fact'>"
            f"<span>{_esc(label)}</span><strong>{_esc(value)}</strong>"
            "</div>"
        )
    meta: List[str] = []
    for key, label in meta_fields:
        value = _sanitize_reader_markdown(_reader_product_text(hero.get(key)))
        if not value:
            continue
        meta.append(f"<span><b>{_esc(label)}</b> {_esc(value)}</span>")
    if not primary and not meta:
        return ""
    return (
        f"<div class='hero-facts'>{''.join(primary)}</div>"
        f"<div class='hero-meta'>{''.join(meta)}</div>"
    )


def _reader_v3_html(artifact: Dict[str, Any], reader: Dict[str, Any]) -> str:
    hero = reader.get("hero") if isinstance(reader.get("hero"), dict) else {}
    timing = reader.get("timing") if isinstance(reader.get("timing"), dict) else {}
    evidence_summary = reader.get("evidenceSummary") if isinstance(reader.get("evidenceSummary"), dict) else {}
    report_date = str(timing.get("reportDate") or artifact.get("runDate") or "未标")
    evidence_time = timing.get("dataAsOf") or ""
    data_as_of = _reader_datetime(evidence_time)
    generated_at = _reader_datetime(
        timing.get("generatedAt") or artifact.get("generatedAt"),
        time_only=True,
    )
    one_line = _sanitize_reader_markdown(str(hero.get("oneLine") or "本轮未生成总判断。"))
    limitation = _sanitize_reader_markdown(str(hero.get("maxLimitation") or "仍需人工复核，不自动执行交易。"))
    additive_fields = _hero_additive_fields_html(hero)
    key_reasons = _html_bullets(reader.get("keyReasons") or [], limit=3) or "<p class='muted'>未提供核心理由。</p>"
    counterpoints = _html_bullets(reader.get("counterpoints") or [], limit=3) or "<p class='muted'>未提供反证。</p>"
    next_steps = _html_bullets(reader.get("nextSteps") or [], limit=3) or "<p class='muted'>等待下一次刷新。</p>"
    market_matrix = _reader_market_matrix_html(reader.get("marketMatrix") or [])
    stock_matrix = _reader_stock_matrix_html(reader.get("stockMatrix") or [])
    market_geo = _html_bullets(reader.get("marketGeo") or [], limit=3)
    adjudication = reader.get("adjudication") if isinstance(reader.get("adjudication"), dict) else {}
    reliability = reader.get("reliability") if isinstance(reader.get("reliability"), dict) else {}
    shared_facts = _html_bullets(adjudication.get("sharedFacts") or [], limit=3)
    invalidation_triggers = _html_bullets(adjudication.get("invalidationTriggers") or [], limit=3)
    reliability_warnings = _html_bullets(reliability.get("warnings") or [], limit=3)
    core_evidence_rows: List[Dict[str, Any]] = []
    seen_evidence: set[str] = set()
    for department in reader.get("departmentCards") or []:
        if not isinstance(department, dict):
            continue
        for sample in department.get("evidenceSamples") or []:
            if not isinstance(sample, dict):
                continue
            key = str(
                sample.get("id")
                or f"{sample.get('sourceName') or sample.get('provider')}:{sample.get('asOf')}:{sample.get('label')}"
            )
            if key in seen_evidence:
                continue
            seen_evidence.add(key)
            core_evidence_rows.append(sample)
            if len(core_evidence_rows) >= 6:
                break
        if len(core_evidence_rows) >= 6:
            break
    core_evidence = _evidence_sample_bullets(
        core_evidence_rows,
        limit=6,
        fallback_time=evidence_time,
    )
    departments = _department_cards(reader.get("departmentCards") or [], evidence_time=evidence_time)
    fallback_sections = (
        ""
        if departments
        else _reader_v3_report_sections_html(
            reader.get("reportSections") or [],
            evidence_time=evidence_time,
        )
    )
    verified_count = evidence_summary.get("verifiedFacts", 0)
    derived_count = evidence_summary.get("derivedFacts", 0)
    discovery_count = evidence_summary.get("discoveryItems", 0)
    critical_gap_count = evidence_summary.get("missingCriticalFacts", 0)
    department_gap_count = evidence_summary.get("departmentGapItems", 0)
    gap_text = (
        f"关键证据缺口 {critical_gap_count}；部门待确认 {department_gap_count}"
        if int(critical_gap_count or 0) > 0
        else f"无关键证据缺口；部门待确认 {department_gap_count}"
    )
    coverage = _sanitize_reader_markdown(str(hero.get("coverage") or ""))
    return f"""
<section class="institution-hero">
  <div class="hero-kicker"><span>{_esc(str(hero.get('status') or '跨市场机构简报'))}</span><span>{_esc(report_date)}</span></div>
  <h1>今日总判断</h1>
  <p class="muted">报告日期 {_esc(report_date)} · 综合数据截至 {_esc(data_as_of)} · 生成于 {_esc(generated_at)}</p>
  {f'<p class="muted">{_esc(coverage)}</p>' if coverage else ''}
  <p class="decision-line">{_esc(one_line)}</p>
  {additive_fields}
  <div class="research-boundary"><strong>研究边界</strong><span>{_esc(limitation)}</span></div>
</section>
<section class="research-section executive-grid">
  <div><p class="eyebrow">核心依据</p><h2>核心理由</h2>{key_reasons}</div>
  <div><p class="eyebrow">反证与风险</p><h2>最大反证 / 风险</h2>{counterpoints}</div>
  <div><p class="eyebrow">后续观察</p><h2>下一步</h2>{next_steps}</div>
</section>
{("<details class='core-evidence-drawer'><summary>查看核心证据</summary><div><p class='muted'>来源与时间</p>" + core_evidence + "</div></details>") if core_evidence else ''}
<section class="research-section">
  <div class="section-heading"><p class="eyebrow">情景裁决</p><h2>基准情景与竞争情景</h2></div>
  {('<h3>双方共同事实</h3>' + shared_facts) if shared_facts else ''}
  <div class="scenario-grid">
    <div><span class="scope-tag">基准情景</span><p>{_esc(_sanitize_reader_markdown(str(adjudication.get('baseCase') or '当前基准情景尚未形成。')))}</p></div>
    <div><span class="scope-tag">竞争情景</span><p>{_esc(_sanitize_reader_markdown(str(adjudication.get('strongestAlternative') or '暂无形成证据链的竞争情景。')))}</p></div>
  </div>
  <div class="cio-verdict"><span>CIO 裁决</span><p>{_esc(_sanitize_reader_markdown(str(adjudication.get('judgment') or one_line)))}</p></div>
  {('<p class="muted">为什么：' + _esc(_sanitize_reader_markdown(str(adjudication.get('why')))) + '</p>') if adjudication.get('why') else ''}
  {('<h3>推翻当前裁决的信号</h3>' + invalidation_triggers) if invalidation_triggers else ''}
</section>
{market_matrix}
{stock_matrix}
{('<section class="research-section"><div class="section-heading"><p class="eyebrow">宏观与地缘</p><h2>市场与地缘</h2></div>' + market_geo + '</section>') if market_geo else ''}
{fallback_sections}
<section class="research-section">
  <div class="section-heading"><p class="eyebrow">部门摘要</p><h2>部门研究摘要</h2></div>
  <p class="muted">摘要直接可见；依据、反证、待确认项和证据默认折叠。</p>
  <div class="department-list">{departments or '<p class="muted">本轮未记录到分部门结论。</p>'}</div>
</section>
<details class="methodology-drawer"><summary>数据与方法说明</summary><div>
  <p>{_esc(_sanitize_reader_markdown(str(reader.get('dataConfidence') or '本轮数据可用于投研复核，仍需人工判断。')))}</p>
  <p class="muted">已验证 {_esc(verified_count)}；推导 {_esc(derived_count)}；发现线索 {_esc(discovery_count)}；{_esc(gap_text)}</p>
  {('<div class="warn">' + reliability_warnings + '</div>') if reliability_warnings else ''}
</div></details>
"""


def _reader_v3_report_sections_html(
    sections: Iterable[Any],
    *,
    evidence_time: Any = "",
) -> str:
    cards: List[str] = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        title = _sanitize_reader_markdown(str(section.get("title") or "报告环节"))
        body = _sanitize_reader_markdown(str(section.get("body") or "本环节未形成独立结论。"))
        bullets = _html_bullets(section.get("bullets") or [], limit=5)
        counters = _html_bullets(section.get("counterpoints") or [], limit=4)
        next_actions = _html_bullets(section.get("nextActions") or [], limit=3)
        evidence = _evidence_sample_bullets(
            section.get("evidenceSamples") or [],
            limit=5,
            fallback_time=evidence_time,
        )
        details = ""
        if counters or next_actions or evidence:
            details = (
                "<details><summary>可展开证据 / 反证 / 下一步</summary>"
                f"{('<h4>风险和反证</h4>' + counters) if counters else ''}"
                f"{('<h4>下一步</h4>' + next_actions) if next_actions else ''}"
                f"{('<h4>证据样例</h4>' + evidence) if evidence else ''}"
                "</details>"
            )
        cards.append(
            "<article class='flow-card'>"
            f"<h3>{_esc(title)}</h3>"
            f"<p>{_esc(body)}</p>"
            f"{bullets or ''}"
            f"{details}"
            "</article>"
        )
    if not cards:
        return ""
    return (
        "<section class='card'>"
        "<h2>可读汇总</h2>"
        "<p class='muted'>本轮没有独立部门摘要，以下保留按主题整理的可读结论。</p>"
        f"<div class='flow-grid'>{''.join(cards)}</div>"
        "</section>"
    )


def _sanitize_list(items: Iterable[Any]) -> List[str]:
    return [_sanitize_reader_markdown(str(item)) for item in items if str(item)]


def _department_cards(rows: Iterable[Any], *, evidence_time: Any = "") -> str:
    featured_labels = {"CIO 报告", "风险部门", "市场部门", "持仓复核部门"}
    featured: List[str] = []
    other: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("readerVisible") is False:
            continue
        title = _sanitize_reader_markdown(str(row.get("label") or row.get("agent") or "分析部门"))
        summary = _sanitize_reader_markdown(str(row.get("conclusion") or row.get("summaryForReader") or "本部门未给出可读结论。"))
        next_action = _sanitize_reader_markdown(str(row.get("nextAction") or "等待下一轮复核。"))
        next_actions = _html_bullets(row.get("nextActions") or [next_action], limit=3)
        claims = _html_bullets(row.get("keyClaims") or [], limit=5)
        challenged = _challenged_claims_html(row.get("challengedClaims") or [])
        counters = _html_bullets(row.get("counterpoints") or [], limit=4)
        gaps = _html_bullets(row.get("dataGaps") or [], limit=4)
        support = _html_bullets(row.get("supportSignals") or [], limit=4)
        samples = _evidence_sample_bullets(
            row.get("evidenceSamples") or [],
            fallback_time=evidence_time,
        )
        empty = '<p class="muted">未提供。</p>'
        no_key_gap = '<p class="muted">暂无会改变结论的关键缺口。</p>'
        card = (
            "<details class='department-card'>"
            "<summary>"
            f"<span class='department-title'>{_esc(title)}</span>"
            "<span class='department-open-label'>查看依据</span>"
            f"<span class='department-summary'>{_esc(summary)}</span>"
            "</summary>"
            "<div class='department-details'>"
            f"<h4>下一步</h4>{next_actions}"
            f"<h4>依据</h4>{claims or empty}"
            f"{('<h4>已识别的争议结论</h4>' + challenged) if challenged else ''}"
            f"<h4>反证</h4>{counters or empty}"
            f"<h4>还需要确认</h4>{gaps or no_key_gap}"
            f"<h4>支撑信号</h4>{support or empty}"
            f"<h4>证据样例</h4>{samples or empty}"
            "</div>"
            "</details>"
        )
        (featured if title in featured_labels and len(featured) < 4 else other).append(card)
    if other:
        featured.append(
            "<details class='department-group'>"
            f"<summary><span>其余 {len(other)} 个研究部门</span><span>展开全部</span></summary>"
            f"<div class='department-group-body'>{''.join(other)}</div>"
            "</details>"
        )
    return "".join(featured)


def _challenged_claims_html(items: Iterable[Any], *, limit: int = 3) -> str:
    rows: List[str] = []
    for item in list(items or [])[:limit]:
        if not isinstance(item, dict):
            continue
        claim = _sanitize_reader_markdown(str(item.get("claim") or ""))
        status = _sanitize_reader_markdown(str(item.get("status") or "存在有效反证"))
        opposing = _sanitize_reader_markdown(str(item.get("opposingScenario") or ""))
        falsifier = _sanitize_reader_markdown(str(item.get("falsifier") or ""))
        detail = f"<strong>{_esc(status)}</strong>"
        if opposing:
            detail += f"<br>反方情景：{_esc(opposing)}"
        if falsifier:
            detail += f"<br>如何验证：{_esc(falsifier)}"
        rows.append(f"<li>{_esc(claim)}<br>{detail}</li>")
    return f"<ul class='challenge-list'>{''.join(rows)}</ul>" if rows else ""


_EVIDENCE_SOURCE_LABELS = {
    "DataFetcherManager": "综合行情数据",
    "原系统数据聚合": "综合行情数据",
    "YfinanceFetcher": "Yahoo Finance 行情",
    "YfinanceFundamentalAdapter": "Yahoo Finance 公开财务数据",
    "AkshareFetcher": "AkShare 公开数据",
    "TushareFetcher": "Tushare 行情",
    "SEC_EDGAR": "SEC 官方披露",
    "CNINFO": "巨潮资讯官方公告",
    "FRED": "美国圣路易斯联储数据",
    "RELIEFWEB": "联合国 ReliefWeb",
    "GDELT": "GDELT 新闻数据",
    "official": "官方披露",
}

_EVIDENCE_FACT_LABELS = {
    "verified_fact": "已验证事实",
    "derived_fact": "推导事实",
    "discovery": "发现线索",
    "missing": "缺失项",
    "agent_opinion": "部门判断",
    "final_claim": "最终判断",
}


def _source_label_from_url(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    for suffix, label in (
        ("sec.gov", "SEC 官方披露"),
        ("cninfo.com.cn", "巨潮资讯官方公告"),
        ("fred.stlouisfed.org", "美国圣路易斯联储数据"),
        ("finance.yahoo.com", "Yahoo Finance 公开数据"),
        ("reliefweb.int", "联合国 ReliefWeb"),
    ):
        if host == suffix or host.endswith(f".{suffix}"):
            return label
    return host or "来源未标"


def _reader_evidence_source(item: Dict[str, Any], source_url: str) -> str:
    raw = next(
        (
            str(item.get(key)).strip()
            for key in ("sourceLabel", "sourceName", "publisher", "source", "provider")
            if item.get(key)
        ),
        "",
    )
    if raw in _EVIDENCE_SOURCE_LABELS:
        return _EVIDENCE_SOURCE_LABELS[raw]
    if re.search(r"(?:Fetcher|Adapter|Manager|Provider|Client|Collector|Service)$", raw):
        return _source_label_from_url(source_url) if source_url else "系统整合数据"
    return _sanitize_reader_markdown(raw) if raw else _source_label_from_url(source_url)


def _reader_evidence_text(item: Dict[str, Any]) -> str:
    raw = str(item.get("label") or item.get("value") or item.get("title") or "证据")
    text = _sanitize_reader_markdown(raw)
    if re.search(r"\b(?:rows|records)\s*=", text, flags=re.IGNORECASE):
        names = re.findall(
            r"\b(?:name|title|headline)\s*=\s*([^,;|]+)",
            text,
            flags=re.IGNORECASE,
        )
        text = "；".join(dict.fromkeys(name.strip() for name in names if name.strip()))
        if not text:
            text = "结构化数据快照"
    text = re.sub(
        r"\b[A-Z][A-Za-z0-9]*(?:Fetcher|Adapter|Manager|Provider|Client|Collector|Service)\b",
        "",
        text,
    )
    text = re.sub(r"\s+", " ", text).strip(" ；，,|")
    return text or "结构化数据快照"


def _reader_evidence_time(item: Dict[str, Any], fallback_time: Any = "") -> str:
    for key, label in (
        ("publishedAt", "发布时间"),
        ("eventTime", "发生时间"),
        ("asOf", "数据截至"),
        ("observedAt", "观测时间"),
        ("fetchedAt", "获取时间"),
        ("date", "日期"),
    ):
        value = item.get(key)
        if value:
            text = str(value).strip()
            formatted = text if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) else _reader_datetime(text)
            return f"{label} {formatted}"
    if fallback_time:
        return f"数据截至 {_reader_datetime(fallback_time)}"
    return "时间未标"


def _evidence_sample_bullets(
    items: Iterable[Any],
    *,
    limit: int = 4,
    fallback_time: Any = "",
) -> str:
    rows: List[str] = []
    for item in list(items or [])[:limit]:
        if not isinstance(item, dict):
            continue
        source_url = _valid_http_url(item.get("sourceUrl"))
        source_label = _reader_evidence_source(item, source_url)
        source_html = _esc(source_label)
        if source_url:
            source_html = (
                f"<a href='{_esc(source_url)}' target='_blank' rel='noreferrer'>"
                f"{source_html}</a>"
            )
        raw_fact_type = str(item.get("factType") or item.get("fact_type") or "")
        fact_type = _EVIDENCE_FACT_LABELS.get(raw_fact_type, _sanitize_reader_markdown(raw_fact_type))
        time_text = _reader_evidence_time(item, fallback_time)
        copy = _reader_evidence_text(item)
        copy_html = "" if copy == "结构化数据快照" else f"<span class='evidence-copy'>{_esc(copy)}</span>"
        rows.append(
            "<li>"
            f"<span class='evidence-meta'>{source_html} · {_esc(fact_type or '事实')} · {_esc(time_text)}</span>"
            f"{copy_html}"
            "</li>"
        )
    if not rows:
        return ""
    return "<ul class='evidence-list'>" + "".join(rows) + "</ul>"


def _reader_v2_section(sections: Iterable[Any], key: str) -> Dict[str, Any]:
    for section in sections:
        if isinstance(section, dict) and section.get("key") == key:
            return section
    return {}


def _html_bullets(items: Iterable[Any], *, limit: int = 5) -> str:
    rows = [_sanitize_reader_markdown(str(item)) for item in list(items or [])[:limit] if str(item).strip()]
    if not rows:
        return ""
    return "<ul>" + "".join(f"<li>{_esc(item)}</li>" for item in rows) + "</ul>"


def build_report_diagnostics(docs_dir: Path, run_date: str, artifact: Dict[str, Any]) -> str:
    source_health_v2 = artifact.get("sourceHealthV2") if isinstance(artifact.get("sourceHealthV2"), dict) else {}
    provider_matrix = source_health_v2.get("providerMatrix") if isinstance(source_health_v2.get("providerMatrix"), list) else []
    domains = source_health_v2.get("domains") if isinstance(source_health_v2.get("domains"), dict) else {}
    refs = artifact.get("snapshotRefs") if isinstance(artifact.get("snapshotRefs"), dict) else {}
    run_matrix = _read_json(docs_dir / "run_status" / run_date / "run_matrix.json") or {}
    llm_runs = _read_jsonl(docs_dir / "run_status" / run_date / "llm_agent_runs.jsonl")
    model_selection = _read_json(docs_dir / "run_status" / run_date / "agent_model_selection.json") or {}
    cio_requests = _read_json(docs_dir / "run_status" / run_date / "cio_data_requests.json") or {}
    cio_runs = _read_jsonl(docs_dir / "run_status" / run_date / "cio_enrichment_runs.jsonl")
    provider_rows = "".join(
        "<tr>"
        f"<td>{_esc(row.get('provider') or '')}</td>"
        f"<td>{_esc(row.get('domain') or '')}</td>"
        f"<td>{_esc(row.get('operation') or '')}</td>"
        f"<td>{_esc(row.get('status') or '')}</td>"
        f"<td>{_esc(row.get('authState') or '')}</td>"
        f"<td>{_esc(row.get('recordCount') if row.get('recordCount') is not None else '')}</td>"
        f"<td>{_esc(row.get('errorType') or '')}</td>"
        f"<td>{_esc(row.get('fallbackTo') or '')}</td>"
        f"<td>{_esc(row.get('sourceTier') or '')}</td>"
        "</tr>"
        for row in provider_matrix
        if isinstance(row, dict)
    )
    domain_cards = "".join(
        "<article class='flow-card'>"
        f"<h3>{_esc(row.get('label') or key)}</h3>"
        f"<p>status={_esc(row.get('status') or '')} · coverage={_esc(row.get('coverage') or '')}</p>"
        f"<p class='muted'>{_esc('；'.join(row.get('blockers') or []))}</p>"
        "</article>"
        for key, row in domains.items()
        if isinstance(row, dict)
    )
    refs_html = "".join(f"<li>{_esc(key)}：{_esc(value)}</li>" for key, value in refs.items())
    matrix_html = _esc(json.dumps(run_matrix, ensure_ascii=False, indent=2))
    llm_rows = "".join(
        "<tr>"
        f"<td>{_esc(row.get('agent') or '')}</td>"
        f"<td>{_esc(row.get('status') or '')}</td>"
        f"<td>{_esc(row.get('backend') or '')}</td>"
        f"<td>{_esc(row.get('provider') or '')}</td>"
        f"<td>{_esc(row.get('model') or '')}</td>"
        f"<td>{_esc(row.get('attempt') or '')}</td>"
        f"<td>{_esc(row.get('durationSeconds') or '')}</td>"
        f"<td>{_esc((row.get('usage') or {}).get('total_tokens') if isinstance(row.get('usage'), dict) else '')}</td>"
        f"<td>{_esc(row.get('errorType') or '')}</td>"
        f"<td>{_esc(row.get('error') or '')}</td>"
        "</tr>"
        for row in llm_runs
        if isinstance(row, dict)
    )
    model_rows = "".join(
        "<tr>"
        f"<td>{_esc(row.get('model') or '')}</td>"
        f"<td>{_esc(row.get('status') or '')}</td>"
        f"<td>{_esc(row.get('durationSeconds') or '')}</td>"
        f"<td>{_esc(row.get('error') or '')}</td>"
        "</tr>"
        for row in (model_selection.get("candidates") or [])
        if isinstance(row, dict)
    )
    cio_request_rows = "".join(
        "<tr>"
        f"<td>{_esc(row.get('id') or '')}</td>"
        f"<td>{_esc(row.get('domain') or '')}</td>"
        f"<td>{_esc(row.get('symbol') or '')}</td>"
        f"<td>{_esc(row.get('reason') or '')}</td>"
        "</tr>"
        for row in (cio_requests.get("requests") or [])
        if isinstance(row, dict)
    )
    cio_run_rows = "".join(
        "<tr>"
        f"<td>{_esc(row.get('request_id') or '')}</td>"
        f"<td>{_esc(row.get('domain') or '')}</td>"
        f"<td>{_esc(row.get('symbol') or '')}</td>"
        f"<td>{_esc(row.get('success'))}</td>"
        f"<td>{_esc(row.get('record_count') if row.get('record_count') is not None else '')}</td>"
        f"<td>{_esc(row.get('error_type') or '')}</td>"
        "</tr>"
        for row in cio_runs
        if isinstance(row, dict)
    )
    body = f"""
<section class="card">
  <h2>{_esc(run_date)} 高级诊断</h2>
  <p class="muted">此页用于工程排障。默认报告页不展示这些字段。</p>
  <h3>Snapshot refs</h3>
  <ul>{refs_html or '<li>未提供</li>'}</ul>
</section>
<section class="card">
  <h2>Provider Matrix</h2>
  <div class="table-wrap"><table><thead><tr><th>Provider</th><th>Domain</th><th>Operation</th><th>Status</th><th>Auth</th><th>Records</th><th>Error</th><th>Fallback</th><th>Tier</th></tr></thead><tbody>{provider_rows}</tbody></table></div>
</section>
<section class="card">
  <h2>Domain Health</h2>
  <div class="flow-grid">{domain_cards or '<p class="muted">未提供</p>'}</div>
</section>
<section class="card">
  <h2>Agent Model Selection</h2>
  <p>selected={_esc(model_selection.get('selectedModel') or '')} · policy={_esc(model_selection.get('policy') or '')}</p>
  <div class="table-wrap"><table><thead><tr><th>Model</th><th>Status</th><th>Seconds</th><th>Error</th></tr></thead><tbody>{model_rows}</tbody></table></div>
</section>
<section class="card">
  <h2>LLM Agent Runs</h2>
  <div class="table-wrap"><table><thead><tr><th>Agent</th><th>Status</th><th>Backend</th><th>Provider</th><th>Model</th><th>Attempt</th><th>Seconds</th><th>Tokens</th><th>Error Type</th><th>Error</th></tr></thead><tbody>{llm_rows}</tbody></table></div>
</section>
<section class="card">
  <h2>CIO Enrichment</h2>
  <p>{_esc(json.dumps(cio_requests.get('summary') or artifact.get('cioEnrichment') or {}, ensure_ascii=False))}</p>
  <h3>Requests</h3>
  <div class="table-wrap"><table><thead><tr><th>ID</th><th>Domain</th><th>Symbol</th><th>Reason</th></tr></thead><tbody>{cio_request_rows}</tbody></table></div>
  <h3>Runs</h3>
  <div class="table-wrap"><table><thead><tr><th>Request</th><th>Domain</th><th>Symbol</th><th>Success</th><th>Records</th><th>Error</th></tr></thead><tbody>{cio_run_rows}</tbody></table></div>
</section>
<section class="card">
  <h2>Run Matrix</h2>
  <pre>{matrix_html}</pre>
</section>
"""
    return _html_page(f"{run_date} 高级诊断", body)


def _source_item(path: str, label: str) -> Dict[str, str]:
    return {"path": path, "label": label}


def _department_source_links(docs_dir: Path, sources: Iterable[Dict[str, str]]) -> str:
    items: List[str] = []
    for item in sources:
        path = str(item.get("path") or "").strip()
        label = str(item.get("label") or path or "来源详情").strip()
        if not path:
            continue
        if path.endswith(".json") or path.endswith(".jsonl"):
            continue
        exists = (docs_dir / path).exists()
        if exists:
            items.append(f"<li><a href='../../{_esc(path)}'>{_esc(label)}</a></li>")
        else:
            items.append(f"<li class='muted'>{_esc(label)}（本轮未生成）</li>")
    if not items:
        return "<p class='muted'>本轮没有可下钻的来源页。</p>"
    return f"<ul>{''.join(items)}</ul>"


def _department_decision_card(model: Dict[str, Any]) -> str:
    conclusion = _short_text(model.get("conclusion"), max_len=260)
    status = _short_text(model.get("status"), max_len=80)
    source = _short_text(model.get("source"), max_len=220)
    inference = _short_text(model.get("inference"), max_len=260)
    reasons = _html_list(model.get("reasons") or [], empty="本轮没有足够依据形成更细结论。")
    risks = _html_list(model.get("risks") or [], empty="本轮没有额外反证摘要。")
    next_steps = _html_list(model.get("next_steps") or [], empty="等待下一次数据刷新后复核。")
    inference_html = (
        f'<div class="flow-row"><span class="flow-label">推论</span>{_esc(inference)}</div>'
        if inference and inference != conclusion
        else ""
    )
    return f"""
<section class="card">
  <h2>本环节结论</h2>
  <p><span class="pill">{_esc(status)}</span></p>
  <div class="flow-row"><span class="flow-label">信息源</span>{_esc(source)}</div>
  <div class="flow-row"><span class="flow-label">分析结论</span>{_esc(conclusion)}</div>
  {inference_html}
  <div class="grid">
    <div><h3>核心依据</h3><ul>{reasons}</ul></div>
    <div><h3>风险和反证</h3><ul>{risks}</ul></div>
  </div>
  <div><h3>下一步</h3><ul>{next_steps}</ul></div>
</section>
"""


def _macro_section_model(docs_dir: Path, run_date: str, title: str, source_rel: str) -> Dict[str, Any]:
    ctx = _context(docs_dir, run_date)
    macro = ctx["macro"]
    inference, conclusion, next_step = _macro_reader_copy(macro)
    dimensions = macro.get("macro_dimensions") if isinstance(macro.get("macro_dimensions"), dict) else {}
    reasons = []
    risks = []
    for name, row in dimensions.items():
        if not isinstance(row, dict):
            continue
        evidence = _short_text(row.get("evidence"), max_len=180)
        status = _reader_status(row.get("status"))
        line = f"{name}：{status}；{evidence}" if evidence else f"{name}：{status}"
        if str(row.get("status") or "").lower() in {"missing", "degraded"}:
            risks.append(line)
        else:
            reasons.append(line)
    if macro.get("headline"):
        reasons.insert(0, _short_text(macro.get("headline"), max_len=180))
    if macro.get("data_gaps"):
        risks.extend(_as_text_list(macro.get("data_gaps"), limit=4))
    return {
        "title": title,
        "status": f"宏观状态：{_reader_status(macro.get('status'))}；置信度：{_reader_confidence_text(macro.get('confidence'))}",
        "source": "FRED 官方宏观序列、六因子状态、市场热度和只读概率校准",
        "conclusion": conclusion,
        "inference": inference,
        "reasons": reasons[:6],
        "risks": risks[:6],
        "next_steps": [next_step, "宏观只作为背景和风险温度输入，个股动作仍看个股证据和复核。"],
        "sources": [_source_item(source_rel, "宏观详情页"), _source_item(f"market_cycle/{run_date}/01_macro_review.json", "宏观机器快照")],
    }


def _market_section_model(docs_dir: Path, run_date: str, title: str, source_rel: str) -> Dict[str, Any]:
    ctx = _context(docs_dir, run_date)
    strategy = ctx["strategy"]
    queue = ctx["queue"]
    block = strategy.get("strategy") if isinstance(strategy.get("strategy"), dict) else {}
    headline = _first_nonempty(block.get("headline"), default="维持观察，等待价格和证据共振。")
    reasons = _as_text_list(block.get("actions"), limit=4)
    reasons.append(f"深评候选 {len(queue.get('candidates') or [])} 个；自动深评 {len(queue.get('auto_governed_candidates') or [])} 个。")
    reasons.extend(_top_candidates(queue)[:4])
    risks = _as_text_list(block.get("avoid"), limit=5)
    risks.append("热榜和候选池只代表发现线索，不能直接等同交易建议。")
    return {
        "title": title,
        "status": f"市场状态：{_reader_regime(strategy.get('regime'))}；置信度：{_reader_confidence_text(strategy.get('confidence'))}",
        "source": "宏观快照、市场热度、筛选漏斗、深评队列和市场策略总控",
        "conclusion": headline,
        "inference": "市场允许观察和候选发现；真正行动仍要等个股深评、红蓝反证、评分和最终复核。",
        "reasons": reasons[:7],
        "risks": risks[:6],
        "next_steps": ["把热度转成等待条件。", "候选先补公告、研报、技术承接；没有承接不追高。", "只有证据足够的标的进入个股深评。"],
        "sources": [
            _source_item(source_rel, "市场策略详情页"),
            _source_item(f"market_cycle/{run_date}/11_deep_review_queue.html", "深评队列"),
            _source_item(f"market_cycle/{run_date}/14_market_strategy.json", "市场策略快照"),
        ],
    }


def _official_event_summary(events: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    provider_labels = {
        "SEC_EDGAR": "SEC 法披",
        "CNINFO": "巨潮公告",
        "SSE_DISCLOSURE": "上交所公告",
        "SZSE_DISCLOSURE": "深交所公告",
        "HKEXNEWS": "港交所披露易",
        "GDELT": "全球新闻发现",
    }
    operation_labels = {
        "sec_submissions": "法披列表",
        "sec_companyfacts": "财务事实",
        "cninfo_announcements": "公司公告",
        "exchange_announcements": "交易所公告",
        "hkex_announcements": "港股公告",
        "gdelt_doc": "新闻发现",
    }
    runs = events.get("providerRuns") if isinstance(events.get("providerRuns"), list) else []
    facts = events.get("evidenceFacts") if isinstance(events.get("evidenceFacts"), list) else []
    success_runs = [row for row in runs if isinstance(row, dict) and row.get("success")]
    failed_runs = [row for row in runs if isinstance(row, dict) and not row.get("success")]
    reasons = [
        f"官方事件源成功 {len(success_runs)}/{len(runs)} 个；证据事实 {len(facts)} 条。",
        _join_items(
            [
                f"{provider_labels.get(str(row.get('provider')), str(row.get('provider') or '来源'))} {operation_labels.get(str(row.get('operation')), str(row.get('operation') or '检查'))} 记录 {row.get('record_count', 0)}"
                for row in success_runs[:5]
                if isinstance(row, dict)
            ],
            limit=5,
        ),
    ]
    for fact in facts[:5]:
        if isinstance(fact, dict):
            reasons.append(
                f"{provider_labels.get(str(fact.get('provider')), str(fact.get('provider') or '来源'))} · {fact.get('symbol')}：{_short_text(fact.get('value'), max_len=140)}"
            )
    risks = [
        f"{provider_labels.get(str(row.get('provider')), str(row.get('provider') or '来源'))}：{_reader_status(row.get('error_type') or 'failed')}"
        for row in failed_runs[:5]
        if isinstance(row, dict)
    ]
    if not risks:
        risks.append("新闻和搜索结果仍只能做发现线索，不能直接当已验证事实。")
    return reasons, risks


def _news_section_model(docs_dir: Path, run_date: str, title: str, source_rel: str) -> Dict[str, Any]:
    events = _read_json(docs_dir / "official_events" / f"{run_date}.json") or {}
    reasons, risks = _official_event_summary(events if isinstance(events, dict) else {})
    health = _context(docs_dir, run_date)["health"]
    stale = [
        str(row.get("component"))
        for row in (health.get("rows") or [])
        if isinstance(row, dict) and str(row.get("freshness_status") or "").lower() == "stale"
    ]
    if stale:
        risks.append(f"部分辅助情报已变旧：{_join_items(stale, limit=4)}。")
    return {
        "title": title,
        "status": "事件发现：可读；搜索和新闻只作线索",
        "source": "CNINFO、上交所/深交所、SEC、HKEX、GDELT/搜索发现、市场热度",
        "conclusion": "新闻情报本轮只能支撑事件发现；能进入事实层的，必须回到公告、法披、交易所或公司 IR。",
        "inference": "官方源验证后的事件可以进入证据池；搜索、GDELT、Tavily 和研报观点只提供线索与假设。",
        "reasons": reasons,
        "risks": risks,
        "next_steps": ["对候选标的回跳公告、SEC、HKEX、交易所或公司 IR。", "搜索线索必须二次验证后再进入评分。", "把可验证事件同步到个股深评和风险反证。"],
        "sources": [
            _source_item(source_rel, "市场热度页"),
            _source_item(f"official_events/{run_date}.json", "官方事件快照"),
        ],
    }


def _stocks_section_model(docs_dir: Path, run_date: str, title: str, source_rel: str) -> Dict[str, Any]:
    rows = _context(docs_dir, run_date)["governed_today"]
    if not rows:
        return {
            "title": title,
            "status": "个股深评：本轮未完成",
            "source": "个股深评、评分卡、红蓝反证和最终复核",
            "conclusion": "本轮没有完成个股深评，不能从候选池直接推出交易动作。",
            "inference": "候选仍是观察清单，缺少个股证据链和最终复核。",
            "reasons": [],
            "risks": ["没有完成深评的标的不能被包装成交易建议。"],
            "next_steps": ["先补个股公告、财务、估值、技术承接和反证，再重跑深评。"],
            "sources": [_source_item(source_rel, "个股报告")],
        }
    labels = _governed_labels(rows)
    blocked_count = sum(1 for row in rows if _is_blocked_governed(row))
    if blocked_count == len(rows):
        conclusion = "今日完成深评的标的全部暂停行动；不新增仓位。"
    else:
        conclusion = "今日存在可进入人工复核的个股候选，但仍需逐条核证据和风险。"
    reasons: List[str] = []
    risks: List[str] = []
    next_steps: List[str] = []
    for row in rows[:4]:
        reasons.extend(_stock_reasons(row)[:2])
        risks.extend(_stock_risks(row)[:2])
        next_steps.extend(_stock_next_steps(row)[:2])
    return {
        "title": title,
        "status": f"深评标的 {len(rows)} 个；暂停行动 {blocked_count} 个",
        "source": "行情、技术指标、基本面线索、红蓝反证、评分卡和最终复核",
        "conclusion": conclusion,
        "inference": "个股动作只看深评结果；候选和热榜不能替代个股复核。",
        "reasons": labels[:3] + list(dict.fromkeys(reasons))[:4],
        "risks": list(dict.fromkeys(risks))[:6],
        "next_steps": list(dict.fromkeys(next_steps))[:6],
        "sources": [_source_item(source_rel, "个股报告"), _source_item("governed_results.json", "个股深评快照")],
    }


def _portfolio_section_model(docs_dir: Path, run_date: str, title: str, source_rel: str) -> Dict[str, Any]:
    memo_rel = source_rel or f"agent_memos/{run_date}/market/05_portfolio_review.html"
    payload = _read_json(docs_dir / f"agent_memos/{run_date}/market/05_portfolio_review.json") or {}
    health = _context(docs_dir, run_date)["health"]
    holding_rows = [
        row
        for row in (health.get("rows") or [])
        if isinstance(row, dict) and str(row.get("component") or "") == "portfolio_holdings"
    ]
    holding = holding_rows[0] if holding_rows else {}
    facts = _as_text_list(payload.get("facts"), limit=5)
    if holding:
        facts.append(
            f"持仓源：{holding.get('holding_source') or '未标明'}；状态：{holding.get('holding_status') or holding.get('status') or '未知'}；入选 {holding.get('selected_count', 0)} 个。"
        )
    return {
        "title": title,
        "status": f"持仓复核：{_reader_status(payload.get('status') or holding.get('status'))}",
        "source": "持仓服务、源健康快照和个股深评结果",
        "conclusion": _first_nonempty(payload.get("conclusion"), default="本轮没有结构化持仓输入。"),
        "inference": _join_items(payload.get("reasoning") or ["没有持仓上下文时，系统只能做空仓/观察口径复核。"], limit=4),
        "reasons": facts,
        "risks": _as_text_list(payload.get("missing_data"), limit=5) or ["缺少持仓成本、当前价、浮盈亏和公告联动时，持仓页只能做轻量复核。"],
        "next_steps": [_first_nonempty(payload.get("next_step"), default="补持仓成本、当前价、浮盈亏和公告联动。")],
        "sources": [_source_item(memo_rel, "持仓复核详情页"), _source_item(f"market_cycle/{run_date}/13_source_health.json", "数据健康快照")],
    }


def _risk_section_model(docs_dir: Path, run_date: str, title: str, source_rel: str) -> Dict[str, Any]:
    ctx = _context(docs_dir, run_date)
    health = ctx["health"]
    governed_today = ctx["governed_today"]
    source_inference, source_conclusion, source_next = _source_health_reader_copy(health)
    rows = health.get("rows") if isinstance(health.get("rows"), list) else []
    stale_or_warn = [
        f"{row.get('component')}：{_reader_status(row.get('status'))}/{_reader_status(row.get('freshness_status'))}"
        for row in rows
        if isinstance(row, dict)
        and (
            str(row.get("freshness_status") or "").lower() == "stale"
            or str(row.get("blocking_level") or "").lower() not in {"", "none"}
        )
    ]
    blocked = [row for row in governed_today if _is_blocked_governed(row)]
    reasons = [
        f"源健康：{_reader_status(health.get('usability_verdict'))}；交易审查：{_reader_status(health.get('trade_review_usability'))}。",
        f"个股深评 {len(governed_today)} 个；暂停行动 {len(blocked)} 个。",
    ]
    risks = stale_or_warn[:5]
    for row in blocked[:3]:
        risks.append(f"{_first_nonempty(row.get('name'), row.get('code'))}：{_short_text(row.get('headline'), max_len=150)}")
    return {
        "title": title,
        "status": f"风险复核：{_reader_status(health.get('usability_verdict'))}",
        "source": _source_names(health),
        "conclusion": source_conclusion,
        "inference": source_inference,
        "reasons": reasons,
        "risks": risks,
        "next_steps": [source_next, "把暂停行动的个股先补证据，再重跑个股深评。"],
        "sources": [_source_item(source_rel, "数据健康详情页"), _source_item(f"market_cycle/{run_date}/13_source_health.json", "数据健康快照")],
    }


def _section_view_model(
    docs_dir: Path,
    run_date: str,
    *,
    slug: str,
    title: str,
    source_rel: str,
) -> Dict[str, Any]:
    department_model = _department_section_model(docs_dir, run_date, slug=slug, title=title, source_rel=source_rel)
    if department_model:
        return department_model
    if slug == "macro":
        return _macro_section_model(docs_dir, run_date, title, source_rel)
    if slug == "market":
        return _market_section_model(docs_dir, run_date, title, source_rel)
    if slug in {"sectors", "candidates"}:
        return _market_section_model(docs_dir, run_date, title, source_rel)
    if slug == "news":
        return _news_section_model(docs_dir, run_date, title, source_rel)
    if slug == "stocks":
        return _stocks_section_model(docs_dir, run_date, title, source_rel)
    if slug == "portfolio":
        return _portfolio_section_model(docs_dir, run_date, title, source_rel)
    if slug == "risk":
        return _risk_section_model(docs_dir, run_date, title, source_rel)
    return {
        "title": title,
        "status": "本轮已生成",
        "source": source_rel or "同一运行快照",
        "conclusion": "本板块已生成，但没有独立的读者版模型。",
        "inference": "请回到汇总报告阅读。",
        "reasons": [],
        "risks": [],
        "next_steps": ["返回汇总报告。"],
        "sources": [_source_item(source_rel, "来源详情页")],
    }


_SECTION_AGENT_GROUPS = {
    "macro": {"MacroAgent", "MacroGeopoliticsAgent", "宏观部门"},
    "geo": {"GeoPolicyAgent", "地缘政策部门"},
    "market": {"MarketAgent", "MarketStrategyAgent", "市场部门"},
    "sectors": {"SectorAgent", "CandidateReviewAgent", "行业/风格部门"},
    "candidates": {"SectorAgent", "CandidateReviewAgent", "行业/风格部门"},
    "news": {"IntelAgent", "IntelCatalystAgent", "新闻情报部门"},
    "stocks": {"FundamentalAgent", "FundamentalReportsAgent", "TechnicalAgent", "基本面部门", "技术面部门"},
    "portfolio": {"PortfolioAgent", "PortfolioReviewAgent", "持仓复核部门"},
    "risk": {"RiskAgent", "RiskPositionAgent", "RedTeamAgent", "RedBlueAgent", "风险部门", "红队反证"},
}


def _department_section_model(docs_dir: Path, run_date: str, *, slug: str, title: str, source_rel: str) -> Dict[str, Any] | None:
    artifact = _read_json(docs_dir / "reports" / f"{run_date}.artifact.json") or {}
    reader = artifact.get("readerV3") if isinstance(artifact.get("readerV3"), dict) else {}
    reader_cards = reader.get("departmentCards") if isinstance(reader.get("departmentCards"), list) else []
    reports = reader_cards or (
        artifact.get("departmentReports")
        if isinstance(artifact.get("departmentReports"), list)
        else []
    )
    agents = _SECTION_AGENT_GROUPS.get(slug) or set()
    rows = [
        row
        for row in reports
        if isinstance(row, dict) and str(row.get("agent") or "") in agents
    ]
    if not rows:
        return None
    conclusion = "；".join(
        _short_text(
            _sanitize_reader_markdown(
                str(row.get("conclusion") or row.get("summaryForReader") or "")
            ),
            max_len=220,
        )
        for row in rows[:2]
        if row.get("conclusion") or row.get("summaryForReader")
    ) or "本板块已完成分析，但未产出可读摘要。"
    reasons = _collect_department_items(rows, "keyClaims", fallback_key="evidenceIds", limit=5)
    risks = _collect_department_items(rows, "counterpoints", fallback_key="dataGaps", limit=5)
    if not risks:
        risks = _collect_department_items(rows, "dataGaps", limit=5)
    next_steps = [
        _sanitize_reader_markdown(str(row.get("nextAction") or ""))
        for row in rows
        if row.get("nextAction")
    ]
    evidence_samples = [
        sample
        for row in rows
        for sample in row.get("evidenceSamples") or []
        if isinstance(sample, dict)
    ][:8]
    return {
        "title": title,
        "status": "部门研究已完成",
        "source": "同一轮市场、公司与官方事件证据",
        "conclusion": conclusion,
        "inference": conclusion,
        "reasons": list(dict.fromkeys(reason for reason in reasons if reason))[:5],
        "risks": list(dict.fromkeys(risk for risk in risks if risk))[:5],
        "next_steps": list(dict.fromkeys(step for step in next_steps if step))[:4] or ["等待下一轮数据刷新后复核。"],
        "sources": [],
        "evidence_samples": evidence_samples,
    }


def _collect_department_items(
    rows: List[Dict[str, Any]],
    key: str,
    *,
    fallback_key: str = "",
    limit: int = 5,
) -> List[str]:
    items: List[str] = []
    for row in rows:
        values = row.get(key)
        if not values and fallback_key:
            values = row.get(fallback_key)
        if not isinstance(values, list):
            continue
        for value in values:
            text = _sanitize_reader_markdown(str(value or "").strip())
            if text:
                items.append(_short_text(text, max_len=180))
            if len(items) >= limit:
                return items
    return items


def build_section_report(
    docs_dir: Path,
    run_date: str,
    *,
    slug: str,
    title: str,
    source_rel: str,
    summary: str,
) -> str:
    model = _section_view_model(docs_dir, run_date, slug=slug, title=title, source_rel=source_rel)
    intro = _department_decision_card(model)
    evidence = _evidence_sample_bullets(model.get("evidence_samples") or [], limit=8)
    body = f"""
<section class="hero">
  <div><span class="pill">分部门报告</span><h1>{_esc(title)}</h1><p class="muted">{_esc(summary)}</p></div>
  <div class="kpi"><small>运行日期</small><b>{_esc(run_date)}</b><span>同一份报告数据</span></div>
</section>
{intro}
<section class="card">
  <h2>证据与来源</h2>
  <p>本页结论来自同一轮研究证据，不另起一套分析。公开页只展示可读证据摘要；维护诊断不随报告公开。</p>
  {evidence or '<p class="muted">本板块本轮没有独立可公开的证据样例；核心依据已列在上方。</p>'}
  <p class="muted"><a href="../{_esc(run_date)}.html">返回汇总报告</a></p>
</section>
"""
    return _html_page(f"{run_date} {title}", body)


def write_section_reports(docs_dir: Path, run_date: str) -> List[Tuple[str, str, str, str]]:
    compact = run_date.replace("-", "")
    agent_links = _agent_memo_links(docs_dir, run_date)
    specs = [
        ("macro", "宏观报告", f"market_cycle/{run_date}/01_macro_review.html", "宏观、利率和流动性背景。"),
        ("geo", "地缘政策报告", agent_links.get("geo") or "", "贸易、制裁、冲突、政策事件和市场传导。"),
        ("market", "市场 / 板块报告", f"market_cycle/{run_date}/14_market_strategy.html", "市场状态、候选队列和策略总控。"),
        ("sectors", "行业 / 风格报告", f"market_cycle/{run_date}/14_market_strategy.html", "行业强弱、风格切换和热点持续性。"),
        ("candidates", "候选观察报告", f"market_cycle/{run_date}/11_deep_review_queue.html", "候选池来源、等待条件和不追高边界。"),
        ("news", "新闻情报报告", "market_heat/latest_market_heat.html", "新闻发现、热度和事件线索。"),
        ("stocks", "个股深挖报告", f"report_{compact}.html", "个股深评、反证复核和行动状态。"),
        ("portfolio", "持仓复核报告", agent_links.get("portfolio") or "", "持仓影响和待复核事项。"),
        ("risk", "风险 / 反证报告", f"market_cycle/{run_date}/13_source_health.html", "待确认项、反证、暂停理由和修复方向。"),
    ]
    generated: List[Tuple[str, str, str, str]] = []
    for slug, title, source_rel, summary in specs:
        dst = docs_dir / "reports" / run_date / f"{slug}.html"
        dst.parent.mkdir(parents=True, exist_ok=True)
        html = build_section_report(
            docs_dir,
            run_date,
            slug=slug,
            title=title,
            source_rel=source_rel,
            summary=summary,
        )
        dst.write_text(html, encoding="utf-8")
        generated.append(("section", source_rel, dst.relative_to(docs_dir).as_posix(), title))
    return generated


def _system_status_table(docs_dir: Path, run_date: str) -> str:
    compact = run_date.replace("-", "")
    agent_links = _agent_memo_links(docs_dir, run_date)
    specs = [
        ("macro", "宏观", f"market_cycle/{run_date}/01_macro_review.html"),
        ("geo", "地缘政策", agent_links.get("geo") or ""),
        ("market", "市场 / 板块", f"market_cycle/{run_date}/14_market_strategy.html"),
        ("sectors", "行业 / 风格", f"market_cycle/{run_date}/14_market_strategy.html"),
        ("candidates", "候选观察", f"market_cycle/{run_date}/11_deep_review_queue.html"),
        ("news", "新闻情报", "market_heat/latest_market_heat.html"),
        ("stocks", "个股深挖", f"report_{compact}.html"),
        ("portfolio", "持仓复核", agent_links.get("portfolio") or ""),
        ("risk", "风险 / 反证", f"market_cycle/{run_date}/13_source_health.html"),
    ]
    rows: List[str] = []
    for slug, title, source_rel in specs:
        model = _section_view_model(docs_dir, run_date, slug=slug, title=title, source_rel=source_rel)
        risks = model.get("risks") or []
        next_steps = model.get("next_steps") or []
        missing = _short_text(risks[0] if risks else "无关键缺失", max_len=120)
        next_step = _short_text(next_steps[0] if next_steps else "等待下一轮复核", max_len=120)
        href = f"{run_date}/{slug}.html"
        rows.append(
            "<tr>"
            f"<td><a href='{_esc(href)}'>{_esc(title)}</a></td>"
            f"<td>{_esc(_short_text(model.get('conclusion'), max_len=150))}</td>"
            f"<td>{_esc(_sanitize_reader_markdown(missing))}</td>"
            f"<td>{_esc(_sanitize_reader_markdown(next_step))}</td>"
            "</tr>"
        )
    return f"""
<section class="card">
  <h2>各板块结论与下一步</h2>
  <div class="table-wrap">
    <table>
      <thead><tr><th>板块</th><th>当前结论</th><th>主要风险</th><th>下一步</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
  </div>
</section>
"""


def build_report_center(
    docs_dir: Path,
    run_date: str,
    generated: Iterable[Tuple[str, str, str, str]],
    *,
    artifact: Optional[Dict[str, Any]] = None,
) -> str:
    artifact = artifact or _read_json(docs_dir / "reports" / f"{run_date}.artifact.json") or {}
    reader_v3 = artifact.get("readerV3") if isinstance(artifact.get("readerV3"), dict) else {}
    legacy_header = ""
    if not reader_v3:
        source_health_v2 = artifact.get("sourceHealthV2") if isinstance(artifact.get("sourceHealthV2"), dict) else {}
        research_reliability = artifact.get("researchReliability") if isinstance(artifact.get("researchReliability"), dict) else {}
        mode_label = _reader_status(artifact.get("analysisMode") or source_health_v2.get("overallMode") or "OBSERVE_ONLY")
        confidence_label = str(
            research_reliability.get("label")
            or _reader_confidence(source_health_v2.get("overallScore"))
        )
        legacy_header = f"""
<section class="hero">
  <div><span class="pill">投研日报</span><h1>{_esc(run_date)} 投研报告</h1><p class="muted">先读总判断，再看依据、风险和下一步。</p></div>
  <div class="kpi"><small>本轮状态</small><b>{_esc(mode_label)}</b><span>{_esc(confidence_label)}</span></div>
</section>
"""
    output_body = f"""
{legacy_header}
{_artifact_contract_html(artifact)}

{_artifact_sections(docs_dir, run_date)}
"""
    return _html_page(f"{run_date} 投研报告中心", output_body)


def render_agent_memo_markdowns(docs_dir: Path, run_date: str) -> List[Tuple[str, str, str, str]]:
    base = docs_dir / "agent_memos" / run_date
    if not base.exists():
        return []
    generated: List[Tuple[str, str, str, str]] = []
    for src in sorted(base.rglob("*.md")):
        dst = src.with_suffix(".html")
        rel_src = src.relative_to(docs_dir).as_posix()
        rel_dst = dst.relative_to(docs_dir).as_posix()
        title = src.stem.replace("_", " ")
        intro = _agent_memo_intro(src)
        if render_markdown_file(src, dst, title, intro_html=intro, raw_summary="查看模块记录"):
            generated.append(("agent_memo", rel_src, rel_dst, title))
    return generated


def render_all(docs_dir: Path, run_date: str) -> List[Tuple[str, str, str, str]]:
    generated: List[Tuple[str, str, str, str]] = []
    artifact = write_daily_report_artifact(docs_dir, run_date)
    generated.append(("artifact", "", f"reports/{run_date}.artifact.json", "报告 JSON"))
    for category, src_rel, dst_rel, title in _report_specs(run_date):
        src = docs_dir / src_rel
        dst = docs_dir / dst_rel
        intro = _report_intro(docs_dir, run_date, dst_rel, title)
        raw_summary = "查看分析记录" if category == "stock" else "查看模块正文"
        if render_markdown_file(src, dst, title, intro_html=intro, raw_summary=raw_summary):
            generated.append((category, src_rel, dst_rel, title))
            if dst_rel.endswith("/summary.html"):
                legacy = dst.with_name("run_status.html")
                legacy.write_text(dst.read_text(encoding="utf-8"), encoding="utf-8")
                generated.append((category, src_rel, legacy.relative_to(docs_dir).as_posix(), "运行状态（兼容）"))
    generated.extend(render_agent_memo_markdowns(docs_dir, run_date))
    generated.extend(write_section_reports(docs_dir, run_date))

    center = build_report_center(docs_dir, run_date, generated, artifact=artifact)
    center_path = docs_dir / "reports" / f"{run_date}.html"
    center_path.parent.mkdir(parents=True, exist_ok=True)
    center_path.write_text(center, encoding="utf-8")
    generated.append(("center", "", f"reports/{run_date}.html", "报告中心"))
    diagnostics_path = docs_dir / "reports" / f"{run_date}.diagnostics.html"
    diagnostics_path.write_text(build_report_diagnostics(docs_dir, run_date, artifact), encoding="utf-8")
    generated.append(("diagnostics", "", f"reports/{run_date}.diagnostics.html", "高级诊断"))
    return generated


def _resolve_date(value: str) -> str:
    return resolve_analysis_run_date(value or None)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Render published report Markdown as Pages HTML")
    parser.add_argument("--date", default="", help="Run date YYYY-MM-DD")
    parser.add_argument("--docs-dir", default="docs")
    args = parser.parse_args(argv)

    run_date = _resolve_date(args.date)
    docs_dir = Path(args.docs_dir)
    generated = render_all(docs_dir, run_date)
    print(f"render_report_html: generated {len(generated)} HTML files for {run_date}")
    for _category, _src, dst, title in generated:
        print(f"- {dst}: {title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
