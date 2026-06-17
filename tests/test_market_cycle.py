import json
from pathlib import Path


def test_market_cycle_generates_three_core_reports(tmp_path):
    from src.market_cycle import build_market_cycle_payload, write_market_cycle_outputs

    report = tmp_path / "reports" / "report_20260602.md"
    report.parent.mkdir()
    report.write_text("# 个股报告\n", encoding="utf-8")

    macro_context = {
        "schema": "macro_context_v1",
        "status": "REFRESHED",
        "as_of": "2026-06-02T01:00:00+00:00",
        "regime": {"risk_state": "risk_on", "confidence": "medium", "reason": "VIX low"},
        "warnings": [],
    }
    market_heat = {
        "schema": "market_heat_v1",
        "status": "available",
        "as_of": "2026-06-02T01:01:00+00:00",
        "watchlist": ["301013", "160644"],
        "focus_items": [{"symbol": "301013", "reason": "watchlist_member", "heat_bucket": "watch"}],
        "warnings": ["polymarket_optional_unavailable"],
    }

    payload = build_market_cycle_payload(
        run_date="2026-06-02",
        symbols=["301013", "160644"],
        macro_context=macro_context,
        market_heat=market_heat,
        prediction_market={
            "schema": "prediction_market_signal_v1",
            "status": "available",
            "scenario_fusion": [],
            "warnings": [],
        },
        report_files=[report],
    )

    assert payload["macro_status"] == "REFRESHED"
    assert payload["macro_review"]["schema"] == "macro_review_v1"
    assert payload["prediction_market_status"] == "AVAILABLE"
    assert payload["screening_funnel"]["schema"] == "screening_funnel_v1"
    assert payload["deep_review_queue"]["schema"] == "deep_review_queue_v1"
    assert payload["source_health"]["macro_status"] == "REFRESHED"
    assert payload["source_health"]["trade_review_usability"] == "usable"
    assert payload["source_health"]["usability_verdict"] == "degraded"
    assert payload["market_strategy"]["participation_allowed"] is True

    paths = write_market_cycle_outputs(payload, tmp_path / "market_cycle")
    expected = {
        "00_one_screen_brief.html",
        "01_macro_review.html",
        "01_macro_review.md",
        "01_macro_review.json",
        "09_screening_funnel.md",
        "09_screening_funnel.json",
        "11_deep_review_queue.md",
        "11_deep_review_queue.json",
        "12_preliminary_deep_review.md",
        "13_source_health.html",
        "13_source_health.md",
        "13_source_health.json",
        "14_market_strategy.html",
        "14_market_strategy.md",
        "14_market_strategy.json",
        "summary.md",
    }
    assert expected.issubset({p.name for p in paths.values()})
    assert "统一看盘" in (tmp_path / "market_cycle" / "00_one_screen_brief.html").read_text(encoding="utf-8")
    assert "STRUCTURAL_RISK_ON" in (tmp_path / "market_cycle" / "14_market_strategy.md").read_text(encoding="utf-8")


def test_market_cycle_critical_macro_unavailable_blocks_trade_review(tmp_path):
    from src.market_cycle import build_market_cycle_payload

    payload = build_market_cycle_payload(
        run_date="2026-06-02",
        symbols=["301013"],
        macro_context={"status": "UNAVAILABLE", "warnings": ["macro_down"]},
        market_heat={"status": "available", "watchlist": ["301013"], "warnings": []},
        prediction_market={"status": "degraded", "warnings": ["optional_down"]},
        report_files=[],
    )

    assert payload["source_health"]["trade_review_usability"] == "unavailable"
    assert payload["market_strategy"]["participation_allowed"] is False
    assert payload["market_strategy"]["participation_gate_reason"] == "critical_source_unavailable"


def test_prediction_market_optional_failure_only_degrades_daily_report():
    from src.market_cycle import build_market_cycle_payload

    payload = build_market_cycle_payload(
        run_date="2026-06-02",
        symbols=["301013"],
        macro_context={"status": "REFRESHED", "regime": {"risk_state": "neutral", "confidence": "medium"}, "warnings": []},
        market_heat={"status": "available", "focus_items": [{"symbol": "301013", "heat_bucket": "watch"}], "warnings": []},
        prediction_market={"status": "degraded", "warnings": ["polymarket_live_disabled"]},
        report_files=[],
    )

    assert payload["source_health"]["trade_review_usability"] == "usable_limited"
    assert payload["source_health"]["usability_verdict"] == "degraded"
    assert payload["market_strategy"]["participation_allowed"] is True


def test_market_cycle_report_files_are_date_scoped(tmp_path, monkeypatch):
    from src.market_cycle import _find_report_files

    reports = tmp_path / "reports"
    reports.mkdir()
    old_report = reports / "report_20260601.md"
    old_report.write_text("# old\n", encoding="utf-8")
    today_report = reports / "report_20260615.md"
    today_report.write_text("# today\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert _find_report_files("2026-06-15", "reports/report_*.md") == [Path("reports/report_20260615.md")]
    assert _find_report_files("2026-06-16", "reports/report_*.md") == []


def test_market_cycle_source_health_includes_empty_portfolio_as_non_blocking():
    from src.market_cycle import build_market_cycle_payload

    payload = build_market_cycle_payload(
        run_date="2026-06-17",
        symbols=["600519"],
        macro_context={"status": "REFRESHED", "regime": {"risk_state": "neutral", "confidence": "medium"}, "warnings": []},
        market_heat={"status": "available", "focus_items": [], "warnings": []},
        prediction_market={"status": "available", "warnings": [], "scenario_fusion": []},
        portfolio_holdings={"status": "empty", "symbols": [], "warnings": []},
        report_files=[],
    )

    rows = {row["component"]: row for row in payload["source_health"]["rows"]}
    assert rows["portfolio_holdings"]["holding_status"] == "EMPTY"
    assert rows["portfolio_holdings"]["usability"] == "usable"
    assert rows["portfolio_holdings"]["selected_count"] == 0
    assert rows["portfolio_holdings"]["governed_count"] == 0
    assert rows["portfolio_holdings"]["light_review_count"] == 0


def test_market_cycle_source_health_reports_portfolio_review_tiers():
    from src.market_cycle import build_market_cycle_payload

    payload = build_market_cycle_payload(
        run_date="2026-06-17",
        symbols=["301013", "160644"],
        macro_context={"status": "REFRESHED", "regime": {"risk_state": "neutral", "confidence": "medium"}, "warnings": []},
        market_heat={"status": "available", "focus_items": [], "warnings": []},
        prediction_market={"status": "available", "warnings": [], "scenario_fusion": []},
        portfolio_holdings={
            "status": "available",
            "symbols": ["160644", "301013"],
            "governed_symbols": ["301013"],
            "light_review_symbols": ["160644"],
            "warnings": [],
        },
        report_files=[],
    )

    rows = {row["component"]: row for row in payload["source_health"]["rows"]}
    assert rows["portfolio_holdings"]["selected_count"] == 2
    assert rows["portfolio_holdings"]["governed_count"] == 1
    assert rows["portfolio_holdings"]["light_review_count"] == 1
