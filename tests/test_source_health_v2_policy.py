import json


def _verified_fact(domain: str, idx: int) -> dict:
    return {
        "id": f"verified:{domain}:{idx}",
        "domain": domain,
        "fact_type": "verified_fact",
        "provider": "fixture_official_source",
        "source_url": f"https://example.test/{domain}/{idx}",
        "confidence": "high",
        "as_of": "2099-01-02",
    }


def test_source_health_v2_modes_and_claim_policy():
    from src.source_health.policy import build_source_health_v2

    # Add portfolio/publish via legacy rows so all weighted domains can hit full strength.
    full = build_source_health_v2(
        {
            "rows": [
                {"component": "portfolio_snapshot", "status": "available"},
                {"component": "governed_reports", "status": "available"},
            ]
        },
        provider_runs=[{"provider": "YfinanceFetcher", "data_type": "daily_data", "success": True, "record_count": 2}],
        evidence_facts=[
            _verified_fact("price", 0),
            _verified_fact("fundamentals", 1),
            _verified_fact("filings_events", 2),
            _verified_fact("macro", 3),
            _verified_fact("news_sentiment", 4),
            _verified_fact("portfolio", 5),
        ],
        agent_origin_counts={"RAW_AGENT": 1},
    )
    assert full["overallMode"] == "FULL_REVIEW"
    assert full["claimPolicy"] == {
        "canScore": True,
        "canActionableAdvice": True,
        "canPositionSizing": True,
        "mustShowCaveat": False,
    }

    screen = build_source_health_v2(
        {},
        provider_runs=[{"provider": "YfinanceFetcher", "data_type": "daily_data", "success": True, "record_count": 2}],
    )
    assert screen["overallMode"] == "SCREEN_ONLY"
    assert screen["claimPolicy"]["canActionableAdvice"] is False
    assert screen["claimPolicy"]["mustShowCaveat"] is True

    observe = build_source_health_v2({}, evidence_facts=[_verified_fact("macro", 5)])
    assert observe["overallMode"] == "OBSERVE_ONLY"
    assert observe["claimPolicy"]["canScore"] is False
    assert observe["claimPolicy"]["mustShowCaveat"] is True

    blocked = build_source_health_v2({})
    assert blocked["overallMode"] == "BLOCKED"
    assert blocked["claimPolicy"] == {
        "canScore": False,
        "canActionableAdvice": False,
        "canPositionSizing": False,
        "mustShowCaveat": True,
    }


def test_source_health_v2_marks_caveat_and_disables_actions_when_verified_facts_missing():
    from src.source_health.policy import build_source_health_v2

    legacy_health = {
        "usability_verdict": "degraded",
        "trade_review_usability": "usable_limited",
        "rows": [
            {"component": "macro_context", "status": "PARTIAL", "criticality": "critical"},
            {"component": "governed_reports", "status": "available", "criticality": "optional"},
        ],
    }
    provider_runs = [
        {"provider": "YfinanceFetcher", "data_type": "daily_data", "success": True, "record_count": 240},
        {
            "provider": "Tavily",
            "data_type": "news",
            "success": False,
            "error_type": "rate_limited",
            "fallback_to": "SearXNG",
        },
    ]
    evidence_facts = [
        {"id": "discovery:news:1", "domain": "news_sentiment", "fact_type": "discovery"},
        {"id": "missing:fundamental:1", "domain": "fundamentals", "fact_type": "missing"},
    ]

    health = build_source_health_v2(
        legacy_health,
        provider_runs=provider_runs,
        evidence_facts=evidence_facts,
        agent_origin_counts={"RAW_AGENT": 1, "DERIVED_FROM_ARTIFACT": 2, "MISSING": 0},
    )

    assert health["schema"] == "source_health_v2"
    assert health["overallMode"] == "LIMITED_REVIEW"
    assert health["claimPolicy"] == {
        "canScore": False,
        "canActionableAdvice": False,
        "canPositionSizing": False,
        "mustShowCaveat": True,
    }
    assert health["claimEvidence"]["claims"]["score"]["status"] == "missing"
    assert health["claimEvidence"]["claims"]["actionable_advice"]["status"] == "missing"
    assert health["claimEvidence"]["claims"]["position_sizing"]["status"] == "missing"
    assert health["domains"]["price"]["status"] == "partial"
    assert health["domains"]["price"]["confidence"] == "medium"
    assert health["domains"]["news_sentiment"]["status"] == "degraded"
    assert health["domains"]["fundamentals"]["status"] == "missing"
    assert health["evidenceStats"]["verifiedFacts"] == 0
    assert health["evidenceStats"]["discoveryItems"] == 1
    assert health["evidenceStats"]["missingCriticalFacts"] >= 1


