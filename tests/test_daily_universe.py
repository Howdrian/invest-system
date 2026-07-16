import json


def test_daily_universe_does_not_fallback_to_single_600519(tmp_path, monkeypatch):
    from src.source_health.daily_universe import build_daily_universe

    monkeypatch.setenv("STOCK_LIST", "600519")
    docs = tmp_path / "docs"
    payload = build_daily_universe(docs, "2099-01-02")

    assert payload["mode"] == "market_and_candidates"
    assert payload["subjectSymbols"] == []
    watchlist = next(row for row in payload["groups"] if row["name"] == "watchlist")
    assert watchlist["symbols"] == []
    assert "不回退" in watchlist["whyIncluded"]


def test_daily_universe_uses_explicit_multi_market_symbols(tmp_path, monkeypatch):
    from src.source_health.daily_universe import build_daily_universe

    monkeypatch.setenv("STOCK_LIST", "600519")
    payload = build_daily_universe(
        tmp_path / "docs",
        "2099-01-02",
        symbols=["600519", "000001", "AAPL", "HK00700", "aapl"],
        market="cn",
    )

    assert payload["mode"] == "multi_subject_daily"
    assert payload["subjectSymbols"] == ["600519", "000001", "AAPL", "HK00700"]
    watchlist = next(row for row in payload["groups"] if row["name"] == "watchlist")
    assert watchlist["source"] == "cli_symbols"
    assert watchlist["symbols"] == ["600519", "000001", "AAPL", "HK00700"]


def test_daily_universe_includes_candidate_symbols_from_market_docs(tmp_path, monkeypatch):
    from src.source_health.daily_universe import build_daily_universe

    monkeypatch.setenv("ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("STOCK_LIST", "")
    docs = tmp_path / "docs"
    date = "2099-01-02"
    path = docs / "market_cycle" / date
    path.mkdir(parents=True)
    (path / "11_deep_review_queue.json").write_text(
        json.dumps({"candidates": [{"symbol": "300750"}, {"code": "002594"}]}),
        encoding="utf-8",
    )

    payload = build_daily_universe(docs, date)

    assert payload["mode"] == "market_and_candidates"
    assert payload["subjectSymbols"] == ["300750", "002594"]
    candidates = next(row for row in payload["groups"] if row["name"] == "candidates")
    assert candidates["symbols"] == ["300750", "002594"]
