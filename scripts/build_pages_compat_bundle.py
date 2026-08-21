#!/usr/bin/env python3
"""Build legacy-compatible Pages entries from the current report bundle.

The product report now lives under ``docs/reports/{date}*``.  The static Pages
validator and old homepage still expect a small ``daily/`` and
``market_cycle/`` bundle.  This script creates that compatibility bundle from
the real run status, evidence, and report artifacts.  It does not fetch data
and does not change analysis results.
"""

from __future__ import annotations

import argparse
import html
import json
import shutil
from pathlib import Path
from typing import Any, Mapping


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Pages compatibility bundle")
    parser.add_argument("--date", required=True)
    parser.add_argument("--docs-dir", default="docs")
    parser.add_argument("--runtime-reports-dir", default="reports")
    args = parser.parse_args(argv)

    docs = Path(args.docs_dir)
    runtime_reports = Path(args.runtime_reports_dir)
    run_date = args.date
    compact = run_date.replace("-", "")

    artifact = _read_json(docs / "reports" / f"{run_date}.artifact.json")
    health = _read_json(docs / "run_status" / run_date / "source_health_v2.json")
    universe = _read_json(docs / "run_status" / run_date / "daily_universe.json")
    macro_context = _read_json(docs.parent / "data" / "macro_cache" / "macro_context_latest.json")
    source_health_v1 = _source_health_v1(health, run_date)
    macro_review = _macro_review(artifact, health, run_date, macro_context)
    screening = _screening_funnel(universe, artifact, run_date)
    queue = _deep_review_queue(universe, artifact, run_date)
    strategy = _market_strategy(artifact, health, run_date)

    daily_md = docs / "daily" / f"{run_date}.md"
    daily_html = docs / "daily" / f"{run_date}.html"
    daily_md.parent.mkdir(parents=True, exist_ok=True)
    stock_report = runtime_reports / f"report_{compact}.md"
    if stock_report.exists():
        shutil.copy2(stock_report, docs / f"report_{compact}.md")
    daily_md.write_text(_daily_markdown(artifact, health, universe, run_date), encoding="utf-8")
    daily_html.write_text(_html_page("今日日报 / 运行状态", _markdown_to_html(daily_md.read_text(encoding="utf-8"))), encoding="utf-8")

    market_dir = docs / "market_cycle" / run_date
    market_dir.mkdir(parents=True, exist_ok=True)
    _write_json_md_html(market_dir, "01_macro_review", "宏观与市场背景", macro_review, _macro_markdown(macro_review))
    _write_json_md_html(market_dir, "09_screening_funnel", "筛选 / 候选范围", screening, _screening_markdown(screening))
    _write_json_md_html(market_dir, "11_deep_review_queue", "深评候选队列", queue, _queue_markdown(queue))
    _write_json_md_html(market_dir, "13_source_health", "数据源健康", source_health_v1, _health_markdown(source_health_v1))
    _write_json_md_html(market_dir, "14_market_strategy", "市场策略总控", strategy, _strategy_markdown(strategy))
    (market_dir / "summary.md").write_text(_summary_markdown(macro_review, source_health_v1, queue, strategy, run_date), encoding="utf-8")
    (market_dir / "summary.html").write_text(
        _html_page("运行状态", _markdown_to_html((market_dir / "summary.md").read_text(encoding="utf-8"))),
        encoding="utf-8",
    )
    (market_dir / "00_one_screen_brief.html").write_text(
        _one_screen_html(artifact, source_health_v1, universe, strategy),
        encoding="utf-8",
    )

    print(json.dumps({
        "schema": "pages_compat_bundle_v1",
        "runDate": run_date,
        "daily": str(daily_md),
        "marketCycle": str(market_dir),
    }, ensure_ascii=False, indent=2))
    return 0


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _short(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _reader_status(value: Any) -> str:
    text = str(value or "未标")
    mapping = {
        "FULL_REVIEW": "完整复盘",
        "LIMITED_REVIEW": "有限复盘",
        "SCREEN_ONLY": "仅筛选观察",
        "OBSERVE_ONLY": "仅市场观察",
        "BLOCKED": "数据不足，暂停结论",
        "available": "可用",
        "partial": "部分可用",
        "degraded": "降级",
        "failed": "失败",
        "usable": "可用",
        "usable_limited": "有限可用",
        "unknown": "未知",
    }
    return mapping.get(text, text)


def _source_health_v1(health: dict[str, Any], run_date: str) -> dict[str, Any]:
    domains = health.get("domains") if isinstance(health.get("domains"), dict) else {}
    rows = []
    for name, domain in domains.items():
        if not isinstance(domain, dict):
            continue
        status = _short(domain.get("status"), "unknown")
        rows.append({
            "component": name,
            "status": status,
            "usability": "usable" if status == "available" else ("degraded" if status in {"degraded", "partial"} else status),
            "criticality": "critical" if name in {"price", "macro", "filings_events"} else "supporting",
            "blocking_level": "critical" if status == "failed" and name in {"price", "macro", "filings_events"} else "none",
            "warnings": domain.get("blockers") or [],
            "source": name,
            "coverage_score": domain.get("coverage"),
            "decision_impact": "; ".join(domain.get("repairHints") or []) or "纳入本轮数据健康判断。",
        })
    return {
        "schema": "source_health_v1",
        "generated_at": health.get("generatedAt"),
        "run_date": run_date,
        "macro_status": (domains.get("macro") or {}).get("status", "unknown") if isinstance(domains, dict) else "unknown",
        "usability_verdict": _reader_status(health.get("overallMode") or "UNKNOWN"),
        "trade_review_usability": "usable" if (health.get("claimPolicy") or {}).get("canActionableAdvice") else "limited",
        "overall_score": health.get("overallScore"),
        "blocking_reasons": health.get("blockingReasons") or [],
        "rows": rows,
    }


def _macro_review(artifact: dict[str, Any], health: dict[str, Any], run_date: str, macro_context: dict[str, Any]) -> dict[str, Any]:
    reader = artifact.get("readerV3") or {}
    hero = reader.get("hero") or {}
    macro_section = _reader_section(reader, "macro_geo")
    domains = health.get("domains") if isinstance(health.get("domains"), dict) else {}
    macro = domains.get("macro") if isinstance(domains.get("macro"), dict) else {}
    fred = ((macro_context.get("components") or {}).get("fred") or {}) if isinstance(macro_context.get("components"), dict) else {}
    series = fred.get("series") if isinstance(fred.get("series"), list) else []
    fred_points = [
        f"FRED {item.get('series_id')}={item.get('value')}@{item.get('date')}"
        for item in series[:8]
        if isinstance(item, dict) and item.get("series_id")
    ]
    regime = macro_context.get("regime") if isinstance(macro_context.get("regime"), dict) else {}
    return {
        "schema": "macro_review_v1",
        "runDate": run_date,
        "status": macro_context.get("status") or macro.get("status") or "unknown",
        "confidence": regime.get("confidence") or macro.get("confidence") or "medium",
        "headline": regime.get("reason") or _short(macro_section.get("body") or hero.get("oneLine"), "等待价格和证据共振。"),
        "key_points": fred_points + [item for item in macro_section.get("bullets") or []][:5],
        "risks": [item for item in macro_section.get("counterpoints") or reader.get("counterpoints") or []][:5],
        "next_steps": [item for item in macro_section.get("nextActions") or reader.get("nextSteps") or []][:5],
        "evidence_refs": [f"FRED:{item.get('series_id')}" for item in series if isinstance(item, dict) and item.get("series_id")],
    }


def _screening_funnel(universe: dict[str, Any], artifact: dict[str, Any], run_date: str) -> dict[str, Any]:
    groups = universe.get("groups") or []
    return {
        "schema": "screening_funnel_v1",
        "runDate": run_date,
        "mode": universe.get("mode") or "unknown",
        "groups": groups,
        "watchlist": universe.get("subjectSymbols") or [],
        "candidates": (_reader_section(artifact.get("readerV3") or {}, "candidates").get("bullets") or []),
        "boundary": "候选只做观察清单；进入交易前需证据、部门分析和 CIO 复核。",
    }


def _deep_review_queue(universe: dict[str, Any], artifact: dict[str, Any], run_date: str) -> dict[str, Any]:
    subjects = universe.get("subjectSymbols") or []
    reports = artifact.get("departmentReports") or []
    hidden = [
        {"symbol": row.get("subject"), "summary": row.get("summaryForReader"), "bucket": "stock_drilldown"}
        for row in reports
        if isinstance(row, dict) and row.get("readerVisible") is False
    ]
    return {
        "schema": "deep_review_queue_v1",
        "runDate": run_date,
        "candidates": hidden or [{"symbol": symbol, "bucket": "watch", "summary": "已纳入日报观察范围。"} for symbol in subjects],
        "auto_governed_candidates": [],
        "boundary": "日报主结论不被单一股票污染；个股进入下钻页。",
    }


def _market_strategy(artifact: dict[str, Any], health: dict[str, Any], run_date: str) -> dict[str, Any]:
    reader = artifact.get("readerV3") or {}
    hero = reader.get("hero") or {}
    domains = health.get("domains") if isinstance(health.get("domains"), dict) else {}
    macro_status = ((domains.get("macro") or {}).get("status") or "unknown") if isinstance(domains.get("macro"), dict) else "unknown"
    portfolio_status = ((domains.get("portfolio") or {}).get("status") or "unknown") if isinstance(domains.get("portfolio"), dict) else "unknown"
    if macro_status == "available":
        headline = "宏观数据已刷新；当前维持观察，等待价格与证据共振。"
    else:
        headline = "宏观数据仍不完整；当前维持观察，等待证据补齐。"
    return {
        "schema": "market_strategy_v1",
        "runDate": run_date,
        "regime": _reader_status(artifact.get("analysisMode") or "UNKNOWN"),
        "confidence": hero.get("confidence") or "中",
        "strategy": {
            "headline": headline,
            "stance": "observe",
            "actions": [
                "先读市场/宏观/行业，再下钻重点个股。",
                "候选清单只做观察，等待证据和价格条件共振。",
                "搜索和新闻只做线索，关键事实回到公告、SEC、交易所或公司 IR。",
                "个股操作以原系统个股分析和人工复核为准。",
            ],
            "avoid": ["把搜索结果当事实", "让单一个股覆盖日报主结论", "忽略数据源失败"],
        },
        "participation_allowed": bool((health.get("claimPolicy") or {}).get("canActionableAdvice", False)),
        "participation_gate_reason": "; ".join(health.get("blockingReasons") or []) or f"macro={macro_status}; portfolio={portfolio_status}",
    }


def _daily_markdown(artifact: dict[str, Any], health: dict[str, Any], universe: dict[str, Any], run_date: str) -> str:
    reader = artifact.get("readerV3") or {}
    hero = reader.get("hero") or {}
    subjects = ", ".join(universe.get("subjectSymbols") or [])
    risks = "\n".join(f"- {item}" for item in (reader.get("counterpoints") or [])[:6]) or "- 暂无"
    why = "\n".join(f"- {item}" for item in (reader.get("keyReasons") or [])[:6]) or "- 暂无"
    next_steps = "\n".join(f"- {item}" for item in (reader.get("nextSteps") or [])[:6]) or "- 暂无"
    return f"""# {run_date} 投研日报

## 今日结论
{hero.get("oneLine") or artifact.get("summary", {}).get("oneLine") or "报告已生成。"}

## 覆盖范围
- 标的：{subjects or "无"}
- 模式：{_reader_status(artifact.get("analysisMode") or "UNKNOWN")}
- 数据健康：{health.get("overallScore", "unknown")}

## 为什么
{why}

## 风险和缺口
{risks}

## 下一步
{next_steps}

## 入口
- [报告中心](../reports/{run_date}.html)
- [高级诊断](../reports/{run_date}.diagnostics.html)
"""


def _macro_markdown(payload: dict[str, Any]) -> str:
    return _section_md("Macro Review", payload.get("headline"), payload.get("key_points"), payload.get("risks"), payload.get("next_steps"))


def _screening_markdown(payload: dict[str, Any]) -> str:
    groups = payload.get("groups") or []
    lines = ["# Screening Funnel", "", f"- Mode: `{payload.get('mode')}`", f"- Boundary: {payload.get('boundary')}", "", "## Groups"]
    for group in groups:
        if isinstance(group, dict):
            lines.append(f"- `{group.get('name')}`: {', '.join(group.get('symbols') or []) or '无'} — {group.get('whyIncluded')}")
    return "\n".join(lines) + "\n"


def _queue_markdown(payload: dict[str, Any]) -> str:
    lines = ["# Deep Review Queue", "", f"- Boundary: {payload.get('boundary')}", "", "| Symbol | Bucket | Summary |", "|---|---|---|"]
    for row in payload.get("candidates") or []:
        lines.append(f"| {_short(row.get('symbol'))} | {_short(row.get('bucket'))} | {_short(row.get('summary'))} |")
    return "\n".join(lines) + "\n"


def _health_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Source Health",
        "",
        f"- Mode: `{_reader_status(payload.get('usability_verdict'))}`",
        f"- Score: `{payload.get('overall_score')}`",
        f"- Blocking: `{', '.join(payload.get('blocking_reasons') or []) or 'none'}`",
        "",
        "| Domain | Status | Impact |",
        "|---|---|---|",
    ]
    for row in payload.get("rows") or []:
        lines.append(f"| `{row.get('component')}` | `{row.get('status')}` | {_short(row.get('decision_impact'))} |")
    return "\n".join(lines) + "\n"


