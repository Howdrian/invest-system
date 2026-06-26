import json


def test_render_homepage_ignores_stale_governed_results(tmp_path, monkeypatch):
    from src import render_homepage

    reports = tmp_path / "reports"
    docs = tmp_path / "docs"
    reports.mkdir()
    docs.mkdir()
    (docs / "governed_results.json").write_text(
        json.dumps([{"run_date": "2026-06-01", "code": "OLD"}]),
        encoding="utf-8",
    )
    (reports / "governed_results.json").write_text(
        json.dumps([
            {"run_date": "2026-06-15", "code": "600519"},
            {"run_date": "2026-06-01", "code": "000858"},
        ]),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    rows = render_homepage._load_today_governed_results("2026-06-15")

    assert [row["code"] for row in rows] == ["600519"]


def test_render_homepage_accepts_run_date_and_output_paths(tmp_path, monkeypatch):
    from src import render_homepage

    reports = tmp_path / "cloud_reports"
    docs = tmp_path / "published"
    market_cycle = reports / "market_cycle" / "2026-06-17"
    market_cycle.mkdir(parents=True)
    docs.mkdir()

    (reports / "governed_results.json").write_text(
        json.dumps(
            [
                {
                    "run_date": "2026-06-17",
                    "code": "301013",
                    "name": "利和兴",
                    "score": 0.5,
                    "cio_status": "BLOCKED_BY_FATAL",
                    "trade_plan": {"action": "no_action"},
                }
            ]
        ),
        encoding="utf-8",
    )
    (market_cycle / "01_macro_review.json").write_text(json.dumps({"status": "DEGRADED"}), encoding="utf-8")
    (market_cycle / "13_source_health.json").write_text(
        json.dumps({"trade_review_usability": "usable_limited"}),
        encoding="utf-8",
    )
    (market_cycle / "14_market_strategy.json").write_text(
        json.dumps({"regime": "NEUTRAL_WATCH", "strategy": {"headline": "等待确认"}}),
        encoding="utf-8",
    )
    (market_cycle / "09_screening_funnel.json").write_text(json.dumps({"candidates": []}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    out = docs / "index.html"
    rc = render_homepage.main(
        [
            "--date",
            "2026-06-17",
            "--reports-dir",
            str(reports),
            "--market-cycle-dir",
            str(reports / "market_cycle"),
            "--macro-cache",
            str(tmp_path / "missing_macro.json"),
            "--market-heat-dir",
            str(tmp_path / "market_heat"),
            "--output",
            str(out),
            "--stock-list",
            "301013",
        ]
    )

    assert rc == 0
    html = out.read_text(encoding="utf-8")
    assert "./reports/2026-06-17.html" in html
    assert "./daily/2026-06-17.html" in html
    assert "./agent_memos/2026-06-17/index.html" in html
    assert "./market_cycle/2026-06-17/summary.html" in html
    assert "./market_cycle/2026-06-17/13_source_health.html" in html
    assert "./report_20260617.html" not in html
    assert "./market_cycle/2026-06-17/09_screening_funnel.html" not in html
    assert "利和兴" in html
    assert "301013" in html
