"""Provider capability registry for free-first data governance."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List


DEFAULT_PROVIDER_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    "EfinanceFetcher": {
        "markets": ["cn"],
        "domains": ["price"],
        "fields": ["quote", "daily", "volume"],
        "credentialRequired": False,
        "sourceTier": "free",
        "freshnessSla": "market_day",
    },
    "AkshareFetcher": {
        "markets": ["cn", "hk"],
        "domains": ["price", "fundamentals", "filings_events", "macro"],
        "fields": ["quote", "daily", "valuation", "capital_flow", "macro"],
        "credentialRequired": False,
        "sourceTier": "free_aggregator",
        "freshnessSla": "best_effort",
    },
    "AKShare": {
        "markets": ["cn", "hk"],
        "domains": ["price", "fundamentals", "filings_events", "macro"],
        "fields": ["quote", "daily", "valuation", "capital_flow", "macro"],
        "credentialRequired": False,
        "sourceTier": "free_aggregator",
        "freshnessSla": "best_effort",
    },
    "Eastmoney": {
        "markets": ["cn"],
        "domains": ["price", "fundamentals", "news_sentiment"],
        "fields": ["quote", "daily", "valuation", "capital_flow"],
        "credentialRequired": False,
        "sourceTier": "free_aggregator",
        "freshnessSla": "best_effort",
    },
    "PytdxFetcher": {
        "markets": ["cn"],
        "domains": ["price"],
        "fields": ["quote", "daily"],
        "credentialRequired": False,
        "sourceTier": "free",
        "freshnessSla": "market_day",
    },
    "BaostockFetcher": {
        "markets": ["cn"],
        "domains": ["price"],
        "fields": ["daily"],
        "credentialRequired": False,
        "sourceTier": "free",
        "freshnessSla": "market_day",
    },
    "YfinanceFetcher": {
        "markets": ["cn", "hk", "us"],
        "domains": ["price", "fundamentals"],
        "fields": ["quote", "daily", "valuation", "statements"],
        "credentialRequired": False,
        "sourceTier": "free_aggregator",
        "freshnessSla": "best_effort",
    },
    "TushareFetcher": {
        "markets": ["cn", "hk"],
        "domains": ["price", "fundamentals", "filings_events"],
        "fields": ["quote", "daily", "stock_basic", "fina_indicator"],
        "credentialRequired": True,
        "sourceTier": "optional_free_tier",
        "freshnessSla": "market_day",
    },
    "Tushare": {
        "markets": ["cn", "hk"],
        "domains": ["price", "fundamentals", "filings_events"],
        "fields": ["quote", "daily", "stock_basic", "fina_indicator"],
        "credentialRequired": True,
        "sourceTier": "optional_free_tier",
        "freshnessSla": "market_day",
    },
    "TickFlowFetcher": {
        "markets": ["cn"],
        "domains": ["price"],
        "fields": ["index_quote", "breadth"],
        "credentialRequired": True,
        "sourceTier": "optional_disabled",
        "freshnessSla": "market_day",
    },
    "LongbridgeFetcher": {
        "markets": ["hk", "us"],
        "domains": ["price", "fundamentals"],
        "fields": ["quote", "daily", "turnover", "pe", "pb"],
        "credentialRequired": True,
        "sourceTier": "optional_disabled",
        "freshnessSla": "market_day",
    },
    "FinnhubFetcher": {
        "markets": ["us"],
        "domains": ["price", "news_sentiment", "fundamentals"],
        "fields": ["quote", "candle", "company_news", "metrics"],
        "credentialRequired": True,
        "sourceTier": "optional_free_tier",
        "freshnessSla": "best_effort",
    },
    "AlphaVantageFetcher": {
        "markets": ["us"],
        "domains": ["price", "fundamentals", "macro", "news_sentiment"],
        "fields": ["time_series", "overview", "income_statement", "news_sentiment"],
        "credentialRequired": True,
        "sourceTier": "optional_free_tier",
        "freshnessSla": "best_effort",
    },
    "FMP": {
        "markets": ["us", "macro"],
        "domains": ["price", "fundamentals", "macro"],
        "fields": ["quote", "ratios", "macro_proxy"],
        "credentialRequired": True,
        "sourceTier": "optional_disabled",
        "freshnessSla": "best_effort",
    },
    "Polygon": {
        "markets": ["us"],
        "domains": ["price", "fundamentals", "news_sentiment"],
        "fields": ["quote", "aggregates", "reference", "news"],
        "credentialRequired": True,
        "sourceTier": "optional_disabled",
        "freshnessSla": "best_effort",
    },
    "SEC_EDGAR": {
        "markets": ["us"],
        "domains": ["filings_events", "fundamentals"],
        "fields": ["submissions", "companyfacts", "xbrl_frames"],
        "credentialRequired": False,
        "sourceTier": "official_free",
        "freshnessSla": "official",
    },
    "CNINFO": {
        "markets": ["cn"],
        "domains": ["filings_events"],
        "fields": ["announcements", "disclosure_pdf"],
        "credentialRequired": False,
        "sourceTier": "official_free",
        "freshnessSla": "official",
    },
    "SSE_DISCLOSURE": {
        "markets": ["cn"],
        "domains": ["filings_events"],
        "fields": ["announcements", "disclosure_pdf"],
        "credentialRequired": False,
        "sourceTier": "official_free",
        "freshnessSla": "official",
    },
    "SZSE_DISCLOSURE": {
        "markets": ["cn"],
        "domains": ["filings_events"],
        "fields": ["announcements", "disclosure_pdf"],
        "credentialRequired": False,
        "sourceTier": "official_free",
        "freshnessSla": "official",
    },
    "HKEXNEWS": {
        "markets": ["hk"],
        "domains": ["filings_events"],
        "fields": ["announcements", "disclosure_pdf"],
        "credentialRequired": False,
        "sourceTier": "official_free",
        "freshnessSla": "official",
    },
    "FRED": {
        "markets": ["macro"],
        "domains": ["macro"],
        "fields": ["series_observations", "releases", "sources"],
        "credentialRequired": False,
        "sourceTier": "official_free",
        "freshnessSla": "official",
    },
    "GDELT": {
        "markets": ["global"],
        "domains": ["news_sentiment"],
        "fields": ["events", "gkg", "doc"],
        "credentialRequired": False,
        "sourceTier": "official_free",
        "freshnessSla": "near_realtime",
    },
    "RELIEFWEB": {
        "markets": ["global"],
        "domains": ["news_sentiment"],
        "fields": ["reports", "disasters", "humanitarian_events"],
        "credentialRequired": True,
        "sourceTier": "official_free_requires_appname",
        "freshnessSla": "near_realtime",
        "factType": "discovery",
    },
    "OFAC_SDN": {
        "markets": ["global"],
        "domains": ["filings_events"],
        "fields": ["sanctions_public_list"],
        "credentialRequired": False,
        "sourceTier": "official_free_optional_large_download",
        "freshnessSla": "official",
    },
    "Tavily": {
        "markets": ["global"],
        "domains": ["news_sentiment"],
        "fields": ["search_results"],
        "credentialRequired": True,
        "sourceTier": "optional_free_tier_discovery",
        "freshnessSla": "best_effort",
        "factType": "discovery",
    },
    "SerpAPI": {
        "markets": ["global"],
        "domains": ["news_sentiment"],
        "fields": ["search_results"],
        "credentialRequired": True,
        "sourceTier": "optional_free_tier_discovery",
        "freshnessSla": "best_effort",
        "factType": "discovery",
    },
    "Brave": {
        "markets": ["global"],
        "domains": ["news_sentiment"],
        "fields": ["search_results"],
        "credentialRequired": True,
        "sourceTier": "optional_disabled",
        "freshnessSla": "best_effort",
        "factType": "discovery",
    },
    "SearXNG": {
        "markets": ["global"],
        "domains": ["news_sentiment"],
        "fields": ["search_results"],
        "credentialRequired": False,
        "sourceTier": "free_self_host_or_public",
        "freshnessSla": "best_effort",
        "factType": "discovery",
    },
    "PagesValidator": {
        "markets": ["internal"],
        "domains": ["publish_bundle"],
        "fields": ["required_files", "links", "legacy_public_files", "snapshot_chain"],
        "credentialRequired": False,
        "sourceTier": "internal_derived",
        "freshnessSla": "run_scoped",
        "factType": "derived_fact",
    },
    "agent_memo": {
        "markets": ["internal"],
        "domains": ["agent_memos"],
        "fields": ["source_refs", "missing_evidence", "runtime_context"],
        "credentialRequired": False,
        "sourceTier": "internal_derived",
        "freshnessSla": "run_scoped",
    },
    "market_cycle": {
        "markets": ["internal"],
        "domains": ["publish_bundle", "macro", "news_sentiment"],
        "fields": ["daily_cycle_json", "evidence_refs"],
        "credentialRequired": False,
        "sourceTier": "internal_derived",
        "freshnessSla": "run_scoped",
    },
    "source_health_v1": {
        "markets": ["internal"],
        "domains": ["publish_bundle"],
        "fields": ["legacy_source_health"],
        "credentialRequired": False,
        "sourceTier": "internal_derived",
        "freshnessSla": "run_scoped",
    },
    "screening_funnel": {
        "markets": ["internal"],
        "domains": ["news_sentiment"],
        "fields": ["candidate_queue", "screening"],
        "credentialRequired": False,
        "sourceTier": "internal_derived",
        "freshnessSla": "run_scoped",
    },
    "Polymarket": {
        "markets": ["global"],
        "domains": ["macro"],
        "fields": ["prediction_market"],
        "credentialRequired": False,
        "sourceTier": "optional_discovery",
        "freshnessSla": "best_effort",
    },
    "src.prediction_market.polymarket": {
        "markets": ["global"],
        "domains": ["macro"],
        "fields": ["prediction_market"],
        "credentialRequired": False,
        "sourceTier": "optional_discovery",
        "freshnessSla": "best_effort",
    },
    "src.macro.official_sources": {
        "markets": ["macro"],
        "domains": ["macro"],
        "fields": ["macro_context"],
        "credentialRequired": False,
        "sourceTier": "official_free",
        "freshnessSla": "official",
    },
    "src.macro.review": {
        "markets": ["macro"],
        "domains": ["macro"],
        "fields": ["macro_review"],
        "credentialRequired": False,
        "sourceTier": "internal_derived",
        "freshnessSla": "run_scoped",
    },
}


def normalize_provider_name(provider: Any) -> str:
    return str(provider or "unknown").strip() or "unknown"


def provider_capability(provider: Any) -> Dict[str, Any]:
    name = normalize_provider_name(provider)
    payload = deepcopy(DEFAULT_PROVIDER_CAPABILITIES.get(name) or {})
    payload.setdefault("provider", name)
    payload.setdefault("markets", ["unknown"])
    payload.setdefault("domains", ["unknown"])
    payload.setdefault("fields", [])
    payload.setdefault("credentialRequired", False)
    payload.setdefault("sourceTier", "unknown")
    payload.setdefault("freshnessSla", "unknown")
    return payload


def providers_for_domain(domain: str, *, free_first: bool = True) -> List[Dict[str, Any]]:
    rows = [
        provider_capability(name)
        for name, spec in DEFAULT_PROVIDER_CAPABILITIES.items()
        if domain in (spec.get("domains") or [])
    ]
    if free_first:
        rows.sort(key=lambda item: (str(item.get("sourceTier")).startswith("optional_"), item["provider"]))
    return rows


def all_provider_capabilities() -> Iterable[Dict[str, Any]]:
    for name in sorted(DEFAULT_PROVIDER_CAPABILITIES):
        yield provider_capability(name)
