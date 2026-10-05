from types import SimpleNamespace
from datetime import date, timedelta

import pytest


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
            "growth": {"status": "ok", "data": {"revenue_yoy": 4.6}},
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
    assert fundamental["as_of"]
    assert "report_period" not in fundamental
    assert all(row.get("evidence_scope") == "subject_evidence" for row in evidence_rows)

    quote = next(row for row in evidence_rows if row["id"] == f"subject:600519:quote:{date}")
    assert quote["metric"] == "realtime_quote"
    assert quote["measurements"] == {"price": 10.5, "change_pct": 1.2}
    assert quote["session_phase"] in {
        "premarket", "intraday", "lunch_break", "closing_auction", "postmarket", "non_trading", "unknown"
    }


def test_subject_evidence_collects_market_indices_for_each_universe_market(tmp_path):
    from src.source_health.daily_universe import write_daily_universe
    from src.source_health.evidence_ledger import load_evidence_ledger
    from src.source_health.subject_evidence import collect_subject_evidence

    class MultiMarketManager(FakeManager):
        regions = []

        def get_main_indices(self, market):
            self.regions.append(market)
            codes = {"cn": "sh000001", "hk": "HSI", "us": "SPX"}
            return [{"code": codes[market], "close": 3000, "change_pct": -1.0}]

    docs = tmp_path / "docs"
    run_date = "2099-01-02"
    manager = MultiMarketManager()
    write_daily_universe(docs, run_date, symbols=["600519", "AAPL", "HK00700"], market="cn")

    summary = collect_subject_evidence(docs, run_date, manager=manager)

    assert summary["marketRegions"] == ["cn", "us", "hk"]
    assert manager.regions == ["cn", "us", "hk"]
    evidence = load_evidence_ledger(docs / "run_status" / run_date / "subject_evidence.jsonl")
    ids = {row["id"] for row in evidence}
    assert f"subject:market:main_indices:{run_date}" in ids
    assert f"subject:market_us:main_indices:{run_date}" in ids
    assert f"subject:market_hk:main_indices:{run_date}" in ids


def test_market_only_refresh_preserves_existing_symbol_evidence(tmp_path):
    from src.source_health.daily_universe import write_daily_universe
    from src.source_health.evidence_ledger import load_evidence_ledger
    from src.source_health.subject_evidence import collect_subject_evidence

    docs = tmp_path / "docs"
    run_date = "2099-01-02"
    write_daily_universe(docs, run_date, symbols=["600519", "AAPL"], market="cn")
    manager = FakeManager()
    collect_subject_evidence(docs, run_date, manager=manager)
    collect_subject_evidence(docs, run_date, manager=manager, market_only=True)

    evidence = load_evidence_ledger(docs / "run_status" / run_date / "subject_evidence.jsonl")
    assert any(row.get("id") == f"subject:600519:daily_data:{run_date}" for row in evidence)
    assert any(row.get("id") == f"subject:AAPL:daily_data:{run_date}" for row in evidence)
    assert any(row.get("id") == f"subject:market_us:main_indices:{run_date}" for row in evidence)


def test_explicit_three_market_scope_does_not_require_foreign_watchlist_stocks(tmp_path):
    from src.source_health.daily_universe import write_daily_universe
    from src.source_health.subject_evidence import collect_subject_evidence

    class Manager(FakeManager):
        def __init__(self):
            self.sector_markets = []

        def get_sector_performance(self, market, run_date):
            self.sector_markets.append(market)
            return {"records": [], "provider_runs": []}

    manager = Manager()
    write_daily_universe(tmp_path, "2026-09-07", symbols=["600519"], market="cn,hk,us")
    result = collect_subject_evidence(tmp_path, "2026-09-07", manager=manager)
    assert result["marketRegions"] == ["cn", "hk", "us"]
    assert manager.sector_markets == ["hk", "us"]


