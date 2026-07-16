"""Product-facing Source Health v2 policy."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .evidence_ledger import has_fact_source, normalize_evidence_fact
from .provider_registry import provider_capability


DOMAINS = (
    "price",
    "fundamentals",
    "filings_events",
    "macro",
    "news_sentiment",
    "portfolio",
    "publish_bundle",
    "agent_memos",
)

_DOMAIN_LABELS = {
    "price": "行情/K线",
    "fundamentals": "基本面",
    "filings_events": "公告/事件",
    "macro": "宏观",
    "news_sentiment": "新闻/舆情",
    "portfolio": "持仓/组合",
    "publish_bundle": "发布包",
    "agent_memos": "Agent 卷宗",
}

_STATUS_SCORE = {
    "available": 1.0,
    "partial": 0.65,
    "degraded": 0.45,
    "missing": 0.0,
    "blocked": 0.0,
}

POSITION_SIZING_MISSING_CRITICAL_THRESHOLD = 20

_CLAIM_REQUIREMENTS = {
    "score": {
        "label": "评分",
        "domains": ("price", "fundamentals", "filings_events", "macro"),
    },
    "actionable_advice": {
        "label": "交易建议",
        "domains": ("filings_events", "macro", "news_sentiment"),
    },
    "position_sizing": {
        "label": "仓位建议",
        "domains": ("price", "fundamentals", "macro"),
    },
    "risk_warning": {
        "label": "风险提示",
        "domains": ("filings_events", "macro", "news_sentiment"),
    },
}


def build_source_health_v2(
    legacy_health: Optional[Mapping[str, Any]],
    *,
    provider_runs: Optional[Iterable[Mapping[str, Any]]] = None,
    evidence_facts: Optional[Iterable[Mapping[str, Any]]] = None,
    agent_origin_counts: Optional[Mapping[str, int]] = None,
    subject_symbols: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    """Build additive product data-confidence payload.

    This function is fail-open and deterministic. It does not call networks.
    """

    legacy = legacy_health if isinstance(legacy_health, Mapping) else {}
    runs = [dict(row) for row in (provider_runs or []) if isinstance(row, Mapping)]
    facts = [normalize_evidence_fact(row) for row in (evidence_facts or []) if isinstance(row, Mapping)]
    counts = dict(agent_origin_counts or {})
    subjects = _normalize_subjects(subject_symbols or [])

    provider_matrix = [_provider_matrix_row(row) for row in runs]
    subject_provider_matrix = [
        row for row in provider_matrix if str(row.get("sourceScope") or "subject_evidence") == "subject_evidence"
    ]
    source_smoke_provider_matrix = [
        row for row in provider_matrix if str(row.get("sourceScope") or "subject_evidence") == "source_smoke"
    ]
    agent_memo_facts = [row for row in facts if _is_agent_memo_fact(row)]
    subject_facts = [
        row
        for row in facts
        if str(row.get("evidence_scope") or "subject_evidence") == "subject_evidence"
        and not _is_agent_memo_fact(row)
    ]
    source_smoke_facts = [
        row for row in facts if str(row.get("evidence_scope") or "subject_evidence") == "source_smoke"
    ]
    domains = _base_domains()
    _apply_legacy_health(domains, legacy)
    _apply_provider_runs(domains, subject_provider_matrix)
    _apply_evidence_facts(domains, subject_facts)
    _apply_subject_coverage(domains, subject_provider_matrix, subject_facts, subjects)
    _apply_agent_counts(domains, counts)

    evidence_stats = _evidence_stats(subject_facts, domains)
    overall_score = _overall_score(domains)
    claim_evidence = _claim_evidence(subject_facts, evidence_stats, domains)
    overall_mode = _overall_mode(domains, overall_score, legacy, claim_evidence, evidence_stats)
    claim_policy = _claim_policy(overall_mode, claim_evidence, evidence_stats)

    return {
        "schema": "source_health_v2",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "overallMode": overall_mode,
        "overallScore": overall_score,
        "domains": domains,
        "providerMatrix": provider_matrix,
        "evidenceScopes": {
            "subjectEvidenceFacts": len(subject_facts),
            "sourceSmokeFacts": len(source_smoke_facts),
            "subjectProviderRuns": len(subject_provider_matrix),
            "sourceSmokeProviderRuns": len(source_smoke_provider_matrix),
            "agentMemoFactsExcluded": len(agent_memo_facts),
            "otherProviderRunsExcluded": len(provider_matrix)
            - len(subject_provider_matrix)
            - len(source_smoke_provider_matrix),
        },
        "claimPolicy": claim_policy,
        "claimEvidence": claim_evidence,
        "evidenceStats": evidence_stats,
        "blockingReasons": _blocking_reasons(domains, overall_mode),
    }


def _base_domains() -> Dict[str, Dict[str, Any]]:
    return {
        domain: {
            "label": _DOMAIN_LABELS[domain],
            "status": "missing",
            "coverage": 0.0,
            "freshness": "missing",
            "confidence": "low",
            "blockers": ["not_observed"],
            "repairHints": [_default_repair_hint(domain)],
        }
        for domain in DOMAINS
    }


def _is_agent_memo_fact(fact: Mapping[str, Any]) -> bool:
    provider = str(fact.get("provider") or "").strip().lower()
    fact_id = str(fact.get("id") or "").strip().lower()
    return provider == "agent_memo" or fact_id.startswith("agent_memo:")


def _normalize_subjects(values: Iterable[Any]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        key = text.upper()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out


def _default_repair_hint(domain: str) -> str:
    hints = {
        "price": "补行情/K线 provider run",
        "fundamentals": "补 SEC/财报/估值事实",
        "filings_events": "补公告/SEC/交易所/公司 IR 原文",
        "macro": "补 FRED/官方宏观序列",
        "news_sentiment": "补新闻发现后回跳权威源",
        "portfolio": "补持仓或显式 empty 持仓快照",
        "publish_bundle": "补日报 artifact/pages bundle",
        "agent_memos": "补真实 Agent memo 或明确回填来源",
    }
    return hints.get(domain, "补数据源")


def _set_domain(
    domains: Dict[str, Dict[str, Any]],
    domain: str,
    *,
    status: str,
    coverage: float,
    freshness: str = "fresh",
    confidence: str = "medium",
    blocker: Optional[str] = None,
    repair_hint: Optional[str] = None,
) -> None:
    if domain not in domains:
        return
    row = domains[domain]
    if _STATUS_SCORE.get(status, 0.0) < _STATUS_SCORE.get(str(row.get("status")), 0.0):
        # Keep stronger observed status unless this is a hard blocker.
        if status != "blocked":
            return
    row["status"] = status
    row["coverage"] = max(float(row.get("coverage") or 0.0), max(0.0, min(1.0, float(coverage))))
    row["freshness"] = freshness
    row["confidence"] = confidence
    blockers = [] if status == "available" else list(row.get("blockers") or [])
    if blocker and status != "available" and blocker not in blockers:
        blockers.append(blocker)
    row["blockers"] = blockers
    hints = [] if status == "available" else list(row.get("repairHints") or [])
    if repair_hint and repair_hint not in hints:
        hints.append(repair_hint)
    row["repairHints"] = hints


def _apply_legacy_health(domains: Dict[str, Dict[str, Any]], legacy: Mapping[str, Any]) -> None:
    rows = legacy.get("rows") if isinstance(legacy.get("rows"), list) else []
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        component = str(raw.get("component") or raw.get("source") or "").lower()
        status = _domain_status_from_text(raw.get("usability"), raw.get("status"))
        coverage = _coverage_from_status(status, raw.get("coverage_score"))
        if "macro" in component:
            _set_domain(domains, "macro", status=status, coverage=coverage, blocker="macro_degraded")
        elif "portfolio" in component:
            _set_domain(domains, "portfolio", status=status, coverage=coverage, blocker="portfolio_missing")
        elif "governed" in component or "report" in component:
            _set_domain(domains, "publish_bundle", status=status, coverage=coverage, blocker="publish_incomplete")
        elif "market_heat" in component or "screening" in component or "deep_review" in component:
            _set_domain(domains, "price", status=status, coverage=max(coverage, 0.35), blocker="market_context_degraded")

    text = f"{legacy.get('usability_verdict', '')} {legacy.get('trade_review_usability', '')}".lower()
    if any(token in text for token in ("degraded", "limited", "partial")):
        domains["macro"]["status"] = "degraded" if domains["macro"]["status"] == "missing" else domains["macro"]["status"]
        domains["macro"]["coverage"] = max(float(domains["macro"]["coverage"]), 0.35)
        if "legacy_source_health_limited" not in domains["macro"]["blockers"]:
            domains["macro"]["blockers"].append("legacy_source_health_limited")


def _apply_provider_runs(domains: Dict[str, Dict[str, Any]], matrix: List[Dict[str, Any]]) -> None:
    for row in matrix:
        domain = str(row.get("domain") or "unknown")
        if domain not in domains:
            continue
        status = str(row.get("status") or "")
        if status == "success":
            # A successful call proves provider availability, not that the
            # returned rows substantively support a research conclusion.
            _set_domain(domains, domain, status="partial", coverage=0.55, confidence="medium")
        elif status in {"empty", "partial"}:
            if _is_nonblocking_optional_provider(row):
                continue
            _set_domain(domains, domain, status="partial", coverage=0.55, blocker=status)
        elif status in {"auth_missing", "permission_limited", "rate_limited", "failed", "not_supported"}:
            if _is_nonblocking_optional_provider(row):
                continue
            _set_domain(domains, domain, status="degraded", coverage=0.2, blocker=status, repair_hint=_repair_hint_for_provider(row))


def _apply_evidence_facts(domains: Dict[str, Dict[str, Any]], facts: List[Dict[str, Any]]) -> None:
    reference_date = _latest_evidence_date(facts)
    grouped: Dict[str, List[Dict[str, Any]]] = {domain: [] for domain in domains}
    for fact in facts:
        domain = str(fact.get("domain") or "")
        if domain in grouped:
            grouped[domain].append(fact)

    for domain, rows in grouped.items():
        if not rows:
            continue
        verified = [row for row in rows if str(row.get("fact_type") or "") == "verified_fact" and has_fact_source(row)]
        derived = [row for row in rows if str(row.get("fact_type") or "") == "derived_fact"]
        discovery = [row for row in rows if str(row.get("fact_type") or "") == "discovery"]
        missing = [row for row in rows if str(row.get("fact_type") or "") == "missing"]
        fresh_verified = [row for row in verified if _fact_is_fresh(row, reference_date)]
        fresh_derived = [row for row in derived if _fact_is_fresh(row, reference_date)]

        if fresh_verified:
            _set_domain(domains, domain, status="available", coverage=1.0, freshness="fresh", confidence="high")
        elif fresh_derived:
            _set_domain(domains, domain, status="partial", coverage=0.65, freshness="fresh", confidence="medium")
        elif verified or derived:
            _set_domain(
                domains,
                domain,
                status="partial",
                coverage=0.45,
                freshness="stale",
                confidence="low",
                blocker="stale_evidence",
                repair_hint="刷新该域证据后再提高结论可信度",
            )
        elif discovery:
            _set_domain(
                domains,
                domain,
                status="degraded",
                coverage=0.4,
                freshness="fresh",
                confidence="low",
                blocker="search_only_discovery",
                repair_hint="回跳公告/SEC/交易所/公司 IR 验证",
            )
        elif missing:
            blocker = "verified_fact_missing_source" if any(row.get("missingReason") == "verified_fact_missing_source" for row in missing) else "missing_verified_fact"
            _set_domain(domains, domain, status="missing", coverage=0.0, blocker=blocker)

        if discovery and not verified:
            row = domains[domain]
            blockers = list(row.get("blockers") or [])
            if "search_only_discovery" not in blockers:
                blockers.append("search_only_discovery")
            row["blockers"] = blockers
            hints = list(row.get("repairHints") or [])
            hint = "回跳公告/SEC/交易所/公司 IR 验证"
            if hint not in hints:
                hints.append(hint)
            row["repairHints"] = hints


def _latest_evidence_date(facts: Iterable[Mapping[str, Any]]) -> date:
    dates = [_parse_date(row.get("as_of") or row.get("asOf")) for row in facts]
    return max((value for value in dates if value is not None), default=datetime.now(timezone.utc).date())


def _fact_is_fresh(fact: Mapping[str, Any], reference_date: date) -> bool:
    domain = str(fact.get("domain") or "")
    if domain == "news_sentiment":
        observed_value = (
            fact.get("published_at")
            or fact.get("publishedAt")
            or fact.get("event_time")
            or fact.get("eventTime")
            or fact.get("as_of")
            or fact.get("asOf")
        )
    elif domain == "price":
        observed_value = fact.get("event_time") or fact.get("eventTime") or fact.get("as_of") or fact.get("asOf")
    else:
        observed_value = fact.get("as_of") or fact.get("asOf")
    observed = _parse_date(observed_value)
    if observed is None:
        return False
    age = max(0, (reference_date - observed).days)
    metric = str(fact.get("metric") or fact.get("symbol") or fact.get("subject") or "").upper()
    if domain == "price":
        limit = 5
    elif domain == "news_sentiment":
        limit = 10
    elif domain == "filings_events":
        limit = 90
    elif domain == "fundamentals":
        limit = 190
    elif domain == "macro" and metric in {"GDP"}:
        limit = 150
    elif domain == "macro" and metric in {"UNRATE", "CPIAUCSL", "SAHMREALTIME"}:
        limit = 50
    elif domain == "macro":
        limit = 14
    else:
        limit = 30
    return age <= limit


def _parse_date(value: Any) -> date | None:
    text = str(value or "")[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _apply_subject_coverage(
    domains: Dict[str, Dict[str, Any]],
    provider_rows: Iterable[Mapping[str, Any]],
    facts: Iterable[Mapping[str, Any]],
    subjects: List[str],
) -> None:
    if not subjects:
        return
    subject_by_key = {subject.upper(): subject for subject in subjects}
    supported: Dict[str, set[str]] = {"price": set(), "fundamentals": set()}
    fundamental_depth: set[str] = set()
    for row in provider_rows:
        domain = str(row.get("domain") or "")
        if domain not in supported or str(row.get("status") or "") != "success":
            continue
        if domain == "fundamentals":
            # Provider success only proves that a call returned. Fundamental
            # coverage requires an analyzable fact below.
            continue
        for symbol in _symbols_from_row(row):
            key = symbol.upper()
            if key in subject_by_key:
                supported[domain].add(key)
    for fact in facts:
        domain = str(fact.get("domain") or "")
        if domain not in supported:
            continue
        fact_type = str(fact.get("fact_type") or fact.get("factType") or "").lower()
        if fact_type not in {"verified_fact", "derived_fact"}:
            continue
        if fact_type == "verified_fact" and not has_fact_source(fact):
            continue
        for symbol in _symbols_from_row(fact):
            key = symbol.upper()
            if key in subject_by_key:
                supported[domain].add(key)
                if domain == "fundamentals" and _is_deep_fundamental_fact(fact):
                    fundamental_depth.add(key)

    for domain in ("price", "fundamentals"):
        covered = [subject for subject in subjects if subject.upper() in supported[domain]]
        missing = [subject for subject in subjects if subject.upper() not in supported[domain]]
        shallow: List[str] = []
        if domain == "fundamentals":
            depth_covered = [subject for subject in covered if subject.upper() in fundamental_depth]
            shallow = [subject for subject in covered if subject.upper() not in fundamental_depth]
            coverage = (len(depth_covered) + 0.5 * len(shallow)) / len(subjects)
        else:
            depth_covered = covered
            coverage = len(covered) / len(subjects)
        row = domains[domain]
        complete = not missing and not shallow
        blockers: List[str] = []
        hints: List[str] = []
        if missing:
            blockers.append("subject_coverage_incomplete")
            hints.append(f"补齐 {domain} 缺失标的: {', '.join(missing)}")
        if shallow:
            blockers.append("subject_fundamental_depth_incomplete")
            hints.append(f"补齐结构化财务/增长事实: {', '.join(shallow)}")
        row.update(
            {
                "status": "available" if complete else ("partial" if covered else "missing"),
                "coverage": round(coverage, 4),
                "freshness": "fresh" if covered else "missing",
                "confidence": "high" if complete else ("medium" if covered else "low"),
                "blockers": blockers,
                "repairHints": hints,
                "subjectCoverageRequired": True,
                "requiredSubjects": list(subjects),
                "coveredSubjects": covered,
                "missingSubjects": missing,
                "depthCoveredSubjects": depth_covered,
                "shallowSubjects": shallow,
            }
        )


def _symbols_from_row(row: Mapping[str, Any]) -> List[str]:
    values: List[Any] = []
    for key in ("symbol", "subject", "symbols"):
        value = row.get(key)
        if isinstance(value, (list, tuple, set)):
            values.extend(value)
        elif value not in (None, ""):
            values.extend(str(value).replace(";", ",").split(","))
    return _normalize_subjects(values)


def _is_deep_fundamental_fact(fact: Mapping[str, Any]) -> bool:
    text = " ".join(
        str(fact.get(key) or "")
        for key in ("id", "value", "fact_subtype", "provider")
    ).lower()
    return any(
        token in text
        for token in (
            "fundamental:growth",
            "fundamental:earnings",
            "sec_companyfacts",
            "revenue",
            "net_income",
            "operating_income",
            "cash_flow",
            "gross_margin",
            "roe=",
            "assets",
            "liabilities",
            "营收",
            "净利润",
            "现金流",
        )
    )


def _apply_agent_counts(domains: Dict[str, Dict[str, Any]], counts: Mapping[str, int]) -> None:
    raw = int(counts.get("RAW_AGENT") or counts.get("raw") or 0)
    derived = int(counts.get("DERIVED_FROM_ARTIFACT") or counts.get("derived") or 0)
    missing = int(counts.get("MISSING") or counts.get("missing") or 0)
    if raw > 0:
        _set_domain(domains, "agent_memos", status="available", coverage=1.0, confidence="high")
    elif derived > 0:
        _set_domain(domains, "agent_memos", status="partial", coverage=0.55, confidence="medium", blocker="derived_only")
    elif missing > 0:
        _set_domain(domains, "agent_memos", status="degraded", coverage=0.2, blocker="memos_missing")


def _provider_matrix_row(run: Mapping[str, Any]) -> Dict[str, Any]:
    provider = str(run.get("provider") or "unknown")
    cap = provider_capability(provider)
    domain = _infer_domain(run, cap)
    status = _provider_status(run)
    row = {
        "provider": provider,
        "market": _first(cap.get("markets"), default="unknown"),
        "domain": domain,
        "operation": run.get("operation"),
        "symbol": run.get("symbol") or run.get("subject"),
        "symbols": run.get("symbols"),
        "status": status,
        "authState": _auth_state(status, cap),
        "recordCount": run.get("record_count") if run.get("record_count") is not None else run.get("recordCount"),
        "latencyMs": run.get("latency_ms") or run.get("latencyMs"),
        "observedAt": run.get("observed_at") or run.get("observedAt"),
        "errorType": run.get("error_type") or run.get("errorType"),
        "fallbackTo": run.get("fallback_to") or run.get("fallbackTo"),
        "sourceTier": cap.get("sourceTier") or "unknown",
        "sourceScope": run.get("source_scope") or run.get("sourceScope") or "subject_evidence",
        "factType": cap.get("factType"),
    }
    row["blocking"] = not _is_nonblocking_optional_provider(row)
    return {key: value for key, value in row.items() if value not in (None, "", [])}


def _is_nonblocking_optional_provider(row: Mapping[str, Any]) -> bool:
    tier = str(row.get("sourceTier") or "").lower()
    if tier.startswith("optional_"):
        return True
    provider = str(row.get("provider") or "")
    return provider in {"FMP", "Polygon", "Brave", "LongbridgeFetcher", "TickFlowFetcher"}


def _provider_status(run: Mapping[str, Any]) -> str:
    text = " ".join(str(run.get(key) or "") for key in ("error_type", "errorType", "error_message_sanitized", "error_message", "message")).lower()
    if any(token in text for token in ("auth_missing", "missing key", "api_key missing", "token missing", "unauthorized", "forbidden")):
        return "auth_missing"
    if any(token in text for token in ("permission_limited", "permission", "没有接口", "权限不足", "no permission")):
        return "permission_limited"
    if any(token in text for token in ("rate_limited", "too many requests", "429", "quota", "usage limit")):
        return "rate_limited"
    raw_status = str(run.get("status") or "").lower()
    if raw_status in {"permission_limited"}:
        return "permission_limited"
    if raw_status in {"not_supported", "unsupported"}:
        return "not_supported"
    if bool(run.get("success")):
        count = run.get("record_count") if run.get("record_count") is not None else run.get("recordCount")
        if count == 0:
            return "empty"
        return "success"
    if str(run.get("success")).lower() == "false":
        return "failed"
    return "partial"


def _auth_state(status: str, cap: Mapping[str, Any]) -> str:
    if not cap.get("credentialRequired"):
        return "not_required"
    if status == "auth_missing":
        return "missing"
    return "configured"


def _infer_domain(run: Mapping[str, Any], cap: Mapping[str, Any]) -> str:
    data_type = str(run.get("data_type") or run.get("operation") or run.get("domain") or "").lower()
    if any(token in data_type for token in ("daily", "quote", "realtime", "kline", "candle", "price")):
        return "price"
    if any(token in data_type for token in ("fundamental", "financial", "valuation", "statement")):
        return "fundamentals"
    if any(token in data_type for token in ("filing", "announcement", "event", "notice")):
        return "filings_events"
    if any(token in data_type for token in ("macro", "fred", "economic")):
        return "macro"
    if any(token in data_type for token in ("news", "search", "sentiment", "gdelt")):
        return "news_sentiment"
    domains = cap.get("domains") if isinstance(cap.get("domains"), list) else []
    return str(domains[0]) if domains else "unknown"


def _domain_status_from_text(*values: Any) -> str:
    text = " ".join(str(value or "") for value in values).lower()
    if any(token in text for token in ("blocked", "failed", "unavailable")):
        return "blocked"
    if any(token in text for token in ("degraded", "partial", "limited", "unknown")):
        return "degraded"
    if any(token in text for token in ("available", "usable", "ok", "refreshed", "empty")):
        return "available"
    return "missing"


def _coverage_from_status(status: str, explicit: Any = None) -> float:
    try:
        if explicit is not None:
            return max(0.0, min(1.0, float(explicit)))
    except Exception:
        pass
    return _STATUS_SCORE.get(status, 0.0)


def _overall_score(domains: Mapping[str, Mapping[str, Any]]) -> float:
    # Research confidence is independent from renderer/deployment/runtime
    # health.  Those remain visible as diagnostic domains but cannot upgrade or
    # downgrade the investment evidence itself.
    weights = {
        "price": 0.24,
        "fundamentals": 0.18,
        "filings_events": 0.18,
        "macro": 0.20,
        "news_sentiment": 0.15,
        "portfolio": 0.05,
    }
    total = 0.0
    for domain, weight in weights.items():
        total += float(domains.get(domain, {}).get("coverage") or 0.0) * weight
    return round(total, 4)


def _overall_mode(
    domains: Mapping[str, Mapping[str, Any]],
    score: float,
    legacy: Mapping[str, Any],
    claim_evidence: Mapping[str, Any],
    evidence_stats: Mapping[str, Any],
) -> str:
    legacy_text = f"{legacy.get('usability_verdict', '')} {legacy.get('trade_review_usability', '')}".lower()
    if domains["price"]["status"] == "blocked":
        return "BLOCKED"
    core_domains_ready = not any(
        domains[d]["status"] in {"missing", "blocked", "degraded"} for d in ("price", "fundamentals", "filings_events", "macro")
    )
    claims = claim_evidence.get("claims") if isinstance(claim_evidence.get("claims"), Mapping) else {}
    core_claims_have_evidence = all(
        _claim_status(claims, key) == "supported"
        for key in ("score", "actionable_advice", "position_sizing", "risk_warning")
    )
    if (
        score >= 0.85
        and core_domains_ready
        and core_claims_have_evidence
        and _safe_int(evidence_stats.get("missingCriticalFacts")) <= POSITION_SIZING_MISSING_CRITICAL_THRESHOLD
    ):
        return "FULL_REVIEW"
    if any(token in legacy_text for token in ("degraded", "limited", "partial")):
        return "LIMITED_REVIEW"
    if float(domains["price"].get("coverage") or 0.0) >= 0.5:
        research_context_available = any(
            float(domains[d].get("coverage") or 0.0) > 0
            for d in ("fundamentals", "filings_events", "macro", "news_sentiment")
        )
        if not research_context_available:
            return "SCREEN_ONLY"
        return "LIMITED_REVIEW"
    if score > 0:
        return "OBSERVE_ONLY"
    return "BLOCKED"


def _claim_policy(mode: str, claim_evidence: Mapping[str, Any], evidence_stats: Mapping[str, Any]) -> Dict[str, bool]:
    claims = claim_evidence.get("claims") if isinstance(claim_evidence.get("claims"), Mapping) else {}
    score_supported = _claim_status(claims, "score") == "supported"
    actionable_supported = _claim_status(claims, "actionable_advice") == "supported"
    position_supported = _claim_status(claims, "position_sizing") == "supported"
    critical_missing_ok = _safe_int(evidence_stats.get("missingCriticalFacts")) <= POSITION_SIZING_MISSING_CRITICAL_THRESHOLD
    if mode == "FULL_REVIEW":
        base = {
            "canScore": score_supported,
            "canActionableAdvice": actionable_supported,
            "canPositionSizing": position_supported and critical_missing_ok,
            "mustShowCaveat": not (score_supported and actionable_supported and position_supported and critical_missing_ok),
        }
    elif mode == "LIMITED_REVIEW":
        base = {
            "canScore": score_supported,
            "canActionableAdvice": actionable_supported,
            "canPositionSizing": False,
            "mustShowCaveat": True,
        }
    else:
        return {
            "canScore": mode not in {"BLOCKED", "OBSERVE_ONLY"} and score_supported,
            "canActionableAdvice": False,
            "canPositionSizing": False,
            "mustShowCaveat": True,
        }
    if any(_claim_status(claims, key) != "supported" for key in ("score", "actionable_advice", "position_sizing")):
        base["mustShowCaveat"] = True
    if _safe_int(evidence_stats.get("missingCriticalFacts")) > POSITION_SIZING_MISSING_CRITICAL_THRESHOLD:
        base["canPositionSizing"] = False
        base["mustShowCaveat"] = True
    return base


def _claim_status(claims: Mapping[str, Any], key: str) -> str:
    row = claims.get(key) if isinstance(claims.get(key), Mapping) else {}
    return str(row.get("status") or "missing")


def _claim_evidence(
    facts: List[Dict[str, Any]],
    evidence_stats: Mapping[str, Any],
    domains_payload: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    support_by_domain: Dict[str, List[str]] = {domain: [] for domain in DOMAINS}
    for fact in facts:
        fact_type = str(fact.get("fact_type") or fact.get("factType") or "").lower()
        if fact_type not in {"verified_fact", "derived_fact"}:
            continue
        domain = str(fact.get("domain") or "")
        if domain not in support_by_domain:
            continue
        fact_id = str(fact.get("id") or "")
        if fact_id and fact_id not in support_by_domain[domain]:
            support_by_domain[domain].append(fact_id)

    claims: Dict[str, Dict[str, Any]] = {}
    for claim, spec in _CLAIM_REQUIREMENTS.items():
        domains = list(spec["domains"])
        evidence_ids: List[str] = []
        for domain in domains:
            evidence_ids.extend(support_by_domain.get(domain) or [])
        evidence_ids = list(dict.fromkeys(evidence_ids))
        missing_domains = [domain for domain in domains if not support_by_domain.get(domain)]
        partial_domains = [
            domain
            for domain in domains
            if support_by_domain.get(domain)
            and bool(domains_payload.get(domain, {}).get("subjectCoverageRequired"))
            and float(domains_payload.get(domain, {}).get("coverage") or 0.0) < 1.0
        ]
        status = "supported" if evidence_ids and not missing_domains and not partial_domains else ("partial" if evidence_ids else "missing")
        claims[claim] = {
            "label": spec["label"],
            "status": status,
            "requiredDomains": domains,
            "evidenceIds": evidence_ids[:12],
            "evidenceCount": len(evidence_ids),
            "missingDomains": missing_domains,
            "partialDomains": partial_domains,
        }

    if _safe_int(evidence_stats.get("missingCriticalFacts")) > POSITION_SIZING_MISSING_CRITICAL_THRESHOLD:
        row = claims["position_sizing"]
        if row.get("evidenceCount", 0):
            row["status"] = "partial"
        row.setdefault("blockers", []).append("missing_critical_facts_above_threshold")

    return {
        "schema": "claim_evidence_v1",
        "supportFactTypes": ["verified_fact", "derived_fact"],
        "positionSizingMissingCriticalThreshold": POSITION_SIZING_MISSING_CRITICAL_THRESHOLD,
        "claims": claims,
    }


def _evidence_stats(facts: List[Dict[str, Any]], domains: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    counts = {"verifiedFacts": 0, "derivedFacts": 0, "discoveryItems": 0, "missingFacts": 0}
    for fact in facts:
        fact_type = str(fact.get("fact_type") or fact.get("factType") or "").lower()
        if fact_type == "verified_fact":
            if has_fact_source(fact):
                counts["verifiedFacts"] += 1
            else:
                counts["missingFacts"] += 1
        elif fact_type == "derived_fact":
            counts["derivedFacts"] += 1
        elif fact_type == "discovery":
            counts["discoveryItems"] += 1
        elif fact_type == "missing":
            counts["missingFacts"] += 1
    missing_critical = sum(1 for domain in ("price", "fundamentals", "filings_events", "macro") if domains[domain]["status"] in {"missing", "blocked", "degraded"})
    return {
        "schema": "evidence_stats_v1",
        **counts,
        "missingCriticalFacts": missing_critical + counts["missingFacts"],
    }


def _blocking_reasons(domains: Mapping[str, Mapping[str, Any]], mode: str) -> List[str]:
    reasons: List[str] = []
    if mode == "FULL_REVIEW":
        return reasons
    for domain, row in domains.items():
        if domain in {"publish_bundle", "agent_memos"}:
            continue
        for blocker in row.get("blockers") or []:
            if blocker and blocker != "not_observed":
                reasons.append(f"{domain}:{blocker}")
    return reasons[:12]


def _repair_hint_for_provider(row: Mapping[str, Any]) -> str:
    provider = str(row.get("provider") or "provider")
    status = str(row.get("status") or "")
    if status == "auth_missing":
        if provider in {"FRED", "src.macro.official_sources", "src.macro.review"}:
            return "配置 FRED_API_KEY 或刷新官方宏观快照"
        if _is_nonblocking_optional_provider(row):
            return f"{provider} 是可选增强源；可忽略或补 key"
        return f"配置 {provider} key 或移出主路由"
    if status == "rate_limited":
        return f"等待 {provider} 配额恢复或使用 fallback"
    if status == "permission_limited":
        return f"{provider} 当前 key 权限不足；改用免费 fallback 或升级权限"
    return f"检查 {provider} 返回与 fallback"


def _first(values: Any, *, default: str) -> str:
    if isinstance(values, list) and values:
        return str(values[0])
    return default


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
