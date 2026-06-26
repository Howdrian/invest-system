from src.analyzer import AnalysisResult
from src.notification import NotificationService


def test_blocked_governance_sanitizes_position_advice_in_markdown():
    result = AnalysisResult(
        code="301013",
        name="利和兴",
        sentiment_score=10,
        trend_prediction="治理层阻断",
        operation_advice="减仓/卖出",
        decision_type="sell",
        dashboard={
            "core_conclusion": {
                "one_sentence": "治理层已阻断，不能交易。",
                "position_advice": {
                    "no_position": "立即买入试错",
                    "has_position": "立即减仓或清仓",
                },
            },
            "battle_plan": {
                "sniper_points": {
                    "ideal_buy": "48.00",
                    "secondary_buy": "45.00",
                    "stop_loss": "40.00",
                    "take_profit": "55.00",
                },
                "position_strategy": {
                    "suggested_position": "控制仓位",
                    "entry_plan": "立即买入",
                    "risk_control": "跌破后清仓",
                },
            },
            "governance": {
                "cio_status": "BLOCKED_BY_FATAL",
                "score": 1,
                "gate": "BLOCKED",
                "trade_plan": {"action": "no_action", "target_position_pct": 0},
            },
        },
    )

    report = NotificationService().generate_single_stock_report(result)

    assert "立即买入" not in report
    assert "清仓" not in report
    assert "减仓" not in report
    assert "理想买入点" not in report
    assert "0%" in report
    assert "阻断" in report
    assert "观望" not in report
    assert result.decision_type == "blocked"
    assert result.dashboard["governance"]["trade_plan"]["action"] == "no_action"