def test_empty_preopen_market_payload_is_not_breadth_or_sector_leadership():
    from src.source_health.subject_evidence import _collect_market_scope

    class Manager(FakeManager):
        def get_main_indices(self, market):
            return [{"code": "GOOD", "current": 3000}, {"code": "EMPTY", "current": 0}]

        def get_market_stats(self, purpose=None):
            return {"up_count": 0, "down_count": 0, "flat_count": 0, "total_amount": 0}

        def get_sector_rankings(self, n=8):
            return ([{"name": "农业", "change_pct": 0}], [{"name": "农业", "change_pct": 0}])

    facts = []
    runs = _collect_market_scope(Manager(), "2026-09-07", "cn", facts)
    assert not any(r["metric"] in {"market_stats", "sector_rankings"} for r in facts)
    indices = next(r for r in facts if r["metric"] == "main_indices")
    assert [r["code"] for r in indices["records"]] == ["GOOD"]
    assert all(not r["success"] for r in runs if r["operation"] in {"market_stats", "sector_rankings"})


def test_zero_sector_snapshots_do_not_create_historical_persistence(tmp_path):
    from src.source_health.subject_evidence import _sector_history_evidence
    from src.source_health.evidence_ledger import write_evidence_ledger

    current = {"metric": "sector_rankings", "as_of": "2026-09-07", "records": [
        {"name": "农业", "rank_side": "top", "change_pct": 0},
        {"name": "农业", "rank_side": "bottom", "change_pct": 0},
    ]}
    prior = {**current, "as_of": "2026-09-04", "records": [
        {"name": "农业", "rank_side": "top", "change_pct": 1},
    ]}
    write_evidence_ledger(tmp_path / "run_status/2026-09-04/subject_evidence.jsonl", [prior])
    assert _sector_history_evidence(tmp_path, "2026-09-07", [current]) is None


def test_market_snapshot_date_uses_each_exchange_effective_bar_date():
    from src.source_health.subject_evidence import _market_snapshot_date

    observed_at = "2026-07-17T02:59:30Z"

    assert _market_snapshot_date("cn", "2026-07-17", observed_at) == "2026-07-17"
    assert _market_snapshot_date("hk", "2026-07-17", observed_at) == "2026-07-17"
    assert _market_snapshot_date("us", "2026-07-17", observed_at) == "2026-07-16"


def test_market_snapshot_date_prefers_provider_bar_date_and_exposes_backfill_lookahead():
    from src.source_health.subject_evidence import _market_payload_date, _market_snapshot_date

    assert _market_payload_date([{"trade_date": "2026-07-15"}, {"trade_date": "2026-07-16"}]) == "2026-07-16"
    assert _market_snapshot_date(
        "us",
        "2026-01-02",
        "2026-07-17T02:59:30Z",
        source_date="2026-07-16",
    ) == "2026-07-16"
    assert _market_snapshot_date("cn", "2026-01-02", "2026-07-17T02:59:30Z") == "2026-07-17"


def test_market_sample_records_ignores_array_values_and_normalizes_numpy_scalars():
    import numpy as np

    from src.source_health.subject_evidence import _market_sample_records

    records = _market_sample_records([
        {
            "name": "AI",
            "change_pct": np.float64(1.25),
            "history": np.array([1.0, 2.0]),
            "empty": np.array([]),
        }
    ])

    assert records == [{"name": "AI", "change_pct": 1.25}]


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


def test_partial_primary_fundamentals_are_supplemented_by_missing_block(tmp_path, monkeypatch):
    from src.source_health.daily_universe import write_daily_universe
    from src.source_health.evidence_ledger import load_evidence_ledger
    from src.source_health.subject_evidence import collect_subject_evidence

    class ValuationOnlyManager(FakeManager):
        def get_fundamental_context(self, symbol, budget_seconds=8):
            return {
                "status": "partial",
                "source_chain": [{"provider": "efinance", "result": "ok"}],
                "valuation": {"status": "ok", "data": {"pe": 12.0, "pb": 1.5}},
            }

    monkeypatch.setattr(
        "src.source_health.subject_evidence._akshare_cn_fundamental_context",
        lambda _symbol: {
            "status": "partial",
            "source_chain": ["growth:stock_financial_abstract"],
            "growth": {"status": "partial", "data": {"revenue_yoy": 4.6}},
            "earnings": {"status": "not_supported", "data": {}},
            "institution": {"status": "not_supported", "data": {}},
        },
    )

    docs = tmp_path / "docs"
    run_date = "2099-01-02"
    write_daily_universe(docs, run_date, symbols=["600519"], market="cn")
    collect_subject_evidence(docs, run_date, manager=ValuationOnlyManager())

    evidence = load_evidence_ledger(docs / "run_status" / run_date / "subject_evidence.jsonl")
    metrics = [row.get("metric") for row in evidence if row.get("symbol") == "600519"]
    assert metrics.count("fundamental_valuation") == 1
    assert metrics.count("fundamental_growth") == 1


