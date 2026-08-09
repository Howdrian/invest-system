import json


def test_daily_universe_emits_explicit_unconnected_portfolio_evidence():
    from src.source_health.daily_evidence import evidence_from_daily_universe

    rows = evidence_from_daily_universe(
        {
            "groups": [
                {
                    "name": "portfolio",
                    "symbols": [],
                    "whyIncluded": "当前未发现结构化持仓源；保留分组以便后续接入",
                },
                {"name": "watchlist", "symbols": ["600519", "AAPL"]},
            ]
        },
        "2099-01-02",
    )

    assert rows[0]["domain"] == "portfolio"
    assert "portfolio_snapshot_status=not_connected" in rows[0]["value"]
    assert rows[0]["measurements"]["snapshot_available"] == 0.0
    assert rows[0]["supports_claims"] is False
    assert rows[0]["measurements"]["watchlist_count"] == 2.0


def test_configured_portfolio_symbols_do_not_masquerade_as_position_snapshot():
    from src.source_health.daily_evidence import evidence_from_daily_universe

    rows = evidence_from_daily_universe(
        {
            "groups": [
                {
                    "name": "portfolio",
                    "symbols": ["160644", "301013"],
                    "scope": "symbols_only",
                    "snapshotAvailable": False,
                    "whyIncluded": "来自 PORTFOLIO_HOLDINGS 的标的清单",
                },
                {"name": "watchlist", "symbols": ["AAPL"]},
            ]
        },
        "2099-01-02",
    )

    assert "portfolio_snapshot_status=symbols_only" in rows[0]["value"]
    assert rows[0]["measurements"]["snapshot_available"] == 0.0
    assert rows[0]["measurements"]["holdings_count"] == 0.0
    assert rows[0]["measurements"]["configured_symbols_count"] == 2.0
    assert rows[0]["supports_claims"] is False
    assert rows[0]["measurements"]["watchlist_count"] == 1.0


def test_source_health_refresh_preserves_existing_runtime_stages(tmp_path):
    from src.source_health.daily_ledgers import write_daily_source_health_ledgers
    from src.source_health.run_matrix import write_run_matrix

    docs = tmp_path / "docs"
    run_date = "2099-01-02"
    write_run_matrix(
        docs,
        run_date,
        symbols=["AAPL"],
        stages=[{"name": "llm_department_agents", "status": "success", "blocking": True}],
    )

    write_daily_source_health_ledgers(docs, run_date)

    matrix = json.loads((docs / "run_status" / run_date / "run_matrix.json").read_text(encoding="utf-8"))
    stages = {row["name"] for row in matrix["stages"]}
    assert "llm_department_agents" in stages
    assert "source_health_snapshot" in stages


