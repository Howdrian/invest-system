# -*- coding: utf-8 -*-
"""Render published Markdown/JSON report artifacts into human-readable HTML.

This is a Pages presentation layer only.  It does not run analysis and does not
touch the Web dashboard app.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.report_artifact import write_daily_report_artifact


CSS = """<style>
:root{--bg:#0b1020;--card:#121a2b;--line:#26344f;--text:#edf2ff;--muted:#9aa8c7;--accent:#7dd3fc;--red:#fb7185;--yellow:#facc15;--green:#86efac}
*{box-sizing:border-box}body{margin:0;background:linear-gradient(135deg,#08101f,#111827);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.65}
main{max-width:1120px;margin:0 auto;padding:28px}a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
h1{font-size:32px;margin:.2em 0 .4em}h2{font-size:23px;margin:1.1em 0 .5em;color:#cfe0ff}h3{font-size:18px;margin:1em 0 .35em;color:#dbeafe}
.hero,.card,.flow-card{border:1px solid var(--line);background:rgba(18,26,43,.94);border-radius:22px;padding:20px;margin:16px 0}.hero{display:grid;grid-template-columns:1.4fr 1fr 1fr;gap:16px}
.muted,small{color:var(--muted)}.kpi{border-left:1px solid var(--line);padding-left:16px}.kpi b{display:block;font-size:24px;color:var(--accent)}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.grid3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.pill{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:3px 10px;margin:2px 4px 2px 0;font-size:12px;color:#dbeafe;background:#0f172a}
.flow-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.flow-card{margin:0}.flow-card h3{margin-top:0}.flow-row{border-top:1px solid #22304a;padding:10px 0}.flow-row:first-of-type{border-top:0}.flow-label{display:block;color:#9db2d5;font-size:12px;letter-spacing:.08em;text-transform:uppercase;margin-bottom:4px}.raw-report{opacity:.92}.raw-report h1:first-child{font-size:24px}
.warn{color:var(--yellow)}.bad{color:var(--red)}.good{color:var(--green)}
table{width:100%;border-collapse:collapse;margin:12px 0}th,td{border-bottom:1px solid #23304a;padding:9px;text-align:left;vertical-align:top}th{color:#9db2d5;font-size:12px;text-transform:uppercase}
blockquote{border-left:4px solid var(--accent);margin:12px 0;padding:8px 14px;background:#0f172a;color:#dbeafe}
code{background:#0f172a;border:1px solid #1f2a44;border-radius:5px;padding:1px 5px}pre{overflow:auto;background:#0f172a;border:1px solid #1f2a44;border-radius:12px;padding:14px}
ul,ol{padding-left:24px}.toc a{display:inline-block;margin:4px 8px 4px 0;padding:6px 10px;border:1px solid var(--line);border-radius:9px;background:#0f172a}
.footer{margin-top:28px;color:var(--muted);font-size:13px}
@media(max-width:900px){.hero,.grid,.grid3,.flow-grid{grid-template-columns:1fr}.kpi{border-left:0;padding-left:0}}
</style>"""


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _inline_md(text: str) -> str:
    escaped = _esc(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', escaped)
    return escaped


def markdown_to_html(markdown: str) -> str:
    """Small deterministic Markdown renderer for report artifacts.

    Covers the report subset we generate: headings, bullets, blockquotes,
    fenced code, simple pipe tables and paragraphs.
    """
    lines = markdown.splitlines()
    parts: List[str] = []
    in_list = False
    in_code = False
    code_lines: List[str] = []
    i = 0

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            parts.append("</ul>")
            in_list = False

    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code:
                parts.append(f"<pre><code>{_esc(chr(10).join(code_lines))}</code></pre>")
                code_lines = []
                in_code = False
            else:
                close_list()
                in_code = True
            i += 1
            continue
        if in_code:
            code_lines.append(raw)
            i += 1
            continue

        if not stripped:
            close_list()
            i += 1
            continue

        if stripped.startswith("|") and i + 1 < len(lines) and _is_table_separator(lines[i + 1]):
            close_list()
            header = _split_table_row(stripped)
            i += 2
            rows: List[List[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(_split_table_row(lines[i].strip()))
                i += 1
            head = "".join(f"<th>{_inline_md(cell)}</th>" for cell in header)
            body = "".join(
                "<tr>" + "".join(f"<td>{_inline_md(cell)}</td>" for cell in row) + "</tr>"
                for row in rows
            )
            parts.append(f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")
            continue

        if stripped.startswith("#"):
            close_list()
            level = min(len(stripped) - len(stripped.lstrip("#")), 4)
            text = stripped[level:].strip()
            parts.append(f"<h{level}>{_inline_md(text)}</h{level}>")
        elif stripped.startswith(">"):
            close_list()
            parts.append(f"<blockquote>{_inline_md(stripped.lstrip('>').strip())}</blockquote>")
        elif stripped.startswith(("- ", "* ")):
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{_inline_md(stripped[2:].strip())}</li>")
        elif re.match(r"^\d+\.\s+", stripped):
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{_inline_md(re.sub(r'^\\d+\\.\\s+', '', stripped))}</li>")
        else:
            close_list()
            parts.append(f"<p>{_inline_md(stripped)}</p>")
        i += 1

    close_list()
    if in_code:
        parts.append(f"<pre><code>{_esc(chr(10).join(code_lines))}</code></pre>")
    return "\n".join(parts)


def _is_table_separator(line: str) -> bool:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells)


def _split_table_row(line: str) -> List[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _html_page(title: str, body: str, *, subtitle: str = "") -> str:
    sub = f"<p class='muted'>{_esc(subtitle)}</p>" if subtitle else ""
    return (
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{_esc(title)}</title>{CSS}</head><body><main>"
        f"{sub}{body}<p class='footer'>Generated by invest-system · report-only · no trade execution</p>"
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
    return f"""
<article class="flow-card">
  <h3>{heading}</h3>
  <div class="flow-row"><span class="flow-label">信息源</span>{_esc(source)}</div>
  <div class="flow-row"><span class="flow-label">关键数据</span>{_esc(facts)}</div>
  <div class="flow-row"><span class="flow-label">推论</span>{_esc(inference)}</div>
  <div class="flow-row"><span class="flow-label">分析结论</span>{_esc(conclusion)}</div>
  <div class="flow-row"><span class="flow-label">下一步</span>{_esc(next_step)}</div>
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
        target = ((row.get("trade_plan") or {}).get("target_pct") if isinstance(row.get("trade_plan"), dict) else "")
        blocked = _is_blocked_governed(row)
        if blocked:
            decision = "阻断 / 不操作 / 0%"
            gate_label = "门控=已阻断"
        else:
            decision = _human_action(action)
            gate_label = "门控=待复核"
        labels.append(
            f"{name or code}({code})：{decision}，{gate_label}，评分={_format_score(row.get('score'))}，仓位={target}%"
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
    text = re.sub(r"(?<![A-Za-z0-9])N/A(?![A-Za-z0-9])", "未提供", text)
    text = text.replace("原始报告（审计原文）", "模块正文")
    text = text.replace("BLOCKED_BY_FATAL", "治理层阻断")
    text = text.replace("no_action", "不操作")
    text = text.replace("RAW_AGENT", "真实 Agent")
    text = text.replace("DERIVED_FROM_ARTIFACT", "回填审计")
    text = text.replace("MISSING agent", "未运行 Agent")
    return _sanitize_blocked_trade_phrases(text)


def _sanitize_stock_report_markdown(markdown: str) -> str:
    """Remove misleading legacy governed wording from published stock reports."""
    text = _sanitize_reader_markdown(markdown)
    text = re.sub(r"治理层阻断 \| 评分\s+50\b", "治理层阻断 | 评分 0.5/10", text)
    text = re.sub(r"评分\s+50\b", "评分 0.5/10", text)
    text = text.replace("观望 — 治理层阻断", "阻断 / 不操作 / 0% — 治理层阻断")
    text = text.replace("**⚪ 观望** |", "**⛔ 阻断 / 不操作 / 0%** |")
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
            f"宏观状态={_first_nonempty(macro.get('status'))}",
            f"置信度={_first_nonempty(macro.get('confidence'))}",
            macro_headline,
            f"六因子缺项={_join_items(six_factor.get('missing_factors') or [], limit=5)}",
            f"数据缺口={_join_items(macro.get('data_gaps') or [], limit=5)}",
        ],
        limit=5,
    )

    source_facts = _join_items(
        [
            f"总可用性={_first_nonempty(health.get('usability_verdict'))}",
            f"交易审查={_first_nonempty(health.get('trade_review_usability'))}",
            f"宏观源={_first_nonempty(health.get('macro_status'))}",
            f"组件={_source_names(health)}",
        ],
        limit=4,
    )

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
            f"Regime={_first_nonempty(strategy.get('regime'))}",
            f"置信度={_first_nonempty(strategy.get('confidence'))}",
            _first_nonempty(strategy_block.get("headline"), default=""),
            f"应做={_join_items(strategy_block.get('actions') or [], limit=3)}",
            f"避免={_join_items(strategy_block.get('avoid') or [], limit=3)}",
        ],
        limit=5,
    )

    stock_facts = _join_items(_governed_labels(governed_today), limit=4)

    cards = [
        _flow_card(
            "宏观与地缘",
            href=f"{link_prefix}market_cycle/{run_date}/01_macro_review.html" if link_prefix else "",
            source="官方宏观入口 + 六因子 regime + Polymarket 只读概率 + 市场热度摘要",
            facts=macro_facts,
            inference="宏观不满血：只能判断风险温度和候选优先级，不能把 DEGRADED 当成完整宏观结论。",
            conclusion="当前是中性观察，不支持放大风险暴露；宏观只做背景约束。",
            next_step="补齐 FMP/官方扩展源后再判断增长、通胀、信用、美元和能源链条。",
        ),
        _flow_card(
            "数据源健康",
            href=f"{link_prefix}market_cycle/{run_date}/13_source_health.html" if link_prefix else "",
            source=_source_names(health),
            facts=source_facts,
            inference="critical 宏观源降级，但没有 critical unavailable；日报可读，交易审查只能 limited。",
            conclusion="可以做观察和候选筛选；不该把这轮报告当满血交易依据。",
            next_step="优先修宏观源、官方扩展源和持仓复核人类报告；宏观只可背景参考，不是满血 regime。",
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
            conclusion="NEUTRAL_WATCH：维持观察，等待价格和证据共振。",
            next_step="把热度转成等待条件；只让证据足够的标的进入 governed。",
        ),
        _flow_card(
            "个股 Governed",
            href=f"{link_prefix}report_{run_date.replace('-', '')}.html" if link_prefix else "",
            source="技术面 + 基本面估值 + 红蓝对抗 + 评分卡 + CIO gate",
            facts=stock_facts,
            inference="301013 的技术强势被基本面亏损、PB 高、乖离过高和红队 fatal 风险抵消。",
            conclusion="阻断 / 不操作 / 0%。CIO gate 已阻断：最终动作不操作，目标仓位 0%。",
            next_step="不执行交易；如需复盘，只补公告、业绩、催化剂和估值证据后重新审。",
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
        return _flow_card(
            f"阅读摘要：{title}",
            source="官方宏观入口 + 六因子 regime + Polymarket 只读概率",
            facts=_join_items(
                [
                    f"状态={_first_nonempty(macro.get('status'))}",
                    f"置信={_first_nonempty(macro.get('confidence'))}",
                    _first_nonempty(macro.get("headline")),
                ]
            ),
            inference="宏观不满血：缺增长、通胀、信用/轮动等关键因子，只能给风险温度。",
            conclusion="宏观中性观察；不作为买卖触发器。",
            next_step="补宏观源，再让 MacroAgent 读取完整 macro review。",
        )
    if dst_rel.endswith("13_source_health.html"):
        return _flow_card(
            f"阅读摘要：{title}",
            source=_source_names(health),
            facts=f"源健康={_first_nonempty(health.get('usability_verdict'))}；交易审查={_first_nonempty(health.get('trade_review_usability'))}",
            inference="critical 宏观源降级，系统只能 limited 使用。",
            conclusion="可生成日报；不可冒充满血投研。",
            next_step="先修宏观源和缺口，再提高分析深度。",
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
            facts=f"Regime={_first_nonempty(strategy.get('regime'))}；置信={_first_nonempty(strategy.get('confidence'))}；{_first_nonempty(strategy_block.get('headline'))}",
            inference="允许观察，不等于允许交易。",
            conclusion="维持观察，等待价格和证据共振。",
            next_step="把热度转成等待条件，保留 CIO/评分硬门控。",
        )
    if dst_rel == f"report_{compact}.html":
        return _flow_card(
            f"阅读摘要：{title}",
            source="governed_results + 评分卡 + CIO gate",
            facts=_join_items(_governed_labels(governed_today), limit=4),
            inference="技术强势没有穿透治理层；红队 fatal 和低分压倒蓝队。",
            conclusion="阻断 / 不操作 / 0%。最终动作不操作；目标仓位 0%。",
            next_step="不交易；补证据后重新审。",
        )
    if dst_rel.endswith(f"daily/{run_date}.html"):
        return _flow_card(
            f"阅读摘要：{title}",
            source="GitHub Actions 运行状态 + 已发布报告链接",
            facts=f"宏观={_first_nonempty(macro.get('status'))}；源健康={_first_nonempty(health.get('usability_verdict'))}；governed={len(governed_today)}",
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
) -> bool:
    if not src.exists():
        return False
    body = intro_html
    if intro_html:
        body += "<details class='card raw-report'><summary>查看模块正文</summary>"
    original_markdown = _read_text(src)
    markdown = original_markdown
    if src.name.startswith("report_"):
        markdown = _sanitize_stock_report_markdown(markdown)
    else:
        markdown = _sanitize_reader_markdown(markdown)
    if markdown != original_markdown:
        src.write_text(markdown, encoding="utf-8")
    body += markdown_to_html(markdown)
    if intro_html:
        body += "</details>"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(_html_page(title or src.stem, body, subtitle=str(src)), encoding="utf-8")
    return True


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
    return {
        "overview": f"agent_memos/{run_date}/index.html",
        "macro": f"agent_memos/{run_date}/market/02_macro_geopolitics.html",
        "sources": f"agent_memos/{run_date}/sources/01_source_gap_plan.html",
        "candidates": f"agent_memos/{run_date}/market/04_candidate_review.html",
        "portfolio": f"agent_memos/{run_date}/market/05_portfolio_review.html",
        "stock": f"agent_memos/{run_date}/stocks/{first_stock}/11_decision_report.html" if first_stock else "",
        "evidence": f"agent_memos/{run_date}/stocks/{first_stock}/00_context_pack.html" if first_stock else f"agent_memos/{run_date}/sources/00_source_inventory.html",
        "source_review": f"agent_memos/{run_date}/market/01_source_review.html",
    }


def _artifact_sections(docs_dir: Path, run_date: str) -> str:
    links = _agent_memo_links(docs_dir, run_date)

    def card(title: str, key: str, note: str) -> str:
        href = links.get(key) or ""
        exists = bool(href) and (docs_dir / href).exists()
        title_html = f"<a href='{_esc(_relative_from_report_center(href))}'>{_esc(title)}</a>" if exists else _esc(title)
        state = "已生成" if exists else "待生成"
        return f"<article class='flow-card'><h3>{title_html}</h3><p>{_esc(note)}</p><span class='pill'>{state}</span></article>"

    origin_counts = _agent_origin_counts(docs_dir, run_date)
    origin_note = (
        f"真实 Agent={origin_counts.get('RAW_AGENT', 0)}；"
        f"回填={origin_counts.get('DERIVED_FROM_ARTIFACT', 0)}；"
        f"缺失={origin_counts.get('MISSING', 0)}。"
    )
    return f"""
<section class="card">
  <h2>统一 ReportArtifact 报告入口</h2>
  <p class="muted">docs 和 Web 共享同一份 artifact：数据源 → 关键数据 → 推论 → 总结论 → 下一步。</p>
  <div class="flow-grid">
    {card("数据源", "source_review", "按来源解释今天用了什么、坏了什么、影响什么。")}
    {card("关键数据", "overview", "保留能支撑判断的核心事实，避免堆工程字段。")}
    {card("推论", "macro", "宏观、地缘、热度和个股证据如何推到结论。")}
    {card("总结论", "stock", "展示门控后的行动、评分和阻断原因。")}
    {card("下一步", "candidates", "为什么入池、为什么等待、谁需要补证据。")}
    {card("持仓复核", "portfolio", "持仓轻量复核；异常才进入 governed。")}
    {card("Agent 来源", "source_review", origin_note)}
    {card("证据链", "evidence", "ContextPack、source refs、missing data、fatal objection、JSON 下载。")}
  </div>
  <p class="muted">源健康总审：<a href="{_esc(_relative_from_report_center(links['source_review']))}">SourceReviewAgent memo</a></p>
</section>
"""


def _artifact_contract_html(artifact: Dict[str, Any]) -> str:
    summary = artifact.get("summary") if isinstance(artifact.get("summary"), dict) else {}
    source_health = artifact.get("sourceHealth") if isinstance(artifact.get("sourceHealth"), dict) else {}
    agent_origins = artifact.get("agentOrigins") if isinstance(artifact.get("agentOrigins"), dict) else {}
    decision = artifact.get("decision") if isinstance(artifact.get("decision"), dict) else {}
    sections = artifact.get("sections") if isinstance(artifact.get("sections"), list) else []

    source_note = str(source_health.get("decisionImpact") or "")
    if not source_note and str(source_health.get("verdict") or "").lower().endswith("limited"):
        source_note = "数据源降级，可观察，不可作为满血交易依据"
    key_facts = "".join(f"<li>{_esc(item)}</li>" for item in summary.get("keyFacts") or [])
    next_steps = "".join(f"<li>{_esc(item)}</li>" for item in summary.get("nextSteps") or [])
    section_cards = []
    for section in sections:
        if not isinstance(section, dict) or section.get("kind") == "raw":
            continue
        content = markdown_to_html(str(section.get("contentMarkdown") or "未提供"))
        section_cards.append(
            "<article class='flow-card'>"
            f"<h3>{_esc(str(section.get('title') or section.get('key') or '未命名'))}</h3>"
            f"{content}"
            "</article>"
        )
    source_warning = (
        f"<p class='warn'>{_esc(source_note)}</p>"
        if source_note and source_note != "数据源可用于常规审查"
        else f"<p class='good'>{_esc(source_note or '数据源状态未标明。')}</p>"
    )
    action_label = _human_action(decision.get("action"))
    gate_label = "已阻断" if decision.get("gateStatus") == "blocked" else ("等待观察" if decision.get("gateStatus") == "watch" else "门控通过")
    return f"""
<section class="card">
  <h2>标准报告数据包</h2>
  <p><span class="pill">artifact</span>{_esc(artifact.get('artifactId') or '')} <span class="pill">type</span>{_esc(artifact.get('artifactType') or '')}</p>
  <p>{_esc(summary.get('oneLine') or '未提供')}</p>
  {source_warning}
  <div class="grid3">
    <div><h3>门控</h3><p>动作：{_esc(action_label)}；状态：{_esc(gate_label)}；评分：{_esc(decision.get('score') if decision.get('score') is not None else '未提供')}</p></div>
    <div><h3>数据源</h3><p>状态：{_esc(source_health.get('status') or '未提供')}；交易审查：{_esc(source_health.get('verdict') or '未提供')}</p></div>
    <div><h3>Agent 来源</h3><p>真实：{_esc(agent_origins.get('raw', 0))}；回填：{_esc(agent_origins.get('derived', 0))}；缺失：{_esc(agent_origins.get('missing', 0))}</p></div>
  </div>
  <div class="grid">
    <div><h3>关键事实</h3><ul>{key_facts or '<li>未提供</li>'}</ul></div>
    <div><h3>下一步</h3><ul>{next_steps or '<li>未提供</li>'}</ul></div>
  </div>
  <div class="flow-grid">{''.join(section_cards)}</div>
</section>
"""


def build_report_center(
    docs_dir: Path,
    run_date: str,
    generated: Iterable[Tuple[str, str, str, str]],
    *,
    artifact: Optional[Dict[str, Any]] = None,
) -> str:
    compact = run_date.replace("-", "")
    health = _read_json(docs_dir / "market_cycle" / run_date / "13_source_health.json") or {}
    macro = _read_json(docs_dir / "market_cycle" / run_date / "01_macro_review.json") or {}
    queue = _read_json(docs_dir / "market_cycle" / run_date / "11_deep_review_queue.json") or {}
    strategy = _read_json(docs_dir / "market_cycle" / run_date / "14_market_strategy.json") or {}
    governed = _read_json(docs_dir / "governed_results.json")
    governed_rows = governed if isinstance(governed, list) else []
    governed_today = [row for row in governed_rows if str(row.get("run_date") or "") == run_date]
    governed_symbols = [
        str(row.get("code") or row.get("symbol") or "").strip()
        for row in governed_today
        if str(row.get("code") or row.get("symbol") or "").strip()
    ]

    generated_map = {dst: (category, src, title) for category, src, dst, title in generated}
    specs = _report_specs(run_date)

    human_links: Dict[str, List[str]] = {"daily": [], "market": [], "heat": [], "stock": [], "audit": []}
    for category, _src, dst, title in specs:
        exists = dst in generated_map or (docs_dir / dst).exists()
        note = "人类可读 HTML" if exists else "未生成"
        human_links.setdefault(category, []).append(_link(dst, title, exists, note=note))

    json_links = [
        _link(f"market_cycle/{run_date}/01_macro_review.json", "宏观 JSON", (docs_dir / "market_cycle" / run_date / "01_macro_review.json").exists(), note="机器可读"),
        _link(f"market_cycle/{run_date}/13_source_health.json", "源健康 JSON", (docs_dir / "market_cycle" / run_date / "13_source_health.json").exists(), note="机器可读"),
        _link(f"market_cycle/{run_date}/14_market_strategy.json", "策略 JSON", (docs_dir / "market_cycle" / run_date / "14_market_strategy.json").exists(), note="机器可读"),
        _link(f"governed_results.json", "governed_results.json", (docs_dir / "governed_results.json").exists(), note="机器可读；不作为主阅读入口"),
    ]

    macro_status = macro.get("status") or health.get("macro_status") or "unknown"
    source_status = health.get("usability_verdict") or "unknown"
    trade_status = health.get("trade_review_usability") or "unknown"
    regime = strategy.get("regime") or "unknown"
    candidate_count = len(queue.get("candidates") or [])
    auto_governed_count = len(queue.get("auto_governed_candidates") or [])

    readable_count = sum(1 for _category, _src, dst, _title in specs if (docs_dir / dst).exists())
    quality_flags: List[str] = []
    if str(macro_status).upper() == "DEGRADED":
        quality_flags.append("宏观降级：宏观/地缘结论只能作为背景参考，不应当单独驱动个股交易。")
    if source_status != "usable":
        quality_flags.append("源健康非满血：需要优先看数据源健康页确认缺口。")
    if candidate_count and auto_governed_count == 0:
        quality_flags.append("候选池未自动进入 governed：筛选结果仍是观察，不是交易建议。")
    if not governed_today:
        quality_flags.append("今日没有 completed governed 个股报告。")

    artifact = artifact or _read_json(docs_dir / "reports" / f"{run_date}.artifact.json") or {}
    output_body = f"""
<section class="hero">
  <div><span class="pill">报告中心</span><h1>{_esc(run_date)} 投研报告</h1><p class="muted">Web/App 与 docs 共享 ReportArtifact 口径；HTML 是阅读入口，JSON 只做追溯下载。</p></div>
  <div class="kpi"><small>人类可读 HTML</small><b>{readable_count}</b><span>本页已生成的报告页数</span></div>
  <div class="kpi"><small>运行状态</small><b>{_esc(source_status)}</b><span>trade={_esc(trade_status)}</span></div>
</section>

{_reading_digest(docs_dir, run_date, link_prefix='../')}

{_artifact_contract_html(artifact)}

{_artifact_sections(docs_dir, run_date)}

<section class="card">
  <h2>第一部分：报告产出</h2>
  <div class="grid">
    <div><h3>云端报告</h3><p>当前 Pages 展示的是发布到 <code>docs/</code> 的报告产物。</p><p class="good">本轮已有报告已转成 HTML/Markdown/JSON 入口。</p></div>
    <div><h3>本地报告</h3><p class="warn">Pages 不展示本地 live 目录；以 <code>docs/</code> 发布物为准。</p><p>本地 <code>reports/</code> 仅是运行中间产物目录，不作为 Pages 主入口。</p></div>
  </div>
  <h3>人类可读报告</h3>
  <div class="grid3">
    <div><h3>入口 / 日报</h3><ul>{''.join(human_links.get('daily', []))}</ul></div>
    <div><h3>大盘 / 策略</h3><ul>{''.join(human_links.get('market', []))}</ul></div>
    <div><h3>热度 / 个股 / 审计</h3><ul>{''.join(human_links.get('heat', []) + human_links.get('stock', []) + human_links.get('audit', []))}</ul></div>
  </div>
  <h3>机器可读产物</h3>
  <ul>{''.join(json_links)}</ul>
</section>

<section class="card">
  <h2>报告质量状态</h2>
  <p><span class="pill">Macro</span>{_esc(macro_status)} <span class="pill">Regime</span>{_esc(regime)} <span class="pill">Candidates</span>{candidate_count} <span class="pill">Auto governed</span>{auto_governed_count} <span class="pill">Governed done</span>{len(governed_today)}</p>
  <p>今日 governed 标的：{_esc(', '.join(governed_symbols) if governed_symbols else 'none')}</p>
  <ul>{''.join(f'<li>{_esc(flag)}</li>' for flag in quality_flags) or '<li class="good">未发现阻断性质量提示。</li>'}</ul>
</section>

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
        if render_markdown_file(src, dst, title):
            generated.append(("agent_memo", rel_src, rel_dst, title))
    return generated


def render_all(docs_dir: Path, run_date: str) -> List[Tuple[str, str, str, str]]:
    generated: List[Tuple[str, str, str, str]] = []
    artifact = write_daily_report_artifact(docs_dir, run_date)
    generated.append(("artifact", "", f"reports/{run_date}.artifact.json", "ReportArtifact JSON"))
    for category, src_rel, dst_rel, title in _report_specs(run_date):
        src = docs_dir / src_rel
        dst = docs_dir / dst_rel
        intro = _report_intro(docs_dir, run_date, dst_rel, title)
        if render_markdown_file(src, dst, title, intro_html=intro):
            generated.append((category, src_rel, dst_rel, title))
            if dst_rel.endswith("/summary.html"):
                legacy = dst.with_name("run_status.html")
                legacy.write_text(dst.read_text(encoding="utf-8"), encoding="utf-8")
                generated.append((category, src_rel, legacy.relative_to(docs_dir).as_posix(), "运行状态（兼容）"))
    generated.extend(render_agent_memo_markdowns(docs_dir, run_date))

    center = build_report_center(docs_dir, run_date, generated, artifact=artifact)
    center_path = docs_dir / "reports" / f"{run_date}.html"
    center_path.parent.mkdir(parents=True, exist_ok=True)
    center_path.write_text(center, encoding="utf-8")
    generated.append(("center", "", f"reports/{run_date}.html", "报告中心"))
    return generated


def _resolve_date(value: str) -> str:
    return value or datetime.now().strftime("%Y-%m-%d")


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
