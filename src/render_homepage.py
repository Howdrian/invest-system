# -*- coding: utf-8 -*-
"""Generate the GitHub Pages homepage from runtime artifacts.

Reads governed_results.json (structured CIO/scoring/RedBlue), market-cycle JSON,
and macro cache. Renders rich stock cards with derivation chains.
"""

from __future__ import annotations

import json
import sys
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.core.run_context import resolve_analysis_run_date

DEFAULT_REPORTS_DIR = Path("reports")
DEFAULT_MARKET_CYCLE_DIR = Path("reports/market_cycle")
DEFAULT_MACRO_CACHE = Path("data/macro_cache/macro_context_latest.json")
DEFAULT_MARKET_HEAT_DIR = Path("reports/market_heat")
DEFAULT_OUTPUT = Path("docs/index.html")

BEIJING = timezone(timedelta(hours=8))


def _today_str() -> str:
    return resolve_analysis_run_date()


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_today_governed_results(
    today: str,
    *,
    reports_dir: Path = DEFAULT_REPORTS_DIR,
    docs_dir: Path = Path("docs"),
) -> List[Dict[str, Any]]:
    """Prefer current runtime results and ignore stale governed rows."""
    payload = _read_json(reports_dir / "governed_results.json")
    if payload is None:
        payload = _read_json(docs_dir / "governed_results.json")
    if not isinstance(payload, list):
        return []
    rows: List[Dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        run_date = str(item.get("run_date") or "").strip()
        if run_date != today:
            continue
        rows.append(item)
    return rows


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


MODE_LABELS = {
    "FULL_REVIEW": "完整复盘",
    "LIMITED_REVIEW": "有限复盘",
    "SCREEN_ONLY": "仅筛选观察",
    "OBSERVE_ONLY": "仅市场观察",
    "BLOCKED": "数据不足，暂停结论",
}

STATUS_LABELS = {
    "REFRESHED": "已刷新",
    "AVAILABLE": "可用",
    "DEGRADED": "降级",
    "PARTIAL": "部分可用",
    "usable": "可用",
    "usable_limited": "有限可用",
    "unavailable": "不可用",
    "unknown": "未知",
    "NEUTRAL_WATCH": "中性观察",
    "RISK_OFF": "风险收缩",
    "RISK_ON": "风险偏好",
    "FULL_REVIEW": "完整复盘",
    "LIMITED_REVIEW": "有限复盘",
    "SCREEN_ONLY": "仅筛选观察",
    "OBSERVE_ONLY": "仅市场观察",
    "BLOCKED": "数据不足，暂停结论",
}

DIMENSION_LABELS = {
    "fundamental_strength": "基本面",
    "catalyst_clarity": "催化剂",
    "risk_reward_ratio": "赔率",
    "timing": "时机",
    "evidence_quality": "证据质量",
}


def _label_mode(value: Any) -> str:
    text = str(value or "未标")
    return MODE_LABELS.get(text, text)


def _label_status(value: Any) -> str:
    text = str(value or "未知")
    return STATUS_LABELS.get(text, text)


def _label_blocker(value: Any) -> str:
    text = str(value or "")
    domain, _, reason = text.partition(":")
    domain_map = {
        "fundamentals": "基本面",
        "macro": "宏观",
        "portfolio": "持仓",
        "publish_bundle": "发布包",
        "news_sentiment": "新闻舆情",
        "price": "行情",
    }
    reason_map = {
        "failed": "失败",
        "macro_degraded": "仍有宏观因子缺口",
        "portfolio_missing": "未配置持仓快照",
        "publish_incomplete": "发布包仍有缺口",
        "rate_limited": "限流",
        "auth_missing": "缺少授权",
        "agent_reported_data_gap": "部门待确认项",
    }
    if not reason:
        return text
    return f"{domain_map.get(domain, domain)}：{reason_map.get(reason, reason)}"


def _decision_label(blocked: bool, direction: Any = "") -> str:
    if blocked:
        return "暂停行动"
    direction_text = str(direction or "").lower()
    if "buy" in direction_text or "long" in direction_text or "看多" in direction_text:
        return "可观察偏多"
    if "sell" in direction_text or "short" in direction_text or "看空" in direction_text:
        return "可观察偏空"
    return "观察"


def _redblue_label(value: Any) -> str:
    text = str(value or "")
    mapping = {"red": "红方", "blue": "蓝方", "draw": "未分胜负"}
    return mapping.get(text.lower(), text)


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


def _reader_list(items: Any, *, limit: int = 3) -> str:
    rows = [str(item).strip() for item in (items or []) if str(item).strip()][:limit]
    return "".join(f"<li>{_esc(item)}</li>" for item in rows) or "<li class='muted'>本轮未提供。</li>"


def _render_reader_homepage(artifact: Dict[str, Any], today: str, generated_at: str) -> str:
    reader = artifact.get("readerV3") if isinstance(artifact.get("readerV3"), dict) else {}
    hero = reader.get("hero") if isinstance(reader.get("hero"), dict) else {}
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(today)} 投研日报</title>{CSS}<style>
body{{max-width:980px;padding-top:3rem}}.reader-home{{padding:1rem 0 2rem;border-bottom:1px solid var(--border)}}
.reader-home h1{{max-width:820px;margin:.8rem 0 1rem;color:#f0f6fc;font-size:clamp(2rem,6vw,3.25rem);line-height:1.2}}
.reader-home .lead{{max-width:860px;font-size:1.25rem;line-height:1.75;color:#f0f6fc}}
.home-facts{{display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin:1.6rem 0}}
.home-fact{{padding:1rem 0;border-top:1px solid var(--border)}}.home-fact span{{display:block;color:var(--muted);font-size:.75rem}}
.home-fact strong{{display:block;margin-top:.35rem;font-size:1rem;color:#f0f6fc}}
.brief-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:1.4rem;margin:2rem 0}}
.brief-grid section{{border-left:2px solid var(--border);padding-left:1rem}}.brief-grid h2{{margin:0 0 .6rem;color:#f0f6fc}}
.brief-grid ul{{padding-left:1.1rem}}.report-cta{{display:inline-block;margin-top:1rem;padding:.75rem 1.1rem;border-radius:10px;background:var(--accent);color:#07111f;font-weight:700}}
@media(max-width:720px){{.home-facts,.brief-grid{{grid-template-columns:1fr}}.brief-grid section{{border-left:0;border-top:1px solid var(--border);padding:1rem 0 0}}}}
</style></head>
<body>
<header class="reader-home">
  <p class="muted">{_esc(str(hero.get('status') or '每日投研'))} · {_esc(today)}</p>
  <h1>今日总判断</h1>
  <p class="lead">{_esc(str(hero.get('oneLine') or '本轮未生成总判断。'))}</p>
  <div class="home-facts">
    <div class="home-fact"><span>研究立场</span><strong>{_esc(str(hero.get('marketStance') or '待确认'))}</strong></div>
    <div class="home-fact"><span>组合动作</span><strong>{_esc(str(hero.get('portfolioAction') or '待确认'))}</strong></div>
  </div>
  <p class="muted">可信度：{_esc(str(hero.get('confidence') or '未标'))} · 时效：{_esc(str(hero.get('validity') or '未标'))} · 页面生成：{_esc(generated_at)} 北京时</p>
  <a class="report-cta" href="./reports/{_esc(today)}.html">阅读完整报告</a>
</header>
<main class="brief-grid">
  <section><h2>核心理由</h2><ul>{_reader_list(reader.get('keyReasons'))}</ul></section>
  <section><h2>最大反证 / 风险</h2><ul>{_reader_list(reader.get('counterpoints'))}</ul></section>
  <section><h2>下一步</h2><ul>{_reader_list(reader.get('nextSteps'))}</ul></section>
</main>
<p class="muted">本报告用于研究复核，不自动执行交易。</p>
</body></html>"""


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render GitHub Pages homepage from report artifacts")
    parser.add_argument("--date", default="", help="Run date YYYY-MM-DD")
    parser.add_argument("--reports-dir", default=str(DEFAULT_REPORTS_DIR))
    parser.add_argument("--market-cycle-dir", default=str(DEFAULT_MARKET_CYCLE_DIR))
    parser.add_argument("--macro-cache", default=str(DEFAULT_MACRO_CACHE))
    parser.add_argument("--market-heat-dir", default=str(DEFAULT_MARKET_HEAT_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--docs-dir", default="", help="Published docs root; sets report input/output defaults")
    parser.add_argument("--stock-list", default="", help="Kept for workflow compatibility")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    today = args.date or _today_str()
    docs_root = Path(args.docs_dir) if args.docs_dir else None
    reports_dir = docs_root if docs_root and args.reports_dir == str(DEFAULT_REPORTS_DIR) else Path(args.reports_dir)
    market_cycle_dir = (docs_root / "market_cycle") if docs_root and args.market_cycle_dir == str(DEFAULT_MARKET_CYCLE_DIR) else Path(args.market_cycle_dir)
    macro_cache = Path(args.macro_cache)
    output = (docs_root / "index.html") if docs_root and args.output == str(DEFAULT_OUTPUT) else Path(args.output)
    docs_dir = output.parent

    # Files
    def _path(name: str) -> Path:
        p = market_cycle_dir / today / name
        return p if p.exists() else (docs_dir / "market_cycle" / today / name)

    macro = _read_json(macro_cache) or {}
    macro_r = _read_json(_path("01_macro_review.json")) or {}
    strategy = _read_json(_path("14_market_strategy.json")) or {}
    health = _read_json(_path("13_source_health.json")) or {}
    screening = _read_json(_path("09_screening_funnel.json")) or {}
    artifact = _read_json(docs_dir / "reports" / f"{today}.artifact.json") or {}
    generated_at = datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M")
    if isinstance(artifact.get("readerV3"), dict):
        html = _render_reader_homepage(artifact, today, generated_at)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(html, encoding="utf-8")
        print(f"✅ render_homepage: {len(html)} bytes, reader homepage rendered", file=sys.stderr)
        return 0
    governed = _load_today_governed_results(today, reports_dir=reports_dir, docs_dir=docs_dir)

    regime = strategy.get("regime", "UNKNOWN")
    headline = (strategy.get("strategy") or {}).get("headline", "")
    usability = health.get("trade_review_usability", "unknown")
    macro_status = macro_r.get("status") or macro.get("status", "?")
    source_health_v2 = artifact.get("sourceHealthV2") if isinstance(artifact.get("sourceHealthV2"), dict) else {}
    claim_policy = source_health_v2.get("claimPolicy") if isinstance(source_health_v2.get("claimPolicy"), dict) else {}
    analysis_mode = artifact.get("analysisMode") or source_health_v2.get("overallMode") or "未标"
    try:
        overall_score = f"{round(float(source_health_v2.get('overallScore')) * 100)}%"
    except Exception:
        overall_score = "未标"
    can_advice = "是" if claim_policy.get("canActionableAdvice") else "否"
    can_position = "是" if claim_policy.get("canPositionSizing") else "否"
    blockers = source_health_v2.get("blockingReasons") if isinstance(source_health_v2.get("blockingReasons"), list) else []
    blockers_text = " | ".join(_label_blocker(item) for item in blockers[:5]) if blockers else "无"

    # Macro dimensions
    dims = macro_r.get("dimensions") or {}
    dim_parts = []
    for k, v in dims.items():
        s = v.get("status", "?") if isinstance(v, dict) else str(v)
        dim_parts.append(f"{_label_blocker(k)}：{_label_status(s)}")
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
            tt = _decision_label(blocked, direction)

            # 5-dim
            dp = " | ".join(
                f"{DIMENSION_LABELS.get(str(k), str(k))}：{v.get('score','?')}"
                for k, v in dims_g.items()
                if isinstance(v, dict)
            )
            # RedBlue
            rb_text = f"{_redblue_label(rb.get('stronger_side',''))}胜出 — {rb.get('verdict','')}"[:200]
            # Conditions
            cd = " · ".join(str(c) for c in conds[:3])[:200]

            gov_html += f"""<div class="stock-card">
  <div class="stock-header">
    <span class="stock-name">{_esc(name)} ({_esc(code)})</span>
    <span class="tag {tc}">{tt}</span>
    <span class="score-badge">综合评分 {score}/10</span>
  </div>
  <div class="stock-cio">方向：{_esc(_decision_label(blocked, direction))} — {_esc(headline_g[:200])}</div>"""
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
        if not isinstance(c, dict):
            continue
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
    generated_at = datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M")
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>投研日报 | invest-system</title>{CSS}</head>
<body>
<h1>📊 投研日报</h1>
<p class="muted">报告日期：{_esc(today)} · 页面生成：{_esc(generated_at)} 北京时 ·
  <a href="https://github.com/Howdrian/invest-system/actions">Actions</a></p>

<div class="card"><h2>🌍 宏观背景</h2>
  <div class="macro-line"><strong>市场状态：{_esc(_label_status(regime))}</strong> — {_esc(headline)}</div>
  <div class="macro-line">{_esc(dim_text)}</div>
  <div class="macro-line">宏观：{_esc(_label_status(macro_status))} · 交易审查：{_esc(_label_status(usability))}</div>
  <div class="macro-line">今日模式：{_esc(_label_mode(analysis_mode))} · 总可信度：{_esc(overall_score)} · 可交易建议：{_esc(can_advice)} · 可仓位建议：{_esc(can_position)}</div>
  <div class="macro-line">主要限制：{_esc(blockers_text)}</div>
</div>

<div class="card"><h2>🎯 个股深评 ({gov_count} 只)</h2>
  {gov_html if gov_html else '<div class="muted">暂无个股深评结果。</div>'}
</div>

<div class="card"><h2>📋 筛选候选</h2>
  {scr_html if scr_html else '<div class="muted">暂无筛选候选。</div>'}
</div>

<div class="card"><h2>📊 今日主入口</h2><div class="section-links">
    <a href="./reports/{today}.html">报告中心</a>
    <a href="./daily/{today}.html">日报</a>
    <a href="./agent_memos/{today}/index.html">Agent卷宗</a>
    <a href="./market_cycle/{today}/summary.html">市场周期</a>
    <a href="./market_cycle/{today}/13_source_health.html">源健康</a>
</div>
</div>

<p class="muted" style="margin-top:1.5rem">⚠️ 系统分析意见，非交易指令。最终决策由你做出。</p>
</body></html>"""

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    print(f"✅ render_homepage: {len(html)} bytes, {gov_count} deep-review rows, cards rendered", file=sys.stderr)
    return 0


if __name__ == "__main__":
    import traceback
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"❌ {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
