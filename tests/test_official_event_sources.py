import json
import urllib.parse


def test_official_event_sources_normalize_sec_cninfo_and_gdelt(monkeypatch):
    from src.source_health.official_event_sources import OfficialEventSourceClient

    client = OfficialEventSourceClient(timeout_s=0.1, sec_user_agent="test@example.com")

    def fake_get_json(url, headers=None):
        if "company_tickers.json" in url:
            return {"0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc."}}
        if "companyfacts/CIK0000320193.json" in url:
            return {
                "facts": {
                    "us-gaap": {
                        "Revenues": {
                            "units": {
                                "USD": [
                                    {"end": "2099-01-01", "filed": "2099-01-01", "val": 123}
                                ]
                            }
                        }
                    }
                }
            }
        if "CIK0000320193.json" in url:
            return {
                "filings": {
                    "recent": {
                        "form": ["10-Q"],
                        "filingDate": ["2099-01-01"],
                        "accessionNumber": ["0000320193-99-000001"],
                        "primaryDocument": ["aapl-20990101.htm"],
                    }
                }
            }
        if "queryCompanyBulletin" in url:
            return {
                "result": [
                    {
                        "SECURITY_CODE": "600519",
                        "TITLE": "上交所年度报告",
                        "SSEDATE": "2099-01-01",
                        "URL": "/disclosure/listedinfo/announcement/c/new.pdf",
                    }
                ]
            }
        if "gdeltproject.org" in url:
            query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["query"][0]
            assert query.startswith("(") and " OR " in query
            return {"articles": [{"title": "AI chips event", "url": "https://news.example/a", "seendate": "20990102120000"}]}
        raise AssertionError(url)

    def fake_post_json(url, *, data, headers=None):
        assert b"600519" in data
        return {
            "announcements": [
                {
                    "announcementId": "cn-1",
                    "secCode": "600519",
                    "announcementTitle": "<em>年度报告</em>",
                    "announcementTime": 4070995200000,
                    "adjunctUrl": "finalpage/2099-01-01/test.pdf",
                }
            ]
        }

    monkeypatch.setattr(client, "_get_json", fake_get_json)
    monkeypatch.setattr(client, "_post_json", fake_post_json)

    result = client.fetch(symbols=["AAPL", "600519"], query_terms=["AI chips", "tariffs"], run_date="2099-01-02")

    providers = {row["provider"]: row for row in result.provider_runs}
    assert providers["SEC_EDGAR"]["success"] is True
    assert providers["CNINFO"]["success"] is True
    assert providers["GDELT"]["success"] is True

    facts = {row["provider"]: row for row in result.evidence_facts}
    assert facts["SEC_EDGAR"]["fact_type"] == "verified_fact"
    assert facts["SEC_EDGAR"]["source_url"].startswith("https://data.sec.gov/")
    assert facts["CNINFO"]["fact_type"] == "verified_fact"
    assert facts["CNINFO"]["value"] == "年度报告"
    assert facts["SSE_DISCLOSURE"]["value"] == "上交所年度报告"
    assert facts["GDELT"]["fact_type"] == "discovery"


def test_tavily_search_creates_discovery_from_env_file(monkeypatch):
    from src.source_health import official_event_sources as module
    from src.source_health.official_event_sources import OfficialEventSourceClient

    monkeypatch.setattr(module, "_project_env_values", lambda: {"TAVILY_API_KEYS": "tvly-a,tvly-b"})
    client = OfficialEventSourceClient(timeout_s=0.1)

    calls = []

    def fake_post_json_body(url, *, data, headers=None):
        calls.append({"url": url, "headers": headers, "data": data})
        assert headers["Authorization"].startswith("Bearer tvly-")
        payload = json.loads(data.decode("utf-8"))
        assert payload["query"].startswith("(")
        return {"results": [{"title": "Tariff update", "url": "https://news.example/tariff", "published_date": "2099-01-02"}]}

    monkeypatch.setattr(client, "_post_json_body", fake_post_json_body)

    result = client.fetch_tavily_search(query_terms=["China tariffs", "AAPL"], run_date="2099-01-02")

    assert calls
    assert result.provider_runs[0]["provider"] == "Tavily"
    assert result.provider_runs[0]["success"] is True
    assert result.evidence_facts[0]["fact_type"] == "discovery"
    assert result.evidence_facts[0]["provider"] == "Tavily"


