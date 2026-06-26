def test_select_governed_symbols_prioritizes_holdings_and_records_omissions():
    from src.intel.candidate_selector import select_governed_symbols

    result = select_governed_symbols(
        portfolio={
            "governed_symbols": ["600519", "301013", "000001"],
            "light_review_symbols": ["160644"],
        },
        deep_queue={
            "auto_governed_candidates": [{"symbol": "AAPL"}],
            "candidates": [
                {"symbol": "TSLA", "verdict": "DEEP_REVIEW_WAIT_ENTRY"},
                {"symbol": "301013", "verdict": "DEEP_REVIEW_NOW"},
            ],
        },
        limits={"portfolio": 2, "candidates": 2, "total": 3},
    )

    assert result["selected"] == ["600519", "301013", "AAPL"]
    assert result["selected_by_source"]["portfolio"] == ["600519", "301013"]
    assert result["selected_by_source"]["candidate"] == ["AAPL"]
    assert {"symbol": "000001", "reason": "portfolio_limit"} in result["omitted"]
    assert {"symbol": "TSLA", "reason": "total_limit"} in result["omitted"]
    assert result["light_review_symbols"] == ["160644"]