def _strategy_markdown(payload: dict[str, Any]) -> str:
    strategy = payload.get("strategy") or {}
    return _section_md(
        "Market Regime Strategy",
        strategy.get("headline"),
        strategy.get("actions"),
        strategy.get("avoid"),
        [f"Participation: {payload.get('participation_allowed')}", f"Reason: {payload.get('participation_gate_reason')}"],
    )


def _summary_markdown(macro: dict[str, Any], health: dict[str, Any], queue: dict[str, Any], strategy: dict[str, Any], run_date: str) -> str:
    return f"""# 投研日报运行摘要 — {run_date}

- Macro status: `{macro.get('status')}`
- Source health: `{_reader_status(health.get('usability_verdict'))}`
- Source score: `{health.get('overall_score')}`
- Regime: `{_reader_status(strategy.get('regime'))}`
- Deep review candidates: `{len(queue.get('candidates') or [])}`
- Boundary: report-only; no trade execution.
"""


def _section_md(title: str, headline: Any, facts: Any, risks: Any, next_steps: Any) -> str:
    def block(items: Any) -> str:
        return "\n".join(f"- {item}" for item in (items or [])) or "- 暂无"
    return f"""# {title}

## 主结论
{_short(headline, "等待价格和证据共振。")}

## 关键依据
{block(facts)}

## 风险 / 反证
{block(risks)}

## 下一步
{block(next_steps)}
"""