def test_partial_primary_market_cap_is_enriched_with_generic_valuation_ratios(tmp_path, monkeypatch):
    from src.source_health.daily_universe import write_daily_universe
    from src.source_health.evidence_ledger import load_evidence_ledger
    from src.source_health.subject_evidence import collect_subject_evidence

    class MarketCapOnlyManager(FakeManager):
        def get_fundamental_context(self, symbol, budget_seconds=8):
            return {
                "status": "partial",
                "source_chain": [{"provider": "quote", "result": "ok"}],
                "valuation": {"status": "partial", "data": {"total_mv": 1000.0, "as_of": "2099-01-01"}},
                "growth": {"status": "partial", "data": {"revenue_yoy": 8.0}},
            }

    monkeypatch.setattr(
        "src.source_health.subject_evidence._yfinance_public_fundamental_context",
        lambda _symbol: {
            "status": "partial",
            "source_chain": ["valuation:yfinance.info"],
            "valuation": {
                "status": "partial",
                "data": {"trailing_pe": 22.0, "price_to_book": 5.0, "as_of": "2099-01-02"},
            },
            "growth": {"status": "not_supported", "data": {}},
            "earnings": {"status": "not_supported", "data": {}},
            "institution": {"status": "not_supported", "data": {}},
        },
    )

    docs = tmp_path / "docs"
    run_date = "2099-01-02"
    write_daily_universe(docs, run_date, symbols=["AAPL"], market="us")
    collect_subject_evidence(docs, run_date, manager=MarketCapOnlyManager())

    evidence = load_evidence_ledger(docs / "run_status" / run_date / "subject_evidence.jsonl")
    valuation = next(
        row for row in evidence
        if row.get("symbol") == "AAPL" and row.get("metric") == "fundamental_valuation"
    )
    assert valuation["measurements"]["total_mv"] == 1000.0
    assert valuation["measurements"]["trailing_pe"] == 22.0
    assert valuation["measurements"]["price_to_book"] == 5.0
    assert valuation["supplemental_providers"] == ["YfinanceFundamentalAdapter"]
    assert valuation["as_of"] == "2099-01-01"
    assert valuation["supplemental_sources"][0]["as_of"] == "2099-01-02"


def test_fundamental_merge_rejects_mismatched_periods_and_currency_amounts():
    from src.source_health.subject_evidence import _merge_fundamental_facts

    primary = [{
        "metric": "fundamental_growth",
        "provider": "primary",
        "report_period": "2026-03-31",
        "comparison_period": "2025-03-31",
        "currency": "USD",
        "measurements": {"revenue_yoy_pct": 8.0},
    }]
    fallback = [{
        "metric": "fundamental_growth",
        "provider": "fallback",
        "report_period": "2025-12-31",
        "comparison_period": "2024-12-31",
        "currency": "CNY",
        "measurements": {"net_profit_yoy_pct": 7.0},
    }]

    assert _merge_fundamental_facts(primary, fallback) == []
    assert primary[0]["measurements"] == {"revenue_yoy_pct": 8.0}


def test_valuation_merge_adds_only_ratios_and_preserves_primary_as_of():
    from src.source_health.subject_evidence import _merge_fundamental_facts

    primary = [{
        "metric": "fundamental_valuation",
        "provider": "primary",
        "as_of": "2026-07-15",
        "currency": "CNY",
        "measurements": {"total_mv": 1000.0},
    }]
    fallback = [{
        "metric": "fundamental_valuation",
        "provider": "fallback",
        "as_of": "2026-07-17",
        "currency": "USD",
        "measurements": {"trailing_pe": 22.0, "market_cap": 9999.0},
    }]

    assert _merge_fundamental_facts(primary, fallback) == []
    assert primary[0]["measurements"] == {"total_mv": 1000.0, "trailing_pe": 22.0}
    assert primary[0]["as_of"] == "2026-07-15"
    assert primary[0]["supplemental_sources"][0]["as_of"] == "2026-07-17"