def test_sec_companyfacts_create_fundamental_verified_facts(monkeypatch):
    from src.source_health.official_event_sources import OfficialEventSourceClient

    client = OfficialEventSourceClient(timeout_s=0.1, sec_user_agent="test@example.com")

    def fake_get_json(url, headers=None):
        if "company_tickers.json" in url:
            return {"0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc."}}
        if "companyfacts/CIK0000320193.json" in url:
            return {
                "facts": {
                    "us-gaap": {
                        "Assets": {"units": {"USD": [{
                            "start": "2098-10-01", "end": "2099-01-01", "filed": "2099-01-02",
                            "val": 456, "form": "10-Q", "fp": "Q1", "fy": 2099, "frame": "CY2099Q1I",
                        }]}},
                        "FutureMetric": {"units": {"USD": [{"end": "2099-01-03", "filed": "2099-01-03", "val": 999}]}},
                    }
                }
            }
        raise AssertionError(url)

    monkeypatch.setattr(client, "_get_json", fake_get_json)

    result = client.fetch_sec_companyfacts(symbols=["AAPL"], run_date="2099-01-02")

    assert result.provider_runs[0]["provider"] == "SEC_EDGAR"
    assert result.provider_runs[0]["domain"] == "fundamentals"
    assert result.provider_runs[0]["success"] is True
    assert [fact["value"] for fact in result.evidence_facts] == ["Assets=456 USD @ 2099-01-01 filed 2099-01-02"]
    assert result.evidence_facts[0]["fact_type"] == "verified_fact"
    assert result.evidence_facts[0]["source_url"].startswith("https://data.sec.gov/api/xbrl/companyfacts/")
    assert result.evidence_facts[0]["period_start"] == "2098-10-01"
    assert result.evidence_facts[0]["period_end"] == "2099-01-01"
    assert result.evidence_facts[0]["filing_form"] == "10-Q"
    assert result.evidence_facts[0]["fiscal_period"] == "Q1"
    assert result.evidence_facts[0]["fiscal_year"] == "2099"
    assert result.evidence_facts[0]["frame"] == "CY2099Q1I"


def test_fetch_uses_independent_geopolitical_query_scope(monkeypatch):
    from src.source_health.official_event_sources import OfficialEventSourceClient, OfficialEventSourceResult

    client = OfficialEventSourceClient(timeout_s=0.1)
    empty = OfficialEventSourceResult(provider_runs=[], evidence_facts=[], raw={})
    monkeypatch.setattr(client, "fetch_sec_filings", lambda **kwargs: empty)
    monkeypatch.setattr(client, "fetch_sec_companyfacts", lambda **kwargs: empty)
    monkeypatch.setattr(client, "fetch_cninfo_announcements", lambda **kwargs: empty)
    monkeypatch.setattr(client, "fetch_exchange_disclosures", lambda **kwargs: empty)
    monkeypatch.setattr(client, "fetch_hkex_disclosures", lambda **kwargs: empty)
    seen = {}

    def capture(name):
        def inner(**kwargs):
            seen[name] = list(kwargs["query_terms"])
            return empty
        return inner

    monkeypatch.setattr(client, "fetch_gdelt_events", capture("gdelt"))
    monkeypatch.setattr(client, "fetch_tavily_search", capture("tavily"))
    monkeypatch.setattr(client, "fetch_reliefweb_reports", capture("reliefweb"))
    monkeypatch.setattr(client, "fetch_ofac_sanctions_signals", capture("ofac"))

    result = client.fetch(symbols=["AAPL"], query_terms=["AAPL"], run_date="2099-01-02")

    assert "AAPL" not in seen["gdelt"]
    assert "AAPL" not in seen["reliefweb"]
    assert any("conflict" in term or "sanctions" in term for term in seen["gdelt"])
    assert seen["ofac"] == ["AAPL"]
    assert result.raw["queryScopes"]["subject"] == ["AAPL"]


