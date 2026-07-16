from types import SimpleNamespace
from datetime import date, timedelta


class FakeManager:
    def get_main_indices(self, market):
        return [{"code": "000001", "close": 3000}]

    def get_market_stats(self, purpose=None):
        return {"up": 100, "down": 50, "purpose": purpose}

    def get_sector_rankings(self, n=8):
        return [{"name": "AI", "change_pct": 1.2}]

    def get_concept_rankings(self, n=8):
        return [{"name": "算力", "change_pct": 2.3}]

    def get_hot_stocks(self, n=10):
        return [{"code": "300750"}]

    def get_realtime_quote(self, symbol, log_final_failure=False):
        return SimpleNamespace(source=SimpleNamespace(value="efinance"), price=10.5, change_pct=1.2)

    def get_daily_data(self, symbol, days=30):
        return ([{"close": 10}, {"close": 11}], "tencent")

    def get_fundamental_context(self, symbol, budget_seconds=8):
        return {
            "status": "partial",
            "source_chain": [{"provider": "akshare", "result": "ok", "duration_ms": 12}],
            "valuation": {"status": "ok", "data": {"pe": 12, "pb": 1.5}},
            "growth": {"status": "missing", "data": {}},
        }

    def get_capital_flow_context(self, symbol, budget_seconds=4):
        return {
            "status": "available",
            "source_chain": [{"provider": "tushare", "result": "permission denied", "duration_ms": 2}],
            "capital_flow": {"data": {"net_inflow": 1}},
        }

    def get_belong_boards(self, symbol):
        return [{"name": "银行"}]


def test_subject_evidence_collector_calls_upstream_manager_and_writes_ledgers(tmp_path):
    from src.source_health.daily_universe import write_daily_universe
    from src.source_health.evidence_ledger import load_evidence_ledger
    from src.source_health.provider_ledger import load_provider_ledger
    from src.source_health.subject_evidence import collect_subject_evidence

    docs = tmp_path / "docs"
    date = "2099-01-02"
    write_daily_universe(docs, date, symbols=["600519", "AAPL"], market="cn")

    summary = collect_subject_evidence(docs, date, max_symbols=1, manager=FakeManager())

    assert summary["symbols"] == ["600519"]
    assert summary["providerRuns"] >= 10
    assert summary["evidenceFacts"] >= 8

    provider_rows = load_provider_ledger(docs / "run_status" / date / "subject_provider_runs.jsonl")
    providers = {row["provider"] for row in provider_rows}
    assert {"DataFetcherManager", "EfinanceFetcher", "TencentFetcher", "AkshareFetcher", "TushareFetcher"} <= providers
    assert any(row.get("operation") == "capital_flow" and row.get("error_type") == "permission_limited" for row in provider_rows)
    assert all(row.get("source_scope") == "subject_evidence" for row in provider_rows)

    evidence_rows = load_evidence_ledger(docs / "run_status" / date / "subject_evidence.jsonl")
    assert any(row["id"] == f"subject:600519:quote:{date}" and row["fact_type"] == "derived_fact" for row in evidence_rows)
    assert any(row["id"] == f"subject:600519:fundamental:valuation:{date}" for row in evidence_rows)
    daily = next(row for row in evidence_rows if row["id"] == f"subject:600519:daily_data:{date}")
    assert "latest_close=11" in daily["value"]
    assert "period_return_pct=10.0" in daily["value"]
    market = {row["id"]: row for row in evidence_rows if row.get("subject") == "market"}
    assert market[f"subject:market:main_indices:{date}"]["measurements"]["index_000001_current"] == 3000
    assert "up_count=100" in market[f"subject:market:market_stats:{date}"]["value"]
    assert market[f"subject:market:market_stats:{date}"]["measurements"]["up_count"] == 100
    assert market[f"subject:market:market_stats:{date}"]["measurements"]["down_count"] == 50
    assert "AI" in market[f"subject:market:sector_rankings:{date}"]["value"]
    fundamental = next(row for row in evidence_rows if row["id"] == f"subject:600519:fundamental:valuation:{date}")
    assert "pe=12" in fundamental["value"]
    assert "pb=1.5" in fundamental["value"]
    assert all(row.get("evidence_scope") == "subject_evidence" for row in evidence_rows)

    quote = next(row for row in evidence_rows if row["id"] == f"subject:600519:quote:{date}")
    assert quote["metric"] == "realtime_quote"
    assert quote["measurements"] == {"price": 10.5, "change_pct": 1.2}
    assert quote["session_phase"] in {
        "premarket", "intraday", "lunch_break", "closing_auction", "postmarket", "non_trading", "unknown"
    }


