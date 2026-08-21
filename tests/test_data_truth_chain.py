import json


def test_agent_memo_source_refs_do_not_support_source_health(tmp_path):
    from src.source_health.daily_ledgers import write_daily_source_health_ledgers
    from src.source_health.evidence_ledger import load_evidence_ledger
    from src.source_health.policy import build_source_health_v2

    docs = tmp_path / "docs"
    run_date = "2099-01-02"
    memo_dir = docs / "agent_memos" / run_date / "market"
    memo_dir.mkdir(parents=True)
    (docs / "run_status" / run_date).mkdir(parents=True)
    (docs / "run_status" / run_date / "daily_universe.json").write_text(
        json.dumps({"subjectSymbols": ["AAPL"], "groups": []}),
        encoding="utf-8",
    )
    (memo_dir / "04_candidate_review.json").write_text(
        json.dumps(
            {
                "schema": "agent_memo_v1",
                "agent": "CandidateReviewAgent",
                "scope": "market",
                "origin": "RAW_AGENT",
                "source_refs": ["subject:AAPL:fundamentals:stale"],
            }
        ),
        encoding="utf-8",
    )

    write_daily_source_health_ledgers(docs, run_date)

    facts = load_evidence_ledger(docs / "run_status" / run_date / "evidence_ledger.jsonl")
    assert not any(str(row.get("id") or "").startswith("agent_memo:") for row in facts)

    legacy_fact_health = build_source_health_v2(
        {},
        evidence_facts=[
            {
                "id": "agent_memo:market:CandidateReviewAgent:source_ref:0",
                "domain": "fundamentals",
                "fact_type": "derived_fact",
                "provider": "agent_memo",
                "raw_path": "agent_memos/2099-01-02/market/04_candidate_review.json",
            }
        ],
        agent_origin_counts={"RAW_AGENT": 1},
    )
    assert legacy_fact_health["domains"]["fundamentals"]["status"] == "missing"
    assert legacy_fact_health["evidenceStats"]["derivedFacts"] == 0
    assert legacy_fact_health["claimEvidence"]["claims"]["score"]["status"] == "missing"


def test_price_and_fundamentals_coverage_uses_daily_subjects(tmp_path):
    from src.source_health.daily_ledgers import write_daily_source_health_ledgers
    from src.source_health.evidence_ledger import write_evidence_ledger
    from src.source_health.provider_ledger import write_provider_ledger

    docs = tmp_path / "docs"
    run_date = "2099-01-02"
    run_dir = docs / "run_status" / run_date
    run_dir.mkdir(parents=True)
    subjects = ["600519", "000001", "HK00700", "AAPL"]
    (run_dir / "daily_universe.json").write_text(
        json.dumps({"subjectSymbols": subjects, "groups": []}),
        encoding="utf-8",
    )
    write_provider_ledger(
        run_dir / "subject_provider_runs.jsonl",
        [
            *[
                {
                    "provider": "QuoteProvider",
                    "operation": "quote",
                    "domain": "price",
                    "symbol": symbol,
                    "success": True,
                    "record_count": 1,
                    "source_scope": "subject_evidence",
                }
                for symbol in subjects
            ],
            {
                "provider": "FundamentalProvider",
                "operation": "fundamentals",
                "domain": "fundamentals",
                "symbol": "AAPL",
                "success": True,
                "record_count": 1,
                "source_scope": "subject_evidence",
            },
        ],
    )
    write_evidence_ledger(
        run_dir / "subject_evidence.jsonl",
        [{
            "id": f"subject:AAPL:fundamental:earnings:{run_date}",
            "domain": "fundamentals",
            "symbol": "AAPL",
            "subject": "AAPL",
            "provider": "YfinanceFundamentalAdapter",
            "value": "revenue=100 net_income=20",
            "fact_type": "derived_fact",
            "evidence_scope": "subject_evidence",
            "raw_path": f"run_status/{run_date}/subject_evidence.jsonl",
            "as_of": run_date,
        }],
    )
    write_daily_source_health_ledgers(docs, run_date)

    health = json.loads((run_dir / "source_health_v2.json").read_text(encoding="utf-8"))
    assert health["domains"]["price"]["coverage"] == 1.0
    assert health["domains"]["fundamentals"]["coverage"] == 0.25
    assert health["domains"]["fundamentals"]["status"] == "partial"
    assert health["domains"]["fundamentals"]["coveredSubjects"] == ["AAPL"]
    assert health["domains"]["fundamentals"]["missingSubjects"] == ["600519", "000001", "HK00700"]
    assert health["claimEvidence"]["claims"]["score"]["status"] != "supported"
    assert health["overallMode"] != "FULL_REVIEW"


