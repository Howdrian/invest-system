import json


def test_evidence_pack_records_failed_search_attempts_as_limited():
    from src.evidence_pack import build_evidence_pack, source_attempts_from_tool_calls

    attempts = source_attempts_from_tool_calls([
        {
            "tool": "search_stock_news",
            "arguments": {"stock_code": "300308", "stock_name": "中际旭创"},
            "success": True,
            "result_success": False,
            "result_error": "This request exceeds your plan set usage limit",
            "provider": "Tavily",
            "query": "中际旭创 300308 股票 最新消息",
            "results_count": 0,
        },
        {
            "tool": "search_comprehensive_intel",
            "arguments": {"stock_code": "300308", "stock_name": "中际旭创"},
            "success": False,
            "error": "Too Many Requests",
            "provider": "SearXNG",
            "results_count": 0,
        },
    ])

    pack = build_evidence_pack(
        scope="stock",
        symbol="300308",
        source_attempts=attempts,
        evidence_items=[],
        missing_evidence=["news", "reports"],
    )

    assert pack["schema"] == "evidence_pack_v1"
    assert pack["evidence_level"] == "LIMITED"
    assert pack["limited_report"] is True
    assert pack["confidence"] == "low"
    assert pack["can_go_redblue"] is False
    assert pack["can_trade_review"] is False
    assert pack["source_attempts"][0]["failure_reason"] == "rate_limited"
    assert pack["source_attempts"][1]["status"] == "FAILED"


def test_runner_tool_log_summarizes_returned_tool_errors():
    from src.agent.runner import _summarize_tool_result

    summary = _summarize_tool_result(json.dumps({
        "query": "东方锆业 002167 股票 最新消息",
        "success": False,
        "error": "Too Many Requests",
        "provider": "SearXNG",
        "results": [],
    }, ensure_ascii=False))

    assert summary["result_success"] is False
    assert summary["result_error"] == "Too Many Requests"
    assert summary["query"] == "东方锆业 002167 股票 最新消息"
    assert summary["provider"] == "SearXNG"
    assert summary["results_count"] == 0
