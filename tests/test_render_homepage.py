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