def test_valuation_only_fundamentals_do_not_count_as_full_depth():
    from src.source_health.policy import build_source_health_v2

    subjects = ["600519", "000001", "AAPL", "HK00700"]
    facts = []
    for symbol in subjects:
        value = "pe_ratio=5 pb_ratio=0.5"
        fact_id = f"cio:fundamentals:{symbol}"
        if symbol != "000001":
            value += " revenue=100 net_income=20"
            fact_id = f"subject:{symbol}:fundamental:earnings"
        facts.append({
            "id": fact_id,
            "domain": "fundamentals",
            "symbol": symbol,
            "subject": symbol,
            "provider": "test",
            "value": value,
            "fact_type": "derived_fact",
            "evidence_scope": "subject_evidence",
            "raw_path": "fixture.jsonl",
            "as_of": "2099-01-02",
        })

    health = build_source_health_v2(
        {},
        evidence_facts=facts,
        subject_symbols=subjects,
        agent_origin_counts={"RAW_AGENT": 1},
    )

    fundamentals = health["domains"]["fundamentals"]
    assert fundamentals["status"] == "partial"
    assert fundamentals["coverage"] == 0.875
    assert fundamentals["shallowSubjects"] == ["000001"]
    assert "subject_fundamental_depth_incomplete" in fundamentals["blockers"]
    assert health["overallMode"] != "FULL_REVIEW"


