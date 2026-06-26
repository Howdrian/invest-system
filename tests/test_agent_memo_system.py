import json
import subprocess
from pathlib import Path


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_agent_memo_builder_generates_required_daily_files(tmp_path):
    from src import agent_memos

    reports = tmp_path / "reports"
    market = reports / "market_cycle" / "2026-06-17"
    market.mkdir(parents=True)
    _write_json(
        market / "13_source_health.json",
        {
            "macro_status": "DEGRADED",
            "usability_verdict": "degraded",
            "trade_review_usability": "usable_limited",
            "rows": [
                {
                    "component": "macro_context",
                    "status": "DEGRADED",
                    "criticality": "critical",
                    "blocking_level": "none",
                    "warnings": ["fmp_unavailable"],
                    "source": "src.macro.official_sources",
                },
                {
                    "component": "market_heat",
                    "status": "AVAILABLE",
                    "criticality": "supporting",
                    "blocking_level": "none",
                    "warnings": [],
                    "source": "src.intel.market_heat",
                },
            ],
        },
    )
    _write_json(
        market / "01_macro_review.json",
        {
            "status": "DEGRADED",
            "confidence": "LOW_TO_MEDIUM",
            "headline": "宏观中性，等待价格和证据共振",
            "prediction_market_status": "available",
            "data_gaps": ["macro_context_not_refreshed"],
            "six_factor_regime": {
                "risk_state": "neutral",
                "missing_factors": ["credit_conditions", "sector_rotation"],
            },
        },
    )
    _write_json(
        market / "11_deep_review_queue.json",
        {
            "candidates": [
                {
                    "symbol": "SZ000725",
                    "name": "京东方Ａ",
                    "verdict": "DEEP_REVIEW_WAIT_ENTRY",
                    "price_risk": "OVERHEATED_WAIT_ENTRY",
                    "evidence": ["hot_stock_rank"],
                    "next_action": "读公告/研报和技术承接；不追高。",
                }
            ],
            "auto_governed_candidates": [],
        },
    )
    _write_json(
        market / "14_market_strategy.json",
        {
            "regime": "NEUTRAL_WATCH",
            "confidence": "MEDIUM",
            "strategy": {
                "headline": "宏观中性；维持观察。",
                "actions": ["热度只做发现"],
                "avoid": ["追高"],
            },
        },
    )
    _write_json(
        reports / "governed_results.json",
        [
            {
                "run_date": "2026-06-17",
                "code": "301013",
                "name": "利和兴",
                "score": 0.5,
                "gate": "BLOCKED",
                "cio_status": "BLOCKED_BY_FATAL",
                "headline": "技术严重超买且基本面亏损",
                "trade_plan": {"action": "no_action", "target_pct": 0},
                "red_blue": {"arbitration": {"verdict": "red stronger"}},
                "scoring": {"total_score": 0.5, "gate_result": "BLOCKED"},
            }
        ],
    )

    generated = agent_memos.generate_daily_agent_memos(
        "2026-06-17",
        reports_dir=reports,
        output_dir=reports / "daily" / "2026-06-17",
    )

    assert "market/01_source_review.json" in generated
    assert "sources/01_source_gap_plan.json" in generated
    assert "stocks/301013/07_evidence_gate.json" in generated
    assert "stocks/301013/10_trade_decision_gate.json" in generated
    assert (reports / "daily" / "2026-06-17" / "index.html").exists()

    source_review = json.loads((reports / "daily" / "2026-06-17" / "market" / "01_source_review.json").read_text())
    assert source_review["schema"] == "agent_memo_v1"
    assert source_review["origin"] == "RAW_AGENT"
    assert source_review["agent"] == "SourceReviewAgent"
    assert source_review["scope"] == "market"
    assert source_review["facts"]
    assert source_review["reasoning"]
    assert source_review["readable_summary"]
    assert source_review["evidence_blocks"]
    assert source_review["audit_detail"]
    assert source_review["source_refs"]
    assert source_review["no_trade_execution"] is True
    assert source_review["evidence_level"] == "LIMITED"
    assert source_review["limited_report"] is True
    assert source_review["source_attempts"]

    source_review_html = (reports / "daily" / "2026-06-17" / "market" / "01_source_review.html").read_text(
        encoding="utf-8"
    )
    assert "一句话结论" in source_review_html
    assert "有限证据 Agent 输出" in source_review_html
    assert "我看了什么" in source_review_html
    assert "搜到什么" in source_review_html
    assert "有限信息结论" in source_review_html
    assert "审计详情" in source_review_html
    assert "Schema:" not in source_review_html

    gate = json.loads((reports / "daily" / "2026-06-17" / "stocks" / "301013" / "10_trade_decision_gate.json").read_text())
    assert gate["agent"] == "TradeDecisionGate"
    assert gate["origin"] == "DERIVED_FROM_ARTIFACT"
    assert gate["status"] == "BLOCKED"
    assert any("no_action" in item for item in gate["facts"])
    assert "0%" in f"{gate['conclusion']} {gate['next_step']}"
    assert gate["readable_summary"].startswith("阻断")


