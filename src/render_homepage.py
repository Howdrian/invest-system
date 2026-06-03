# -*- coding: utf-8 -*-
"""Generate the GitHub Pages homepage from runtime artifacts.

Reads market-cycle JSON, governed reports, and macro cache to produce a rich
index.html that shows conclusions, reasoning, and facts — not just labels.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_REPORTS_DIR = Path("reports")
DEFAULT_MARKET_CYCLE_DIR = Path("reports/market_cycle")
DEFAULT_MACRO_CACHE = Path("data/macro_cache/macro_context_latest.json")
DEFAULT_MARKET_HEAT_DIR = Path("reports/market_heat")
DEFAULT_OUTPUT = Path("docs/index.html")
TZ_CN = timezone(timedelta(hours=8))


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _extract_stock_cards(screening_json: Dict, deep_review_json: Dict, reports_dir: Path, today: str) -> List[Dict[str, str]]:
    """Build stock cards from screening funnel and deep review queue JSON."""
    cards = []
    
    # Layer 1: user watchlist stocks (from screening funnel)
    for row in screening_json.get("rows") or []:
        symbol = str(row.get("symbol") or "").strip()
        source = str(row.get("source") or "")
        verdict = str(row.get("verdict") or "")
        price_risk = str(row.get("price_risk") or "")
        next_action = str(row.get("next_action") or "")
        evidence = row.get("evidence") or []
        if isinstance(evidence, list):
            evidence = ", ".join(str(e) for e in evidence)
        
        # Skip non-user stocks (market heat hot stocks)
        card = {
            "symbol": symbol,
            "name": str(row.get("name") or symbol),
            "source": source,
            "verdict": verdict,
            "score": str(row.get("base_score") or "?"),
            "price_risk": price_risk,
            "next_action": next_action[:200],
            "evidence": str(evidence)[:100],
        }
        
        if source == "watchlist":
            card["icon"] = "📋"
            card["tag"] = "自选观察"
            card["tag_class"] = "tag-blue"
        elif verdict == "DEEP_REVIEW_WAIT_ENTRY":
            card["icon"] = "🟡"
            card["tag"] = "等待承接"
            card["tag_class"] = "tag-yellow"
        elif verdict == "WATCH_ONLY":
            card["icon"] = "📋"
            card["tag"] = "继续观察"
            card["tag_class"] = "tag-blue"
        else:
            card["icon"] = "🔍"
            card["tag"] = "观察"
            card["tag_class"] = "tag-blue"
        
        cards.append(card)
    
    # Layer 2: deep review candidates
    for row in deep_review_json.get("rows") or []:
        symbol = str(row.get("symbol") or "").strip()
        verdict = str(row.get("verdict") or "")
        price_risk = str(row.get("price_risk") or "")
        next_action = str(row.get("next_action") or "")
        evidence = row.get("evidence") or ""
        
        # Only show DEEP_REVIEW candidates
        if "DEEP_REVIEW" not in verdict:
            continue
        
        cards.append({
            "symbol": symbol,
            "name": symbol,
            "source": "deep_review",
            "verdict": verdict,
            "score": "待评分",
            "price_risk": price_risk,
            "next_action": next_action[:200],
            "evidence": str(evidence)[:100],
            "icon": "🔍",
            "tag": "深度候选",
            "tag_class": "tag-green",
        })
    
    return cards


def _html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _now_cn() -> str:
    return datetime.now(TZ_CN).strftime("%Y-%m-%d %H:%M:%S")


def _today_str() -> str:
    return datetime.now(TZ_CN).strftime("%Y-%m-%d")


def _report_sort_key(path: Path) -> tuple[str, float]:
    match = re.search(r"report_(\d{8})", path.name)
    date_key = match.group(1) if match else ""
    return date_key, path.stat().st_mtime


def generate(
    reports_dir: Path = DEFAULT_REPORTS_DIR,
    market_cycle_dir: Path = DEFAULT_MARKET_CYCLE_DIR,
    macro_cache: Path = DEFAULT_MACRO_CACHE,
    market_heat_dir: Path = DEFAULT_MARKET_HEAT_DIR,
    output: Path = DEFAULT_OUTPUT,
    stock_list: str = "",
) -> None:
    today = _today_str()
    today_compact = today.replace("-", "")
    stock_list_display = stock_list or "未设置"

    # Data sources
    macro = _read_json(macro_cache)
    macro_review_json = _read_json(market_cycle_dir / today / "01_macro_review.json")
    strategy_json = _read_json(market_cycle_dir / today / "14_market_strategy.json")
    health_json = _read_json(market_cycle_dir / today / "13_source_health.json")
    heat_json = _read_json(market_heat_dir / "latest_market_heat.json")
    screening_json = _read_json(market_cycle_dir / today / "09_screening_funnel.json")
    deep_review_json = _read_json(market_cycle_dir / today / "11_deep_review_queue.json")

    # Macro context — prefer macro_review (richer) over macro_cache
    macro_status = macro_review_json.get("status") or macro.get("status", "UNAVAILABLE")
    regime = strategy_json.get("regime", "UNKNOWN")
    confidence = strategy_json.get("confidence", "LOW")
    headline = (strategy_json.get("strategy") or {}).get("headline", "待分析")
    usability = health_json.get("trade_review_usability", "unknown")

    # Build macro data from macro_review (preferred) or macro_cache
    dims = macro_review_json.get("macro_dimensions") or macro_review_json.get("dimensions") or {}
    macro_lines = []
    for key, val in dims.items():
        status = val.get("status") if isinstance(val, dict) else str(val)
        signal = val.get("signal") if isinstance(val, dict) else ""
        macro_lines.append(f"{key}: {status}" + (f" ({signal})" if signal else ""))
    if not macro_lines:
        macro_indicators = macro.get("indicators") or {}
        for key, val in macro_indicators.items():
            if isinstance(val, dict):
                v = val.get("value") or val.get("latest")
                if v:
                    macro_lines.append(f"{key}: {v}")
            elif val:
                macro_lines.append(f"{key}: {val}")
    macro_data_str = " | ".join(macro_lines[:8]) if macro_lines else "暂无宏观数据"

    # Geo scenarios from macro_review
    scenarios = macro_review_json.get("geopolitical_scenarios") or macro_review_json.get("scenarios") or []
    geo_html = ""
    if scenarios:
        rows = ""
        for s in scenarios[:4]:
            name = s.get("name") or s.get("scenario") or s.get("scenario_id") or "?"
            internal = s.get("internal_pct") or s.get("internal_probability") or "-"
            market_p = s.get("market_pct") or s.get("market_probability") or "-"
            fused = s.get("fused_pct") or s.get("fused_probability") or "-"
            rows += f"<tr><td>{_html_escape(str(name))}</td><td>{internal}%</td><td>{market_p}%</td><td>{fused}%</td></tr>"
        geo_html = f'<div class="macro-line"><strong>地缘四场景</strong><table style="width:100%;font-size:.8rem;margin-top:.3rem"><tr><th>场景</th><th>内部</th><th>市场</th><th>融合</th></tr>{rows}</table></div>'

    # Source health
    health_rows = health_json.get("rows", [])
    critical_ok = all(
        r.get("usability") == "usable"
        for r in health_rows
        if r.get("criticality") == "critical"
    )
    source_status = "✅ 全部正常" if critical_ok else "⚠️ 有关键源异常"

    # Parse governed reports. A cloud run can publish a next-day market-cycle
    # page while the latest governed stock report still carries the prior
    # market date, so do not assume report_YYYYMMDD.md always exists for today.
    all_report_files = sorted(reports_dir.glob("report_*.md"), key=_report_sort_key, reverse=True)
    report_files = sorted(reports_dir.glob(f"*{today_compact}*.md"), key=_report_sort_key, reverse=True)
    if not report_files and all_report_files:
        report_files = all_report_files[:1]
    latest_report = report_files[0] if report_files else (all_report_files[0] if all_report_files else None)
    report_link_html = (
        f'<a href="./{_html_escape(latest_report.name)}">个股完整报告</a>'
        if latest_report
        else '<span class="muted">暂无个股完整报告</span>'
    )
    # Build stock cards from market_cycle JSON (deterministic, not regex on .md)
    stock_cards_data = _extract_stock_cards(screening_json, deep_review_json, reports_dir, today)

    stock_cards = ""
    for s in stock_cards_data[:30]:
        symbol = s.get("symbol", "?")
        name = s.get("name", symbol)
        verdict = s.get("verdict", "")
        next_action = s.get("next_action", "")
        evidence = s.get("evidence", "")
        icon = s.get("icon", "📋")
        tag_class = s.get("tag_class", "tag-blue")
        tag_text = s.get("tag", "")

        stock_cards += f"""
        <div class="stock-card">
          <div class="stock-header">
            <span class="stock-icon">{icon}</span>
            <span class="stock-name">{_html_escape(name)} ({_html_escape(symbol)})</span>
            <span class="tag {tag_class}">{tag_text}</span>
            <span class="score-badge">{_html_escape(verdict)}</span>
          </div>
          <div class="stock-cio">{_html_escape(next_action[:250])}</div>"""

        if evidence:
            stock_cards += f'<div class="stock-conditions">📌 {_html_escape(evidence[:200])}</div>'
        stock_cards += "</div>"

    if not stock_cards:
        stock_cards = '<div class="muted">暂无分析数据，等待下一次 Actions 触发。</div>'

        stock_cards += "</div>"

    if not stock_cards:
        stock_cards = '<div class="muted">暂无个股分析报告，等待下一次 Actions 触发。</div>'

    # Market heat
    heat_summary = ""
    heat = heat_json if isinstance(heat_json, dict) else {}
    heat_data = heat.get("data") or heat.get("summary") or {}
    if isinstance(heat_data, dict):
        heat_items = list(heat_data.items())[:6]
        heat_summary = " | ".join(f"{k}: {v}" for k, v in heat_items if v)

    # Render
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>投研日报 | invest-system</title>
<style>
:root {{ --bg: #0d1117; --card: #161b22; --border: #30363d; --text: #c9d1d9;
  --accent: #58a6ff; --red: #f85149; --yellow: #d2991d; --green: #3fb950; --muted: #8b949e; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  max-width: 1024px; margin: 0 auto; padding: 1.5rem 1rem; background: var(--bg); color: var(--text); line-height: 1.6; }}
h1 {{ color: var(--accent); font-size: 1.8rem; margin-bottom: .3rem; }}
h2 {{ color: var(--accent); font-size: 1.2rem; margin: 1.2rem 0 .5rem; }}
a {{ color: var(--accent); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.muted {{ color: var(--muted); font-size: .85rem; }}
.tag {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: .75rem; margin: 0 .3rem; }}
.tag-blue {{ background: #1f6feb33; color: var(--accent); }}
.tag-red {{ background: #f8514933; color: var(--red); }}
.tag-yellow {{ background: #d2991d33; color: var(--yellow); }}
.tag-green {{ background: #3fb95033; color: var(--green); }}
.card {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 1rem; margin-bottom: 1rem; }}
.grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }}
@media (max-width: 700px) {{ .grid2 {{ grid-template-columns: 1fr; }} }}
.macro-line {{ font-size: .9rem; padding: .5rem; background: #1a2332; border-radius: 8px; margin-bottom: .5rem; }}
.stock-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: .8rem 1rem; margin-bottom: .6rem; }}
.stock-header {{ display: flex; align-items: center; gap: .5rem; margin-bottom: .3rem; }}
.stock-icon {{ font-size: 1.1rem; }}
.stock-name {{ font-weight: 600; }}
.score-badge {{ font-size: .8rem; color: var(--muted); margin-left: auto; }}
.stock-cio {{ font-size: .85rem; margin: .3rem 0; padding: .4rem .6rem; background: #1a2332; border-left: 3px solid var(--accent); border-radius: 6px; }}
.stock-reason {{ font-size: .8rem; color: var(--red); margin: .3rem 0; }}
.stock-conditions {{ font-size: .8rem; color: var(--green); margin: .3rem 0; }}
.section-links {{ display: flex; flex-wrap: wrap; gap: .4rem; margin: .5rem 0; }}
.section-links a {{ padding: .3rem .7rem; background: var(--card); border: 1px solid var(--border); border-radius: 8px; font-size: .85rem; }}
.section-links a:hover {{ background: #1f6feb22; }}
</style>
</head>
<body>

<h1>📊 投研日报</h1>
<p class="muted">更新: {_now_cn()} 北京时 · 自选: {_html_escape(stock_list_display[:80])} · 
  <a href="https://github.com/Howdrian/invest-system/actions">Actions</a></p>

<!-- MACRO CONTEXT -->
<div class="card">
  <h2>🌍 宏观背景</h2>
  <div class="macro-line">
    <strong>Regime: {_html_escape(regime)}</strong> (置信度: {_html_escape(confidence)}) — {_html_escape(headline)}
  </div>
  <div class="macro-line">
    {_html_escape(macro_data_str)}
  </div>
  <div class="macro-line">
    数据源: {source_status} · 宏观: {_html_escape(macro_status)} · 交易审查: {_html_escape(usability)}
  </div>
  {geo_html}
</div>

<!-- STOCK CIO CONCLUSIONS -->
<div class="card">
  <h2>🎯 今日关注 ({len(stock_cards_data)} 条)</h2>
  {stock_cards}
</div>

<!-- LINKS -->
<div class="grid2">
  <div class="card">
    <h2>📋 完整报告</h2>
    <div class="section-links">
      <a href="./daily/{today}.md">日报 Markdown</a>
      {report_link_html}
    </div>
  </div>
  <div class="card">
    <h2>📊 大盘看板</h2>
    <div class="section-links">
      <a href="./market_cycle/{today}/00_one_screen_brief.html">一屏总览</a>
      <a href="./market_cycle/{today}/14_market_strategy.html">市场策略</a>
      <a href="./market_cycle/{today}/13_source_health.html">数据源健康</a>
      <a href="./market_heat/latest_market_heat.md">市场热度</a>
    </div>
  </div>
</div>

<p class="muted" style="margin-top:1.5rem;">
⚠️ 以上为系统分析意见，非交易指令。最终决策由你做出。<br>
本页面通过 GitHub Actions 自动生成，修改自选/持仓请通过 Web UI 或 .env。
</p>

</body>
</html>""",
        encoding="utf-8",
    )


if __name__ == "__main__":
    import argparse
    import traceback
    import sys

    p = argparse.ArgumentParser(description="Generate rich GitHub Pages homepage")
    p.add_argument("--reports-dir", default=str(DEFAULT_REPORTS_DIR))
    p.add_argument("--market-cycle-dir", default=str(DEFAULT_MARKET_CYCLE_DIR))
    p.add_argument("--macro-cache", default=str(DEFAULT_MACRO_CACHE))
    p.add_argument("--market-heat-dir", default=str(DEFAULT_MARKET_HEAT_DIR))
    p.add_argument("--output", default=str(DEFAULT_OUTPUT))
    p.add_argument("--stock-list", default="")
    args = p.parse_args()
    try:
        generate(
            reports_dir=Path(args.reports_dir),
            market_cycle_dir=Path(args.market_cycle_dir),
            macro_cache=Path(args.macro_cache),
            market_heat_dir=Path(args.market_heat_dir),
            output=Path(args.output),
            stock_list=args.stock_list,
        )
        print("✅ render_homepage: success")
    except Exception as e:
        print(f"❌ render_homepage failed: {e}")
        traceback.print_exc()
        sys.exit(1)