def test_same_date_rerun_drops_stale_cio_and_agent_provider_rows(tmp_path):
    from src.source_health.daily_ledgers import write_daily_source_health_ledgers
    from src.source_health.provider_ledger import load_provider_ledger, write_provider_ledger

    docs = tmp_path / "docs"
    run_date = "2099-01-02"
    run_dir = docs / "run_status" / run_date
    run_dir.mkdir(parents=True)
    (run_dir / "daily_universe.json").write_text(
        json.dumps({"subjectSymbols": ["AAPL"], "groups": []}),
        encoding="utf-8",
    )
    write_provider_ledger(
        run_dir / "provider_runs.jsonl",
        [
            {
                "provider": "CurrentQuoteProvider",
                "operation": "quote",
                "domain": "price",
                "symbol": "AAPL",
                "success": True,
                "record_count": 1,
                "source_scope": "subject_evidence",
            },
            {
                "provider": "DataFetcherManager",
                "operation": "cio_enrichment",
                "domain": "fundamentals",
                "symbol": "AAPL",
                "success": True,
                "record_count": 1,
                "source_scope": "cio_enrichment",
            },
            {
                "provider": "OldMemoProvider",
                "operation": "source_attempt",
                "data_type": "fundamentals",
                "domain": "fundamentals",
                "success": True,
                "record_count": 1,
            },
        ],
    )
    memo_dir = docs / "agent_memos" / run_date / "market"
    memo_dir.mkdir(parents=True)
    (memo_dir / "04_candidate_review.json").write_text(
        json.dumps(
            {
                "schema": "agent_memo_v1",
                "agent": "CandidateReviewAgent",
                "source_attempts": [
                    {
                        "source": "OldMemoProvider",
                        "tool": "source_attempt",
                        "domain": "fundamentals",
                        "status": "SUCCESS",
                        "results_count": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    write_daily_source_health_ledgers(docs, run_date)

    rows = load_provider_ledger(run_dir / "provider_runs.jsonl")
    assert any(row.get("provider") == "CurrentQuoteProvider" for row in rows)
    assert not any(row.get("source_scope") == "cio_enrichment" for row in rows)
    assert not any(row.get("source_scope") == "agent_memo" for row in rows)
    assert not any(row.get("provider") == "OldMemoProvider" for row in rows)
    health = json.loads((run_dir / "source_health_v2.json").read_text(encoding="utf-8"))
    assert health["domains"]["fundamentals"]["status"] == "missing"


def test_post_publish_refresh_can_preserve_current_cio_enrichment(tmp_path):
    from src.source_health.daily_ledgers import write_daily_source_health_ledgers
    from src.source_health.evidence_ledger import load_evidence_ledger, write_evidence_ledger
    from src.source_health.provider_ledger import load_provider_ledger, write_provider_ledger

    docs = tmp_path / "docs"
    run_date = "2099-01-02"
    run_dir = docs / "run_status" / run_date
    run_dir.mkdir(parents=True)
    (run_dir / "daily_universe.json").write_text(
        json.dumps({"subjectSymbols": ["AAPL"], "groups": []}),
        encoding="utf-8",
    )
    write_provider_ledger(
        run_dir / "provider_runs.jsonl",
        [{
            "provider": "DataFetcherManager",
            "operation": "cio_enrichment",
            "domain": "fundamentals",
            "symbol": "AAPL",
            "success": True,
            "record_count": 1,
            "source_scope": "cio_enrichment",
        }],
    )
    evidence_id = f"cio:fundamentals:AAPL:DataFetcherManager:{run_date}"
    write_evidence_ledger(
        run_dir / "evidence_ledger.jsonl",
        [{
            "id": evidence_id,
            "domain": "fundamentals",
            "symbol": "AAPL",
            "subject": "AAPL",
            "provider": "DataFetcherManager",
            "value": "pe_ratio=25.1 total_revenue=100",
            "fact_type": "derived_fact",
            "evidence_scope": "subject_evidence",
            "origin": "CIO_REQUESTED",
            "as_of": run_date,
            "raw_path": f"run_status/{run_date}/cio_enrichment_runs.jsonl",
        }],
    )

    write_daily_source_health_ledgers(
        docs,
        run_date,
        preserve_runtime_enrichment=True,
    )

    providers = load_provider_ledger(run_dir / "provider_runs.jsonl")
    evidence = load_evidence_ledger(run_dir / "evidence_ledger.jsonl")
    assert any(row.get("source_scope") == "cio_enrichment" for row in providers)
    assert any(row.get("id") == evidence_id for row in evidence)


def test_cio_reused_evidence_is_not_reported_as_added_or_new_success(tmp_path):
    from src.cio_enrichment import run_cio_enrichment
    from src.source_health.evidence_ledger import load_evidence_ledger, write_evidence_ledger
    from src.source_health.provider_ledger import load_provider_ledger, write_provider_ledger

    class ManagerMustNotRun:
        def get_realtime_quote(self, *args, **kwargs):
            raise AssertionError("existing evidence must be reused before provider fetch")

    docs = tmp_path / "docs"
    run_date = "2099-01-02"
    run_dir = docs / "run_status" / run_date
    run_dir.mkdir(parents=True)
    (run_dir / "daily_universe.json").write_text(
        json.dumps({"subjectSymbols": ["AAPL"], "groups": []}),
        encoding="utf-8",
    )
    (run_dir / "source_health_v2.json").write_text(
        json.dumps(
            {
                "domains": {"price": {"status": "missing"}},
                "claimEvidence": {"claims": {"score": {"missingDomains": ["price"]}}},
            }
        ),
        encoding="utf-8",
    )
    existing_id = f"subject:AAPL:quote:{run_date}"
    write_evidence_ledger(
        run_dir / "evidence_ledger.jsonl",
        [
            {
                "id": existing_id,
                "domain": "price",
                "symbol": "AAPL",
                "provider": "QuoteProvider",
                "fact_type": "derived_fact",
                "raw_path": f"run_status/{run_date}/subject_provider_runs.jsonl",
            }
        ],
    )
    write_provider_ledger(
        run_dir / "provider_runs.jsonl",
        [
            {
                "provider": "DataFetcherManager",
                "operation": "cio_enrichment",
                "domain": "price",
                "symbol": "AAPL",
                "success": True,
                "record_count": 1,
                "source_scope": "cio_enrichment",
            }
        ],
    )

    summary = run_cio_enrichment(
        docs,
        run_date,
        {"agent": "CIOAgent", "data_gaps": ["缺少 AAPL 价格"]},
        manager=ManagerMustNotRun(),
    )

    assert summary["requestCount"] == 1
    assert summary["successCount"] == 0
    assert summary["failedCount"] == 0
    assert summary["reusedCount"] == 1
    assert summary["addedEvidenceIds"] == []
    assert summary["reusedEvidenceIds"] == [existing_id]
    assert summary["remainingGaps"] == []
    facts = load_evidence_ledger(run_dir / "evidence_ledger.jsonl")
    assert [row["id"] for row in facts] == [existing_id]
    runs = [json.loads(line) for line in (run_dir / "cio_enrichment_runs.jsonl").read_text().splitlines()]
    assert runs[0]["status"] == "reused"
    assert runs[0]["success"] is False
    assert not any(
        row.get("source_scope") == "cio_enrichment"
        for row in load_provider_ledger(run_dir / "provider_runs.jsonl")
    )


def test_cio_requests_each_missing_subject_without_reusing_covered_subject_slots():
    from src.cio_enrichment import build_cio_data_requests

    requests = build_cio_data_requests(
        {"agent": "CIOAgent", "data_gaps": ["基本面覆盖不完整"]},
        source_health={
            "domains": {
                "fundamentals": {
                    "status": "partial",
                    "coverage": 0.25,
                    "coveredSubjects": ["AAPL"],
                    "missingSubjects": ["600519", "000001", "HK00700"],
                }
            },
            "claimEvidence": {
                "claims": {"score": {"partialDomains": ["fundamentals"]}}
            },
        },
        universe={"subjectSymbols": ["AAPL", "600519", "000001", "HK00700"]},
        max_requests=8,
    )

    assert [(row["domain"], row["symbol"]) for row in requests] == [
        ("fundamentals", "600519"),
        ("fundamentals", "000001"),
        ("fundamentals", "HK00700"),
    ]


def test_cio_added_ids_are_unique_and_failed_subjects_remain_gaps(tmp_path):
    from src.cio_enrichment import run_cio_enrichment

    docs = tmp_path / "docs"
    run_date = "2099-01-02"
    run_dir = docs / "run_status" / run_date
    run_dir.mkdir(parents=True)
    (run_dir / "daily_universe.json").write_text(
        json.dumps({"subjectSymbols": ["AAPL", "MSFT"], "groups": []}),
        encoding="utf-8",
    )
    (run_dir / "source_health_v2.json").write_text(
        json.dumps(
            {
                "domains": {
                    "filings_events": {
                        "status": "partial",
                        "missingSubjects": ["AAPL", "MSFT"],
                    }
                },
                "claimEvidence": {
                    "claims": {"score": {"missingDomains": ["filings_events"]}}
                },
            }
        ),
        encoding="utf-8",
    )
    official_dir = docs / "official_events"
    official_dir.mkdir(parents=True)
    (official_dir / f"{run_date}.json").write_text(
        json.dumps(
            {
                "evidenceFacts": [
                    {
                        "provider": "SEC_EDGAR",
                        "symbol": "AAPL",
                        "title": "first filing fact",
                        "fact_type": "verified_fact",
                        "source_url": "https://www.sec.gov/Archives/first",
                    },
                    {
                        "provider": "SEC_EDGAR",
                        "symbol": "AAPL",
                        "title": "second filing fact",
                        "fact_type": "verified_fact",
                        "source_url": "https://www.sec.gov/Archives/second",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    summary = run_cio_enrichment(
        docs,
        run_date,
        {"agent": "CIOAgent", "data_gaps": ["缺少公告"]},
    )

    assert summary["successCount"] == 1
    assert summary["failedCount"] == 1
    assert summary["addedEvidenceIds"] == [
        f"cio:filings_events:AAPL:SEC_EDGAR:{run_date}"
    ]
    assert summary["remainingGaps"] == ["filings_events:MSFT"]


def test_cio_new_price_and_fundamental_evidence_contains_analytic_values(tmp_path):
    from types import SimpleNamespace

    from src.cio_enrichment import run_cio_enrichment
    from src.source_health.evidence_ledger import load_evidence_ledger

    class AnalyticManager:
        def get_realtime_quote(self, symbol, log_final_failure=False):
            return SimpleNamespace(
                price=188.25,
                change_pct=1.4,
                currency="USD",
                pe_ratio=31.2,
            )

        def get_fundamental_context(self, symbol, budget_seconds=8):
            return {
                "status": "partial",
                "valuation": {
                    "status": "ok",
                    "data": {"pe_ratio": 31.2, "pb_ratio": 47.8},
                },
                "growth": {
                    "status": "ok",
                    "data": {"revenue_yoy": 6.3, "net_profit_yoy": 9.1},
                },
                "earnings": {
                    "status": "ok",
                    "data": {
                        "financial_report": {
                            "report_date": "2098-12-31",
                            "revenue": 391_000_000_000,
                            "net_profit_parent": 98_000_000_000,
                            "currency": "USD",
                        }
                    },
                },
            }

    docs = tmp_path / "docs"
    run_date = "2099-01-02"
    run_dir = docs / "run_status" / run_date
    run_dir.mkdir(parents=True)
    (run_dir / "daily_universe.json").write_text(
        json.dumps({"subjectSymbols": ["AAPL"], "groups": []}),
        encoding="utf-8",
    )
    (run_dir / "source_health_v2.json").write_text(
        json.dumps(
            {
                "domains": {
                    "price": {"status": "missing", "missingSubjects": ["AAPL"]},
                    "fundamentals": {"status": "missing", "missingSubjects": ["AAPL"]},
                },
                "claimEvidence": {
                    "claims": {
                        "score": {"missingDomains": ["price", "fundamentals"]}
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    summary = run_cio_enrichment(
        docs,
        run_date,
        {"agent": "CIOAgent", "data_gaps": ["缺少价格和基本面"]},
        manager=AnalyticManager(),
    )

    assert summary["successCount"] == 2
    facts = {
        row["domain"]: row
        for row in load_evidence_ledger(run_dir / "evidence_ledger.jsonl")
        if row.get("origin") == "CIO_REQUESTED"
    }
    assert "price=188.25" in facts["price"]["value"]
    assert "change_pct=1.4" in facts["price"]["value"]
    assert "pe_ratio=31.2" in facts["fundamentals"]["value"]
    assert "revenue_yoy=6.3" in facts["fundamentals"]["value"]
    assert "revenue=391000000000" in facts["fundamentals"]["value"]
    assert "available" not in facts["price"]["value"].lower()
    assert "available" not in facts["fundamentals"]["value"].lower()


def test_cio_availability_only_payloads_do_not_become_evidence(tmp_path):
    from types import SimpleNamespace

    from src.cio_enrichment import run_cio_enrichment

    class AvailabilityOnlyManager:
        def get_realtime_quote(self, symbol, log_final_failure=False):
            return SimpleNamespace(price=None, data_quality="available")

        def get_fundamental_context(self, symbol, budget_seconds=8):
            return {
                "status": "partial",
                "market": "us",
                "coverage": {"valuation": "available"},
                "source_chain": [
                    {"provider": "metadata-only", "result": "available"}
                ],
                "errors": [],
            }

    docs = tmp_path / "docs"
    run_date = "2099-01-02"
    run_dir = docs / "run_status" / run_date
    run_dir.mkdir(parents=True)
    (run_dir / "daily_universe.json").write_text(
        json.dumps({"subjectSymbols": ["AAPL"], "groups": []}),
        encoding="utf-8",
    )
    (run_dir / "source_health_v2.json").write_text(
        json.dumps(
            {
                "domains": {
                    "price": {"status": "missing", "missingSubjects": ["AAPL"]},
                    "fundamentals": {"status": "missing", "missingSubjects": ["AAPL"]},
                },
                "claimEvidence": {
                    "claims": {
                        "score": {"missingDomains": ["price", "fundamentals"]}
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    summary = run_cio_enrichment(
        docs,
        run_date,
        {"agent": "CIOAgent", "data_gaps": ["缺少价格和基本面"]},
        manager=AvailabilityOnlyManager(),
    )

    assert summary["successCount"] == 0
    assert summary["failedCount"] == 2
    assert summary["addedEvidenceIds"] == []
    assert summary["remainingGaps"] == ["price:AAPL", "fundamentals:AAPL"]
