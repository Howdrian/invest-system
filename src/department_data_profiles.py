# -*- coding: utf-8 -*-
"""Department input profiles for the daily research workflow.

The profiles are a contract between the evidence/original-analysis layer and the
LLM/rule department agents.  They keep the v1.3 flow simple: every department
gets a bounded, pre-built information pack; agents do not fetch data by
calling providers or reading local files directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Sequence


@dataclass(frozen=True)
class DepartmentDataProfile:
    agent: str
    input_profile: str
    source_kinds: tuple[str, ...]
    original_kinds: tuple[str, ...]
    evidence_domains: tuple[str, ...]
    description: str


DEPARTMENT_DATA_PROFILES: tuple[DepartmentDataProfile, ...] = (
    DepartmentDataProfile(
        agent="MacroAgent",
        input_profile="macro",
        source_kinds=("fred", "market_cycle", "rates", "dollar", "energy"),
        original_kinds=("macro_context",),
        evidence_domains=("macro",),
        description="宏观、利率、流动性、通胀、美元、能源和市场周期。",
    ),
    DepartmentDataProfile(
        agent="GeoPolicyAgent",
        input_profile="geo_policy",
        source_kinds=("official_policy", "tavily", "gdelt", "rss", "sellside_opinion"),
        original_kinds=("geo_policy_seed", "intel_events"),
        evidence_domains=("macro", "news_sentiment", "filings_events"),
        description="地缘、贸易、制裁、冲突、政策事件及其市场传导。",
    ),
    DepartmentDataProfile(
        agent="MarketAgent",
        input_profile="market",
        source_kinds=("market_review", "main_indices", "market_stats", "market_light"),
        original_kinds=("market_review", "market_snapshot"),
        evidence_domains=("price", "macro", "news_sentiment"),
        description="大盘结构、市场宽度、指数、资金面和风险偏好。",
    ),
    DepartmentDataProfile(
        agent="SectorAgent",
        input_profile="sector_candidates",
        source_kinds=("sector_rankings", "concept_rankings", "hot_stocks", "screening"),
        original_kinds=("screening", "sector_candidates"),
        evidence_domains=("news_sentiment", "price", "filings_events"),
        description="强弱行业、热点链条、候选池和持续性。",
    ),
    DepartmentDataProfile(
        agent="FundamentalAgent",
        input_profile="fundamentals",
        source_kinds=("stock_analysis", "fundamental_context", "sec", "cninfo", "hkex", "sse", "szse"),
        original_kinds=("stock_analysis_context", "fundamental_context"),
        evidence_domains=("fundamentals", "filings_events"),
        description="个股基本面、估值、财报、公告和法披。",
    ),
    DepartmentDataProfile(
        agent="TechnicalAgent",
        input_profile="technical",
        source_kinds=("stock_analysis", "daily_data", "technical_indicators", "kline", "volume_price"),
        original_kinds=("technical_context", "stock_analysis_context"),
        evidence_domains=("price",),
        description="K 线、趋势、量价、技术指标、支撑和压力。",
    ),
    DepartmentDataProfile(
        agent="IntelAgent",
        input_profile="intel",
        source_kinds=("announcements", "intelligence_sources", "tavily", "gdelt", "sellside_opinion"),
        original_kinds=("intel_events", "stock_analysis_context"),
        evidence_domains=("filings_events", "news_sentiment"),
        description="公告、新闻、舆情、研报观点和事件线索。",
    ),
    DepartmentDataProfile(
        agent="PortfolioAgent",
        input_profile="portfolio",
        source_kinds=("portfolio_snapshot", "watchlist", "portfolio_risk"),
        original_kinds=("portfolio_snapshot", "watchlist_snapshot"),
        evidence_domains=("portfolio", "price", "fundamentals"),
        description="持仓、watchlist、组合暴露和持仓风险。",
    ),
    DepartmentDataProfile(
        agent="RiskAgent",
        input_profile="risk",
        source_kinds=("department_summaries", "decision_signals", "risk_evidence"),
        original_kinds=("decision_signals", "portfolio_snapshot", "market_review"),
        evidence_domains=("price", "fundamentals", "filings_events", "macro", "news_sentiment", "portfolio"),
        description="风险、反证、异常缺口、决策信号和不应行动条件。",
    ),
    DepartmentDataProfile(
        agent="RedTeamAgent",
        input_profile="red_team",
        source_kinds=("department_summaries", "risk_output", "core_evidence"),
        original_kinds=("decision_signals", "market_review"),
        evidence_domains=("price", "fundamentals", "filings_events", "macro", "news_sentiment", "portfolio"),
        description="反驳前面结论，找证据跳跃、偏见和 discovery 误用。",
    ),
    DepartmentDataProfile(
        agent="CIOAgent",
        input_profile="cio",
        source_kinds=("department_summaries", "red_team", "risk", "core_evidence", "source_health"),
        original_kinds=("market_review", "decision_signals", "portfolio_snapshot", "history_summary"),
        evidence_domains=("price", "fundamentals", "filings_events", "macro", "news_sentiment", "portfolio"),
        description="最终编辑，读部门结论、红队、风险、核心证据和数据可信度。",
    ),
)

_PROFILE_BY_AGENT = {profile.agent: profile for profile in DEPARTMENT_DATA_PROFILES}


def department_profile(agent: str) -> DepartmentDataProfile | None:
    return _PROFILE_BY_AGENT.get(str(agent or ""))


def department_profile_payload(agent: str) -> Dict[str, Any]:
    profile = department_profile(agent)
    if profile is None:
        return {
            "agent": agent,
            "inputProfile": "unknown",
            "sourceKinds": [],
            "originalKinds": [],
            "evidenceDomains": [],
            "description": "未登记部门信息包。",
        }
    return {
        "agent": profile.agent,
        "inputProfile": profile.input_profile,
        "sourceKinds": list(profile.source_kinds),
        "originalKinds": list(profile.original_kinds),
        "evidenceDomains": list(profile.evidence_domains),
        "description": profile.description,
    }


def filter_original_refs_for_agent(refs: Sequence[Mapping[str, Any]], agent: str, *, limit: int = 10) -> List[Dict[str, Any]]:
    profile = department_profile(agent)
    allowed_kinds = set(profile.original_kinds if profile else ())
    out: List[Dict[str, Any]] = []
    for row in refs:
        if not isinstance(row, Mapping):
            continue
        targets = {str(item) for item in row.get("agentTargets") or [] if str(item)}
        kind = str(row.get("kind") or "")
        if agent not in targets and (allowed_kinds and kind not in allowed_kinds):
            continue
        out.append(
            {
                "kind": kind,
                "status": row.get("status"),
                "summary": row.get("summary"),
                "sourceKind": row.get("sourceKind"),
                "recordId": row.get("recordId"),
                "queryId": row.get("queryId"),
                "createdAt": row.get("createdAt"),
                "contentSha256": row.get("contentSha256"),
                "analysis": dict(row.get("analysis") or {}) if isinstance(row.get("analysis"), Mapping) else {},
                "evidenceIds": list(row.get("evidenceIds") or [])[:12],
                "symbols": list(row.get("symbols") or [])[:12],
            }
        )
        if len(out) >= limit:
            break
    return out


def build_department_inputs(
    department_reports: Sequence[Mapping[str, Any]],
    *,
    original_refs: Sequence[Mapping[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    refs = list(original_refs or [])
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for row in department_reports:
        if not isinstance(row, Mapping):
            continue
        agent = str(row.get("agent") or "")
        if not agent or agent in seen:
            continue
        seen.add(agent)
        payload = department_profile_payload(agent)
        payload["evidenceIds"] = [str(item) for item in row.get("evidenceIds") or [] if str(item)][:12]
        payload["originalAnalysisRefs"] = filter_original_refs_for_agent(refs, agent, limit=8)
        out.append(payload)
    for profile in DEPARTMENT_DATA_PROFILES:
        if profile.agent in seen:
            continue
        payload = department_profile_payload(profile.agent)
        payload["evidenceIds"] = []
        payload["originalAnalysisRefs"] = filter_original_refs_for_agent(refs, profile.agent, limit=8)
        out.append(payload)
    return out