def test_write_daily_source_health_ledgers_from_agent_memos_and_market_cycle(tmp_path):
    from src.source_health.daily_ledgers import write_daily_source_health_ledgers
    from src.source_health.evidence_ledger import load_evidence_ledger
    from src.source_health.provider_ledger import load_provider_ledger

    docs = tmp_path / "docs"
    run_date = "2099-01-02"
    memo_dir = docs / "agent_memos" / run_date / "market"
    memo_dir.mkdir(parents=True)
    (docs / "market_cycle" / run_date).mkdir(parents=True)
    (docs / "market_cycle" / run_date / "11_deep_review_queue.json").write_text(
        json.dumps({"queue": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    (docs / "market_cycle" / run_date / "01_macro_review.json").write_text(
        json.dumps({"headline": "macro", "evidence_refs": ["macro_context"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    (memo_dir / "04_candidate_review.json").write_text(
        json.dumps(
            {
                "schema": "agent_memo_v1",
                "agent": "CandidateReviewAgent",
                "scope": "market",
                "source_refs": [f"market_cycle/{run_date}/11_deep_review_queue.json"],
                "source_attempts": [
                    {
                        "schema": "source_attempt_v1",
                        "source": "Tavily",
                        "tool": "search",
                        "domain": "news",
                        "status": "FAILED",
                        "failure_reason": "429 Too Many Requests",
                        "results_count": 0,
                    },
                    {
                        "schema": "source_attempt_v1",
                        "source": "screening_funnel",
                        "tool": "deep_review_queue",
                        "domain": "candidate",
                        "status": "DEGRADED",
                        "failure_reason": "limited evidence",
                        "results_count": 3,
                    },
                ],
                "evidence_pack": {
                    "schema": "evidence_pack_v1",
                    "missing_evidence": ["announcement_refs"],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = write_daily_source_health_ledgers(docs, run_date)

    assert result["sourceHealthV2"] == f"run_status/{run_date}/source_health_v2.json"
    assert result["runMatrix"] == f"run_status/{run_date}/run_matrix.json"
    assert (docs / "run_status" / run_date / "source_health_v2.json").exists()
    assert (docs / "run_status" / run_date / "run_matrix.json").exists()
    run_matrix = json.loads((docs / "run_status" / run_date / "run_matrix.json").read_text(encoding="utf-8"))
    assert run_matrix["schema"] == "run_matrix_v1"
    assert {row["name"] for row in run_matrix["stages"]} >= {"data_source_pre_smoke", "source_health_snapshot"}

    assert result["providerRuns"] >= 1
    assert result["evidenceFacts"] >= 1
    provider_rows = load_provider_ledger(docs / "run_status" / run_date / "provider_runs.jsonl")
    assert not any(row.get("provider") == "Tavily" for row in provider_rows)

    evidence_rows = load_evidence_ledger(docs / "run_status" / run_date / "evidence_ledger.jsonl")
    by_id = {row["id"]: row for row in evidence_rows}
    assert f"agent_memo:market:CandidateReviewAgent:source_ref:0" not in by_id
    assert f"agent_memo:market:CandidateReviewAgent:missing:0" not in by_id
    assert by_id[f"market_cycle:01_macro_review:0"]["domain"] == "macro"


def test_successful_subject_provider_runs_become_derived_evidence(tmp_path):
    from src.source_health.daily_ledgers import write_daily_source_health_ledgers
    from src.source_health.evidence_ledger import load_evidence_ledger
    from src.source_health.provider_ledger import write_provider_ledger

    docs = tmp_path / "docs"
    run_date = "2099-01-02"
    run_status = docs / "run_status" / run_date
    run_status.mkdir(parents=True)
    write_provider_ledger(
        run_status / "provider_runs.jsonl",
        [
            {
                "provider": "AkshareFetcher",
                "data_type": "daily_data",
                "operation": "daily_data",
                "success": True,
                "record_count": 240,
                "source_scope": "subject_evidence",
            },
            {
                "provider": "SEC_EDGAR",
                "data_type": "fundamentals",
                "operation": "companyfacts",
                "success": True,
                "record_count": 4,
                "source_scope": "source_smoke",
            },
        ],
    )

    write_daily_source_health_ledgers(docs, run_date)

    rows = load_evidence_ledger(run_status / "evidence_ledger.jsonl")
    by_id = {row["id"]: row for row in rows}
    price = by_id["provider_run:subject_evidence:AkshareFetcher:daily_data:price"]
    assert price["fact_type"] == "derived_fact"
    assert price["evidence_scope"] == "subject_evidence"
    assert price["raw_path"] == f"run_status/{run_date}/provider_runs.jsonl"

    smoke = by_id["provider_run:source_smoke:SEC_EDGAR:companyfacts:fundamentals"]
    assert smoke["evidence_scope"] == "source_smoke"


def test_stale_unscoped_official_provider_runs_do_not_backfill_subject_evidence(tmp_path):
    from src.source_health.daily_ledgers import write_daily_source_health_ledgers
    from src.source_health.evidence_ledger import load_evidence_ledger
    from src.source_health.provider_ledger import load_provider_ledger, write_provider_ledger

    docs = tmp_path / "docs"
    run_date = "2099-01-02"
    run_status = docs / "run_status" / run_date
    run_status.mkdir(parents=True)
    write_provider_ledger(
        run_status / "provider_runs.jsonl",
        [
            {
                "provider": "SEC_EDGAR",
                "data_type": "fundamentals",
                "operation": "sec_companyfacts",
                "success": True,
                "record_count": 4,
            },
            {
                "provider": "AkshareFetcher",
                "data_type": "daily_data",
                "operation": "daily_data",
                "success": True,
                "record_count": 240,
            },
        ],
    )
    official = docs / "official_events"
    official.mkdir(parents=True)
    (official / f"{run_date}.json").write_text(
        json.dumps(
            {
                "schema": "official_event_sources_v1",
                "runDate": run_date,
                "sourceScope": "subject_evidence",
                "providerRuns": [
                    {
                        "provider": "SEC_EDGAR",
                        "domain": "fundamentals",
                        "operation": "sec_companyfacts",
                        "success": False,
                        "record_count": 0,
                        "error_type": "not_supported",
                        "source_scope": "subject_evidence",
                    }
                ],
                "evidenceFacts": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    write_daily_source_health_ledgers(docs, run_date)

    provider_rows = load_provider_ledger(run_status / "provider_runs.jsonl")
    assert not any(row.get("provider") == "SEC_EDGAR" and row.get("success") is True for row in provider_rows)

    evidence_rows = load_evidence_ledger(run_status / "evidence_ledger.jsonl")
    assert not any(row.get("provider") == "SEC_EDGAR" and row.get("domain") == "fundamentals" for row in evidence_rows)
    assert any(row["id"] == "provider_run:subject_evidence:AkshareFetcher:daily_data:price" for row in evidence_rows)


def test_daily_source_health_ledgers_merge_subject_evidence_collection(tmp_path):
    from src.source_health.daily_ledgers import write_daily_source_health_ledgers
    from src.source_health.evidence_ledger import load_evidence_ledger, write_evidence_ledger
    from src.source_health.provider_ledger import load_provider_ledger, write_provider_ledger

    docs = tmp_path / "docs"
    run_date = "2099-01-02"
    run_status = docs / "run_status" / run_date
    run_status.mkdir(parents=True)
    (run_status / "daily_universe.json").write_text(
        json.dumps(
            {
                "schema": "daily_universe_v1",
                "runDate": run_date,
                "mode": "multi_subject_daily",
                "subjectSymbols": ["600519", "000001"],
                "groups": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    write_provider_ledger(
        run_status / "subject_provider_runs.jsonl",
        [
            {
                "provider": "EfinanceFetcher",
                "operation": "realtime_quote",
                "domain": "price",
                "success": True,
                "record_count": 1,
                "source_scope": "subject_evidence",
            }
        ],
    )
    write_evidence_ledger(
        run_status / "subject_evidence.jsonl",
        [
            {
                "id": f"subject:600519:quote:{run_date}",
                "domain": "price",
                "symbol": "600519",
                "provider": "EfinanceFetcher",
                "fact_type": "derived_fact",
                "value": "quote available",
                "raw_path": f"run_status/{run_date}/subject_provider_runs.jsonl",
                "evidence_scope": "subject_evidence",
            }
        ],
    )

    result = write_daily_source_health_ledgers(docs, run_date)

    assert result["universeSubjects"] == 2
    provider_rows = load_provider_ledger(run_status / "provider_runs.jsonl")
    assert any(row.get("provider") == "EfinanceFetcher" for row in provider_rows)
    evidence_rows = load_evidence_ledger(run_status / "evidence_ledger.jsonl")
    assert any(row.get("id") == f"subject:600519:quote:{run_date}" for row in evidence_rows)
    run_matrix = json.loads((run_status / "run_matrix.json").read_text(encoding="utf-8"))
    stages = {row["name"] for row in run_matrix["stages"]}
    assert {"daily_universe", "subject_evidence_collection", "source_health_snapshot"} <= stages
    assert run_matrix["symbols"] == ["600519", "000001"]


def test_daily_source_health_ledgers_include_fred_macro_cache(tmp_path):
    from src.source_health.daily_ledgers import write_daily_source_health_ledgers
    from src.source_health.evidence_ledger import load_evidence_ledger
    from src.source_health.provider_ledger import load_provider_ledger

    docs = tmp_path / "docs"
    run_date = "2099-01-02"
    cache = tmp_path / "data" / "macro_cache"
    cache.mkdir(parents=True)
    (cache / "macro_context_latest.json").write_text(
        json.dumps(
            {
                "status": "REFRESHED",
                "components": {
                    "fred": {
                        "status": "available",
                        "series": [
                            {"series_id": "DGS10", "factor": "liquidity_rates", "date": run_date, "value": 4.2}
                        ],
                    },
                    "china_public": {
                        "status": "available",
                        "series": [
                            {
                                "series_id": "CN_PMI_MANUFACTURING",
                                "factor": "growth",
                                "date": "2099年01月份",
                                "value": 50.3,
                                "source_url": "https://data.eastmoney.com/cjsj/pmi.html",
                            }
                        ],
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    write_daily_source_health_ledgers(docs, run_date)

    provider_rows = load_provider_ledger(docs / "run_status" / run_date / "provider_runs.jsonl")
    evidence_rows = load_evidence_ledger(docs / "run_status" / run_date / "evidence_ledger.jsonl")
    assert any(row.get("provider") == "FRED" and row.get("success") is True for row in provider_rows)
    assert any(row.get("provider") == "AkShareChinaMacro" and row.get("success") is True for row in provider_rows)
    assert any(
        row.get("id") == f"fred:DGS10:{run_date}" and row.get("fact_type") == "verified_fact"
        for row in evidence_rows
    )
    assert any(
        row.get("id") == "china_macro:CN_PMI_MANUFACTURING:2099年01月份"
        and row.get("fact_type") == "derived_fact"
        for row in evidence_rows
    )


def test_pages_validation_stays_out_of_research_evidence_ledgers(tmp_path):
    from src.source_health.daily_ledgers import write_daily_source_health_ledgers
    from src.source_health.evidence_ledger import load_evidence_ledger
    from src.source_health.provider_ledger import load_provider_ledger

    docs = tmp_path / "docs"
    run_date = "2099-01-02"
    run_status = docs / "run_status" / run_date
    run_status.mkdir(parents=True)
    (run_status / "pages_validation.json").write_text(
        json.dumps(
            {
                "schema": "pages_bundle_validation_v1",
                "ok": True,
                "required_files_checked": 20,
                "links_checked": 48,
                "legacy_public_files": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    write_daily_source_health_ledgers(docs, run_date)

    provider_rows = load_provider_ledger(run_status / "provider_runs.jsonl")
    evidence_rows = load_evidence_ledger(run_status / "evidence_ledger.jsonl")
    assert not any(row.get("provider") == "PagesValidator" for row in provider_rows)
    assert not any(row.get("id") == f"pages_bundle:{run_date}:validation" for row in evidence_rows)


def test_final_publication_health_can_include_completed_pages_validation(tmp_path):
    from src.source_health.daily_ledgers import write_daily_source_health_ledgers
    from src.source_health.provider_ledger import load_provider_ledger

    docs = tmp_path / "docs"
    run_date = "2099-01-02"
    run_status = docs / "run_status" / run_date
    run_status.mkdir(parents=True)
    (run_status / "pages_validation.json").write_text(
        json.dumps(
            {
                "schema": "pages_bundle_validation_v1",
                "ok": True,
                "required_files_checked": 20,
                "links_checked": 48,
                "legacy_public_files": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    write_daily_source_health_ledgers(docs, run_date, include_pages_validation=True)

    provider_rows = load_provider_ledger(run_status / "provider_runs.jsonl")
    assert any(row.get("provider") == "PagesValidator" and row.get("success") is True for row in provider_rows)
    health = json.loads((run_status / "source_health_v2.json").read_text(encoding="utf-8"))
    assert health["domains"]["publish_bundle"]["status"] == "available"