def test_claim_evidence_supports_verified_or_derived_but_not_discovery_for_core_claims():
    from src.source_health.policy import build_source_health_v2

    supported = build_source_health_v2(
        {"usability_verdict": "degraded", "trade_review_usability": "usable_limited"},
        provider_runs=[{"provider": "YfinanceFetcher", "data_type": "daily_data", "success": True, "record_count": 2}],
        evidence_facts=[
            _verified_fact("filings_events", 1),
            {
                "id": "derived:macro:1",
                "domain": "macro",
                "fact_type": "derived_fact",
                "provider": "fixture_macro",
                "confidence": "medium",
            },
        ],
    )
    assert supported["claimEvidence"]["claims"]["score"]["status"] == "partial"
    assert supported["claimEvidence"]["claims"]["actionable_advice"]["status"] == "partial"
    assert supported["claimPolicy"]["canActionableAdvice"] is False

    discovery_only = build_source_health_v2(
        {"usability_verdict": "degraded", "trade_review_usability": "usable_limited"},
        provider_runs=[{"provider": "YfinanceFetcher", "data_type": "daily_data", "success": True, "record_count": 2}],
        evidence_facts=[
            {
                "id": "search:news:1",
                "domain": "news_sentiment",
                "fact_type": "discovery",
                "provider": "GDELT",
                "source_url": "https://example.test/news",
            }
        ],
    )
    assert discovery_only["claimEvidence"]["claims"]["actionable_advice"]["status"] == "missing"
    assert discovery_only["claimPolicy"]["canActionableAdvice"] is False
    assert discovery_only["claimPolicy"]["mustShowCaveat"] is True


def test_position_sizing_requires_claim_supporting_portfolio_evidence():
    from src.source_health.policy import build_source_health_v2

    facts = [
        _verified_fact("price", 1),
        _verified_fact("fundamentals", 2),
        _verified_fact("macro", 3),
        {
            "id": "daily_universe:portfolio_snapshot_status:2099-01-02",
            "domain": "portfolio",
            "fact_type": "derived_fact",
            "provider": "DailyUniverse",
            "raw_path": "run_status/2099-01-02/daily_universe.json",
            "as_of": "2099-01-02",
            "supports_claims": False,
        },
    ]

    health = build_source_health_v2({}, evidence_facts=facts)

    claim = health["claimEvidence"]["claims"]["position_sizing"]
    assert claim["status"] == "partial"
    assert claim["missingDomains"] == ["portfolio"]
    assert health["claimPolicy"]["canPositionSizing"] is False


def test_position_sizing_is_disabled_when_missing_critical_facts_exceed_threshold():
    from src.source_health.policy import POSITION_SIZING_MISSING_CRITICAL_THRESHOLD, build_source_health_v2

    facts = [_verified_fact("fundamentals", 1), _verified_fact("macro", 2)]
    facts.extend(
        {"id": f"missing:critical:{idx}", "domain": "filings_events", "fact_type": "missing"}
        for idx in range(POSITION_SIZING_MISSING_CRITICAL_THRESHOLD + 1)
    )

    health = build_source_health_v2(
        {"usability_verdict": "degraded", "trade_review_usability": "usable_limited"},
        provider_runs=[{"provider": "YfinanceFetcher", "data_type": "daily_data", "success": True, "record_count": 2}],
        evidence_facts=facts,
    )

    assert health["evidenceStats"]["missingCriticalFacts"] > POSITION_SIZING_MISSING_CRITICAL_THRESHOLD
    assert health["claimEvidence"]["claims"]["position_sizing"]["status"] == "partial"
    assert "missing_critical_facts_above_threshold" in health["claimEvidence"]["claims"]["position_sizing"]["blockers"]
    assert health["claimPolicy"]["canPositionSizing"] is False
    assert health["claimPolicy"]["mustShowCaveat"] is True


def test_governed_review_with_price_and_agent_outputs_is_limited_not_screen_only():
    from src.source_health.policy import build_source_health_v2

    facts = [
        _verified_fact("filings_events", 1),
        {
            "id": "derived:macro:1",
            "domain": "macro",
            "fact_type": "derived_fact",
            "provider": "FRED",
            "confidence": "medium",
        },
        {
            "id": "derived:fundamentals:1",
            "domain": "fundamentals",
            "fact_type": "derived_fact",
            "provider": "governed_result",
            "confidence": "medium",
        },
        {
            "id": "derived:news:1",
            "domain": "news_sentiment",
            "fact_type": "derived_fact",
            "provider": "governed_result",
            "confidence": "medium",
        },
    ]
    facts.extend(
        {"id": f"missing:critical:{idx}", "domain": "fundamentals", "fact_type": "missing"}
        for idx in range(25)
    )

    health = build_source_health_v2(
        {
            "rows": [
                {"component": "governed_reports", "status": "available"},
            ]
        },
        provider_runs=[{"provider": "AkshareFetcher", "data_type": "daily_data", "success": True, "record_count": 80}],
        evidence_facts=facts,
        agent_origin_counts={"RAW_AGENT": 3},
    )

    assert health["overallMode"] == "LIMITED_REVIEW"
    assert health["claimPolicy"]["canScore"] is False
    assert health["claimPolicy"]["canActionableAdvice"] is True
    assert health["claimPolicy"]["canPositionSizing"] is False