def test_source_status_inventory_marks_failure_reasons(tmp_path):
    from src import agent_memos

    health = {
        "rows": [
            {
                "component": "macro_context",
                "status": "DEGRADED",
                "criticality": "critical",
                "warnings": ["fmp_unavailable"],
                "source": "src.macro.official_sources",
            },
            {
                "component": "prediction_market",
                "status": "AVAILABLE",
                "criticality": "optional",
                "warnings": ["no_matching_market"],
                "source": "src.prediction_market.polymarket",
            },
        ]
    }

    inventory = agent_memos.build_source_inventory(health)

    assert inventory[0]["schema"] == "source_status_v1"
    assert inventory[0]["status"] == "DEGRADED"
    assert inventory[0]["failure_reason"] == "missing_key"
    assert inventory[0]["criticality"] == "critical"
    assert inventory[0]["impact_scope"]
    assert inventory[1]["status"] == "AVAILABLE_NO_MATCHING_MARKET"
    assert inventory[1]["failure_reason"] == "no_matching_market"


def test_source_reports_are_grouped_human_narratives(tmp_path):
    from src import agent_memos

    reports = tmp_path / "reports"
    market = reports / "market_cycle" / "2026-06-17"
    _write_json(
        market / "13_source_health.json",
        {
            "usability_verdict": "degraded",
            "trade_review_usability": "usable_limited",
            "rows": [
                {
                    "component": "macro_context",
                    "status": "DEGRADED",
                    "criticality": "critical",
                    "warnings": ["fmp_unavailable"],
                    "source": "src.macro.official_sources",
                },
                {
                    "component": "prediction_market",
                    "status": "AVAILABLE",
                    "criticality": "optional",
                    "warnings": ["no_matching_market"],
                    "source": "src.prediction_market.polymarket",
                },
            ],
        },
    )
    _write_json(market / "01_macro_review.json", {"status": "DEGRADED"})
    _write_json(market / "11_deep_review_queue.json", {"candidates": []})
    _write_json(market / "14_market_strategy.json", {"regime": "NEUTRAL_WATCH"})

    agent_memos.generate_daily_agent_memos(
        "2026-06-17",
        reports_dir=reports,
        output_dir=reports / "daily" / "2026-06-17",
    )

    inventory_md = (reports / "daily" / "2026-06-17" / "sources" / "00_source_inventory.md").read_text(
        encoding="utf-8"
    )
    gap_md = (reports / "daily" / "2026-06-17" / "sources" / "01_source_gap_plan.md").read_text(
        encoding="utf-8"
    )

    assert "## 宏观" in inventory_md
    assert "## 地缘" in inventory_md
    assert "今天状态" in inventory_md
    assert "影响哪个分析结论" in inventory_md
    assert "是否阻断交易审查" in inventory_md
    assert "AVAILABLE_NO_MATCHING_MARKET" in inventory_md
    assert "API 可用，但未匹配到可用场景市场" in inventory_md
    assert "宏观只可背景参考" in gap_md