def test_offshore_fundamentals_use_generic_yfinance_fallback_and_local_history_comparison(tmp_path, monkeypatch):
    from src.source_health.daily_universe import write_daily_universe
    from src.source_health.evidence_ledger import load_evidence_ledger
    from src.source_health.provider_ledger import load_provider_ledger
    from src.source_health.subject_evidence import collect_subject_evidence

    class NoOffshoreFundamentals(FakeManager):
        def get_fundamental_context(self, symbol, budget_seconds=8):
            return {"status": "failed", "source_chain": [], "errors": ["primary failed"]}

    monkeypatch.setattr(
        "data_provider.yfinance_fundamental_adapter.YfinanceFundamentalAdapter.get_fundamental_bundle",
        lambda _self, _symbol: {
            "status": "partial",
            "growth": {"revenue_yoy": 10.0, "net_profit_yoy": 20.0},
            "earnings": {
                "financial_report": {
                    "report_date": "2098-09-30",
                    "comparison_period": "2097-09-30",
                    "revenue": 110.0,
                    "net_profit_parent": 24.0,
                },
                "financial_history": [
                    {"report_date": "2098-09-30", "revenue": 110.0, "net_profit_parent": 24.0},
                    {"report_date": "2097-09-30", "revenue": 100.0, "net_profit_parent": 20.0},
                ],
            },
            "institution": {},
            "source_chain": ["info", "quarterly_income_stmt"],
            "errors": [],
        },
    )

    docs = tmp_path / "docs"
    run_date = "2099-01-02"
    write_daily_universe(docs, run_date, symbols=["HK00700"], market="hk")

    collect_subject_evidence(docs, run_date, manager=NoOffshoreFundamentals())

    evidence = load_evidence_ledger(docs / "run_status" / run_date / "subject_evidence.jsonl")
    providers = load_provider_ledger(docs / "run_status" / run_date / "subject_provider_runs.jsonl")
    history = next(row for row in evidence if row.get("metric") == "fundamental_history_comparison")
    assert history["symbol"] == "HK00700"
    assert history["comparison_method"] == "online_history_local_same_period_comparison"
    assert history["report_period"] == "2098-09-30"
    assert history["comparison_period"] == "2097-09-30"
    assert history["measurements"]["revenue_yoy_pct"] == 10.0
    assert history["measurements"]["net_profit_yoy_pct"] == 20.0
    assert any(
        row.get("provider") == "YfinanceFundamentalAdapter"
        and row.get("operation") == "fundamental_context_yfinance_public"
        and row.get("success") is True
        for row in providers
    )