def test_exchange_disclosures_parse_sse_szse_and_hkex(monkeypatch):
    from src.source_health.official_event_sources import OfficialEventSourceClient

    client = OfficialEventSourceClient(timeout_s=0.1)

    def fake_get_json(url, headers=None):
        if "queryCompanyBulletin" in url:
            return {"result": [{"SECURITY_CODE": "600519", "TITLE": "上交所公告", "SSEDATE": "2099-01-01", "URL": "/sse.pdf"}]}
        if "announcement/annList" in url:
            return {"data": [{"secCode": "000001", "title": "深交所公告", "publishTime": "2099-01-01", "attachPath": "/szse.pdf"}]}
        raise AssertionError(url)

    monkeypatch.setattr(client, "_get_json", fake_get_json)
    def fake_get_text(url, headers=None):
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path.endswith("/prefix.do"):
            assert query["name"] == ["00700"]
            return 'callback({"stockInfo":[{"stockId":7609,"code":"00700","name":"TENCENT"}]});'
        assert query["category"] == ["0"]
        assert query["stockId"] == ["7609"]
        return """
            <tr>
              <td class="release-time">01/01/2099 12:00</td>
              <td class="stock-short-code"><span>Stock Code: </span>00700<br/>80700</td>
              <td class="stock-short-name"><span>Stock Short Name: </span>TENCENT<br/>TENCENT-R</td>
              <td><a href="/listedco/listconews/sehk/2099/0101/00700.pdf">HKEX announcement</a></td>
            </tr>
        """

    monkeypatch.setattr(client, "_get_text", fake_get_text)

    cn = client.fetch_exchange_disclosures(symbols=["600519", "000001"], run_date="2099-01-02")
    hk = client.fetch_hkex_disclosures(symbols=["HK00700"], run_date="2099-01-02")

    facts = {fact["provider"]: fact for fact in cn.evidence_facts + hk.evidence_facts}
    assert facts["SSE_DISCLOSURE"]["value"] == "上交所公告"
    assert facts["SZSE_DISCLOSURE"]["value"] == "深交所公告"
    assert facts["HKEXNEWS"]["value"] == "HKEX announcement"
    assert all(fact["fact_type"] == "verified_fact" for fact in facts.values())


def test_hkex_filters_announcements_for_other_stock_codes(monkeypatch):
    from src.source_health.official_event_sources import OfficialEventSourceClient

    client = OfficialEventSourceClient(timeout_s=0.1)

    def fake_get_text(url, headers=None):
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path.endswith("/prefix.do"):
            return 'callback({"stockInfo":[{"stockId":7609,"code":"00700","name":"TENCENT"}]});'
        assert query["stockId"] == ["7609"]
        return """
            <table>
              <tr>
                <td class="release-time">02/01/2099 12:00</td>
                <td class="stock-short-code"><span>Stock Code: </span>00362</td>
                <td class="stock-short-name"><span>Stock Short Name: </span>C ZENITH CHEM</td>
                <td><a href="/listedco/listconews/sehk/2099/0102/wrong.pdf">Wrong issuer announcement</a></td>
              </tr>
              <tr>
                <td class="release-time">01/01/2099 12:00</td>
                <td class="stock-short-code"><span>Stock Code: </span>00700</td>
                <td class="stock-short-name"><span>Stock Short Name: </span>TENCENT</td>
                <td><a href="/listedco/listconews/sehk/2099/0101/tencent.pdf">Tencent announcement</a></td>
              </tr>
            </table>
        """

    monkeypatch.setattr(client, "_get_text", fake_get_text)

    result = client.fetch_hkex_disclosures(symbols=["HK00700"], run_date="2099-01-02")

    assert result.provider_runs[0]["success"] is True
    assert result.provider_runs[0]["record_count"] == 1
    assert [fact["value"] for fact in result.evidence_facts] == ["Tencent announcement"]
    assert result.evidence_facts[0]["symbol"] == "00700"
    assert result.evidence_facts[0]["source_url"].endswith("/tencent.pdf")