def test_polymarket_available_without_matched_scenarios_is_marked_no_matching_market(tmp_path):
    from src import agent_memos

    reports = tmp_path / "reports"
    market = reports / "market_cycle" / "2026-06-17"
    _write_json(
        market / "13_source_health.json",
        {
            "rows": [
                {
                    "component": "prediction_market",
                    "status": "AVAILABLE",
                    "criticality": "optional",
                    "warnings": [],
                    "source": "src.prediction_market.polymarket",
                }
            ]
        },
    )
    _write_json(
        market / "01_macro_review.json",
        {
            "status": "DEGRADED",
            "prediction_market_status": "available",
            "geopolitical_scenarios": [
                {"scenario_id": "A", "market_probability": None, "fusion_weight": 0.0},
                {"scenario_id": "B", "market_probability": None, "fusion_weight": 0.0},
            ],
        },
    )
    _write_json(market / "11_deep_review_queue.json", {"candidates": []})
    _write_json(market / "14_market_strategy.json", {"regime": "NEUTRAL_WATCH"})

    agent_memos.generate_daily_agent_memos(
        "2026-06-17",
        reports_dir=reports,
        output_dir=reports / "daily" / "2026-06-17",
    )

    inventory = json.loads((reports / "daily" / "2026-06-17" / "sources" / "00_source_inventory.json").read_text())
    assert inventory[0]["status"] == "AVAILABLE_NO_MATCHING_MARKET"
    assert inventory[0]["failure_reason"] == "no_matching_market"


