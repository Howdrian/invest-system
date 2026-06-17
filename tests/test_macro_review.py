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