def test_evidence_policy_requires_source_for_verified_fact_and_keeps_search_as_discovery():
    from src.source_health.policy import build_source_health_v2

    health = build_source_health_v2(
        {},
        evidence_facts=[
            {
                "id": "bad:verified:1",
                "domain": "filings_events",
                "fact_type": "verified_fact",
                "provider": "SEC_EDGAR",
            },
            {
                "id": "search:news:1",
                "domain": "news_sentiment",
                "fact_type": "verified_fact",
                "provider": "Tavily",
                "source_url": "https://example.test/search",
            },
        ],
    )

    assert health["domains"]["filings_events"]["status"] == "missing"
    assert "verified_fact_missing_source" in health["domains"]["filings_events"]["blockers"]
    assert health["domains"]["news_sentiment"]["status"] == "degraded"
    assert "search_only_discovery" in health["domains"]["news_sentiment"]["blockers"]
    assert health["evidenceStats"]["verifiedFacts"] == 0
    assert health["evidenceStats"]["discoveryItems"] == 1
    assert health["evidenceStats"]["missingFacts"] == 1


def test_evidence_ledger_roundtrip_normalizes_search_and_bad_verified_facts(tmp_path):
    from src.source_health.evidence_ledger import load_evidence_ledger, write_evidence_ledger

    path = tmp_path / "evidence_ledger.jsonl"
    write_evidence_ledger(
        path,
        [
            {
                "id": "search:1",
                "domain": "news_sentiment",
                "fact_type": "verified_fact",
                "provider": "Tavily",
                "source_url": "https://example.test/search",
            },
            {
                "id": "bad:1",
                "domain": "filings_events",
                "fact_type": "verified_fact",
                "provider": "SEC_EDGAR",
            },
            {
                "id": "good:1",
                "domain": "filings_events",
                "fact_type": "verified_fact",
                "provider": "SEC_EDGAR",
                "source_url": "https://www.sec.gov/Archives/example",
            },
        ],
    )

    rows = load_evidence_ledger(path)
    by_id = {row["id"]: row for row in rows}
    assert by_id["search:1"]["fact_type"] == "discovery"
    assert by_id["search:1"]["downgradeReason"] == "search_provider_not_verified_fact"
    assert by_id["bad:1"]["fact_type"] == "missing"
    assert by_id["bad:1"]["missingReason"] == "verified_fact_missing_source"
    assert by_id["good:1"]["fact_type"] == "verified_fact"


def test_provider_matrix_marks_auth_missing_and_rate_limited_without_unknown():
    from src.source_health.policy import build_source_health_v2

    health = build_source_health_v2(
        {},
        provider_runs=[
            {
                "provider": "FinnhubFetcher",
                "data_type": "quote",
                "success": False,
                "error_type": "auth_missing",
                "error_message_sanitized": "FINNHUB_API_KEY missing",
            },
            {
                "provider": "Tavily",
                "data_type": "news",
                "success": False,
                "error_message_sanitized": "429 Too Many Requests",
            },
        ],
    )

    statuses = {row["provider"]: row for row in health["providerMatrix"]}
    assert statuses["FinnhubFetcher"]["status"] == "auth_missing"
    assert statuses["FinnhubFetcher"]["authState"] == "missing"
    assert statuses["Tavily"]["status"] == "rate_limited"
    assert all(row["status"] != "unknown" for row in health["providerMatrix"])


def test_source_smoke_does_not_support_full_review_gate():
    from src.source_health.policy import build_source_health_v2

    health = build_source_health_v2(
        {
            "rows": [
                {"component": "portfolio_snapshot", "status": "available"},
                {"component": "governed_reports", "status": "available"},
            ]
        },
        provider_runs=[
            {"provider": "YfinanceFetcher", "data_type": "daily_data", "success": True, "record_count": 2, "source_scope": "source_smoke"},
        ],
        evidence_facts=[
            {**_verified_fact("price", 0), "evidence_scope": "source_smoke"},
            {**_verified_fact("fundamentals", 1), "evidence_scope": "source_smoke"},
            {**_verified_fact("filings_events", 2), "evidence_scope": "source_smoke"},
            {**_verified_fact("macro", 3), "evidence_scope": "source_smoke"},
            {**_verified_fact("portfolio", 4), "evidence_scope": "source_smoke"},
        ],
        agent_origin_counts={"RAW_AGENT": 1},
    )

    assert health["evidenceScopes"]["sourceSmokeFacts"] == 5
    assert health["evidenceScopes"]["subjectEvidenceFacts"] == 0
    assert health["overallMode"] != "FULL_REVIEW"
    assert health["claimEvidence"]["claims"]["score"]["status"] == "missing"


