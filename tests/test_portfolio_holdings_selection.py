from src.intel.portfolio_holdings import build_portfolio_holding_snapshot, merge_symbols_by_priority


class _EmptyPortfolioService:
    def get_portfolio_snapshot(self):
        return {"as_of": "2026-06-17", "accounts": []}


class _FakePortfolioService:
    def get_portfolio_snapshot(self):
        return {
            "as_of": "2026-06-17",
            "accounts": [
                {
                    "account_id": 1,
                    "account_name": "main",
                    "positions": [
                        {"symbol": "SZ300750", "quantity": 10, "market_value_base": 2000},
                        {"symbol": "600519.SH", "quantity": 1, "market_value_base": 3000},
                        {"symbol": "000858", "quantity": 0, "market_value_base": 9999},
                    ],
                }
            ],
        }


def test_portfolio_holding_snapshot_extracts_positive_positions_by_value():
    payload = build_portfolio_holding_snapshot(max_symbols=1, portfolio_service=_FakePortfolioService())

    assert payload["status"] == "available"
    assert payload["symbols"] == ["600519"]
    assert payload["governed_symbols"] == ["600519"]
    assert payload["light_review_symbols"] == []
    assert payload["omitted_symbols"] == ["300750"]
    assert payload["position_count"] == 2
    assert payload["governed_count"] == 1
    assert payload["light_review_count"] == 0
    assert payload["warnings"] == ["portfolio_holdings_truncated"]


def test_merge_symbols_prioritizes_portfolio_then_candidates_then_fallback():
    result = merge_symbols_by_priority(
        ["600519", "SZ300750"],
        ["300750", "AAPL"],
        ["000858"],
        limit=3,
    )

    assert result["selected"] == ["600519", "300750", "AAPL"]
    assert result["omitted"] == ["000858"]


def test_portfolio_holding_snapshot_falls_back_to_env_symbols(monkeypatch):
    monkeypatch.setenv("PORTFOLIO_HOLDINGS", "160644,301013.SZ")
    monkeypatch.delenv("PORTFOLIO_HOLDINGS_FILE", raising=False)

    payload = build_portfolio_holding_snapshot(max_symbols=6, portfolio_service=_EmptyPortfolioService())

    assert payload["status"] == "available"
    assert payload["source"] == "env"
    assert payload["symbols"] == ["160644", "301013"]
    assert payload["governed_symbols"] == ["301013"]
    assert payload["light_review_symbols"] == ["160644"]
    assert payload["positions"][0]["analysis_tier"] == "light_review_only"
    assert payload["positions"][1]["analysis_tier"] == "governed_deep_review"
    assert payload["notes"] == ["fund_etf_lof_holdings_light_review_only"]


def test_portfolio_holding_snapshot_falls_back_to_legacy_markdown(tmp_path, monkeypatch):
    portfolio_md = tmp_path / "portfolio.md"
    portfolio_md.write_text(
        """
# 当前持仓

## 持仓明细

| 标的 | 代码 | 市场 | 类型 | 方向 | 数量 | 成本价 | 成本金额 | 入场日期 | 状态 | 风险计划 |
|------|------|------|------|------|------|--------|----------|----------|------|----------|
| 港美互联网LOF | 160644 | 深交所 | LOF/QDII基金 | 多 | 39手（约3900份） | 2.175 CNY | 8,482.50 CNY | 2026-05-26 | 持仓中 | 系统默认监控 |
| 利和兴 | 301013.SZ | A股创业板 | 股票 | 多 | 1手（约100股） | 45.93 CNY | 4,593.00 CNY | 2026-05-26 | 持仓中 | 系统默认监控 |

## 已了结
        """.strip(),
        encoding="utf-8",
    )
    monkeypatch.delenv("PORTFOLIO_HOLDINGS", raising=False)
    monkeypatch.delenv("PORTFOLIO_STOCK_LIST", raising=False)
    monkeypatch.setenv("PORTFOLIO_HOLDINGS_FILE", str(portfolio_md))

    payload = build_portfolio_holding_snapshot(max_symbols=6, portfolio_service=_EmptyPortfolioService())

    assert payload["status"] == "available"
    assert payload["source"] == "legacy_portfolio_md"
    assert payload["symbols"] == ["160644", "301013"]
    assert payload["governed_symbols"] == ["301013"]
    assert payload["light_review_symbols"] == ["160644"]
    assert payload["positions"][0]["quantity"] == 3900.0
    assert payload["positions"][0]["type"] == "LOF/QDII基金"
    assert payload["positions"][0]["analysis_tier"] == "light_review_only"
    assert payload["positions"][1]["analysis_tier"] == "governed_deep_review"
