def test_macro_context_refresh_uses_fred_when_key_configured(monkeypatch, tmp_path):
    from src.macro.official_sources import MacroContextService
    from src.macro.source_cache import JsonSourceCache

    calls = []

    def fake_get_json(url, *, timeout_s):
        calls.append(url)
        return {
            "observations": [
                {"date": "2099-01-01", "value": "4.25"},
                {"date": "2098-12-31", "value": "4.20"},
            ]
        }

    cache = JsonSourceCache(cache_dir=tmp_path)
    service = MacroContextService(cache=cache, fred_api_key="fred-key")
    monkeypatch.setattr(service, "_get_json", fake_get_json)
    payload = service.refresh()

    fred = payload["components"]["fred"]
    assert fred["status"] == "available"
    assert fred["source"] == "FRED"
    assert len(fred["series"]) >= 4
    series_ids = {row["series_id"] for row in fred["series"]}
    assert {"DGS2", "T10Y2Y", "T10Y3M", "SAHMREALTIME"} <= series_ids
    unrate = next(row for row in fred["series"] if row["series_id"] == "UNRATE")
    assert len(unrate["history"]) == 2
    assert all(len(row["history"]) == 2 for row in fred["series"])
    assert all(row.get("fetched_at") for row in fred["series"])
    assert all("limit=260" in url for url in calls)
    assert any("api.stlouisfed.org/fred/series/observations" in url for url in calls)
    assert "inflation" in payload["coverage"]["available"]
    assert "liquidity_rates" in payload["coverage"]["available"]


def test_macro_context_refreshes_stale_missing_fred_cache_when_key_appears(monkeypatch, tmp_path):
    from src.macro.official_sources import CACHE_KEY, MacroContextService
    from src.macro.source_cache import JsonSourceCache

    cache = JsonSourceCache(cache_dir=tmp_path)
    cache.write(
        CACHE_KEY,
        {
            "schema": "macro_context_v1",
            "status": "PARTIAL",
            "warnings": ["fred_key_missing", "macro_factor_coverage_incomplete"],
            "components": {"fred": {"status": "missing_key", "source": "FRED"}},
        },
    )
    calls = []

    def fake_refresh():
        calls.append("refresh")
        return {
            "schema": "macro_context_v1",
            "status": "REFRESHED",
            "warnings": [],
            "components": {"fred": {"status": "available", "source": "FRED", "series": []}},
        }

    service = MacroContextService(cache=cache, fred_api_key="fred-key")
    monkeypatch.setattr(service, "refresh", fake_refresh)

    payload = service.get_context(allow_network=True, force_refresh=False, max_age_seconds=999999)

    assert calls == ["refresh"]
    assert payload["status"] == "REFRESHED"
    assert "fred_key_missing" not in payload["warnings"]


def test_macro_context_refreshes_cache_missing_required_methodology_series(monkeypatch, tmp_path):
    from src.macro.official_sources import CACHE_KEY, MacroContextService
    from src.macro.source_cache import JsonSourceCache

    cache = JsonSourceCache(cache_dir=tmp_path)
    cache.write(
        CACHE_KEY,
        {
            "schema": "macro_context_v1",
            "status": "REFRESHED",
            "warnings": [],
            "components": {
                "fred": {
                    "status": "available",
                    "source": "FRED",
                    "series": [{"series_id": "DGS10", "value": 4.2}],
                }
            },
        },
    )
    calls = []

    def fake_refresh():
        calls.append("refresh")
        return {"schema": "macro_context_v1", "status": "REFRESHED", "components": {}}

    service = MacroContextService(cache=cache, fred_api_key="fred-key")
    monkeypatch.setattr(service, "refresh", fake_refresh)

    service.get_context(allow_network=True, max_age_seconds=999999)

    assert calls == ["refresh"]


def test_macro_context_redacts_fred_key_from_errors(monkeypatch, tmp_path):
    from src.macro.official_sources import MacroContextService
    from src.macro.source_cache import JsonSourceCache

    cache = JsonSourceCache(cache_dir=tmp_path)
    service = MacroContextService(cache=cache, fred_api_key="fred-secret")
    monkeypatch.setattr(
        "src.macro.official_sources.record_provider_run",
        lambda **kwargs: None,
    )

    def fake_get_json(url, *, timeout_s):
        raise Exception(f"bad url: {url}")

    monkeypatch.setattr(service, "_get_json", fake_get_json)
    payload = service.refresh()

    fred = payload["components"]["fred"]
    errors = " ".join(fred["errors"].values())
    assert "api_key=<redacted>" in errors
    assert "fred-secret" not in errors