def test_provider_matrix_preserves_operation_record_count_and_official_disclosure_capabilities():
    from src.source_health.policy import build_source_health_v2
    from src.source_health.provider_registry import provider_capability

    health = build_source_health_v2(
        {},
        provider_runs=[
            {
                "provider": "SSE_DISCLOSURE",
                "domain": "filings_events",
                "operation": "sse_announcements",
                "success": True,
                "record_count": 3,
            }
        ],
    )

    row = health["providerMatrix"][0]
    assert row["provider"] == "SSE_DISCLOSURE"
    assert row["operation"] == "sse_announcements"
    assert row["recordCount"] == 3
    assert row["sourceTier"] == "official_free"
    assert provider_capability("HKEXNEWS")["sourceTier"] == "official_free"


def test_provider_success_and_discovery_do_not_create_high_confidence_domain():
    from src.source_health.policy import build_source_health_v2

    health = build_source_health_v2(
        {},
        provider_runs=[{
            "provider": "Tavily", "domain": "news_sentiment", "operation": "search",
            "success": True, "record_count": 3,
        }],
        evidence_facts=[{
            "id": "tavily:1", "domain": "news_sentiment", "fact_type": "discovery",
            "provider": "Tavily", "source_url": "https://example.test/news", "as_of": "2099-01-02",
        }],
    )

    assert health["domains"]["news_sentiment"]["status"] in {"partial", "degraded"}
    assert health["domains"]["news_sentiment"]["confidence"] != "high"
    assert "search_only_discovery" in health["domains"]["news_sentiment"]["blockers"]


def test_optional_paid_and_enhancement_failures_do_not_degrade_default_health():
    from src.source_health.policy import build_source_health_v2

    health = build_source_health_v2(
        {},
        provider_runs=[
            {
                "provider": "LongbridgeFetcher",
                "data_type": "quote",
                "success": False,
                "error_type": "auth_missing",
                "error_message_sanitized": "LONGPORT credentials missing",
            },
            {
                "provider": "TickFlowFetcher",
                "data_type": "market_price",
                "success": False,
                "error_type": "auth_missing",
            },
            {
                "provider": "Brave",
                "data_type": "news",
                "success": False,
                "error_message_sanitized": "missing key",
            },
            {
                "provider": "Polymarket",
                "data_type": "prediction_market",
                "success": False,
                "error_type": "not_supported",
            },
        ],
    )

    rows = {row["provider"]: row for row in health["providerMatrix"]}
    assert rows["LongbridgeFetcher"]["blocking"] is False
    assert rows["TickFlowFetcher"]["blocking"] is False
    assert rows["Brave"]["blocking"] is False
    assert rows["Polymarket"]["blocking"] is False
    assert health["domains"]["price"]["status"] == "missing"
    assert health["domains"]["news_sentiment"]["status"] == "missing"
    assert health["domains"]["macro"]["status"] == "missing"
    assert "price:auth_missing" not in health["blockingReasons"]


def test_provider_ledger_roundtrip_jsonl(tmp_path):
    from src.source_health.provider_ledger import load_provider_ledger, write_provider_ledger

    path = tmp_path / "provider_runs.jsonl"
    rows = [
        {"provider": "YfinanceFetcher", "data_type": "daily_data", "success": True, "record_count": 2},
        {"provider": "Tavily", "data_type": "news", "success": False, "error_type": "rate_limited"},
    ]

    write_provider_ledger(path, rows)

    written = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert all(row.get("observed_at") for row in written)
    assert [{key: value for key, value in row.items() if key != "observed_at"} for row in written] == rows
    assert load_provider_ledger(path) == written


def test_available_legacy_macro_does_not_keep_degraded_blocker():
    from src.source_health.policy import build_source_health_v2

    health = build_source_health_v2(
        {
            "rows": [
                {
                    "component": "macro_context",
                    "status": "REFRESHED",
                    "usability": "usable",
                    "coverage_score": 1.0,
                }
            ],
            "trade_review_usability": "usable",
        },
        evidence_facts=[
            {
                "id": "macro:fred",
                "domain": "macro",
                "provider": "market_cycle",
                "raw_path": "market_cycle/2099-01-02/01_macro_review.json",
                "fact_type": "derived_fact",
            }
        ],
    )

    macro = health["domains"]["macro"]
    assert macro["status"] == "available"
    assert "macro_degraded" not in macro.get("blockers", [])