def test_hkex_unresolved_stock_id_returns_partial_without_verified_facts(monkeypatch):
    from src.source_health.official_event_sources import OfficialEventSourceClient

    client = OfficialEventSourceClient(timeout_s=0.1)
    calls = []

    def fake_get_text(url, headers=None):
        calls.append(url)
        return 'callback({"stockInfo":[{"stockId":700,"code":"00362","name":"C ZENITH CHEM"}]});'

    monkeypatch.setattr(client, "_get_text", fake_get_text)

    result = client.fetch_hkex_disclosures(symbols=["HK00700"], run_date="2099-01-02")

    assert len(calls) == 1
    assert result.raw["symbols"]["00700"]["status"] == "partial"
    assert result.provider_runs[0]["success"] is False
    assert result.evidence_facts == []


def test_daily_ledgers_include_official_event_payload(tmp_path):
    from src.source_health.daily_ledgers import write_daily_source_health_ledgers
    from src.source_health.evidence_ledger import load_evidence_ledger
    from src.source_health.provider_ledger import load_provider_ledger

    docs = tmp_path / "docs"
    run_date = "2099-01-02"
    (docs / "official_events").mkdir(parents=True)
    (docs / "official_events" / f"{run_date}.json").write_text(
        json.dumps(
            {
                "schema": "official_event_sources_v1",
                "providerRuns": [
                    {"provider": "SEC_EDGAR", "domain": "filings_events", "data_type": "filings_events", "operation": "sec_submissions", "success": True, "record_count": 1}
                ],
                "evidenceFacts": [
                    {
                        "id": "sec:AAPL:1",
                        "domain": "filings_events",
                        "fact_type": "verified_fact",
                        "provider": "SEC_EDGAR",
                        "source_url": "https://www.sec.gov/Archives/example",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = write_daily_source_health_ledgers(docs, run_date)

    assert result["providerRuns"] >= 1
    assert result["evidenceFacts"] == 3
    provider_rows = load_provider_ledger(docs / "run_status" / run_date / "provider_runs.jsonl")
    evidence_rows = load_evidence_ledger(docs / "run_status" / run_date / "evidence_ledger.jsonl")
    assert any(row["provider"] == "SEC_EDGAR" for row in provider_rows)
    assert {row["fact_type"] for row in evidence_rows} == {"verified_fact", "derived_fact"}
    assert any(row.get("metric") == "portfolio_snapshot_status" for row in evidence_rows)


def test_cninfo_null_announcements_is_empty_not_crash(monkeypatch):
    from src.source_health.official_event_sources import OfficialEventSourceClient

    client = OfficialEventSourceClient(timeout_s=0.1)
    monkeypatch.setattr(client, "_post_json", lambda *args, **kwargs: {"announcements": None})

    result = client.fetch_cninfo_announcements(symbols=["600519"], run_date="2099-01-02")

    assert result.provider_runs[0]["provider"] == "CNINFO"
    assert result.provider_runs[0]["success"] is False
    assert result.provider_runs[0]["error_type"] == "empty"
    assert result.evidence_facts == []


def test_cninfo_filters_fulltext_false_positive_symbols(monkeypatch):
    from src.source_health.official_event_sources import OfficialEventSourceClient

    client = OfficialEventSourceClient(timeout_s=0.1)
    monkeypatch.setattr(
        client,
        "_post_json",
        lambda *args, **kwargs: {
            "announcements": [
                {"secCode": "300750", "announcementTitle": "包含 002167 的无关公告"},
                {"secCode": "002167", "announcementTitle": "东方锆业真实公告"},
            ]
        },
    )

    result = client.fetch_cninfo_announcements(symbols=["002167"], run_date="2099-01-02")

    assert [fact["value"] for fact in result.evidence_facts] == ["东方锆业真实公告"]


def test_sec_filings_exclude_future_records(monkeypatch):
    from src.source_health.official_event_sources import OfficialEventSourceClient

    client = OfficialEventSourceClient(timeout_s=0.1, sec_user_agent="test@example.com")

    def fake_get_json(url, headers=None):
        if "company_tickers.json" in url:
            return {"0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc."}}
        if "CIK0000320193.json" in url:
            return {
                "filings": {
                    "recent": {
                        "form": ["10-Q", "8-K"],
                        "filingDate": ["2099-01-03", "2099-01-01"],
                        "accessionNumber": ["future", "past"],
                        "primaryDocument": ["future.htm", "past.htm"],
                    }
                }
            }
        raise AssertionError(url)

    monkeypatch.setattr(client, "_get_json", fake_get_json)

    result = client.fetch_sec_filings(symbols=["AAPL"], run_date="2099-01-02")

    assert [fact["value"] for fact in result.evidence_facts] == ["8-K 2099-01-01 past.htm"]


def test_full_review_smoke_symbols_are_fixed_a_hk_us_set():
    from src.source_health.smoke_symbols import FULL_REVIEW_SMOKE_SYMBOLS, full_review_smoke_symbols

    assert FULL_REVIEW_SMOKE_SYMBOLS == {
        "a_share": ["600519", "000001"],
        "us": ["AAPL"],
        "hk": ["HK00700"],
    }
    assert full_review_smoke_symbols() == ["600519", "000001", "AAPL", "HK00700"]


def test_fetch_script_full_review_smoke_profile_uses_fixed_symbols(tmp_path, monkeypatch, capsys):
    import scripts.fetch_official_event_sources as fetch_script
    from src.source_health.official_event_sources import OfficialEventSourceResult

    captured = {}

    class FakeClient:
        def __init__(self, timeout_s):
            captured["timeout_s"] = timeout_s

        def fetch(self, *, symbols, query_terms, run_date):
            captured["symbols"] = list(symbols)
            captured["query_terms"] = list(query_terms)
            captured["run_date"] = run_date
            return OfficialEventSourceResult(
                provider_runs=[
                    {
                        "provider": "SEC_EDGAR",
                        "domain": "filings_events",
                        "operation": "sec_submissions",
                        "success": False,
                        "record_count": 0,
                        "error_type": "not_supported",
                    }
                ],
                evidence_facts=[],
                raw={"schema": "official_event_sources_v1", "symbols": list(symbols)},
            )

    monkeypatch.setattr(fetch_script, "OfficialEventSourceClient", FakeClient)

    rc = fetch_script.main([
        "--date",
        "2099-01-02",
        "--docs-dir",
        str(tmp_path / "docs"),
        "--smoke-profile",
        "full-review",
        "--timeout",
        "0.1",
    ])

    assert rc == 0
    assert captured["timeout_s"] == 0.1
    assert captured["symbols"] == ["600519", "000001", "AAPL", "HK00700"]
    assert captured["query_terms"][:4] == ["600519", "000001", "AAPL", "HK00700"]
    assert any("sanctions" in term for term in captured["query_terms"])
    assert captured["run_date"] == "2099-01-02"
    output = json.loads(capsys.readouterr().out)
    assert output["symbols"] == ["600519", "000001", "AAPL", "HK00700"]
    payload = json.loads((tmp_path / "docs" / "official_events" / "2099-01-02.json").read_text(encoding="utf-8"))
    assert payload["providerRuns"][0]["provider"] == "SEC_EDGAR"


def test_official_event_error_sanitizer_redacts_query_keys():
    from src.source_health.official_event_sources import _sanitize_error

    text = _sanitize_error(
        Exception("failed url: https://api.example.test/search?query=AAPL&apikey=secret-key-123")
    )

    assert "apikey=<redacted>" in text
    assert "secret-key-123" not in text
