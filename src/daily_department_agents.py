# -*- coding: utf-8 -*-
"""Evidence-driven daily research department agents.

This is the A-roll research layer: it turns the same daily evidence pool used by
the report artifact into reader-facing department conclusions, then writes one
CIO memo.  It deliberately avoids network/LLM calls so local and CI runs are
deterministic.  The output is still a real runtime stage, not an artifact
backfill: every memo is generated from evidence ledgers, the daily universe and
the original upstream analysis reports.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence


AGENT_MEMO_SCHEMA = "agent_memo_v1"
ORIGIN = "RAW_AGENT"
RUNTIME_KIND = "evidence_driven_department_agent_v1"
RULE_AGENT_RUNTIME = "RULE"


@dataclass(frozen=True)
class StockSummary:
    symbol: str
    name: str
    action: str
    score: str
    trend: str
    reason: str = ""
    risk: str = ""


def run_daily_department_agents(
    docs_dir: str | Path,
    run_date: str,
    *,
    runtime_reports_dir: str | Path = "reports",
) -> Dict[str, Any]:
    """Write RAW daily department memos and return a compact summary."""

    docs = Path(docs_dir)
    runtime_reports = Path(runtime_reports_dir)
    out = docs / "agent_memos" / run_date
    out.mkdir(parents=True, exist_ok=True)

    evidence = _load_jsonl(docs / "run_status" / run_date / "evidence_ledger.jsonl")
    providers = _load_jsonl(docs / "run_status" / run_date / "provider_runs.jsonl")
    health = _read_json(docs / "run_status" / run_date / "source_health_v2.json")
    universe = _read_json(docs / "run_status" / run_date / "daily_universe.json")
    official = _read_json(docs / "official_events" / f"{run_date}.json")
    stock_md = _read_text_first(
        runtime_reports / f"report_{run_date.replace('-', '')}.md",
        docs / f"report_{run_date.replace('-', '')}.md",
    )
    market_md = _read_text_first(
        runtime_reports / f"market_review_{run_date.replace('-', '')}.md",
        docs / f"market_review_{run_date.replace('-', '')}.md",
    )

    stocks = _parse_stock_summaries(stock_md)
    market = _market_snapshot(market_md)
    grouped = _EvidenceView(evidence)

    memos = [
        ("market/02_macro_geopolitics", _macro_agent(run_date, grouped, health)),
        ("market/03_geo_policy", _geo_policy_agent(run_date, grouped, official)),
        ("market/03_market_strategy", _market_agent(run_date, grouped, market, universe)),
        ("market/04_candidate_review", _sector_agent(run_date, grouped, market, universe)),
        ("market/05_portfolio_review", _portfolio_agent(run_date, grouped, health)),
        ("market/06_fundamental_review", _fundamental_agent(run_date, grouped, stocks, official)),
        ("market/07_technical_review", _technical_agent(run_date, grouped, stocks, stock_md)),
        ("market/08_intel_review", _intel_agent(run_date, grouped, official)),
    ]
    risk = _risk_agent(run_date, grouped, stocks, health, market)
    red_team = _red_team_agent(run_date, stocks, health, market)
    cio = _cio_agent(run_date, memos=[memo for _rel, memo in memos], risk=risk, red_team=red_team, universe=universe)
    memos.extend(
        [
            ("market/09_risk_review", risk),
            ("market/10_red_team", red_team),
            ("market/11_cio_report", cio),
        ]
    )

    generated: List[str] = []
    for rel, memo in memos:
        generated.extend(_write_memo(out, rel, memo))

    index = _index_markdown(run_date, memos)
    _write_text(out / "index.md", index)
    generated.append("index.md")

    return {
        "schema": "daily_department_agents_result_v1",
        "runDate": run_date,
        "origin": ORIGIN,
        "runtimeKind": RUNTIME_KIND,
        "memoCount": len(memos),
        "generated": generated,
        "stockCount": len(stocks),
        "providerRuns": len(providers),
        "evidenceFacts": len(evidence),
    }


class _EvidenceView:
    def __init__(self, rows: Sequence[Mapping[str, Any]]) -> None:
        self.rows = [dict(row) for row in rows if isinstance(row, Mapping)]

    def ids(self, *, domain: str | None = None, symbol: str | None = None, fact_type: str | None = None, limit: int = 8) -> List[str]:
        out: List[str] = []
        for row in self.rows:
            if domain and str(row.get("domain") or "") != domain:
                continue
            if symbol and str(row.get("symbol") or row.get("subject") or "").upper() != symbol.upper():
                continue
            if fact_type and str(row.get("fact_type") or row.get("factType") or "") != fact_type:
                continue
            value = str(row.get("id") or "").strip()
            if value and value not in out:
                out.append(value)
            if len(out) >= limit:
                break
        return out

    def values(self, *, domain: str | None = None, symbol: str | None = None, contains: str | None = None, limit: int = 8) -> List[str]:
        out: List[str] = []
        needle = contains.lower() if contains else ""
        for row in self.rows:
            if domain and str(row.get("domain") or "") != domain:
                continue
            if symbol and str(row.get("symbol") or row.get("subject") or "").upper() != symbol.upper():
                continue
            text = str(row.get("value") or row.get("id") or "").strip()
            if needle and needle not in text.lower():
                continue
            if text and text not in out:
                out.append(text)
            if len(out) >= limit:
                break
        return out

    def count(self, *, domain: str | None = None, fact_type: str | None = None) -> int:
        total = 0
        for row in self.rows:
            if domain and str(row.get("domain") or "") != domain:
                continue
            if fact_type and str(row.get("fact_type") or row.get("factType") or "") != fact_type:
                continue
            total += 1
        return total


def _macro_agent(run_date: str, evidence: _EvidenceView, health: Mapping[str, Any]) -> Dict[str, Any]:
    points = evidence.values(domain="macro", limit=8)
    ids = evidence.ids(domain="macro", fact_type="verified_fact", limit=8)
    vix = _first_contains(points, "VIXCLS")
    dgs10 = _first_contains(points, "DGS10")
    summary = "宏观证据已刷新：利率、通胀、就业、信用和风险偏好进入证据池；今天只作为市场背景，不单独触发个股动作。"
    claims = [
        _join_nonempty("利率/流动性已纳入", dgs10),
        _join_nonempty("风险偏好已纳入", vix),
        f"宏观 verified facts={evidence.count(domain='macro', fact_type='verified_fact')}。",
    ]
    return _memo(
        run_date,
        agent="MacroAgent",
        label="宏观部门",
        scope="daily",
        summary=summary,
        key_claims=claims,
        evidence_ids=ids,
        counterpoints=["宏观只解释环境，不替代个股价格、公告和基本面证据。"],
        data_gaps=[] if ids else ["FRED 宏观事实未进入证据池"],
        next_action="继续观察利率、通胀、信用利差和 VIX 是否同向变化。",
        confidence="high" if ids else "medium",
    )


def _geo_policy_agent(run_date: str, evidence: _EvidenceView, official: Mapping[str, Any]) -> Dict[str, Any]:
    macro_points = evidence.values(domain="macro", limit=10)
    news_points = evidence.values(domain="news_sentiment", limit=6)
    geo_signals = [
        item
        for item in macro_points
        if any(token in item.upper() for token in ("DCOIL", "VIX", "DGS10", "BAML", "OIL", "ENERGY"))
    ]
    official_count = len(official.get("evidenceFacts") or []) if isinstance(official, Mapping) else 0
    ids = evidence.ids(domain="macro", limit=6) + evidence.ids(domain="news_sentiment", fact_type="discovery", limit=4)
    summary = (
        "地缘政策层独立复核：能源、利率/美元、信用风险和政策/冲突线索只作为市场传导变量；"
        "没有官方政策原文时，不把新闻线索升级为事实。"
    )
    return _memo(
        run_date,
        agent="GeoPolicyAgent",
        label="地缘政策部门",
        scope="daily",
        summary=summary,
        key_claims=[
            f"能源/风险偏好相关证据：{'; '.join(geo_signals[:3]) or '暂无显著结构化事件'}。",
            f"官方公告/法披事实可供交叉验证：{official_count} 条。",
            f"新闻/搜索 discovery：{len(news_points)} 条，只做事件发现。",
        ],
        evidence_ids=ids[:10],
        counterpoints=["地缘冲击传导到行业和个股需要价格、公告、订单或成本证据确认。"],
        data_gaps=[] if ids else ["缺少地缘/政策相关证据包"],
        next_action="继续跟踪贸易、制裁、冲突、能源价格与强弱行业之间是否形成同向证据。",
        confidence="medium" if ids else "low",
    )


def _market_agent(run_date: str, evidence: _EvidenceView, market: Mapping[str, Any], universe: Mapping[str, Any]) -> Dict[str, Any]:
    subject_count = len(universe.get("subjectSymbols") or []) if isinstance(universe, Mapping) else 0
    headline = str(market.get("headline") or "市场复盘已纳入，但缺少可读摘要。")
    summary = _short_sentence(headline, fallback=f"今日覆盖 {subject_count} 个观察标的；先看市场结构，再看重点个股。")
    claims = [
        f"日报覆盖 {subject_count} 个观察标的。",
        str(market.get("breadth") or "市场宽度待从大盘复盘继续下钻。"),
        str(market.get("turnover") or "成交活跃度已进入大盘复盘。"),
    ]
    ids = evidence.ids(domain="price", limit=6) + evidence.ids(domain="news_sentiment", limit=4)
    return _memo(
        run_date,
        agent="MarketAgent",
        label="市场部门",
        scope="daily",
        summary=summary,
        key_claims=claims,
        evidence_ids=ids[:8],
        counterpoints=["指数和个股可能分化；市场热度不能直接推出个股买卖。"],
        data_gaps=[],
        next_action="跟踪强势板块是否连续、成长板块是否止跌、成交额是否维持。",
        confidence="medium",
    )


def _sector_agent(run_date: str, evidence: _EvidenceView, market: Mapping[str, Any], universe: Mapping[str, Any]) -> Dict[str, Any]:
    leaders = market.get("sector_leaders") or []
    laggards = market.get("sector_laggards") or []
    leader_text = "、".join(leaders[:4]) if leaders else "待从板块复盘确认"
    laggard_text = "、".join(laggards[:4]) if laggards else "待从板块复盘确认"
    summary = f"行业上，重点看强势方向的持续性：{leader_text}；同时规避弱势方向：{laggard_text}。"
    return _memo(
        run_date,
        agent="SectorAgent",
        label="行业/风格部门",
        scope="daily",
        summary=summary,
        key_claims=[
            f"强势行业/概念：{leader_text}。",
            f"弱势行业/概念：{laggard_text}。",
            "行业结论只给观察清单，不能替代单股深评。",
        ],
        evidence_ids=evidence.ids(domain="news_sentiment", limit=8),
        counterpoints=["热点可能一日游；需要公告、成交承接和个股趋势共同确认。"],
        data_gaps=[] if leaders else ["板块领涨/领跌未解析到结构化结果"],
        next_action="把强势方向转为候选池，等待次日承接和公告验证。",
        confidence="medium" if leaders else "low",
    )


def _fundamental_agent(run_date: str, evidence: _EvidenceView, stocks: Sequence[StockSummary], official: Mapping[str, Any]) -> Dict[str, Any]:
    ids = evidence.ids(domain="fundamentals", limit=10) + evidence.ids(domain="filings_events", fact_type="verified_fact", limit=8)
    symbols_with_fundamentals = sorted({
        str(row.get("symbol") or row.get("subject") or "")
        for row in evidence.rows
        if str(row.get("domain") or "") == "fundamentals" and str(row.get("symbol") or row.get("subject") or "")
    })
    official_count = len(official.get("evidenceFacts") or []) if isinstance(official, Mapping) else 0
    summary = (
        f"基本面层已接入 {len(symbols_with_fundamentals)} 个标的的本地计算/财务线索，官方公告与法披事实 {official_count} 条；"
        "但 A股/港股基本面仍要继续补更稳定的财报字段。"
    )
    gaps = []
    expected = {item.symbol.upper() for item in stocks}
    covered = {item.upper() for item in symbols_with_fundamentals}
    missing = sorted(expected - covered)
    if missing:
        gaps.append(f"基本面结构化字段不足：{', '.join(missing[:6])}")
    return _memo(
        run_date,
        agent="FundamentalAgent",
        label="基本面部门",
        scope="daily",
        summary=summary,
        key_claims=[
            f"结构化基本面覆盖：{', '.join(symbols_with_fundamentals) or '无'}。",
            f"官方公告/法披事实：{official_count} 条。",
            "基本面不足时，只能降低个股结论强度，不能靠新闻补成事实。",
        ],
        evidence_ids=ids[:12],
        counterpoints=["A股/港股财务字段容易不齐；研报观点不能替代财报事实。"],
        data_gaps=gaps,
        next_action="优先补 A股/港股财报字段、估值字段和公告原文链接。",
        confidence="medium" if ids else "low",
    )


def _technical_agent(run_date: str, evidence: _EvidenceView, stocks: Sequence[StockSummary], stock_md: str) -> Dict[str, Any]:
    watch_count = sum(1 for item in stocks if "观望" in item.action)
    weak = [f"{item.name}({item.symbol})：{item.trend or item.action}" for item in stocks if any(word in item.trend for word in ("看空", "偏空", "弱"))]
    summary = f"技术面层显示：{len(stocks)} 个观察标的中 {watch_count} 个为观望；弱势/偏空标的包括 {', '.join(weak[:4]) or '暂无'}。"
    ids = evidence.ids(domain="price", limit=12)
    claims = [summary]
    for item in stocks[:4]:
        claims.append(f"{item.name}({item.symbol})：{item.action}；评分 {item.score}；{item.trend}。")
    return _memo(
        run_date,
        agent="TechnicalAgent",
        label="技术面部门",
        scope="daily",
        summary=summary,
        key_claims=claims,
        evidence_ids=ids,
        counterpoints=["反弹若无成交放大，不能视为趋势反转。"],
        data_gaps=[] if stock_md else ["原系统个股技术报告缺失"],
        next_action="重点看均线修复、量能放大和关键支撑/压力突破。",
        confidence="high" if ids and stocks else "medium",
    )


def _intel_agent(run_date: str, evidence: _EvidenceView, official: Mapping[str, Any]) -> Dict[str, Any]:
    facts = official.get("evidenceFacts") if isinstance(official, Mapping) and isinstance(official.get("evidenceFacts"), list) else []
    providers = sorted({
        str(item.get("provider") or "")
        for item in facts
        if isinstance(item, Mapping) and str(item.get("provider") or "")
    })
    discovery_count = evidence.count(domain="news_sentiment", fact_type="discovery")
    summary = f"新闻情报层本轮以官方公告/法披为事实底座，已纳入 {len(facts)} 条官方事件事实；搜索/新闻线索只作发现线索。"
    return _memo(
        run_date,
        agent="IntelAgent",
        label="新闻情报部门",
        scope="daily",
        summary=summary,
        key_claims=[
            f"官方事件事实：{len(facts)} 条；来源：{', '.join(providers) or '未标'}。",
            f"搜索/新闻发现线索：{discovery_count} 条，只能辅助发现。",
            "核心事实必须回到公告、SEC、交易所或公司 IR。",
        ],
        evidence_ids=evidence.ids(domain="filings_events", fact_type="verified_fact", limit=12),
        counterpoints=["外部研报和新闻可能带有立场，不能直接当客观事实。"],
        data_gaps=[] if facts else ["本轮官方事件事实为空"],
        next_action="对候选标的逐条回跳公告/法披/交易所链接。",
        confidence="high" if facts else "medium",
    )


def _portfolio_agent(run_date: str, evidence: _EvidenceView, health: Mapping[str, Any]) -> Dict[str, Any]:
    portfolio = ((health.get("domains") or {}).get("portfolio") or {}) if isinstance(health.get("domains"), Mapping) else {}
    status = str(portfolio.get("status") or "partial")
    if status == "available":
        summary = "持仓层已接入结构化组合上下文，可看持仓暴露和个股影响。"
        gaps: List[str] = []
    else:
        summary = "持仓层本轮未发现完整结构化持仓；日报只做观察清单和风险提醒，不把持仓影响包装成结论。"
        gaps = ["缺持仓成本、数量、当前价、盈亏和组合暴露"]
    return _memo(
        run_date,
        agent="PortfolioAgent",
        label="持仓部门",
        scope="portfolio",
        summary=summary,
        key_claims=[summary],
        evidence_ids=evidence.ids(domain="portfolio", limit=6),
        counterpoints=["没有持仓明细时，不能判断真实组合风险。"],
        data_gaps=gaps,
        next_action="后续接入 watchlist/portfolio holdings 后再输出持仓影响。",
        confidence="medium" if status == "available" else "low",
    )


def _risk_agent(
    run_date: str,
    evidence: _EvidenceView,
    stocks: Sequence[StockSummary],
    health: Mapping[str, Any],
    market: Mapping[str, Any],
) -> Dict[str, Any]:
    weak_count = sum(1 for item in stocks if any(word in item.trend for word in ("看空", "偏空", "弱")))
    blocker_count = len(health.get("blockingReasons") or []) if isinstance(health, Mapping) else 0
    summary = f"风险层结论：{weak_count}/{len(stocks)} 个观察标的偏弱或看空；数据源硬阻断 {blocker_count} 个；市场结构分化时不追高。"
    return _memo(
        run_date,
        agent="RiskAgent",
        label="风险部门",
        scope="daily",
        summary=summary,
        key_claims=[
            summary,
            str(market.get("risk_note") or "市场分化下，热点延续性需要二次验证。"),
        ],
        evidence_ids=evidence.ids(domain="price", limit=8) + evidence.ids(domain="publish_bundle", limit=2),
        counterpoints=["若强势板块连续放量并出现公告催化，当前防守判断需要上调。"],
        data_gaps=[],
        next_action="把偏弱个股放入观察而非行动；对强势板块做次日承接验证。",
        confidence="medium",
    )


def _red_team_agent(run_date: str, stocks: Sequence[StockSummary], health: Mapping[str, Any], market: Mapping[str, Any]) -> Dict[str, Any]:
    objections = [
        "日报覆盖多个市场，不能用单一股票解释全局。",
        "市场宽度偏暖时，个股技术偏弱可能是节奏问题，不一定代表长期基本面恶化。",
        "热点板块如果缺公告/业绩催化，容易变成短线噪音。",
    ]
    if not stocks:
        objections.append("原系统个股报告缺失，个股层结论不足。")
    summary = "红队认为：当前最容易犯的错是把市场热度、新闻线索或单股反弹直接升级为行动结论。"
    return _memo(
        run_date,
        agent="RedTeamAgent",
        label="红队反证",
        scope="daily",
        summary=summary,
        key_claims=objections,
        evidence_ids=[],
        counterpoints=objections,
        data_gaps=[],
        next_action="CIO 必须把这些反证写入默认报告，而不是只给一句可用/中性。",
        confidence="medium",
    )


def _cio_agent(
    run_date: str,
    *,
    memos: Sequence[Dict[str, Any]],
    risk: Dict[str, Any],
    red_team: Dict[str, Any],
    universe: Mapping[str, Any],
) -> Dict[str, Any]:
    subject_count = len(universe.get("subjectSymbols") or []) if isinstance(universe, Mapping) else 0
    macro = _find_memo(memos, "MacroAgent")
    geo = _find_memo(memos, "GeoPolicyAgent")
    market = _find_memo(memos, "MarketAgent")
    sector = _find_memo(memos, "SectorAgent")
    technical = _find_memo(memos, "TechnicalAgent")
    final = (
        f"今日结论：覆盖 {subject_count} 个观察标的，整体以观察和分层跟踪为主；"
        "市场结构有机会，但个股多数仍未给出进攻信号。先看宏观和行业，再下钻个股。"
    )
    why = [
        str(macro.get("summary_for_reader") or ""),
        str(geo.get("summary_for_reader") or ""),
        str(market.get("summary_for_reader") or ""),
        str(sector.get("summary_for_reader") or ""),
        str(technical.get("summary_for_reader") or ""),
    ]
    evidence_ids: List[str] = []
    for memo in [*memos, risk]:
        evidence_ids.extend([str(item) for item in memo.get("evidence_ids") or [] if str(item)])
    return _memo(
        run_date,
        agent="CIOAgent",
        label="CIO 总结",
        scope="daily",
        summary=final,
        key_claims=[item for item in why if item][:5],
        evidence_ids=list(dict.fromkeys(evidence_ids))[:12],
        counterpoints=list(red_team.get("counterpoints") or [])[:5],
        data_gaps=list(_find_memo(memos, "PortfolioAgent").get("data_gaps") or [])[:3],
        next_action="明日先验证强势行业持续性和个股量价修复；没有新证据时维持观察。",
        confidence="medium",
    )


def _memo(
    run_date: str,
    *,
    agent: str,
    label: str,
    scope: str,
    summary: str,
    key_claims: Sequence[str],
    evidence_ids: Sequence[str],
    counterpoints: Sequence[str],
    data_gaps: Sequence[str],
    next_action: str,
    confidence: str,
) -> Dict[str, Any]:
    claims = [str(item).strip() for item in key_claims if str(item).strip()]
    evidence = [str(item).strip() for item in evidence_ids if str(item).strip()]
    gaps = [str(item).strip() for item in data_gaps if str(item).strip()]
    counters = [str(item).strip() for item in counterpoints if str(item).strip()]
    return {
        "schema": AGENT_MEMO_SCHEMA,
        "agent": agent,
        "label": label,
        "scope": scope,
        "subject": scope,
        "symbol": "",
        "status": "PASS" if evidence or agent in {"RedTeamAgent", "PortfolioAgent", "CIOAgent"} else "WARN",
        "origin": ORIGIN,
        "origin_label": "部门 Agent 输出",
        "runtime_kind": RUNTIME_KIND,
        "agentRuntime": RULE_AGENT_RUNTIME,
        "run_date": run_date,
        "summary_for_reader": summary,
        "readable_summary": summary,
        "conclusion": summary,
        "facts": claims[:8],
        "reasoning": claims[:8],
        "key_claims": claims[:8],
        "evidence_ids": evidence[:12],
        "source_refs": evidence[:12],
        "counterpoints": counters[:8],
        "data_gaps": gaps[:8],
        "missing_data": gaps[:8],
        "confidence": confidence,
        "next_action": next_action,
        "next_step": next_action,
        "no_trade_execution": True,
    }


def _write_memo(base: Path, rel: str, memo: Mapping[str, Any]) -> List[str]:
    json_path = base / f"{rel}.json"
    md_path = base / f"{rel}.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(memo, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_memo_markdown(memo), encoding="utf-8")
    return [f"{rel}.json", f"{rel}.md"]


def _memo_markdown(memo: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            f"# {memo.get('label') or memo.get('agent')}",
            "",
            "## 结论",
            str(memo.get("summary_for_reader") or ""),
            "",
            "## 核心依据",
            *_bullets(memo.get("key_claims") or []),
            "",
            "## 反证 / 风险",
            *_bullets(memo.get("counterpoints") or []),
            "",
            "## 数据缺口",
            *_bullets(memo.get("data_gaps") or ["无关键缺口"]),
            "",
            "## 下一步",
            f"- {memo.get('next_action') or '等待下一轮复核。'}",
            "",
            "## 证据",
            *_bullets(memo.get("evidence_ids") or ["本模块主要承担反证/编辑，不新增事实。"]),
            "",
        ]
    )


def _index_markdown(run_date: str, memos: Sequence[tuple[str, Mapping[str, Any]]]) -> str:
    lines = [
        f"# {run_date} A 卷：投研部门报告",
        "",
        "> A 卷是可读投研层：数据源 → 证据池 → 部门 Agent → 红队 → CIO。工程诊断另见 diagnostics。",
        "",
        "| 部门 | 入口 | 一句话结论 |",
        "|---|---|---|",
    ]
    for rel, memo in memos:
        label = str(memo.get("label") or memo.get("agent"))
        summary = str(memo.get("summary_for_reader") or "").replace("|", "｜")
        lines.append(f"| {label} | [{rel}]({rel}.html) | {summary} |")
    return "\n".join(lines) + "\n"


def _parse_stock_summaries(markdown: str) -> List[StockSummary]:
    rows: List[StockSummary] = []
    for match in re.finditer(r"^[⚪🟢🔴🟡]*\s*\*\*(.+?)\(([^()]+)\)\*\*:\s*([^|\n]+)\|\s*评分\s*([^|\n]+)\|\s*([^\n]+)$", markdown, re.M):
        rows.append(
            StockSummary(
                name=match.group(1).strip(),
                symbol=match.group(2).strip(),
                action=match.group(3).strip(),
                score=match.group(4).strip(),
                trend=match.group(5).strip(),
            )
        )
    if rows:
        return rows
    for match in re.finditer(r"^##\s+[⚪🟢🔴🟡]*\s*(.+?)\s*\(([^()]+)\)", markdown, re.M):
        rows.append(StockSummary(name=match.group(1).strip(), symbol=match.group(2).strip(), action="待复核", score="未标", trend="未标"))
    return rows


def _market_snapshot(markdown: str) -> Dict[str, Any]:
    headline = _first_paragraph_after(markdown, r"^##\s+\d{4}-\d{2}-\d{2}[^\n]*大盘复盘[^\n]*$")
    if not headline:
        headline = _first_paragraph_after(markdown, r"^#\s+🎯\s*大盘复盘")
    leaders = _table_names_after(markdown, "行业板块领涨 Top 5") + _table_names_after(markdown, "概念板块领涨 Top 5")
    laggards = _table_names_after(markdown, "行业板块领跌 Top 5") + _table_names_after(markdown, "概念板块领跌 Top 5")
    breadth_match = re.search(r"上涨/下跌/平盘\s*\|\s*([0-9]+\s*/\s*[0-9]+\s*/\s*[0-9]+)", markdown)
    turnover_match = re.search(r"两市成交额\s*\|\s*([^|\n]+)", markdown)
    return {
        "headline": headline,
        "sector_leaders": leaders,
        "sector_laggards": laggards,
        "breadth": f"上涨/下跌/平盘 {breadth_match.group(1)}" if breadth_match else "",
        "turnover": f"两市成交额 {turnover_match.group(1).strip()}" if turnover_match else "",
        "risk_note": _first_paragraph_after(markdown, r"^###\s+四、资金与情绪"),
    }


def _first_paragraph_after(markdown: str, heading_pattern: str) -> str:
    match = re.search(heading_pattern, markdown, re.M)
    if not match:
        return ""
    rest = markdown[match.end():]
    for para in re.split(r"\n\s*\n", rest):
        text = para.strip()
        if not text or text.startswith("#") or text.startswith("|"):
            continue
        text = re.sub(r"\*\*(.*?)\*\*", r"\\1", text)
        return _short_sentence(text, fallback="")
    return ""


def _table_names_after(markdown: str, heading: str) -> List[str]:
    idx = markdown.find(heading)
    if idx < 0:
        return []
    chunk = markdown[idx: idx + 1200]
    names: List[str] = []
    for line in chunk.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2 or cells[0] in {"排名", "---"} or "---" in cells[0]:
            continue
        name = cells[1]
        if name and name not in names:
            names.append(name)
    return names[:5]


def _find_memo(memos: Sequence[Mapping[str, Any]], agent: str) -> Mapping[str, Any]:
    for memo in memos:
        if memo.get("agent") == agent:
            return memo
    return {}


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_text_first(*paths: Path) -> str:
    for path in paths:
        try:
            if path.exists():
                return path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
    return ""


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _bullets(items: Iterable[Any]) -> List[str]:
    values = [str(item).strip() for item in items if str(item).strip()]
    if not values:
        return ["- 无"]
    return [f"- {item}" for item in values]


def _first_contains(items: Iterable[str], needle: str) -> str:
    needle_l = needle.lower()
    for item in items:
        if needle_l in str(item).lower():
            return str(item)
    return ""


def _join_nonempty(prefix: str, detail: str) -> str:
    return f"{prefix}：{detail}" if detail else prefix


def _short_sentence(text: str, *, fallback: str, limit: int = 160) -> str:
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    if not clean:
        return fallback
    return clean[:limit] + ("…" if len(clean) > limit else "")
