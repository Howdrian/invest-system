from src.macro.review import build_macro_review


def test_macro_review_uses_fmp_etf_proxies_for_six_factor_regime():
    macro = {
        "status": "REFRESHED",
        "warnings": [],
        "regime": {"risk_state": "neutral", "confidence": "medium", "reason": "VIX neutral"},
        "components": {
            "fmp": {
                "status": "available",
                "data": [
                    {"symbol": "^GSPC", "price": 5000, "changePercentage": 0.2},
                    {"symbol": "^VIX", "price": 18, "changePercentage": -1.0},
                    {"symbol": "HYG", "price": 80, "changePercentage": 0.3},
                    {"symbol": "LQD", "price": 100, "changePercentage": 0.1},
                    {"symbol": "IWM", "price": 200, "changePercentage": 0.4},
                    {"symbol": "SPY", "price": 500, "changePercentage": 0.2},
                    {"symbol": "TLT", "price": 90, "changePercentage": -0.2},
                    {"symbol": "XLY", "price": 190, "changePercentage": 0.5},
                    {"symbol": "XLP", "price": 70, "changePercentage": 0.0},
                ],
            }
        },
    }

    review = build_macro_review(
        run_date="2026-06-15",
        macro_context=macro,
        market_heat={"status": "available", "focus_items": []},
        prediction_market={"status": "available", "scenario_fusion": []},
    )

    regime = review["six_factor_regime"]
    assert regime["six_factor_status"] == "REFRESHED"
    assert regime["missing_factors"] == []
    assert regime["factors"]["credit_conditions"]["proxy"] == "high_yield_vs_ig_credit_proxy"
    assert regime["factors"]["size_factor"]["status"] == "available"


def test_macro_context_fmp_quote_only_is_partial_not_refreshed():
    from src.macro.official_sources import MacroContextService

    service = MacroContextService(fmp_api_key="test")
    service._fetch_fmp_market_context = lambda _key: {
        "status": "available",
        "source": "FMP Stable quote",
        "data": [{"symbol": "^VIX", "price": 18}],
        "errors": {},
    }

    payload = service.refresh()

    assert payload["status"] == "PARTIAL"
    assert payload["coverage"]["available_factors"] < 6
    assert "macro_factor_coverage_incomplete" in payload["warnings"]


def test_macro_review_marks_polymarket_available_but_no_matching_market_as_gap():
    review = build_macro_review(
        run_date="2026-06-19",
        macro_context={"status": "DEGRADED", "warnings": []},
        market_heat={"status": "available", "focus_items": []},
        prediction_market={
            "status": "available_no_matching_market",
            "signals": [{"question": "unmapped market"}],
            "scenario_match_count": 0,
            "scenario_coverage_status": "available_no_matching_market",
            "scenario_fusion": [],
            "warnings": ["polymarket_available_no_matching_market"],
        },
    )

    assert review["prediction_market_status"] == "available_no_matching_market"
    assert "prediction_market_available_no_matching_market" in review["data_gaps"]
    assert "prediction_market_optional_degraded" in review["warnings"]
