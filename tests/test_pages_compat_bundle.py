import json


def test_official_event_script_uses_daily_universe_symbols(tmp_path, monkeypatch):
    import scripts.fetch_official_event_sources as fetch_script
    from src.source_health.official_event_sources import OfficialEventSourceResult

    docs = tmp_path / "docs"
    run_date = "2099-01-02"
    (docs / "run_status" / run_date).mkdir(parents=True)
    (docs / "run_status" / run_date / "daily_universe.json").write_text(
        json.dumps({"subjectSymbols": ["600519", "AAPL"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    captured = {}

    class FakeClient:
        def __init__(self, timeout_s):
            pass

        def fetch(self, *, symbols, query_terms, run_date):
            captured["symbols"] = list(symbols)
            captured["query_terms"] = list(query_terms)
            return OfficialEventSourceResult(provider_runs=[], evidence_facts=[], raw={})

    monkeypatch.setattr(fetch_script, "OfficialEventSourceClient", FakeClient)

    assert fetch_script.main(["--date", run_date, "--docs-dir", str(docs)]) == 0
    assert captured["symbols"] == ["600519", "AAPL"]
    assert captured["query_terms"][:2] == ["600519", "AAPL"]
    assert "global sanctions export controls" in captured["query_terms"]


def test_pages_compat_bundle_writes_required_legacy_entries(tmp_path):
    from scripts.build_pages_compat_bundle import main

    docs = tmp_path / "docs"
    run_date = "2099-01-02"
    (docs / "reports").mkdir(parents=True)
    (docs / "reports" / f"{run_date}.artifact.json").write_text(
        json.dumps(
            {
                "analysisMode": "SCREEN_ONLY",
                "readerBrief": {
                    "mode": "SCREEN_ONLY",
                    "oneLine": "覆盖 2 个观察标的。",
                    "finalConclusion": "等待证据共振。",
                    "why": ["市场已纳入"],
                    "risks": ["公告缺口"],
                    "nextSteps": ["看分部门报告"],
                },
                "evidenceStats": {"verifiedFacts": 2},
                "departmentReports": [{"subject": "AAPL", "readerVisible": False, "summaryForReader": "个股下钻"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    status = docs / "run_status" / run_date
    status.mkdir(parents=True)
    (status / "daily_universe.json").write_text(
        json.dumps({"mode": "multi_subject_daily", "subjectSymbols": ["600519", "AAPL"], "groups": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    (status / "source_health_v2.json").write_text(
        json.dumps(
            {
                "overallMode": "SCREEN_ONLY",
                "overallScore": 0.72,
                "blockingReasons": ["filings_events:failed"],
                "claimPolicy": {"canActionableAdvice": True},
                "domains": {"price": {"status": "available", "repairHints": []}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert main(["--date", run_date, "--docs-dir", str(docs), "--runtime-reports-dir", str(tmp_path / "reports")]) == 0
    required = [
        f"daily/{run_date}.md",
        f"daily/{run_date}.html",
        f"market_cycle/{run_date}/summary.html",
        f"market_cycle/{run_date}/00_one_screen_brief.html",
        f"market_cycle/{run_date}/01_macro_review.html",
        f"market_cycle/{run_date}/09_screening_funnel.html",
        f"market_cycle/{run_date}/11_deep_review_queue.html",
        f"market_cycle/{run_date}/13_source_health.html",
        f"market_cycle/{run_date}/14_market_strategy.html",
    ]
    for rel in required:
        assert (docs / rel).exists(), rel