def test_sector_history_uses_prior_local_snapshots(tmp_path):
    import json

    from src.source_health.subject_evidence import _sector_history_evidence

    docs = tmp_path / "docs"
    prior = docs / "run_status" / "2099-01-01" / "subject_evidence.jsonl"
    prior.parent.mkdir(parents=True)
    prior.write_text(
        json.dumps({
            "id": "subject:market:sector_rankings:2099-01-01",
            "metric": "sector_rankings",
            "as_of": "2099-01-01",
            "time_basis": "source",
            "records": [
                {"name": "AI", "rank_side": "top"},
                {"name": "煤炭", "rank_side": "bottom"},
            ],
        }, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    current = [{
        "id": "subject:market:sector_rankings:2099-01-02",
        "metric": "sector_rankings",
        "as_of": "2099-01-02",
        "time_basis": "source",
        "records": [
            {"name": "AI", "rank_side": "top"},
            {"name": "煤炭", "rank_side": "bottom"},
        ],
    }]

    history = _sector_history_evidence(docs, "2099-01-02", current)

    assert history is not None
    assert history["comparison_method"] == "local_snapshot_comparison"
    assert history["observed_dates"] == ["2099-01-02", "2099-01-01"]
    assert "repeated_leaders=AI" in history["value"]
    assert "repeated_laggards=煤炭" in history["value"]


def test_market_breadth_history_uses_prior_local_snapshots(tmp_path):
    import json

    from src.source_health.subject_evidence import _market_stats_history_evidence

    docs = tmp_path / "docs"
    prior = docs / "run_status" / "2099-01-01" / "subject_evidence.jsonl"
    prior.parent.mkdir(parents=True)
    prior.write_text(
        json.dumps({
            "id": "subject:market:market_stats:2099-01-01",
            "subject": "market",
            "metric": "market_stats",
            "measurements": {"up_count": 1000, "down_count": 2000, "total_amount_100m_cny": 9000},
        }) + "\n",
        encoding="utf-8",
    )
    current = [{
        "id": "subject:market:market_stats:2099-01-02",
        "subject": "market",
        "metric": "market_stats",
        "measurements": {"up_count": 1800, "down_count": 1200, "total_amount_100m_cny": 11000},
    }]

    history = _market_stats_history_evidence(docs, "2099-01-02", current)

    assert history is not None
    assert history["measurements"]["observation_count"] == 2
    assert history["measurements"]["advancers_pct"] == 60.0
    assert history["measurements"]["advancers_pct_delta_previous"] > 26
    assert "advancers_pct_local_run_percentile" not in history["measurements"]


def test_valuation_history_uses_local_dated_snapshots_without_fake_long_term_percentile(tmp_path):
    import json

    from src.source_health.subject_evidence import _valuation_history_evidence

    docs = tmp_path / "docs"
    prior = docs / "run_status" / "2099-01-01" / "subject_evidence.jsonl"
    prior.parent.mkdir(parents=True)
    prior.write_text(
        json.dumps({
            "id": "subject:AAPL:fundamental:valuation:2099-01-01",
            "metric": "fundamental_valuation",
            "symbol": "AAPL",
            "as_of": "2099-01-01",
            "measurements": {"trailing_pe": 20.0, "price_to_book": 5.0},
        }) + "\n",
        encoding="utf-8",
    )
    current = [{
        "id": "subject:AAPL:fundamental:valuation:2099-01-02",
        "metric": "fundamental_valuation",
        "symbol": "AAPL",
        "as_of": "2099-01-02",
        "measurements": {"trailing_pe": 22.0, "price_to_book": 5.5},
    }]

    rows = _valuation_history_evidence(docs, "2099-01-02", current)

    assert len(rows) == 1
    row = rows[0]
    assert row["comparison_method"] == "local_dated_valuation_snapshots"
    assert row["measurements"]["pe_change_since_prior_run_pct"] == 10.0
    assert row["measurements"]["pb_change_since_prior_run_pct"] == 10.0
    assert "pe_local_run_percentile" not in row["measurements"]


def test_fundamental_history_does_not_report_percentage_across_negative_profit_base():
    from src.source_health.subject_evidence import _fundamental_history_comparison_evidence

    payload = {
        "earnings": {
            "data": {
                "financial_history": [
                    {"report_date": "2099-03-31", "net_profit_parent": 10.0, "operating_cash_flow": -5.0},
                    {"report_date": "2098-03-31", "net_profit_parent": -20.0, "operating_cash_flow": -10.0},
                ]
            }
        }
    }

    row = _fundamental_history_comparison_evidence(
        "AAPL",
        "2099-04-01",
        payload,
        provider="fixture",
        fetched_at="2099-04-01T00:00:00Z",
    )

    assert row is not None
    assert "net_profit_yoy_pct" not in row["measurements"]
    assert row["transitions"]["net_profit_parent"] == "turned_positive"
    assert row["transitions"]["operating_cash_flow"] == "loss_narrowed"


def test_sector_history_does_not_count_repeated_weekend_payload_as_two_observations(tmp_path):
    import json
    from src.source_health.subject_evidence import _sector_history_evidence

    prior = {'metric': 'sector_rankings', 'market': 'cn', 'as_of': '2026-09-05',
             'records': [{'name': '科技', 'rank_side': 'top', 'change_pct': 1.2}]}
    path = tmp_path / 'run_status/2026-09-05/subject_evidence.jsonl'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(prior) + '\n')
    current = {**prior, 'as_of': '2026-09-04', 'time_basis': 'fetched'}
    assert _sector_history_evidence(tmp_path, '2026-09-06', [current]) is None


@pytest.mark.parametrize("metric", ["market_stats", "fundamental_valuation"])
def test_local_history_does_not_inflate_sample_count_with_unchanged_captures(tmp_path, metric):
    import json
    from src.source_health.subject_evidence import (
        _market_stats_history_evidence,
        _valuation_history_evidence,
    )

    fact = {
        "metric": metric,
        "subject": "market" if metric == "market_stats" else "AAPL",
        "measurements": {"up_count": 1000, "down_count": 2000, "trailing_pe": 20, "price_to_book": 5},
        "time_basis": "fetched",
    }
    # Twenty fetches with no source timestamps do not establish twenty sessions.
    for day in range(1, 21):
        run_date = f"2026-08-{day:02}"
        path = tmp_path / "run_status" / run_date / "subject_evidence.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({**fact, "as_of": run_date}) + "\n")
    if metric == "market_stats":
        assert _market_stats_history_evidence(tmp_path, "2026-08-21", [fact]) is None
    else:
        assert _valuation_history_evidence(tmp_path, "2026-08-21", [fact]) == []


def test_distinct_snapshot_selection_keeps_source_dates_and_latest_revision():
    from src.source_health.subject_evidence import _distinct_local_snapshots

    def source(day):
        return {"time_basis": "source", "as_of": day}

    rows = _distinct_local_snapshots([
        ("2026-09-06", source("2026-09-04"), {"pe": 22}),
        ("2026-09-05", source("2026-09-04"), {"pe": 21}),
        ("2026-09-04", source("2026-09-03"), {"pe": 22}),
    ])
    assert rows == [("2026-09-04", {"pe": 22}), ("2026-09-03", {"pe": 22})]


def test_distinct_snapshots_ignore_row_order_without_erasing_dated_equal_sessions():
    from src.source_health.subject_evidence import _distinct_local_snapshots

    payload = [{"name": "科技", "change_pct": 1.2}, {"name": "金融", "change_pct": 0.1}]
    rows = _distinct_local_snapshots([
        ("2026-09-06", {"time_basis": "fetched"}, list(reversed(payload))),
        ("2026-09-05", {"time_basis": "source", "as_of": "2026-09-04"}, payload),
        ("2026-09-04", {"time_basis": "source", "as_of": "2026-09-03"}, payload),
    ])
    assert [day for day, _ in rows] == ["2026-09-04", "2026-09-03"]


@pytest.mark.parametrize("market", ["cn", "hk", "us"])
def test_market_snapshot_weekend_fetch_after_open_is_not_a_new_trading_day(market):
    from src.source_health.subject_evidence import _market_snapshot_date

    assert _market_snapshot_date(market, "2026-09-06", "2026-09-05T23:40:00Z") == "2026-09-04"


def test_valuation_history_preserves_source_date_when_capture_dates_overlap(tmp_path):
    import json
    from src.source_health.subject_evidence import _valuation_history_evidence

    def fact(day, pe):
        return {"metric": "fundamental_valuation", "symbol": "AAPL", "as_of": day,
                "time_basis": "source", "measurements": {"trailing_pe": pe}}

    path = tmp_path / "run_status/2026-09-04/subject_evidence.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(fact("2026-09-03", 20)) + "\n")
    rows = _valuation_history_evidence(tmp_path, "2026-09-06", [fact("2026-09-04", 22)])
    assert rows[0]["as_of"] == "2026-09-04"
    assert rows[0]["observed_dates"] == ["2026-09-03", "2026-09-04"]


def test_foreign_sector_provider_results_enter_subject_evidence_via_manager(tmp_path):
    from src.source_health.subject_evidence import _collect_sector_performance
    from data_provider.base import DataFetcherManager
    from unittest.mock import patch
    payload = {'records': [{'code': 'XLK', 'name': '科技', 'as_of': '2026-09-04', 'return_20d_pct': 2}],
               'scope': '标普500行业代理', 'benchmark': 'SPY', 'expected_count': 11,
               'provider_runs': [{'provider': 'YfinanceFetcher', 'symbol': 'XLK', 'status': 'success',
                                  'record_count': 70, 'error_type': None},
                                 {'provider': 'YfinanceFetcher', 'symbol': 'XLF', 'status': 'failed',
                                  'record_count': 0, 'error_type': 'TimeoutError'}]}
    # Exercise the real manager seam, not a parallel report-only provider.
    with patch('data_provider.sector_performance.collect_sector_performance', return_value=payload) as fetch:
        manager = DataFetcherManager.__new__(DataFetcherManager)
        facts = []
        runs = _collect_sector_performance(manager, '2026-09-06', 'us', facts)
    fetch.assert_called_once_with('us', '2026-09-06')
    assert facts[0]['market'] == 'us' and facts[0]['fact_type'] == 'derived_fact'
    assert facts[0]['coverage'] == {'actual': 1, 'expected': 11}
    assert facts[0]['records'][0]['return_20d_pct'] == 2
    assert runs[0]['success'] and not runs[1]['success']