def test_subject_evidence_provider_errors_are_redacted():
    from src.source_health.subject_evidence import _timed_call

    _, run = _timed_call(
        "daily_data",
        lambda: (_ for _ in ()).throw(
            Exception("403 for url: https://example.test/data?symbol=AAPL&token=secret-token-123")
        ),
    )

    assert run["error_message_sanitized"].endswith("token=<redacted>")
    assert "secret-token-123" not in run["error_message_sanitized"]


def test_subject_evidence_preserves_source_times_and_builds_price_comparisons(tmp_path):
    from src.source_health.daily_universe import write_daily_universe
    from src.source_health.evidence_ledger import load_evidence_ledger
    from src.source_health.provider_ledger import load_provider_ledger
    from src.source_health.subject_evidence import collect_subject_evidence

    class HistoryManager(FakeManager):
        requested_days = 0

        def get_realtime_quote(self, symbol, log_final_failure=False):
            return SimpleNamespace(
                source=SimpleNamespace(value="efinance"),
                price=20.0,
                change_pct=1.0,
                provider_timestamp="2099-01-02T07:00:00Z",
                fetched_at="2099-01-02T07:00:02Z",
            )

        def get_daily_data(self, symbol, days=30):
            self.requested_days = days
            start = date(2098, 1, 1)
            rows = [
                {"date": (start + timedelta(days=index)).isoformat(), "close": 10 + index * 0.1, "volume": 1000 + index}
                for index in range(260)
            ]
            return rows, "tencent"

    docs = tmp_path / "docs"
    run_date = "2099-01-02"
    manager = HistoryManager()
    write_daily_universe(docs, run_date, symbols=["600519"], market="cn")

    collect_subject_evidence(docs, run_date, manager=manager)

    assert manager.requested_days == 260
    providers = load_provider_ledger(docs / "run_status" / run_date / "subject_provider_runs.jsonl")
    assert all(row.get("observed_at") for row in providers)
    evidence = load_evidence_ledger(docs / "run_status" / run_date / "subject_evidence.jsonl")
    quote = next(row for row in evidence if row["id"] == f"subject:600519:quote:{run_date}")
    assert quote["event_time"] == "2099-01-02T07:00:00Z"
    assert quote["fetched_at"] == "2099-01-02T07:00:02Z"
    comparison = next(row for row in evidence if row.get("metric") == "price_history_comparison")
    assert comparison["comparison"]["return_20d_pct"] > 0
    assert "volatility_60d_annualized_pct" in comparison["comparison"]
    assert any(row.get("metric") == "universe_price_comparison" for row in evidence)


def test_cn_fundamentals_fall_back_to_akshare_core_not_yfinance(tmp_path, monkeypatch):
    from src.source_health.daily_universe import write_daily_universe
    from src.source_health.evidence_ledger import load_evidence_ledger
    from src.source_health.provider_ledger import load_provider_ledger
    from src.source_health.subject_evidence import collect_subject_evidence

    class NoCnFundamentals(FakeManager):
        def get_fundamental_context(self, symbol, budget_seconds=8):
            return {"status": "failed", "source_chain": [], "errors": ["primary failed"]}

    monkeypatch.setattr(
        "data_provider.fundamental_adapter.AkshareFundamentalAdapter.get_core_financials",
        lambda _self, _symbol: {
            "status": "partial",
            "growth": {"revenue_yoy": 4.6516, "net_profit_yoy": 3.0292},
            "earnings": {"financial_report": {"revenue": 35277000000, "net_profit_parent": 14523000000}},
            "institution": {},
            "source_chain": ["growth:stock_financial_abstract"],
            "errors": [],
        },
    )
    monkeypatch.setattr(
        "data_provider.yfinance_fundamental_adapter.YfinanceFundamentalAdapter.get_fundamental_bundle",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("A-share must not use Yahoo fundamentals")),
    )

    docs = tmp_path / "docs"
    date = "2099-01-02"
    write_daily_universe(docs, date, symbols=["600519"], market="cn")

    collect_subject_evidence(docs, date, manager=NoCnFundamentals())

    evidence = load_evidence_ledger(docs / "run_status" / date / "subject_evidence.jsonl")
    providers = load_provider_ledger(docs / "run_status" / date / "subject_provider_runs.jsonl")
    fallback = [row for row in evidence if row.get("provider") == "AkshareFundamentalAdapter"]
    assert fallback
    growth = next(row for row in fallback if row.get("metric") == "fundamental_growth")
    assert growth["measurements"]["revenue_yoy_pct"] == 4.6516
    assert growth["measurements"]["net_profit_yoy_pct"] == 3.0292
    assert any(
        row.get("provider") == "AkshareFundamentalAdapter"
        and row.get("operation") == "fundamental_context_akshare_core"
        and row.get("success") is True
        for row in providers
    )