def test_agent_memo_cli_runs_by_file_path(tmp_path):
    reports = tmp_path / "reports"
    market = reports / "market_cycle" / "2026-06-17"
    _write_json(market / "13_source_health.json", {"rows": []})
    _write_json(market / "01_macro_review.json", {"status": "DEGRADED"})
    _write_json(market / "11_deep_review_queue.json", {"candidates": []})
    _write_json(market / "14_market_strategy.json", {"regime": "NEUTRAL_WATCH"})

    result = subprocess.run(
        [
            ".venv/bin/python",
            "src/agent_memos.py",
            "--date",
            "2026-06-17",
            "--reports-dir",
            str(reports),
            "--output-dir",
            str(tmp_path / "out"),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "out" / "index.html").exists()


def test_runtime_stage_memo_is_raw_and_post_generator_preserves_it(tmp_path):
    from src import agent_memos
    from src.agent.protocols import AgentContext, AgentOpinion, StageResult, StageStatus

    out = tmp_path / "reports" / "daily" / "2026-06-17"
    ctx = AgentContext(query="分析 301013", stock_code="301013", stock_name="利和兴")
    opinion = AgentOpinion(
        agent_name="scoring",
        signal="hold",
        confidence=0.05,
        reasoning="Score 0.5/10. Gate: BLOCKED.",
        raw_data={
            "total_score": 0.5,
            "gate_result": "BLOCKED",
            "position_size_range": "0%",
            "cannot_trade_reasons": ["score below 6"],
        },
    )
    ctx.add_opinion(opinion)
    result = StageResult(
        stage_name="scoring",
        status=StageStatus.COMPLETED,
        opinion=opinion,
        meta={"raw_text": json.dumps(opinion.raw_data, ensure_ascii=False), "models_used": ["test-model"]},
    )

    generated = agent_memos.write_runtime_stage_memo(
        ctx,
        result,
        output_dir=out,
        run_date="2026-06-17",
    )

    assert "stocks/301013/09_scoring.json" in generated
    raw = json.loads((out / "stocks" / "301013" / "09_scoring.json").read_text(encoding="utf-8"))
    assert raw["origin"] == "RAW_AGENT"
    assert raw["status"] == "BLOCKED"
    assert raw["fatal_objection"] is True
    assert raw["audit_detail"]["raw_untrusted"] is True
    assert "raw_text" in raw["audit_detail"]
    md_text = (out / "stocks" / "301013" / "09_scoring.md").read_text(encoding="utf-8")
    html_text = (out / "stocks" / "301013" / "09_scoring.html").read_text(encoding="utf-8")
    assert "raw_text" not in md_text
    assert "raw_text" not in html_text

    reports = tmp_path / "reports"
    market = reports / "market_cycle" / "2026-06-17"
    _write_json(market / "13_source_health.json", {"rows": []})
    _write_json(market / "01_macro_review.json", {"status": "DEGRADED"})
    _write_json(market / "11_deep_review_queue.json", {"candidates": []})
    _write_json(market / "14_market_strategy.json", {"regime": "NEUTRAL_WATCH"})
    _write_json(
        reports / "governed_results.json",
        [
            {
                "run_date": "2026-06-17",
                "code": "301013",
                "name": "利和兴",
                "score": 0.5,
                "gate": "BLOCKED",
                "cio_status": "BLOCKED_BY_FATAL",
                "trade_plan": {"action": "no_action", "target_pct": 0},
            }
        ],
    )

    agent_memos.generate_daily_agent_memos("2026-06-17", reports_dir=reports, output_dir=out)

    preserved = json.loads((out / "stocks" / "301013" / "09_scoring.json").read_text(encoding="utf-8"))
    assert preserved["origin"] == "RAW_AGENT"
    assert preserved["audit_detail"]["models_used"] == ["test-model"]


def test_evidence_gate_agent_records_runtime_payload():
    from src.agent.agents.governance.evidence_gate_agent import EvidenceGateAgent
    from src.agent.protocols import AgentContext, AgentOpinion, StageStatus

    ctx = AgentContext(query="分析 301013", stock_code="301013", stock_name="利和兴")
    ctx.set_data("realtime_quote", {"price": 10.0})
    ctx.set_data("trend_result", {"trend_status": "weak"})
    ctx.set_data("macro_review", {"status": "DEGRADED"})
    ctx.add_opinion(AgentOpinion(agent_name="technical", signal="hold", confidence=0.4, reasoning="weak"))

    result = EvidenceGateAgent().run(ctx)

    assert result.status == StageStatus.COMPLETED
    payload = ctx.get_data("evidence_gate_result")
    assert payload["schema"] == "evidence_gate_v1"
    assert payload["status"] in {"PASS", "NEEDS_EVIDENCE"}
    assert payload["no_trade_execution"] is True

def test_generate_daily_agent_memos_removes_stale_stock_dirs(tmp_path):
    from src.agent_memos import generate_daily_agent_memos

    reports = tmp_path / "reports"
    market = reports / "market_cycle" / "2026-06-19"
    market.mkdir(parents=True)
    for name in ["13_source_health", "01_macro_review", "11_deep_review_queue", "14_market_strategy"]:
        (market / f"{name}.json").write_text("{}", encoding="utf-8")
    (reports / "governed_results.json").write_text(
        json.dumps([{"run_date": "2026-06-19", "code": "301013", "score": 0, "gate": "BLOCKED"}]),
        encoding="utf-8",
    )
    out = reports / "daily" / "2026-06-19"
    stale = out / "stocks" / "600519"
    stale.mkdir(parents=True)
    (stale / "00_context_pack.json").write_text("{}", encoding="utf-8")

    generate_daily_agent_memos("2026-06-19", reports_dir=reports, output_dir=out)

    assert not stale.exists()
    assert (out / "stocks" / "301013" / "11_decision_report.json").exists()


def test_runtime_intel_memo_contains_limited_evidence_pack_and_source_attempts(tmp_path):
    from types import SimpleNamespace
    from src import agent_memos

    class Ctx:
        stock_code = "300308"
        stock_name = "中际旭创"
        data = {}
        opinions = []
        risk_flags = []
        def get_data(self, key):
            return self.data.get(key)

    opinion = SimpleNamespace(
        agent_name="intel",
        signal="hold",
        confidence=0.2,
        reasoning="搜索源限流，只能给有限信息结论。",
        raw_data={
            "risk_alerts": ["缺公告原文"],
            "positive_catalysts": [],
            "key_news": [],
            "missing_data": ["news", "reports"],
        },
    )
    stage = SimpleNamespace(
        stage_name="intel",
        status=SimpleNamespace(value="completed"),
        opinion=opinion,
        tokens_used=10,
        tool_calls_count=1,
        meta={
            "tool_calls_log": [
                {
                    "tool": "search_comprehensive_intel",
                    "arguments": {"stock_code": "300308", "stock_name": "中际旭创"},
                    "success": True,
                    "result_success": False,
                    "result_error": "This request exceeds your plan usage limit",
                    "provider": "Tavily",
                    "query": "中际旭创 300308 最新公告",
                    "results_count": 0,
                }
            ],
            "raw_text": "{}",
            "models_used": ["test"],
        },
    )

    agent_memos.write_runtime_stage_memo(Ctx(), stage, output_dir=tmp_path, run_date="2026-06-19")

    memo = json.loads((tmp_path / "stocks/300308/05_intel_catalyst_memo.json").read_text(encoding="utf-8"))
    assert memo["origin"] == "RAW_AGENT"
    assert memo["evidence_level"] == "LIMITED"
    assert memo["limited_report"] is True
    assert memo["source_attempts"]
    assert memo["evidence_pack"]["can_go_redblue"] is False
    assert "news" in memo["missing_data"]
    html = (tmp_path / "stocks/300308/05_intel_catalyst_memo.html").read_text(encoding="utf-8")
    assert "我搜了什么" in html
    assert "搜不到什么" in html
    assert "有限信息结论" in html


def test_blocked_agent_memo_html_sanitizes_raw_trade_instructions(tmp_path):
    from src import agent_memos

    memo = agent_memos._memo(
        agent="DecisionReportAgent",
        scope="stock",
        symbol="300308",
        status="BLOCKED",
        facts=["operation_advice=建议立即减仓或清仓止损", "status=BLOCKED_BY_FATAL"],
        reasoning=["MACD 金叉，强烈买入信号，但已阻断"],
        conclusion="建议立即减仓或清仓止损；BLOCKED_BY_FATAL；no_action",
        missing_data=[],
        source_refs=["runtime:cio_result"],
        fatal_objection=True,
        next_step="不执行交易动作",
        origin="RAW_AGENT",
    )
    agent_memos._write_memo_triplet(tmp_path, "stocks/300308/11_decision_report", memo, preserve_raw=False)
    html = (tmp_path / "stocks/300308/11_decision_report.html").read_text(encoding="utf-8")
    assert "立即减仓" not in html
    assert "清仓" not in html
    assert "止损" not in html
    assert "强烈买入信号" not in html
    assert "BLOCKED_BY_FATAL" not in html
    assert "no_action" not in html
    assert "阻断 / 不操作 / 0%" in html


def test_source_inventory_includes_key_public_sources_even_when_degraded():
    from src import agent_memos

    inventory = agent_memos.build_source_inventory({
        "rows": [
            {"component": "macro_context", "status": "DEGRADED", "criticality": "critical", "warnings": ["fmp_unavailable"], "source": "src.macro.official_sources"},
            {"component": "prediction_market", "status": "AVAILABLE", "criticality": "optional", "warnings": ["no_matching_market"], "source": "src.prediction_market.polymarket"},
        ]
    })
    sources = {row["source"] for row in inventory}

    for expected in ["Tavily", "SearXNG", "CNINFO", "Eastmoney", "AKShare", "Tushare", "Polymarket"]:
        assert expected in sources
    tavily = next(row for row in inventory if row["source"] == "Tavily")
    assert tavily["domain"] == "news"
    assert tavily["status"] in {"DEGRADED", "DISABLED"}
    polymarket = next(row for row in inventory if row["source"] == "Polymarket")
    assert polymarket["status"] == "AVAILABLE_NO_MATCHING_MARKET"


def test_derived_stock_source_and_fundamental_memos_are_limited_raw(tmp_path):
    from src import agent_memos

    reports = tmp_path / "reports"
    market = reports / "market_cycle" / "2026-06-19"
    _write_json(market / "13_source_health.json", {"rows": []})
    _write_json(market / "01_macro_review.json", {"status": "DEGRADED"})
    _write_json(market / "11_deep_review_queue.json", {"candidates": []})
    _write_json(market / "14_market_strategy.json", {"regime": "NEUTRAL_WATCH"})
    _write_json(reports / "governed_results.json", [{"run_date": "2026-06-19", "code": "300308", "name": "中际旭创", "score": 0.5, "gate": "BLOCKED", "cio_status": "BLOCKED_BY_FATAL", "headline": "证据不足", "trade_plan": {"action": "no_action", "target_pct": 0}}])

    agent_memos.generate_daily_agent_memos("2026-06-19", reports_dir=reports, output_dir=reports / "daily" / "2026-06-19")

    source = json.loads((reports / "daily/2026-06-19/stocks/300308/01_stock_source_memo.json").read_text(encoding="utf-8"))
    fundamental = json.loads((reports / "daily/2026-06-19/stocks/300308/03_fundamental_reports_memo.json").read_text(encoding="utf-8"))
    for memo in [source, fundamental]:
        assert memo["origin"] == "RAW_AGENT"
        assert memo["evidence_level"] == "LIMITED"
        assert memo["limited_report"] is True
        assert memo["source_attempts"]
        assert memo["evidence_pack"]["can_trade_review"] is False
