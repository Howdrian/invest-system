# -*- coding: utf-8 -*-
"""Generate the GitHub Pages homepage from runtime artifacts.

Reads governed_results.json (structured CIO/scoring/RedBlue), market-cycle JSON,
and macro cache. Renders rich stock cards with derivation chains.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_REPORTS_DIR = Path("reports")
DEFAULT_MARKET_CYCLE_DIR = Path("reports/market_cycle")
DEFAULT_MACRO_CACHE = Path("data/macro_cache/macro_context_latest.json")
DEFAULT_MARKET_HEAT_DIR = Path("reports/market_heat")
DEFAULT_OUTPUT = Path("docs/index.html")

BEIJING = timezone(timedelta(hours=8))


def _today_str() -> str:
    return datetime.now(BEIJING).strftime("%Y-%m-%d")


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


CSS = """<style>
:root{--bg:#0d1117;--card:#161b22;--border:#30363d;--text:#c9d1d9;--accent:#58a6ff;--red:#f85149;--yellow:#d2991d;--green:#3fb950;--muted:#8b949e}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;max-width:1024px;margin:0 auto;padding:1.5rem 1rem;background:var(--bg);color:var(--text);line-height:1.6}
h1{color:var(--accent);font-size:1.8rem;margin-bottom:.3rem}
h2{color:var(--accent);font-size:1.2rem;margin:1.2rem 0 .5rem}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.muted{color:var(--muted);font-size:.85rem}
.tag{display:inline-block;padding:2px 8px;border-radius:999px;font-size:.75rem;margin:0 .3rem}
.tag-blue{background:#1f6feb33;color:var(--accent)}.tag-red{background:#f8514933;color:var(--red)}
.tag-yellow{background:#d2991d33;color:var(--yellow)}.tag-green{background:#3fb95033;color:var(--green)}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:1rem;margin-bottom:1rem}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
@media(max-width:700px){.grid2{grid-template-columns:1fr}}
.macro-line{font-size:.9rem;padding:.5rem;background:#1a2332;border-radius:8px;margin-bottom:.5rem}
.stock-card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:.8rem 1rem;margin-bottom:.6rem}
.stock-header{display:flex;align-items:center;gap:.5rem;margin-bottom:.3rem}
.stock-name{font-weight:600}.score-badge{font-size:.8rem;color:var(--muted);margin-left:auto}
.stock-cio{font-size:.85rem;margin:.3rem 0;padding:.4rem .6rem;background:#1a2332;border-left:3px solid var(--accent);border-radius:6px}
.stock-dim{font-size:.8rem;color:var(--yellow);margin:.2rem 0}
.stock-rb{font-size:.8rem;color:#e6b0aa;margin:.2rem 0}
.stock-conditions{font-size:.8rem;color:var(--green);margin:.2rem 0}
.section-links{display:flex;flex-wrap:wrap;gap:.4rem;margin:.5rem 0}
.section-links a{padding:.3rem .7rem;background:var(--card);border:1px solid var(--border);border-radius:8px;font-size:.85rem}
.section-links a:hover{background:#1f6feb22}
</style>"""


def main() -> None:
    today = _today_str()

    # Files
    def _path(market_cycle_dir: Path, name: str) -> Path:
        p = market_cycle_dir / today / name
        return p if p.exists() else (Path("docs/market_cycle") / today / name)

    macro = _read_json(DEFAULT_MACRO_CACHE) or {}
    macro_r = _read_json(_path(DEFAULT_MARKET_CYCLE_DIR, "01_macro_review.json")) or {}
    strategy = _read_json(_path(DEFAULT_MARKET_CYCLE_DIR, "14_market_strategy.json")) or {}
    health = _read_json(_path(DEFAULT_MARKET_CYCLE_DIR, "13_source_health.json")) or {}
    screening = _read_json(_path(DEFAULT_MARKET_CYCLE_DIR, "09_screening_funnel.json")) or {}
    governed = _read_json(Path("docs/governed_results.json")) or _read_json(DEFAULT_REPORTS_DIR / "governed_results.json") or []

    regime = strategy.get("regime", "UNKNOWN")
    headline = (strategy.get("strategy") or {}).get("headline", "")
    usability = health.get("trade_review_usability", "unknown")
    macro_status = macro_r.get("status") or macro.get("status", "?")

    # Macro dimensions
    dims = macro_r.get("dimensions") or {}
    dim_parts = []
    for k, v in dims.items():
        s = v.get("status", "?") if isinstance(v, dict) else str(v)
        dim_parts.append(f"{k}:{s}")
    dim_text = " | ".join(dim_parts[:8]) if dim_parts else "暂无"

    # === GOV GOVERENED CARDS (rich) ===
    gov_html = ""
    gov_codes = set()
    if isinstance(governed, list):
        for g in governed:
            code = str(g.get("code", ""))
            gov_codes.add(code)
            name = str(g.get("name") or code)
            score = g.get("score", 0)
            direction = str(g.get("direction") or "")
            headline_g = str(g.get("headline") or "")
            cio_status = str(g.get("cio_status") or "")
            rb = g.get("red_blue") or {}
            dims_g = g.get("scoring", {}).get("dimensions") or {}
            tp = g.get("trade_plan") or {}
            conds = tp.get("invalidations") or tp.get("conditions") or []

            blocked = cio_status == "BLOCKED_BY_FATAL" or score < 6.0
            tc = "tag-red" if blocked else "tag-yellow"
            tt = "BLOCKED" if blocked else "观察"

            # 5-dim
            dp = " | ".join(f"{k}={v.get('score','?')}" for k, v in dims_g.items() if isinstance(v, dict))
            # RedBlue
            rb_text = f"{rb.get('stronger_side','')}方胜出 — {rb.get('verdict','')}"[:200]
            # Conditions
            cd = " · ".join(str(c) for c in conds[:3])[:200]

            gov_html += f"""<div class="stock-card">
  <div class="stock-header">
    <span class="stock-name">{_esc(name)} ({_esc(code)})</span>
    <span class="tag {tc}">{tt}</span>
    <span class="score-badge">评分 {score}/10</span>
  </div>
  <div class="stock-cio">方向: {_esc(direction)} — {_esc(headline_g[:200])}</div>"""
            if dp:
                gov_html += f'<div class="stock-dim">📊 五维: {_esc(dp)}</div>'
            if rb.get("stronger_side"):
                gov_html += f'<div class="stock-rb">⚔️ 红蓝: {_esc(rb_text)}</div>'
            if cd:
                gov_html += f'<div class="stock-conditions">📌 逆向条件: {_esc(cd)}</div>'
            gov_html += "</div>\n"

    # === SCREENING CARDS (light, skip governed stocks) ===
    scr_html = ""
    for c in (screening.get("candidates") or [])[:25]:
        sym = str(c.get("symbol") or "").replace("SH", "").replace("SZ", "").strip()
        if sym in gov_codes:
            continue
        nm = str(c.get("name") or sym)
        vd = str(c.get("verdict") or "")
        na = str(c.get("next_action") or "")[:150]
        ev = ", ".join(str(e) for e in (c.get("evidence") or []))[:100]

        scr_html += f"""<div class="stock-card">
  <div class="stock-header">
    <span class="stock-name">{_esc(nm)} ({_esc(sym)})</span>
    <span class="tag tag-blue">候选</span>
    <span class="score-badge">{_esc(vd)}</span>
  </div>
  <div class="stock-cio">{_esc(na)}</div>"""
        if ev:
            scr_html += f'<div class="stock-conditions">📌 {_esc(ev)}</div>'
        scr_html += "</div>\n"

    # === RENDER ===
    gov_count = len(governed) if isinstance(governed, list) else 0
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>投研日报 | invest-system</title>{CSS}</head>
<body>
<h1>📊 投研日报</h1>
<p class="muted">{datetime.now(BEIJING).strftime('%Y-%m-%d %H:%M')} 北京时 · 
  <a href="https://github.com/Howdrian/invest-system/actions">Actions</a></p>

<div class="card"><h2>🌍 宏观背景</h2>
  <div class="macro-line"><strong>Regime: {_esc(regime)}</strong> — {_esc(headline)}</div>
  <div class="macro-line">{_esc(dim_text)}</div>
  <div class="macro-line">宏观: {_esc(macro_status)} · 交易审查: {_esc(usability)}</div>
</div>

<div class="card"><h2>🎯 Governed 深评 ({gov_count} 只)</h2>
  {gov_html if gov_html else '<div class="muted">暂无 governed 分析结果。</div>'}
</div>

<div class="card"><h2>📋 筛选候选</h2>
  {scr_html if scr_html else '<div class="muted">暂无筛选候选。</div>'}
</div>

<div class="grid2">
  <div class="card"><h2>📊 完整报告</h2><div class="section-links">
    <a href="./daily/{today}.md">日报</a>
    <a href="./market_cycle/{today}/09_screening_funnel.html">筛选漏斗</a>
    <a href="./market_cycle/{today}/11_deep_review_queue.html">深评队列</a>
  </div></div>
  <div class="card"><h2>📈 大盘看板</h2><div class="section-links">
    <a href="./market_cycle/{today}/00_one_screen_brief.html">一屏总览</a>
    <a href="./market_cycle/{today}/01_macro_review.html">宏观报告</a>
    <a href="./market_cycle/{today}/14_market_strategy.html">市场策略</a>
    <a href="./market_cycle/{today}/13_source_health.html">源健康</a>
  </div></div>
</div>

<p class="muted" style="margin-top:1.5rem">⚠️ 系统分析意见，非交易指令。最终决策由你做出。</p>
</body></html>"""

    DEFAULT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT.write_text(html, encoding="utf-8")
    print(f"✅ render_homepage: {len(html)} bytes, {gov_count} governed, cards rendered", file=sys.stderr)


if __name__ == "__main__":
    import traceback
    try:
        main()
    except Exception as e:
        print(f"❌ {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
