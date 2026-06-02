def _event(
    question,
    price,
    *,
    liquidity=200000,
    volume24h=150000,
    spread_bid=0.39,
    spread_ask=0.40,
    end_date="2026-12-31T00:00:00Z",
):
    return {
        "id": "evt1",
        "title": question,
        "slug": "evt1",
        "markets": [{
            "id": "m1",
            "question": question,
            "outcomes": '["Yes", "No"]',
            "outcomePrices": f'[{price}, {1-price}]',
            "active": True,
            "closed": False,
            "acceptingOrders": True,
            "liquidity": liquidity,
            "volume24hr": volume24h,
            "bestBid": spread_bid,
            "bestAsk": spread_ask,
            "endDate": end_date,
        }],
    }


def test_polymarket_quality_weights_and_cap():
    from src.prediction_market.polymarket import build_prediction_market_snapshot

    payload = build_prediction_market_snapshot(
        keywords=["taiwan"],
        events=[_event("Will China invade Taiwan by end of 2026?", 0.62)],
    )

    signal = payload["signals"][0]
    assert signal["quality_bucket"] == "high"
    assert signal["recommended_weight"] == 0.25
    assert payload["usage_policy"]["max_fusion_weight"] == 0.30
    assert payload["usage_policy"]["score_gate_bypass"] is False


def test_low_quality_polymarket_observe_only():
    from src.prediction_market.polymarket import build_prediction_market_snapshot

    payload = build_prediction_market_snapshot(
        keywords=["random"],
        events=[_event(
            "Will a random low-liquidity event happen?",
            0.51,
            liquidity=100,
            volume24h=50,
            spread_bid=0.2,
            spread_ask=0.5,
            end_date=None,
        )],
    )

    signal = payload["signals"][0]
    assert signal["quality_bucket"] == "low"
    assert signal["recommended_weight"] == 0.0


def test_probability_gap_triggers_red_team_flag():
    from src.prediction_market.polymarket import build_prediction_market_snapshot

    payload = build_prediction_market_snapshot(
        keywords=["taiwan"],
        events=[_event("Will China invade Taiwan by end of 2026?", 0.62)],
    )

    taiwan = [x for x in payload["scenario_fusion"] if x["scenario_id"] == "geopolitics_semis"][0]
    assert taiwan["red_team_trigger"] is True
    assert "prediction_market_probability_gap_red_team_trigger" in payload["warnings"]