def _reader_section(reader: Mapping[str, Any], key: str) -> dict[str, Any]:
    for row in reader.get("reportSections") or []:
        if isinstance(row, Mapping) and str(row.get("key") or "") == key:
            return dict(row)
    return {}


def _write_json_md_html(out: Path, stem: str, title: str, payload: dict[str, Any], markdown: str) -> None:
    (out / f"{stem}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (out / f"{stem}.md").write_text(markdown, encoding="utf-8")
    (out / f"{stem}.html").write_text(_html_page(title, _markdown_to_html(markdown)), encoding="utf-8")


def _one_screen_html(artifact: dict[str, Any], health: dict[str, Any], universe: dict[str, Any], strategy: dict[str, Any]) -> str:
    reader = artifact.get("readerV3") or {}
    hero = reader.get("hero") or {}
    subjects = universe.get("subjectSymbols") or []
    mode_label = _reader_status(artifact.get("analysisMode") or "UNKNOWN")
    source_label = _reader_status(health.get("usability_verdict"))
    body = f"""
<section class="hero">
  <div><span class="label">统一看盘 · 一屏总览</span><h1>{html.escape(mode_label)}</h1><p>{html.escape(str(hero.get('oneLine') or ''))}</p></div>
  <div class="kpi"><small>Evidence</small><b>{html.escape(str((artifact.get('evidenceStats') or {}).get('verifiedFacts', 0)))}</b><span>verified facts</span></div>
  <div class="kpi"><small>数据</small><b>{html.escape(source_label)}</b><span>score: {html.escape(str(health.get('overall_score')))}</span></div>
</section>
<section class="card"><h2>今日边界</h2><ul><li>本地投研报告，不自动交易。</li><li>日报先看市场/行业，再下钻重点个股。</li><li>搜索和新闻只做线索，事实回到公告、SEC、交易所或公司 IR。</li></ul></section>
<section class="card"><h2>覆盖标的</h2><p>{html.escape(', '.join(subjects) or '无')}</p></section>
<section class="card"><h2>策略摘要</h2><p>{html.escape(str((strategy.get('strategy') or {}).get('headline') or '等待证据共振。'))}</p></section>
"""
    return _html_page("统一看盘一屏总览", body)


def _markdown_to_html(markdown: str) -> str:
    lines = []
    in_ul = False
    in_table = False
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if not line:
            if in_ul:
                lines.append("</ul>")
                in_ul = False
            if in_table:
                lines.append("</tbody></table>")
                in_table = False
            continue
        if line.startswith("# "):
            lines.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            lines.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("- "):
            if not in_ul:
                lines.append("<ul>")
                in_ul = True
            lines.append(f"<li>{html.escape(line[2:])}</li>")
        elif line.startswith("|") and "|" in line[1:]:
            if set(line.replace("|", "").replace("-", "").replace(" ", "")) == set():
                continue
            cells = [html.escape(cell.strip()) for cell in line.strip("|").split("|")]
            tag = "th" if not in_table else "td"
            if not in_table:
                lines.append("<table><tbody>")
                in_table = True
            lines.append("<tr>" + "".join(f"<{tag}>{cell}</{tag}>" for cell in cells) + "</tr>")
        else:
            if in_ul:
                lines.append("</ul>")
                in_ul = False
            if in_table:
                lines.append("</tbody></table>")
                in_table = False
            lines.append(f"<p>{html.escape(line)}</p>")
    if in_ul:
        lines.append("</ul>")
    if in_table:
        lines.append("</tbody></table>")
    return "\n".join(lines)


def _html_page(title: str, body: str) -> str:
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(title)}</title><style>
:root{{--bg:#0b1020;--card:#121a2b;--line:#26344f;--text:#edf2ff;--muted:#9aa8c7;--accent:#7dd3fc}}
*{{box-sizing:border-box}}body{{margin:0;background:linear-gradient(135deg,#08101f,#111827);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.65}}main{{max-width:1120px;margin:0 auto;padding:28px}}a{{color:var(--accent)}}h1{{font-size:32px}}h2{{color:#cfe0ff}}.hero,.card{{border:1px solid var(--line);background:rgba(18,26,43,.94);border-radius:22px;padding:20px;margin:16px 0}}.hero{{display:grid;grid-template-columns:1.4fr 1fr 1fr;gap:16px}}.muted,small,.label{{color:var(--muted)}}.kpi{{border-left:1px solid var(--line);padding-left:16px}}.kpi b{{display:block;font-size:24px;color:var(--accent)}}table{{width:100%;border-collapse:collapse}}th,td{{border-bottom:1px solid #23304a;padding:9px;text-align:left;vertical-align:top}}code{{background:#0f172a;border:1px solid #1f2a44;border-radius:5px;padding:1px 5px}}@media(max-width:900px){{.hero{{grid-template-columns:1fr}}.kpi{{border-left:0;padding-left:0}}}}
</style></head><body><main>{body}<p class="muted">Generated by invest-system · report-only · no trade execution</p></main></body></html>"""


if __name__ == "__main__":
    raise SystemExit(main())
