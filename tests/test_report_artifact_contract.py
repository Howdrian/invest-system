from api.v1.schemas.history import AnalysisReport, ReportMeta, ReportSummary
from copy import deepcopy
import json


def test_reader_cio_headline_is_short_and_marks_adjudication():
    from src.report_artifact import _reader_cio_headline

    value = "市场呈现明显分化。第二句是详细解释，不应塞进首屏。"

    assert _reader_cio_headline(value) == "当前基准判断：市场呈现明显分化。"


def test_reader_cio_headline_treats_red_team_as_competing_scenario_not_alarm():
    from src.report_artifact import _reader_cio_headline

    value = (
        "当前裁决偏向基准情景，即“结构性分化与避险轮动”，"
        "但必须对最强竞争情景（系统性共振下跌）保持高度警惕。"
    )

    assert _reader_cio_headline(value) == (
        "当前基准判断：结构性分化与避险轮动；"
        "系统性共振下跌仅作为竞争情景，出现翻转信号时再切换判断。"
    )


def test_reader_cio_headline_skips_generic_model_verdict_and_leads_with_shared_fact():
    from src.report_artifact import _reader_cio_headline

    value = "采纳基准情景。美国信用利差本轮为2.71%，跨市场传导仍待验证。"

    assert _reader_cio_headline(
        value,
        shared_facts=["A股主要指数普遍下跌，科创50跌幅更大。"],
    ) == (
        "当前基准判断：A股主要指数普遍下跌，科创50跌幅更大；"
        "美国信用利差本轮为2.71%，跨市场传导仍待验证。"
    )


def test_reader_next_steps_keeps_analysis_discipline_when_cio_omits_do_not():
    from src.report_artifact import _reader_next_steps

    assert _reader_next_steps(
        "看什么：观察市场宽度；下次复核什么：资金流",
        [],
    ) == [
        "不做什么：不要把单一标的或单日波动直接外推为全市场结论",
        "看什么：观察市场宽度",
        "下次复核什么：资金流",
    ]


def test_reader_next_steps_splits_embedded_chinese_numbering():
    from src.report_artifact import _reader_next_steps

    result = _reader_next_steps(
        "不做什么：不要把单股外推为市场；2）验证 AAPL 突破量能；"
        "下次复核什么：核对美港市场宽度。",
        [],
    )

    assert result == [
        "不做什么：不要把单股外推为市场",
        "看什么：验证 AAPL 突破量能",
        "下次复核什么：核对美港市场宽度",
    ]


def test_reader_step_parser_preserves_decimal_price_levels():
    from src.report_artifact import _split_reader_steps

    rows = _split_reader_steps(
        "看什么：1. 观察贵州茅台是否跌破 SMA20 1200.80 元；2. 核对成交量。"
    )

    assert "1200.80" in " ".join(rows)


def test_reader_scope_adjudication_does_not_promote_stock_samples_to_markets():
    from src.report_artifact import _reader_scope_adjudication

    result = _reader_scope_adjudication(
        {"judgment": "AAPL 上涨，因此美股转强。"},
        market_matrix=[
            {
                "market": "A股",
                "scopeLabel": "A股市场",
                "scopeType": "market",
                "state": "主要指数普遍承压",
                "headline": "上证指数 -1.85%、科创50 -4.02%",
            },
            {
                "market": "US",
                "scopeLabel": "美股观察样本",
                "scopeType": "sample",
                "headline": "AAPL +1.76%",
                "scopeNote": "仅代表 1 只观察标的，不代表美股整体。",
            },
        ],
    )

    assert "A股局部风险释放" in result["baseCase"]
    assert "不外推为对应市场转强" in result["judgment"]
    assert "AAPL 上涨，因此美股转强" not in result["judgment"]


def test_reader_institutional_copy_separates_buyback_fact_from_price_causality():
    from src.report_artifact import _reader_institutional_copy

    text = _reader_institutional_copy("公司回购行动对股价形成机制性抗跌支撑。")

    assert text == "公司已披露回购；是否形成价格支撑仍需验证"


def test_latest_evidence_time_does_not_display_synthetic_midnight():
    from src.report_artifact import _latest_evidence_time

    assert _latest_evidence_time(
        [{"published_at": "2026-07-17T00:00:00Z"}, {"as_of": "2026-07-17"}],
        fallback="2026-07-16",
    ) == "2026-07-17"
    assert _latest_evidence_time(
        [{"published_at": "2026-07-17T03:15:00Z"}, {"as_of": "2026-07-17"}],
        fallback="2026-07-16",
    ) == "2026-07-17T03:15:00Z"


def test_reader_deduplicates_semantically_overlapping_core_reasons():
    from src.report_artifact import _dedupe_nonempty

    rows = _dedupe_nonempty([
        "A股主要指数呈现系统性深调，科创50单日下跌4.02%，上证指数下跌1.85%。",
        "A股市场整体呈现系统性深调，科创50单日下跌4.02%，创业板指下跌2.95%，上证指数下跌1.85%。",
        "本轮观察标的中 AAPL 与腾讯相对走强。",
    ], limit=3)

    assert len(rows) == 2
    assert rows[-1] == "本轮观察标的中 AAPL 与腾讯相对走强"


def test_reader_builds_market_scope_and_stock_matrix_without_sample_pollution():
    from src.report_artifact import _build_market_matrix, _build_stock_matrix

    evidence = [
        {
            "id": "subject:market:main_indices:2026-07-17",
            "fact_type": "derived_fact",
            "domain": "price",
            "metric": "main_indices",
            "as_of": "2026-07-17",
            "measurements": {
                "index_sh000001_change_pct": -1.85,
                "index_sh000300_change_pct": -1.84,
            },
        },
        {
            "id": "subject:AAPL:daily_data:2026-07-17",
            "fact_type": "derived_fact",
            "domain": "price",
            "symbol": "AAPL",
            "as_of": "2026-07-16",
            "value": "latest_close=333.26 sma5=321.65 sma20=303.63 high20=333.26 low20=275.15",
        },
        {
            "id": "subject:AAPL:price_history_comparison:2026-07-17",
            "fact_type": "derived_fact",
            "domain": "price",
            "symbol": "AAPL",
            "metric": "price_history_comparison",
            "as_of": "2026-07-16",
            "value": "return_1d_pct=1.76 return_20d_pct=11.37 range_position_pct=100",
        },
        {
            "id": "sec:AAPL:10Q",
            "fact_type": "verified_fact",
            "provider": "SEC_EDGAR",
            "domain": "filings_events",
            "symbol": "AAPL",
            "as_of": "2026-05-01",
            "source_url": "https://sec.example/aapl",
            "value": "10-Q 2026-05-01",
        },
    ]
    stock_rows = _build_stock_matrix(
        evidence,
        universe={"subjectSymbols": ["AAPL"]},
        original_analysis_snapshot={"records": [{"code": "AAPL", "name": "Apple Inc.", "action": "hold"}]},
    )
    market_rows = _build_market_matrix(evidence, stock_rows)

    assert stock_rows[0]["name"] == "Apple Inc."
    assert stock_rows[0]["trend"] == "短中期趋势向上"
    assert stock_rows[0]["latestEvent"] == "10-Q 2026-05-01"
    assert next(row for row in market_rows if row["market"] == "US")["scopeType"] == "sample"
    assert "不代表美股整体" in next(row for row in market_rows if row["market"] == "US")["scopeNote"]
    assert next(row for row in market_rows if row["market"] == "A股")["scopeType"] == "market"


def test_stock_matrix_uses_completed_session_change_and_clear_fundamental_periods():
    from src.report_artifact import _build_stock_matrix

    evidence = [
        {
            "id": "subject:600519:quote:2026-07-17",
            "fact_type": "derived_fact",
            "domain": "price",
            "symbol": "600519",
            "metric": "realtime_quote",
            "as_of": "2026-07-17",
            "session_phase": "postmarket",
            "measurements": {"price": 1253.0, "change_pct": -0.48},
        },
        {
            "id": "subject:600519:daily_data:2026-07-17",
            "fact_type": "derived_fact",
            "domain": "price",
            "symbol": "600519",
            "as_of": "2026-07-16",
            "value": "latest_close=1258.99 sma5=1228.18 sma20=1200.81 high20=1258.99 low20=1168.63",
        },
        {
            "id": "subject:600519:price_history_comparison:2026-07-17",
            "fact_type": "derived_fact",
            "domain": "price",
            "symbol": "600519",
            "metric": "price_history_comparison",
            "as_of": "2026-07-16",
            "measurements": {"return_1d_pct": 0.63, "return_20d_pct": 3.88},
        },
        {
            "id": "subject:600519:fundamental:growth:2026-07-17",
            "fact_type": "derived_fact",
            "domain": "fundamentals",
            "symbol": "600519",
            "metric": "fundamental_growth",
            "report_period": "2026-03-31",
            "measurements": {"revenue_yoy_pct": 6.336, "net_profit_yoy_pct": 1.4714},
        },
        {
            "id": "subject:600519:fundamental:history_comparison:2026-07-17",
            "fact_type": "derived_fact",
            "domain": "fundamentals",
            "symbol": "600519",
            "metric": "fundamental_history_comparison",
            "report_period": "2026-03-31",
            "comparison_period": "2025-03-31",
            "measurements": {"period_count": 12, "revenue_yoy_pct": 6.336},
        },
        {
            "id": "subject:600519:fundamental:valuation:2026-07-17",
            "fact_type": "derived_fact",
            "domain": "fundamentals",
            "symbol": "600519",
            "metric": "fundamental_valuation",
            "as_of": "2026-07-17",
            "measurements": {"pe_ttm": 21.2, "pb": 7.1},
        },
        {
            "id": "subject:600519:valuation_history_comparison:2026-07-17",
            "fact_type": "derived_fact",
            "domain": "fundamentals",
            "symbol": "600519",
            "metric": "valuation_history_comparison",
            "measurements": {"sample_count": 3, "valuation_percentile_eligible": 0},
        },
    ]

    row = _build_stock_matrix(
        evidence,
        universe={"subjectSymbols": ["600519"]},
        original_analysis_snapshot={"records": [{"code": "600519", "name": "贵州茅台"}]},
    )[0]

    assert row["lastPrice"] == 1253.0
    assert row["return1dPct"] == -0.48
    assert row["asOf"] == "2026-07-17"
    assert "2026-03-31 对 2025-03-31" in row["fundamental"]
    assert "待核验" not in row["fundamental"]
    assert "PE(TTM) 21.20" in row["valuation"]
    assert "已累计 3 个本地日度样本" in row["valuation"]
    assert "历史分位" not in row["valuation"].split("；", 1)[0]


def test_reader_macro_history_uses_local_comparison_window():
    from src.report_artifact import _reader_macro_history_levels

    rows = _reader_macro_history_levels([
        {
            "metric": "BAMLH0A0HYM2_history_comparison",
            "symbol": "BAMLH0A0HYM2",
            "comparison": {
                "series": "BAMLH0A0HYM2",
                "latest": 2.71,
                "history_observations": 258,
                "history_percentile_pct": 10.9,
                "delta_12_observations": -0.09,
            },
        }
    ])

    assert rows == ["美国高收益债利差 2.71%，近258期样本分位 10.9%，较12个观测值前 -0.09"]


def test_fundamental_reader_gap_is_derived_from_current_coverage_not_hardcoded():
    from src.report_artifact import _curate_reader_v3_cards

    cards = [{"agent": "FundamentalAgent"}]
    stocks = [
        {"symbol": "AAPL", "name": "Apple Inc.", "fundamental": "营收同比 +10%"},
        {"symbol": "HK00700", "name": "腾讯控股", "fundamental": "营收同比 +9.1%"},
    ]
    evidence = [{
        "symbol": "AAPL",
        "metric": "fundamental_history_comparison",
        "measurements": {"period_count": 5, "revenue_yoy_pct": 10.0},
    }]

    _curate_reader_v3_cards(
        cards,
        market_matrix=[],
        stock_matrix=stocks,
        evidence_rows=evidence,
        has_portfolio=False,
        adjudication={},
    )

    card = cards[0]
    assert not any("腾讯控股结构化财务指标尚待补强" in item for item in card["dataGaps"])
    assert any("腾讯控股当前有结构化同比指标" in item for item in card["dataGaps"])


def test_reader_preserves_negative_percentages_and_normalizes_overreach():
    from src.report_artifact import (
        _dedupe_reader_sentences,
        _product_copy,
        _reader_evidence_label,
        _reader_institutional_copy,
    )

    assert "-21.28%" in _product_copy("60日回报率为-21.28%")
    text = _reader_institutional_copy(
        "采纳红队关于“A股系统性走弱”及“防御属性过度乐观偏见”的警示，"
        "贵州茅台基本面失速对估值构成实质性压制。"
    )
    assert "采纳红队" not in text
    assert "系统性走弱" not in text
    assert "基本面失速" not in text
    assert "盈利增速放缓" in text
    assert "range_position_pct" not in _reader_institutional_copy("range_position_pct=28%")
    calibrated = _reader_institutional_copy(
        "高收益债信用利差维持在2.71%的低位，风险偏好整体平稳；"
        "市场风格向大盘价值及防御性板块抱团。"
    )
    assert "低位" not in calibrated
    assert "整体平稳" not in calibrated
    assert "是否存在资金抱团仍待资金流验证" in calibrated
    breadth_step = _reader_institutional_copy("监控指数及市场宽度仍待有效数据确认")
    assert "及市场宽度仍待有效数据确认" not in breadth_step
    assert breadth_step == "监控指数，并补充市场宽度数据"
    tencent = _reader_institutional_copy(
        "腾讯控股（HK00700）持续进行股份回购，基本面与资本运作事实支持当前“持有”的保守评级，但茅台盈利放缓。"
    )
    assert "持有" not in tencent
    assert "暂不据此作估值判断" in tencent
    scope = _reader_institutional_copy(
        "A股风险偏好明显收缩，存在局部去杠杆特征；AAPL强势创历史新高。"
    )
    assert "A股主要指数显示风险偏好收缩" in scope
    assert "局部风险释放特征" in scope
    assert "创本轮20日新高" in scope
    assert _dedupe_reader_sentences("结论一。结论一。结论二。") == "结论一。结论二。"
    label = _reader_evidence_label("return_1d_pct=1.76 return_20d_pct=11.37 range_position_pct=100")
    assert label == "区间表现：1日 +1.76%，20日 +11.37%，区间位置 100%"
    assert "return_" not in label


def test_reader_stock_stance_ignores_unvalidated_upstream_action():
    from src.report_artifact import _reader_stock_stance

    assert _reader_stock_stance("buy", "短中期承压") == "谨慎观察"
    assert _reader_stock_stance("sell", "短中期趋势向上") == "趋势跟踪"


def test_department_numbered_steps_are_split_for_reader_bullets():
    from src.report_artifact import _split_reader_steps

    assert _split_reader_steps("1. 看指数；2. 看市场宽度") == ["看指数", "看市场宽度"]


def test_product_copy_hides_inline_evidence_ids_from_reader():
    from src.report_artifact import _product_copy

    value = "科创50下跌4.25%（`subject:market:main_indices:2026-07-15`）。"

    assert _product_copy(value) == "科创50下跌4.25%"


def test_hypothesis_department_summary_is_labeled_as_department_judgment():
    from src.report_artifact import _reader_department_conclusion

    row = {"semanticValidation": {"summary": {"status": "hypothesis"}}}

    assert _reader_department_conclusion(row, "地缘风险是科技股下跌的催化剂。") == (
        "部门判断：地缘风险是科技股下跌的催化剂"
    )


def test_reader_repairs_red_team_flow_wording_after_semantic_rewrite():
    from src.report_artifact import _reader_department_conclusion

    row = {"semanticValidation": {"summary": {"status": "hypothesis"}}}
    value = (
        "前序部门关于“防御板块价格表现相对抗跌；是否属于主动资金抱团仍待资金流与市场宽度验证、"
        "跨市场联动减弱”的基准判断存在严重的‘单股污染’与‘时效错配’。"
    )

    assert _reader_department_conclusion(row, value) == (
        "部门判断：前序部门把少数防御样本的相对抗跌解释为资金抱团，并据此判断跨市场联动减弱；"
        "该结论存在单股污染与时效错配"
    )


def test_hypothesis_department_claim_is_labeled_as_interpretation():
    from src.report_artifact import _reader_department_claims

    row = {
        "claimEvidence": [
            {"claim": "公告线索是下跌催化剂。", "semanticStatus": "hypothesis"},
            {"claim": "科创50下跌4.25%。", "semanticStatus": "supported"},
        ]
    }

    assert _reader_department_claims(row, []) == [
        "解释性判断：公告线索是下跌催化剂",
        "科创50下跌4.25%",
    ]


def test_report_artifact_v1_reader_contract_requires_human_sections():
    from src.report_artifact import validate_report_artifact

    artifact = {
        "schemaVersion": "report_artifact_v1",
        "artifactId": "history:1",
        "runDate": "2026-06-19",
        "generatedAt": "2026-06-19T08:00:00Z",
        "artifactType": "stock_governed",
        "audience": "reader",
        "title": "测试报告",
        "summary": {
            "oneLine": "一句话结论",
            "keyFacts": ["事实"],
            "analysis": "推论",
            "finalConclusion": "总结论",
            "nextSteps": ["下一步"],
        },
        "sections": [
            {"key": "source", "title": "数据源", "kind": "source", "contentMarkdown": "DB"},
            {"key": "facts", "title": "关键数据", "kind": "facts", "contentMarkdown": "事实"},
            {"key": "analysis", "title": "推论", "kind": "analysis", "contentMarkdown": "分析"},
            {"key": "final", "title": "总结论", "kind": "final_conclusion", "contentMarkdown": "结论"},
            {"key": "next", "title": "下一步", "kind": "next_steps", "contentMarkdown": "复核"},
        ],
        "provenance": {"origin": "history", "sourceFiles": [], "generatedBy": "test"},
        "publish": {},
        "quality": {"completeness": "complete", "missingFields": [], "validationErrors": []},
    }

    ok, errors = validate_report_artifact(artifact)

    assert ok is True
    assert errors == []


def test_analysis_report_accepts_optional_report_artifact():
    artifact = {
        "schemaVersion": "report_artifact_v1",
        "artifactId": "history:1",
        "runDate": "2026-06-19",
        "generatedAt": "2026-06-19T08:00:00Z",
        "artifactType": "stock_governed",
        "audience": "reader",
        "title": "测试报告",
        "summary": {
            "oneLine": "一句话结论",
            "keyFacts": ["事实"],
            "analysis": "推论",
            "finalConclusion": "总结论",
            "nextSteps": ["下一步"],
        },
        "sections": [
            {"key": "source", "title": "数据源", "kind": "source", "contentMarkdown": "DB"},
            {"key": "facts", "title": "关键数据", "kind": "facts", "contentMarkdown": "事实"},
            {"key": "analysis", "title": "推论", "kind": "analysis", "contentMarkdown": "分析"},
            {"key": "final", "title": "总结论", "kind": "final_conclusion", "contentMarkdown": "结论"},
            {"key": "next", "title": "下一步", "kind": "next_steps", "contentMarkdown": "复核"},
        ],
        "provenance": {"origin": "history", "sourceFiles": [], "generatedBy": "test"},
        "publish": {},
        "quality": {"completeness": "complete", "missingFields": [], "validationErrors": []},
    }

    report = AnalysisReport(
        meta=ReportMeta(
            id=1,
            query_id="q-1",
            stock_code="301013",
            stock_name="利和兴",
            report_type="simple",
            created_at="2026-06-19T08:00:00Z",
        ),
        summary=ReportSummary(
            analysis_summary="摘要",
            operation_advice="阻断 / 不操作 / 0%",
            trend_prediction="治理层阻断",
            sentiment_score=5,
        ),
        artifact=artifact,
    )

    assert report.artifact["schemaVersion"] == "report_artifact_v1"
    assert report.artifact["summary"]["finalConclusion"] == "总结论"


def test_reports_router_registered_under_api_v1():
    from api.app import create_app

    app = create_app()
    paths = set(app.openapi()["paths"].keys())

    assert "/api/v1/reports/latest" in paths
    assert "/api/v1/reports/artifacts" in paths
    assert "/api/v1/reports/artifacts/{artifact_id}" in paths


def test_stock_artifact_preserves_zero_score_and_target_pct():
    from src.report_artifact import build_stock_artifact_from_history_detail

    artifact = build_stock_artifact_from_history_detail(
        {
            "id": 1,
            "query_id": "q-1",
            "stock_code": "300308",
            "stock_name": "中际旭创",
            "created_at": "2026-06-19T08:00:00Z",
            "operation_advice": "治理层阻断",
            "raw_result": {
                "dashboard": {
                    "governance": {
                        "cio_status": "BLOCKED_BY_FATAL",
                        "score": 0,
                        "trade_plan": {"action": "no_action", "target_pct": 0},
                    }
                }
            },
        }
    )

    assert artifact["decision"]["score"] == 0
    assert artifact["decision"]["targetPct"] == 0
    assert artifact["decision"]["action"] == "no_action"
    assert any("评分：0" in fact for fact in artifact["summary"]["keyFacts"])


def test_source_health_caveat_does_not_replace_upstream_recommendation():
    from src.report_artifact import _apply_claim_policy_to_decision

    decision = {
        "action": "buy",
        "gateStatus": "passed",
        "score": 72,
        "targetPct": 15,
        "blockedReasons": [],
    }
    result = _apply_claim_policy_to_decision(
        decision,
        {"claimPolicy": {"canActionableAdvice": False, "canPositionSizing": False}},
    )

    assert result["action"] == "buy"
    assert result["gateStatus"] == "passed"
    assert result["targetPct"] == 15
    assert result["advisoryCaveats"] == [
        "actionable_advice_evidence_limited",
        "position_sizing_evidence_limited",
    ]


def test_daily_report_artifact_writes_source_health_and_agent_origins(tmp_path):
    from src.report_artifact import validate_report_artifact, write_daily_report_artifact
    from src.source_health.evidence_ledger import write_evidence_ledger

    docs = tmp_path / "docs"
    date = "2026-06-19"
    mc = docs / "market_cycle" / date
    memo = docs / "agent_memos" / date / "stocks" / "300308"
    mc.mkdir(parents=True)
    memo.mkdir(parents=True)
    (docs / "daily").mkdir(parents=True)
    write_evidence_ledger(
        docs / "run_status" / date / "evidence_ledger.jsonl",
        [
            {
                "id": "sec:300308:1",
                "domain": "filings_events",
                "fact_type": "verified_fact",
                "provider": "SEC_EDGAR",
                "symbol": "300308",
                "value": "official filing",
                "source_url": "https://www.sec.gov/Archives/example",
                "as_of": date,
            }
        ],
    )
    (docs / "daily" / f"{date}.md").write_text("# daily", encoding="utf-8")
    (mc / "13_source_health.json").write_text(
        json.dumps(
            {
                "usability_verdict": "degraded",
                "trade_review_usability": "usable_limited",
                "rows": [{"component": "macro_context", "status": "PARTIAL"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (mc / "14_market_strategy.json").write_text(
        json.dumps({"regime": "NEUTRAL_WATCH", "strategy": {"headline": "等待确认"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (mc / "11_deep_review_queue.json").write_text(
        json.dumps({"candidates": [{"symbol": "SZ000725", "name": "京东方Ａ"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    (docs / "governed_results.json").write_text(
        json.dumps(
            [
                {
                    "run_date": date,
                    "code": "300308",
                    "name": "中际旭创",
                    "cio_status": "BLOCKED_BY_FATAL",
                    "score": 0,
                    "trade_plan": {"action": "no_action", "target_pct": 0},
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (memo / "11_decision_report.json").write_text(
        json.dumps({"schema": "agent_memo_v1", "origin": "RAW_AGENT"}, ensure_ascii=False),
        encoding="utf-8",
    )

    artifact = write_daily_report_artifact(docs, date)

    assert (docs / "reports" / f"{date}.artifact.json").exists()
    assert artifact["artifactType"] == "daily"
    assert artifact["sourceHealth"]["verdict"] == "usable_limited"
    assert artifact["sourceHealth"]["decisionImpact"] == "可形成有限复盘；细分结论需结合待确认项。"
    assert artifact["analysisMode"] == "LIMITED_REVIEW"
    assert artifact["sourceHealthV2"]["schema"] == "source_health_v2"
    assert artifact["sourceHealthV2"]["overallMode"] == "LIMITED_REVIEW"
    assert artifact["sourceHealthV2"]["claimPolicy"]["canActionableAdvice"] is False
    assert artifact["sourceHealthV2"]["claimPolicy"]["canPositionSizing"] is False
    assert artifact["sourceHealthV2"]["claimEvidence"]["schema"] == "claim_evidence_v1"
    assert artifact["sourceHealthV2"]["claimEvidence"]["claims"]["actionable_advice"]["status"] == "partial"
    assert artifact["sourceHealthV2"]["domains"]["macro"]["status"] in {"degraded", "missing"}
    assert artifact["evidenceStats"]["schema"] == "evidence_stats_v1"
    assert artifact["evidenceItems"][0]["factType"] == "verified_fact"
    assert artifact["evidenceItems"][0]["provider"] == "SEC_EDGAR"
    assert artifact["runMatrix"]["runDate"] == date
    assert artifact["snapshotRefs"]["providerLedgerSha256"]
    assert artifact["snapshotRefs"]["evidenceLedgerSha256"]
    assert artifact["snapshotRefs"]["sourceHealthSha256"]
    assert artifact["snapshotRefs"]["runMatrixSha256"]
    assert artifact["claimPolicy"]["canPositionSizing"] is False
    assert artifact["readerBrief"]["schema"] == "reader_brief_v1"
    assert artifact["readerV2"]["schema"] == "reader_v2_v1"
    assert isinstance(artifact["readerV2"]["departmentCards"], list)
    assert artifact["originalAnalysis"]["runDate"] == date
    assert isinstance(artifact["departmentInputs"], list)
    assert "universe" in artifact["readerBrief"]
    assert "dailyUniverse" in artifact
    assert artifact["dailyUniverse"].get("schema") in {None, "daily_universe_v1"}
    assert isinstance(artifact["departmentReports"], list)
    assert artifact["claimEvidence"]["schema"] == "claim_evidence_v1"
    assert artifact["agentOrigins"] == {"raw": 1, "derived": 0, "missing": 0}
    assert artifact["decision"]["score"] == 0
    assert artifact["decision"]["targetPct"] == 0
    assert artifact["decision"]["gateStatus"] == "blocked"
    ok, errors = validate_report_artifact(artifact)
    assert ok, errors


def test_build_daily_report_artifact_does_not_write_snapshots(tmp_path):
    from src.report_artifact import build_daily_report_artifact

    docs = tmp_path / "docs"
    date = "2026-06-19"
    mc = docs / "market_cycle" / date
    mc.mkdir(parents=True)
    (docs / "daily").mkdir(parents=True)
    (docs / "daily" / f"{date}.md").write_text("# daily", encoding="utf-8")
    (mc / "13_source_health.json").write_text(
        json.dumps(
            {
                "usability_verdict": "usable",
                "trade_review_usability": "usable",
                "rows": [{"component": "macro_context", "status": "available"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (mc / "14_market_strategy.json").write_text(json.dumps({"regime": "NEUTRAL_WATCH"}), encoding="utf-8")

    artifact = build_daily_report_artifact(docs, date)

    assert artifact["artifactType"] == "daily"
    assert not (docs / "run_status" / date).exists()


def test_agent_gap_text_does_not_rewrite_provider_source_health():
    from src.report_artifact import _align_source_health_with_agent_outputs

    health = {
        "schema": "source_health_v2",
        "overallMode": "FULL_REVIEW",
        "overallScore": 0.9,
        "domains": {"macro": {"status": "available", "coverage": 0.9, "confidence": "high"}},
        "claimPolicy": {"canScore": True, "canActionableAdvice": True, "canPositionSizing": True},
        "blockingReasons": [],
    }
    aligned = _align_source_health_with_agent_outputs(
        health,
        department_reports=[{
            "agent": "CIOAgent",
            "summaryForReader": "中国宏观细分数据仍待增强。",
            "dataGaps": ["中国 PMI 待确认"],
        }],
        has_governed_rows=False,
        daily_universe_mode="multi_subject_daily",
        daily_subject_count=4,
    )

    assert aligned["overallMode"] == "FULL_REVIEW"
    assert aligned["overallScore"] == 0.9
    assert aligned["domains"]["macro"]["status"] == "available"
    assert aligned["departmentObservations"]["reportedGapDomains"]["macro"]


def test_reports_api_prefers_static_daily_artifact(tmp_path, monkeypatch):
    from api.v1.endpoints import reports

    docs_reports = tmp_path / "docs" / "reports"
    docs_reports.mkdir(parents=True)
    artifact = _valid_daily_reader_artifact()
    artifact.update({
        "artifactId": "daily:2026-06-19",
        "runDate": "2026-06-19",
        "generatedAt": "2026-06-19T08:00:00Z",
        "title": "静态日报",
    })
    artifact["readerV3"]["runDate"] = "2026-06-19"
    (docs_reports / "2026-06-19.artifact.json").write_text(
        json.dumps(artifact, ensure_ascii=False),
        encoding="utf-8",
    )

    class ExplodingDb:
        pass

    monkeypatch.chdir(tmp_path)

    loaded = reports._load_report_artifacts(ExplodingDb(), limit=1)

    assert loaded == [artifact]


def test_daily_report_reader_uses_market_scope_not_single_stock_when_universe_is_multi(tmp_path):
    from src.report_artifact import build_daily_report_artifact

    docs = tmp_path / "docs"
    date = "2099-01-02"
    mc = docs / "market_cycle" / date
    stock_memo = docs / "agent_memos" / date / "stocks" / "600519"
    market_memo = docs / "agent_memos" / date / "market"
    run_status = docs / "run_status" / date
    mc.mkdir(parents=True)
    stock_memo.mkdir(parents=True)
    market_memo.mkdir(parents=True)
    run_status.mkdir(parents=True)
    (docs / "daily").mkdir(parents=True)
    (docs / "daily" / f"{date}.md").write_text("# daily", encoding="utf-8")
    (run_status / "daily_universe.json").write_text(
        json.dumps(
            {
                "schema": "daily_universe_v1",
                "runDate": date,
                "mode": "multi_subject_daily",
                "subjectSymbols": ["600519", "000001", "AAPL"],
                "groups": [
                    {"name": "watchlist", "symbols": ["600519", "000001", "AAPL"]},
                    {"name": "portfolio", "symbols": []},
                    {"name": "candidates", "symbols": []},
                    {"name": "market", "symbols": []},
                    {"name": "macro", "symbols": []},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (mc / "13_source_health.json").write_text(json.dumps({"usability_verdict": "usable"}), encoding="utf-8")
    (mc / "14_market_strategy.json").write_text(json.dumps({"regime": "NEUTRAL_WATCH"}), encoding="utf-8")
    (stock_memo / "02_macro_memo.json").write_text(
        json.dumps(
            {
                "schema": "agent_memo_v1",
                "agent": "MacroAgent",
                "subject": "600519",
                "summary_for_reader": "贵州茅台单股宏观结论，不应进日报首页。",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (market_memo / "03_market_strategy.json").write_text(
        json.dumps(
            {
                "schema": "agent_memo_v1",
                "agent": "MarketStrategyAgent",
                "subject": "market",
                "summary_for_reader": "市场层面等待价格和证据共振。",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    artifact = build_daily_report_artifact(docs, date)

    assert "贵州茅台" not in artifact["readerBrief"]["finalConclusion"]
    assert all("贵州茅台" not in item for item in artifact["readerBrief"]["why"])
    stock_rows = [row for row in artifact["departmentReports"] if row.get("subject") == "600519"]
    assert stock_rows and stock_rows[0]["readerVisible"] is False
    assert artifact["readerBrief"]["finalConclusion"] == "市场层面等待价格和证据共振"


def test_reader_v3_full_review_uses_confirm_items_not_missing_critical_facts():
    from src.report_artifact import _build_reader_v3

    reader = _build_reader_v3(
        run_date="2026-07-09",
        reader_brief={"nextSteps": ["先看 CIO 结论和分部门摘要，不直接按单一信号行动"]},
        department_reports=[
            {
                "agent": "CIOAgent",
                "summaryForReader": "当前不应把少数权重股走弱外推为市场整体走弱。",
                "keyClaims": ["市场判断基础不牢，存在单股污染风险。"],
                "counterpoints": ["可能只是结构性风格轮动。"],
                "dataGaps": ["市场宽度仍需人工确认。"],
                "nextAction": (
                    "1. **操作纪律**：不要把少数权重股下跌直接外推为市场整体走弱。 "
                    "* **风险升级信号（触发减仓/对冲）**：关注贵州茅台1180元、腾讯近期前低。 "
                    "* **风险降级信号（可考虑回补仓位）**：数据修复后确认资金流向和市场宽度。"
                ),
                "confidence": "high",
                "readerVisible": True,
            },
            {
                "agent": "MarketAgent",
                "summaryForReader": "市场层面需要等待资金流和市场宽度确认。",
                "dataGaps": ["行业资金待确认。"],
                "confidence": "medium",
                "readerVisible": True,
            },
            {
                "agent": "SectorAgent",
                "summaryForReader": "sector_rankings 与 hot_stocks 只支持候选观察。",
                "keyClaims": ["sector_rankings 暂未形成稳定主线。"],
                "counterpoints": ["hot_stocks 可能只是短期热度。"],
                "confidence": "medium",
                "readerVisible": True,
            },
            {
                "agent": "PortfolioAgent",
                "summaryForReader": "originalAnalysisRefs 中的 portfolio_snapshot 显示本轮没有真实持仓。",
                "nextAction": "补齐 quantity、market_value 和 cost_basis 后再做组合复核。",
                "confidence": "medium",
                "readerVisible": True,
            },
            {
                "agent": "FundamentalAgent",
                "summaryForReader": "FundamentalAgent 尚未拿到完整财报事实。",
                "confidence": "medium",
                "readerVisible": True,
            },
        ],
        department_inputs=[],
        evidence_items=[],
        source_health_v2={"overallMode": "FULL_REVIEW", "overallScore": 0.872},
        evidence_stats={
            "verifiedFacts": 31,
            "derivedFacts": 47,
            "discoveryItems": 6,
            "missingFacts": 0,
            "missingCriticalFacts": 0,
        },
        decision={"action": "watch", "gateStatus": "watch"},
    )

    rendered = json.dumps(reader, ensure_ascii=False)
    visible_reader = json.dumps(reader, ensure_ascii=False)
    for field in (
        "sector_rankings",
        "hot_stocks",
        "originalAnalysisRefs",
        "portfolio_snapshot",
        "FundamentalAgent",
        "quantity",
        "market_value",
        "cost_basis",
    ):
        assert field not in visible_reader
    assert "Agent" not in visible_reader
    assert reader["hero"]["confidence"] == "高可信，含待确认项"
    assert reader["dataConfidence"].startswith(reader["hero"]["confidence"])
    assert "核心证据链完整" in reader["hero"]["maxLimitation"]
    assert reader["evidenceSummary"]["missingCriticalFacts"] == 0
    assert reader["evidenceSummary"]["departmentGapItems"] > 0
    assert "关键数据缺失" not in rendered
    assert "数据修复" not in rendered
    assert "下次复核" in rendered
    assert len(reader["nextSteps"]) <= 3
    assert sum(1 for item in reader["nextSteps"] if "风险升级信号" in item) <= 1
    assert reader["nextSteps"][0].startswith("不做什么：")
    assert reader["nextSteps"][1].startswith("看什么：")
    assert reader["nextSteps"][2].startswith("下次复核什么：")


def test_reader_v3_humanizes_subject_coverage_limitation():
    from src.report_artifact import _build_reader_v3

    reader = _build_reader_v3(
        run_date="2026-07-10",
        reader_brief={},
        department_reports=[],
        department_inputs=[],
        evidence_items=[],
        source_health_v2={
            "overallMode": "LIMITED_REVIEW",
            "overallScore": 0.8,
            "blockingReasons": ["fundamentals:subject_coverage_incomplete"],
        },
        evidence_stats={"missingCriticalFacts": 0},
        decision={"action": "watch", "gateStatus": "watch"},
    )

    limitation = reader["hero"]["maxLimitation"]
    assert "结构化基本面" in limitation
    assert "subject_coverage_incomplete" not in limitation


def test_reader_v3_exposes_multi_market_coverage_in_reader_language():
    from src.report_artifact import _reader_market_coverage

    coverage = _reader_market_coverage({
        "subjectSymbols": ["600519", "000001", "HK00700", "AAPL", "MSFT"],
    })

    assert coverage == "覆盖范围：A股 2、港股 1、美股/ETF 2"


def test_reader_v3_humanizes_subject_fundamental_depth_limitation():
    from src.report_artifact import _build_reader_v3

    reader = _build_reader_v3(
        run_date="2026-07-10",
        reader_brief={},
        department_reports=[],
        department_inputs=[],
        evidence_items=[],
        source_health_v2={
            "overallMode": "LIMITED_REVIEW",
            "overallScore": 0.95,
            "blockingReasons": ["fundamentals:subject_fundamental_depth_incomplete"],
        },
        evidence_stats={"missingCriticalFacts": 0},
        decision={"action": "watch", "gateStatus": "watch"},
    )

    limitation = reader["hero"]["maxLimitation"]
    assert "浅层估值" in limitation
    assert "subject_fundamental_depth_incomplete" not in limitation


def test_reader_v3_ignores_explicit_no_gap_values_and_groups_cio_steps():
    from src.report_artifact import _build_reader_v3

    reader = _build_reader_v3(
        run_date="2026-07-10",
        reader_brief={"nextSteps": ["下次复核行业资金、市场宽度和持仓快照。"]},
        department_reports=[
            {
                "agent": "CIOAgent",
                "label": "CIO",
                "readerVisible": True,
                "summaryForReader": "市场结构仍需分层判断，暂不把权重股波动外推为全市场趋势。",
                "keyClaims": ["指数和个股表现分化。"],
                "counterpoints": ["市场宽度可能继续恶化。"],
                "dataGaps": ["无", "暂无。"],
                "nextAction": {
                    "观察信号": "关注上涨家数和核心指数能否同步企稳。",
                    "风险升级触发条件": "若上涨家数显著减少，重新评估风险暴露。",
                    "禁止操作": "结构企稳前不要追涨杀跌。",
                },
                "confidence": "high",
            }
        ],
        department_inputs=[],
        evidence_items=[],
        source_health_v2={"overallMode": "FULL_REVIEW", "overallScore": 0.9, "blockingReasons": []},
        evidence_stats={"missingCriticalFacts": 0},
        decision={"action": "watch", "gateStatus": "watch"},
    )

    assert reader["evidenceSummary"]["departmentGapItems"] == 0
    assert reader["hero"]["confidence"] == "高可信"
    assert reader["nextSteps"] == [
        "不做什么：结构企稳前不要追涨杀跌",
        "看什么：关注上涨家数和核心指数能否同步企稳；若上涨家数显著减少，重新评估风险暴露",
        "下次复核什么：行业资金、市场宽度和持仓快照",
    ]


def test_reader_v3_tones_down_sensational_cio_language():
    from src.report_artifact import _product_copy

    text = _product_copy("指数崩塌与个股虚涨形成高危结构，禁止基于低估值追涨。")

    assert text == "指数大幅下跌与个股上涨持续性存疑形成高风险结构，不应仅基于低估值追涨"


def test_reader_v3_cleans_nested_numbering_and_common_filing_typo():
    from src.report_artifact import _product_copy, _split_reader_steps

    rows = _split_reader_steps({
        "看什么": "1. 监控成交额；2. 观察市场宽度；待验证情景：3. 调取最新法批公告",
    })

    assert rows == ["看什么：监控成交额；观察市场宽度"]
    assert _product_copy("调取最新法批公告") == "调取最新法披公告"


def test_reader_v3_collapses_repeated_hypothesis_marker_within_one_paragraph():
    from src.report_artifact import _product_copy

    text = _product_copy("待验证情景：指数结构分化；待验证情景：宏观传导仍需确认。")

    assert text == "情景判断：指数结构分化；宏观传导仍需确认"


def test_reader_v3_humanizes_raw_evidence_payloads():
    from src.report_artifact import _reader_v3_evidence_sample

    sample = _reader_v3_evidence_sample({
        "id": "subject:market:main_indices:2026-07-10",
        "provider": "DataFetcherManager",
        "factType": "derived_fact",
        "label": (
            "main_indices records=2; code=sh000001, name=上证指数, "
            "current=3996.16, change_pct=-1.001 | code=sz399006, "
            "name=创业板指, current=3842.73, change_pct=-4.366"
        ),
    })

    assert sample["provider"] == "原系统数据聚合"
    assert sample["label"] == "主要指数：上证指数 -1.00%、创业板指 -4.37%"
    assert "records=" not in sample["label"]
    assert "change_pct" not in sample["label"]


def test_reader_v3_uses_structured_index_measurements_when_available():
    from src.report_artifact import _reader_v3_evidence_sample

    sample = _reader_v3_evidence_sample({
        "id": "subject:market:main_indices:2026-07-15",
        "provider": "DataFetcherManager",
        "factType": "derived_fact",
        "metric": "main_indices",
        "measurements": {
            "index_sh000001_change_pct": -0.291,
            "index_sh000688_change_pct": -4.252,
            "index_sh000016_change_pct": 0.39,
        },
        "label": "main_indices records=3",
    })

    assert sample["label"] == "主要指数：上证指数 -0.29%、科创50 -4.25%、上证50 +0.39%"


def test_reader_v3_department_steps_drop_nested_numbered_lists():
    from src.report_artifact import _concise_numbered_step

    text = (
        "不做什么：1. 不要追涨。 2. 不要只看低估值。 "
        "3. 不要把单日反弹当作反转。"
    )

    assert _concise_numbered_step(text) == "不做什么：不要追涨"


def test_artifact_evidence_items_prioritize_department_references():
    from src.report_artifact import _evidence_items

    facts = [
        {
            "id": f"official:{index}",
            "domain": "filings_events",
            "fact_type": "verified_fact",
            "provider": "official",
            "value": f"公告 {index}",
        }
        for index in range(90)
    ]
    facts.append(
        {
            "id": "subject:600519:daily_data",
            "domain": "price",
            "fact_type": "derived_fact",
            "provider": "DataFetcherManager",
            "value": "OHLCV summary",
        }
    )

    items = _evidence_items(facts, preferred_ids=["subject:600519:daily_data"])

    assert items[0]["id"] == "subject:600519:daily_data"
    assert len(items) == 80


def _valid_daily_reader_artifact():
    return {
        "schemaVersion": "report_artifact_v1",
        "artifactId": "daily:2026-07-17",
        "runDate": "2026-07-17",
        "generatedAt": "2026-07-17T01:02:00Z",
        "artifactType": "daily",
        "audience": "reader",
        "title": "日报",
        "summary": {
            "oneLine": "市场偏弱",
            "keyFacts": ["指数回落"],
            "analysis": "等待验证",
            "finalConclusion": "保持观察",
            "nextSteps": ["复核市场宽度"],
        },
        "sections": [
            {"key": "source", "title": "数据源", "kind": "source"},
            {"key": "facts", "title": "事实", "kind": "facts"},
            {"key": "analysis", "title": "分析", "kind": "analysis"},
            {"key": "final", "title": "结论", "kind": "final_conclusion"},
            {"key": "next", "title": "下一步", "kind": "next_steps"},
        ],
        "provenance": {"origin": "test", "sourceFiles": [], "generatedBy": "test"},
        "publish": {},
        "quality": {"completeness": "partial", "missingFields": [], "validationErrors": []},
        "evidenceItems": [{"id": "fact:1"}],
        "departmentReports": [{"evidenceIds": ["fact:1"]}],
        "readerV3": {
            "schema": "reader_v3_v1",
            "runDate": "2026-07-17",
            "hero": {
                "action": "观察",
                "status": "多市场观察简报",
                "confidence": "中等可信",
                "oneLine": "市场偏弱",
                "maxLimitation": "覆盖有限",
                "marketStance": "A股偏弱",
                "portfolioAction": "未接入真实持仓，不生成组合动作",
                "validity": "盘前简报",
                "dataCoverage": "有限复盘",
            },
            "marketMatrix": [],
            "stockMatrix": [],
            "adjudication": {},
            "reportSections": [],
            "departmentCards": [],
            "evidenceSummary": {},
            "reliability": {
                "headlineSafe": True,
                "headlineEvidenceSupported": True,
                "headlineStatus": "supported",
            },
        },
    }


def test_daily_reader_contract_fails_closed_without_reader_v3():
    from src.report_artifact import validate_report_artifact

    artifact = _valid_daily_reader_artifact()
    artifact.pop("readerV3")

    ok, errors = validate_report_artifact(artifact)

    assert ok is False
    assert "daily reader artifact requires readerV3" in errors


def test_daily_reader_contract_rejects_missing_referenced_evidence():
    from src.report_artifact import validate_report_artifact

    artifact = _valid_daily_reader_artifact()
    artifact["departmentReports"][0]["claimEvidence"] = [
        {"evidence_ids": ["fact:missing"]},
    ]

    ok, errors = validate_report_artifact(artifact)

    assert ok is False
    assert "referenced evidence missing from evidenceItems: fact:missing" in errors


def test_daily_reader_contract_rejects_malformed_nested_reader_values():
    from src.report_artifact import validate_report_artifact

    mutations = [
        ("market row", lambda reader: reader.__setitem__("marketMatrix", [None])),
        ("department card", lambda reader: reader.__setitem__("departmentCards", [None])),
        ("reason", lambda reader: reader.__setitem__("keyReasons", [1])),
        ("headline boolean", lambda reader: reader["reliability"].__setitem__("headlineSafe", "false")),
    ]

    for label, mutate in mutations:
        artifact = deepcopy(_valid_daily_reader_artifact())
        mutate(artifact["readerV3"])

        ok, errors = validate_report_artifact(artifact)

        assert ok is False, label
        assert errors, label


def test_reader_v3_urls_are_sanitized_before_entering_public_contract():
    from src.report_artifact import _build_stock_matrix, _reader_v3_evidence_sample

    canary = "CANARY_READER_URL_SECRET_123456"
    raw_url = (
        f"https://user:{canary}@cninfo.com.cn/announcement"
        f"?lang=zh&api_key={canary}&page=2#access_token={canary}"
    )
    sample = _reader_v3_evidence_sample(
        {
            "id": "cninfo:600519:1",
            "provider": "CNINFO",
            "factType": "verified_fact",
            "sourceUrl": raw_url,
        }
    )
    stock_rows = _build_stock_matrix(
        [
            {
                "id": "cninfo:600519:1",
                "symbol": "600519",
                "domain": "filings_events",
                "fact_type": "verified_fact",
                "provider": "CNINFO",
                "source_url": raw_url,
                "value": "年度报告公告",
                "event_time": "2026-07-17T01:00:00Z",
            }
        ],
        universe={"subjectSymbols": ["600519"]},
        original_analysis_snapshot={"records": []},
    )

    assert sample["sourceUrl"] == "https://cninfo.com.cn/announcement?lang=zh&page=2"
    assert stock_rows[0]["eventUrl"] == sample["sourceUrl"]
    assert canary not in json.dumps({"sample": sample, "stocks": stock_rows})


def test_reader_source_name_requires_official_hostname_boundary():
    from src.report_artifact import _reader_source_name

    assert _reader_source_name("", "https://www.cninfo.com.cn/report") == "巨潮资讯官方公告"
    assert _reader_source_name("", "https://cninfo.evil.example/report") == "公开数据源"


def test_file_artifact_lookup_does_not_follow_path_like_ids(tmp_path):
    from api.v1.endpoints.reports import _load_file_report_artifact_by_id

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    outside = deepcopy(_valid_daily_reader_artifact())
    outside["artifactId"] = "../outside"
    (tmp_path / "outside.artifact.json").write_text(
        json.dumps(outside, ensure_ascii=False),
        encoding="utf-8",
    )

    assert _load_file_report_artifact_by_id("../outside", reports_dir=reports_dir) is None


def test_evidence_items_keeps_preferred_fundamental_history_beyond_default_limit():
    from src.report_artifact import _evidence_items

    history_id = "subject:AAPL:fundamental:history_comparison:2026-07-17"
    facts = [
        {
            "id": f"fact:{index}",
            "domain": "news_sentiment",
            "fact_type": "verified_fact",
            "provider": "fixture",
        }
        for index in range(90)
    ]
    facts.append(
        {
            "id": history_id,
            "domain": "fundamentals",
            "fact_type": "derived_fact",
            "provider": "YfinanceFundamentalAdapter",
            "metric": "fundamental_history_comparison",
        }
    )

    items = _evidence_items(facts, preferred_ids=[history_id])

    assert any(item["id"] == history_id for item in items)


def test_daily_reader_contract_allows_structural_memo_refs():
    from src.report_artifact import validate_report_artifact

    artifact = _valid_daily_reader_artifact()
    artifact["departmentReports"][0]["evidenceIds"] += [
        "memo:MacroAgent",
        "kind:portfolio_snapshot",
        "dailyUniverse",
    ]
    artifact["departmentReports"][0]["rejectedEvidenceIds"] = ["fact:rejected"]

    ok, errors = validate_report_artifact(artifact)

    assert ok is True
    assert errors == []


def test_daily_decision_without_governed_report_is_advisory_not_blocked():
    from src.report_artifact import _apply_claim_policy_to_decision, _daily_decision

    decision = _apply_claim_policy_to_decision(
        _daily_decision([]),
        {"claimPolicy": {"canActionableAdvice": True, "canPositionSizing": False}},
    )

    assert decision["gateStatus"] == "watch"
    assert decision["blockedReasons"] == []
    assert decision["advisoryCaveats"] == [
        "no_completed_governed_report",
        "position_sizing_evidence_limited",
    ]


def test_reader_without_positions_does_not_claim_a_holding_action():
    from src.report_artifact import _reader_no_portfolio_copy

    value = _reader_no_portfolio_copy({
        "summary": "维持持有观察，不宜盲目加仓。",
        "reasons": ["基本面仅支持保守持有。"],
    })

    assert value["summary"] == "维持观察，不宜盲目加仓。"
    assert value["reasons"] == ["基本面仅支持保守观察。"]


def test_premarket_timing_uses_previous_completed_market_date():
    from src.report_artifact import _reader_timing_context

    market = [{"scopeType": "market", "asOf": "2026-07-17", "scopeNote": "宽基指数样本。"}]
    timing = _reader_timing_context(
        run_date="2026-07-17",
        generated_at="2026-07-17T01:02:00Z",
        data_as_of="2026-07-17T00:00:00Z",
        market_matrix=market,
        stock_matrix=[{"asOf": "2026-07-16"}],
    )

    assert timing["sessionLabel"] == "盘前简报"
    assert timing["dataAsOf"] == "2026-07-16"
    assert market[0]["asOf"] == "2026-07-17"
    assert "最近完整交易日" in market[0]["scopeNote"]


def test_premarket_timing_preserves_each_market_and_evidence_source_date():
    from src.report_artifact import _align_reader_evidence_times, _reader_timing_context

    market = [
        {"scopeType": "market", "market": "A股", "asOf": "2026-07-17", "scopeNote": "A。"},
        {"scopeType": "market", "market": "HK", "asOf": "2026-07-16", "scopeNote": "B。"},
        {"scopeType": "market", "market": "US", "asOf": "2026-07-15", "scopeNote": "C。"},
    ]
    cards = [{
        "agent": "MarketAgent",
        "evidenceSamples": [
            {"metric": "main_indices", "market": "cn", "asOf": "2026-07-17"},
            {"metric": "main_indices", "market": "us", "asOf": "2026-07-15"},
        ],
    }]

    timing = _reader_timing_context(
        run_date="2026-07-17",
        generated_at="2026-07-17T01:02:00Z",
        data_as_of="2026-07-17T00:00:00Z",
        market_matrix=market,
        stock_matrix=[],
    )
    _align_reader_evidence_times(cards, timing)

    assert timing["dataAsOf"] == "2026-07-15"
    assert [row["asOf"] for row in market] == ["2026-07-17", "2026-07-16", "2026-07-15"]
    assert [row["asOf"] for row in cards[0]["evidenceSamples"]] == ["2026-07-17", "2026-07-15"]
    assert "各市场" in timing["validity"]


def test_reader_evidence_hides_internal_provider_names_and_raw_daily_payload():
    from src.report_artifact import _reader_v3_evidence_sample

    sample = _reader_v3_evidence_sample({
        "provider": "AlphaVantageFetcher",
        "factType": "derived_fact",
        "metric": "daily_data",
        "label": "日线数据 rows=100 latest_date=2026-07-16 00:00:00 latest_close=333.26 sma5=321.65 sma20=303.63",
        "asOf": "2026-07-16",
    })

    assert sample["sourceName"] == "Alpha Vantage 行情"
    assert "Fetcher" not in sample["provider"]
    assert "rows=" not in sample["label"]
    assert sample["label"] == "日线结构：收盘 333.26，5日线 321.65，20日线 303.63（2026-07-16）"


def test_reader_formats_fred_evidence_without_key_value_syntax():
    from src.report_artifact import _reader_evidence_label

    assert _reader_evidence_label("BAMLH0A0HYM2=2.71 @ 2026-07-15") == (
        "美国高收益债利差 2.71（2026-07-15）"
    )


def test_reader_formats_derived_macro_universe_and_watchlist_payloads():
    from src.report_artifact import _reader_evidence_label

    macro = _reader_evidence_label(
        "latest=31865.721 delta_prev_observation=443.195 history_observations=260 "
        "history_percentile_pct=100.0 series=GDP"
    )
    universe = _reader_evidence_label(
        "universe=4 positive_20d_pct=100.0; leaders=AAPL +11.37%, 600519 +4.97%; "
        "laggards=AAPL +11.37%, 600519 +4.97%"
    )
    watchlist = _reader_evidence_label("持仓/组合/watchlist symbols: 600519, AAPL")
    english_watchlist = _reader_evidence_label("portfolio/watchlist symbols: 600519, AAPL")

    assert macro == "美国名义 GDP趋势快照：最新值 31865.7，较前值 +443.195，历史分位 100%"
    assert universe == "观察池 4 只；20日上涨占比 100%；阶段领先：AAPL +11.37%, 600519 +4.97%"
    assert watchlist == "观察清单：600519, AAPL"
    assert english_watchlist == "观察清单：600519, AAPL"
    assert "=" not in macro + universe + watchlist


def test_limited_review_does_not_claim_complete_evidence_chain():
    from src.report_artifact import _reader_v3_confidence_copy

    text = _reader_v3_confidence_copy(
        "可用，含待确认情景",
        critical_gap_count=0,
        department_gap_count=2,
        analysis_mode="LIMITED_REVIEW",
    )

    assert "核心证据链完整" not in text
    assert "整体覆盖仍为有限复盘" in text


def test_premarket_reader_calibrates_today_and_missing_breadth_language():
    from src.report_artifact import _align_reader_session_language

    cards = [{
        "conclusion": "今日A股市场偏弱，市场宽度略微偏向空头。",
        "keyClaims": ["2026-07-17 A 股市场普跌。"],
        "nextActions": ["AAPL今日开盘后复核。"],
    }]

    _align_reader_session_language(cards, {"sessionLabel": "盘前简报"})

    assert "上一完整交易日A股市场" in cards[0]["conclusion"]
    assert "市场宽度数据缺失" in cards[0]["conclusion"]
    assert "上一完整交易日 A 股主要指数普遍下跌" in cards[0]["keyClaims"][0]
    assert "AAPL下一美股交易时段开盘" in cards[0]["nextActions"][0]


def test_intraday_reader_uses_explicit_report_date_and_removes_engineering_repair_copy():
    from src.report_artifact import _align_reader_session_language

    cards = [{
        "conclusion": "今日A股市场偏弱，市场宽度略微偏向空头。",
        "nextActions": ["AAPL今日开盘后复核。", "下一步需修复资金流数据接口。"],
        "dataGaps": ["概念主题排行数据源返回为空。"],
    }]

    _align_reader_session_language(cards, {
        "sessionLabel": "盘中简报",
        "reportDate": "2026-07-17",
    })

    assert cards[0]["conclusion"].startswith("2026-07-17 A股市场")
    assert "市场宽度数据缺失" in cards[0]["conclusion"]
    assert "AAPL下一美股交易时段开盘" in cards[0]["nextActions"][0]
    assert "补充资金流数据" in cards[0]["nextActions"][1]
    assert "数据源返回为空" not in cards[0]["dataGaps"][0]


def test_public_reader_keeps_raw_red_team_challenges_in_diagnostics_only():
    from src.report_artifact import _public_reader_v3_department_card, _reader_institutional_copy

    card = _public_reader_v3_department_card({
        "agent": "MarketAgent",
        "label": "市场部门",
        "challengedClaims": [{
            "claim": "AAPL 强势。",
            "status": "存在有效反证",
            "opposingScenario": "若 AAPL 的强势（range_position_pct=100）只是单股行情，则不能外推。",
            "falsifier": "标普市场宽度同步改善。",
        }],
    })
    judgment = _reader_institutional_copy(
        "采纳红队与市场部门的综合裁决：当前市场属于“结构性分化”而非“系统性破位深调”"
    )

    assert card["challengedClaims"] == []
    assert "采纳红队" not in judgment
    assert "系统性压力仍需市场宽度与流动性确认" in judgment


def test_daily_reader_validation_requires_evidence_supported_non_rejected_headline():
    from copy import deepcopy
    from src.report_artifact import validate_report_artifact

    artifact = _valid_daily_reader_artifact()
    unsupported = deepcopy(artifact)
    unsupported["readerV3"]["reliability"]["headlineEvidenceSupported"] = False
    rejected = deepcopy(artifact)
    rejected["readerV3"]["reliability"]["headlineStatus"] = "rejected"

    assert validate_report_artifact(unsupported)[0] is False
    assert validate_report_artifact(rejected)[0] is False


def test_reader_style_comparison_names_actual_fallback_benchmark():
    from src.report_artifact import _reader_cn_style_fact

    with_csi300 = _reader_cn_style_fact([{
        "market": "A股", "scopeType": "market",
        "headline": "上证指数 -1.00%、创业板指 -3.00%、科创50 -4.00%、沪深300 -2.00%",
    }])
    with_shanghai = _reader_cn_style_fact([{
        "market": "A股", "scopeType": "market",
        "headline": "上证指数 -1.00%、创业板指 -3.00%、科创50 -4.00%",
    }])
    without_benchmark = _reader_cn_style_fact([{
        "market": "A股", "scopeType": "market",
        "headline": "创业板指 -3.00%、科创50 -4.00%",
    }])

    assert "较沪深300" in with_csi300
    assert "较上证指数" in with_shanghai
    assert "分别较" not in without_benchmark


def test_reader_prefers_claim_evidence_for_department_samples():
    from src.report_artifact import _reader_v2_department_card

    card = _reader_v2_department_card(
        {
            "agent": "GeoPolicyAgent",
            "summaryForReader": "地缘事件需跟踪。",
            "claimEvidence": [{"evidence_ids": ["geo:1"]}],
            "evidenceIds": ["fred:1"],
        },
        [],
        [
            {"id": "geo:1", "value": "制裁事件", "provider": "OFAC", "factType": "verified_fact"},
            {"id": "fred:1", "value": "GDP", "provider": "FRED", "factType": "verified_fact"},
        ],
    )

    assert card["evidenceSamples"][0]["id"] == "geo:1"


def test_reader_rebinds_curated_market_and_geo_evidence_to_visible_claims():
    from src.report_artifact import _rebind_curated_reader_evidence

    cards = [
        {"agent": "MarketAgent", "evidenceIds": ["stock:aapl"], "evidenceSamples": []},
        {"agent": "GeoPolicyAgent", "evidenceIds": ["fred:gdp"], "evidenceSamples": []},
    ]
    rows = [
        {"id": "market:cn", "metric": "main_indices", "market": "cn", "provider": "DataFetcherManager", "fact_type": "derived_fact", "value": "main_indices records=1", "measurements": {"index_sh000001_change_pct": -1.0}},
        {"id": "market:hk", "metric": "main_indices", "market": "hk", "provider": "DataFetcherManager", "fact_type": "derived_fact", "value": "main_indices records=1", "measurements": {"index_hsi_change_pct": -1.2}},
        {"id": "market:us", "metric": "main_indices", "market": "us", "provider": "DataFetcherManager", "fact_type": "derived_fact", "value": "main_indices records=1", "measurements": {"index_spx_change_pct": -0.5}},
        {"id": "geo:reliefweb", "domain": "news_sentiment", "provider": "RELIEFWEB", "fact_type": "discovery", "value": "Lebanon conflict situation report", "source_url": "https://reliefweb.int/report/example"},
    ]
    items = [
        {
            "id": row["id"],
            "metric": row.get("metric", ""),
            "market": row.get("market", ""),
            "provider": row["provider"],
            "factType": row["fact_type"],
            "value": row["value"],
            "measurements": row.get("measurements", {}),
            "sourceUrl": row.get("source_url", ""),
        }
        for row in rows
    ]

    _rebind_curated_reader_evidence(cards, evidence_rows=rows, evidence_items=items)

    assert cards[0]["evidenceIds"] == ["market:cn", "market:hk", "market:us"]
    assert cards[1]["evidenceIds"] == ["geo:reliefweb"]
    assert "主要指数" in cards[0]["evidenceSamples"][0]["label"]
    assert cards[1]["evidenceSamples"][0]["sourceName"] == "ReliefWeb 人道事件"


def test_reader_curation_replaces_stale_next_action_list():
    from src.report_artifact import _curate_reader_v3_cards

    cards = [{
        "agent": "CIOAgent",
        "nextAction": "旧动作：按旧均线复核。",
        "nextActions": ["旧动作：按旧均线复核。"],
    }]

    _curate_reader_v3_cards(
        cards,
        market_matrix=[
            {"market": "A股", "scopeType": "market", "scopeLabel": "A股市场", "headline": "上证指数 -1.00%", "state": "主要指数普遍承压"},
            {"market": "HK", "scopeType": "market", "scopeLabel": "港股市场", "headline": "恒生指数 -1.00%", "state": "主要指数普遍承压"},
            {"market": "US", "scopeType": "market", "scopeLabel": "美股市场", "headline": "标普500 -1.00%", "state": "主要指数普遍承压"},
        ],
        stock_matrix=[],
        evidence_rows=[],
        has_portfolio=False,
        adjudication={"judgment": "维持谨慎", "sharedFacts": ["三地指数承压"], "strongestAlternative": "若止跌则复核"},
    )

    assert cards[0]["nextActions"] == [
        "不做什么：不把单股强势当作市场转强信号",
        "看什么：观察三地主要指数后续表现及成交是否同向确认",
        "下次复核什么：信用利差、波动率与市场级价格信号是否一致",
    ]
    assert "旧均线" not in cards[0]["nextAction"]


def test_reader_risk_card_respects_divergent_cross_market_evidence():
    from src.report_artifact import _curate_reader_v3_cards

    cards = [{"agent": "MarketAgent"}, {"agent": "RiskAgent"}]
    _curate_reader_v3_cards(
        cards,
        market_matrix=[
            {"market": "A股", "scopeType": "market", "scopeLabel": "A股市场", "headline": "上证指数 -3.05%", "state": "主要指数普遍承压"},
            {"market": "HK", "scopeType": "market", "scopeLabel": "港股市场", "headline": "恒生指数 +1.33%", "state": "主要指数偏强"},
            {"market": "US", "scopeType": "market", "scopeLabel": "美股市场", "headline": "标普500 -0.61%", "state": "主要指数普遍承压"},
        ],
        stock_matrix=[],
        evidence_rows=[],
        has_portfolio=False,
        adjudication={"why": "三地表现分化", "strongestAlternative": "若承压市场企稳则下调风险"},
    )

    market, risk = cards
    assert "同向下跌" not in market["counterpoints"][0]
    assert "跨市场表现分化" in market["counterpoints"][0]
    assert "同向承压" not in risk["conclusion"]
    assert "港股主要指数仍偏强" in risk["conclusion"]
    assert "A股、美股" in risk["conclusion"]


def test_reader_curation_uses_current_stock_geo_and_verified_event_evidence():
    from src.report_artifact import _curate_reader_v3_cards

    cards = [
        {"agent": "RedTeamAgent"},
        {"agent": "GeoPolicyAgent"},
        {"agent": "IntelAgent"},
    ]
    evidence = [
        {
            "id": "bis:arctic:1",
            "domain": "news_sentiment",
            "provider": "BIS",
            "fact_type": "discovery",
            "value": "Arctic shipping trade sanctions announced",
            "as_of": "2026-08-09",
        },
        {
            "id": "sec:MSFT:8k:1",
            "domain": "filings_events",
            "provider": "SEC_EDGAR",
            "fact_type": "verified_fact",
            "subject": "MSFT",
            "symbol": "MSFT",
            "value": "8-K quarterly event disclosure",
            "event_time": "2026-08-08",
            "as_of": "2026-08-08",
            "source_url": "https://www.sec.gov/Archives/edgar/data/789019/example.txt",
        },
        {
            "id": "provider_run:sec",
            "domain": "filings_events",
            "provider": "SEC_EDGAR",
            "fact_type": "derived_fact",
            "value": "SEC_EDGAR returned 10 records",
            "as_of": "2026-08-09",
        },
    ]

    _curate_reader_v3_cards(
        cards,
        market_matrix=[],
        stock_matrix=[
            {"symbol": "MSFT", "name": "Microsoft"},
            {"symbol": "TSLA", "name": "Tesla"},
        ],
        evidence_rows=evidence,
        has_portfolio=False,
        adjudication={},
    )

    rendered = json.dumps(cards, ensure_ascii=False)
    assert "Microsoft、Tesla" in cards[0]["conclusion"]
    assert "Arctic shipping trade sanctions announced" in cards[1]["conclusion"]
    assert "Microsoft：8-K quarterly event disclosure" in cards[2]["conclusion"]
    assert "SEC_EDGAR returned 10 records" not in rendered
    for stale_name in ("AAPL", "腾讯", "贵州茅台", "平安银行", "乌克兰", "苏丹", "也门"):
        assert stale_name not in rendered


def test_reader_final_headline_is_not_overwritten_by_rejected_raw_cio():
    from src.report_artifact import _build_reader_v3

    evidence = [
        {"id": "market:cn", "metric": "main_indices", "market": "cn", "provider": "test", "fact_type": "derived_fact", "value": "main indices", "measurements": {"index_sh000001_change_pct": -3.05}, "raw_path": "market.json", "as_of": "2099-01-02"},
        {"id": "market:hk", "metric": "main_indices", "market": "hk", "provider": "test", "fact_type": "derived_fact", "value": "main indices", "measurements": {"index_hsi_change_pct": 1.33}, "raw_path": "market.json", "as_of": "2099-01-02"},
        {"id": "market:us", "metric": "main_indices", "market": "us", "provider": "test", "fact_type": "derived_fact", "value": "main indices", "measurements": {"index_spx_change_pct": -0.61}, "raw_path": "market.json", "as_of": "2099-01-02"},
    ]
    reader = _build_reader_v3(
        run_date="2099-01-02",
        reader_brief={},
        department_reports=[],
        department_inputs=[],
        evidence_items=[
            {"id": row["id"], "metric": row["metric"], "market": row["market"], "provider": row["provider"], "factType": row["fact_type"], "value": row["value"], "measurements": row["measurements"]}
            for row in evidence
        ],
        source_health_v2={"overallMode": "FULL_REVIEW", "overallScore": 0.93},
        evidence_stats={"missingCriticalFacts": 0},
        decision={"action": "watch", "gateStatus": "watch"},
        research_reliability={
            "schema": "research_reliability_v1",
            "label": "结论不足",
            "audited": True,
            "headlineSafe": False,
            "warnings": ["原始 CIO 结论未通过"],
            "supportedClaims": 3,
            "hypothesisClaims": 1,
            "rejectedClaims": 1,
        },
        scenario_adjudication={"judgment": "市场间表现分化，维持观察。"},
        evidence_facts=evidence,
        universe={"subjectSymbols": []},
    )

    assert reader["hero"]["oneLine"] != "本轮核心裁决未通过证据相关性检查；只保留已验证事实和条件化情景。"
    assert "市场间表现分化" in reader["hero"]["oneLine"]
    assert reader["hero"]["confidence"] == "中等可信，含待验证情景"
    assert reader["reliability"]["headlineSafe"] is True


def test_final_reliability_separates_rejected_raw_cio_from_curated_reader():
    from src.report_artifact import _finalize_research_reliability

    result = _finalize_research_reliability(
        {
            "label": "结论不足",
            "headlineSafe": False,
            "hypothesisClaims": 2,
            "rejectedClaims": 1,
            "warnings": ["CIO 总结尚未通过语义可靠性检查。"],
        },
        {
            "label": "中等可信，含待验证情景",
            "headlineSafe": True,
            "headlineStatus": "supported",
        },
    )

    assert result["label"] == "中等可信，含待验证情景"
    assert result["headlineSafe"] is True
    assert result["upstreamHeadlineSafe"] is False
    assert result["upstreamLabel"] == "结论不足"
    assert "默认 Reader 已用通过核验的共同事实重建" in result["warnings"][0]


def test_final_reliability_remains_insufficient_when_reader_headline_fails():
    from src.report_artifact import _finalize_research_reliability

    result = _finalize_research_reliability(
        {"label": "较高可信", "headlineSafe": True, "warnings": []},
        {"headlineSafe": False, "headlineStatus": "rejected"},
    )

    assert result["label"] == "结论不足"
    assert result["headlineSafe"] is False
    assert result["upstreamHeadlineSafe"] is True


def test_reader_distinguishes_confirmed_empty_portfolio_from_unknown_snapshot():
    from src.report_artifact import _curate_reader_v3_cards

    confirmed = [{"agent": "PortfolioAgent"}]
    _curate_reader_v3_cards(
        confirmed,
        market_matrix=[],
        stock_matrix=[],
        evidence_rows=[],
        has_portfolio=False,
        portfolio_snapshot_available=True,
        adjudication={},
    )
    assert confirmed[0]["dataGaps"] == []
    assert "确认组合为空" in confirmed[0]["conclusion"]

    unknown = [{"agent": "PortfolioAgent"}]
    _curate_reader_v3_cards(
        unknown,
        market_matrix=[],
        stock_matrix=[],
        evidence_rows=[],
        has_portfolio=False,
        portfolio_snapshot_available=False,
        adjudication={},
    )
    assert unknown[0]["dataGaps"] == ["真实持仓快照尚未接入。"]
    assert "状态未知" in unknown[0]["keyClaims"][0]


def test_reader_strips_internal_bracket_annotations():
    from src.report_artifact import _product_copy

    assert _product_copy("持仓为空。[ kind: 持仓快照]") == "持仓为空"


def test_legacy_source_health_flags_follow_v2_claim_policy():
    from src.report_artifact import _align_legacy_source_health

    result = _align_legacy_source_health(
        {"canScore": True, "canTradeReview": True},
        {
            "overallMode": "LIMITED_REVIEW",
            "claimPolicy": {"canScore": False, "canActionableAdvice": True},
        },
    )

    assert result["canScore"] is False
    assert result["canTradeReview"] is True
    assert "有限复盘" in result["decisionImpact"]


def test_reports_api_skips_invalid_file_artifact(tmp_path):
    from api.v1.endpoints.reports import _read_file_artifact

    path = tmp_path / "broken.artifact.json"
    artifact = _valid_daily_reader_artifact()
    artifact["readerV3"]["hero"].pop("validity")
    path.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")

    assert _read_file_artifact(path) is None


def test_department_report_respects_explicit_empty_data_gaps(tmp_path):
    from src.report_artifact import _department_reports

    path = tmp_path / "agent_memos" / "2026-07-14" / "market" / "11_cio_report.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "schema": "agent_memo_v1",
        "agent": "CIOAgent",
        "summary_for_reader": "当前证据支持保持观察，并按触发条件复核市场变化。",
        "data_gaps": [],
        "missing_data": ["已被替代证据回答的旧缺口"],
    }, ensure_ascii=False), encoding="utf-8")

    rows = _department_reports(tmp_path, "2026-07-14")

    assert rows[0]["dataGaps"] == []


def test_reader_geo_discovery_deduplicates_same_topic_without_shadowing_pattern():
    from src.report_artifact import _reader_geo_discovery

    rows = _reader_geo_discovery([
        {
            "domain": "news_sentiment",
            "provider": "TAVILY",
            "value": "Ukraine conflict update — search result",
            "as_of": "2026-07-17T09:00:00Z",
        },
        {
            "domain": "news_sentiment",
            "provider": "RELIEFWEB",
            "value": "Ukraine conflict update — official situation report",
            "as_of": "2026-07-17T08:00:00Z",
        },
    ])

    assert rows == ["事件线索：Ukraine conflict update — official situation report"]


def test_reader_card_curation_replaces_raw_cross_scope_and_portfolio_actions():
    from src.report_artifact import _curate_reader_v3_cards

    cards = [
        {
            "agent": "RiskAgent",
            "counterpoints": ["腾讯位于20日区间28%位置"],
            "nextAction": "立即调低整体仓位",
        },
        {
            "agent": "PortfolioAgent",
            "counterpoints": ["腾讯位于20日区间28%位置"],
            "nextAction": "立即调低整体仓位",
        },
        {
            "agent": "SectorAgent",
            "counterpoints": ["腾讯位于20日区间28%位置"],
            "nextAction": "是否会成交量是否放大",
        },
        {
            "agent": "RedTeamAgent",
            "counterpoints": ["GDP 31865.721，因此加仓"],
            "nextAction": "立即调低整体仓位",
        },
    ]
    adjudication = {
        "why": "A股主要指数普遍承压。",
        "strongestAlternative": "若市场宽度修复，判断需要下调。",
    }

    _curate_reader_v3_cards(
        cards,
        market_matrix=[],
        stock_matrix=[],
        evidence_rows=[],
        has_portfolio=False,
        portfolio_snapshot_available=True,
        adjudication=adjudication,
    )

    rendered = json.dumps(cards, ensure_ascii=False)
    assert "20日区间28%" not in rendered
    assert "GDP 31865.721" not in rendered
    assert "立即调低整体仓位" not in rendered
    assert "是否会成交量是否" not in rendered
    assert cards[1]["dataGaps"] == []


def test_reader_market_matrix_uses_market_level_us_and_hk_indices_before_stock_samples():
    from src.report_artifact import _build_market_matrix, _reader_scope_adjudication

    evidence = [
        {
            "id": "cn",
            "metric": "main_indices",
            "market": "cn",
            "measurements": {"index_sh000001_change_pct": -1.0, "index_sz399006_change_pct": -2.0},
            "as_of": "2026-07-17",
        },
        {
            "id": "hk",
            "metric": "main_indices",
            "market": "hk",
            "measurements": {"index_hsi_change_pct": -1.2, "index_hscei_change_pct": -1.4},
            "as_of": "2026-07-17",
        },
        {
            "id": "us",
            "metric": "main_indices",
            "market": "us",
            "measurements": {"index_spx_change_pct": -0.5, "index_ixic_change_pct": -1.5},
            "as_of": "2026-07-16",
        },
    ]
    stock_matrix = [
        {"market": "HK", "name": "腾讯控股", "return1dPct": 2.1, "evidenceIds": ["tencent"]},
        {"market": "US", "name": "Apple", "return1dPct": 1.7, "evidenceIds": ["apple"]},
    ]

    matrix = _build_market_matrix(evidence, stock_matrix)
    adjudication = _reader_scope_adjudication({}, market_matrix=matrix)

    assert [row["scopeType"] for row in matrix] == ["market", "market", "market"]
    assert [row["market"] for row in matrix] == ["A股", "HK", "US"]
    assert "恒生指数 -1.20%" in matrix[1]["headline"]
    assert "标普500 -0.50%" in matrix[2]["headline"]
    assert "跨市场主要指数同步承压" in adjudication["judgment"]
    assert "腾讯控股" not in adjudication["sharedFacts"][1]


def test_reader_market_matrix_maps_jp_kr_tw_without_falling_back_to_cn():
    from src.report_artifact import _build_market_matrix

    matrix = _build_market_matrix([
        {
            "id": "jp",
            "metric": "main_indices",
            "market": "jp",
            "measurements": {"index_n225_change_pct": 1.2, "index_topx_change_pct": 0.8},
            "as_of": "2026-08-07",
        },
        {
            "id": "kr",
            "metric": "main_indices",
            "market": "kr",
            "measurements": {"index_ks11_change_pct": -1.1, "index_kq11_change_pct": -1.5},
            "as_of": "2026-08-07",
        },
        {
            "id": "tw",
            "metric": "main_indices",
            "market": "tw",
            "measurements": {"index_twii_change_pct": 0.4, "index_twoii_change_pct": -0.2},
            "as_of": "2026-08-07",
        },
        {
            "id": "unknown",
            "metric": "main_indices",
            "market": "unknown",
            "measurements": {"index_unknown_change_pct": -3.0},
            "as_of": "2026-08-07",
        },
    ], [])

    assert [row["market"] for row in matrix] == ["JP", "KR", "TW"]
    assert [row["scopeLabel"] for row in matrix] == ["日本市场", "韩国市场", "台湾市场"]
    assert "日经225 +1.20%" in matrix[0]["headline"]
    assert "KOSPI -1.10%" in matrix[1]["headline"]
    assert "台湾加权指数 +0.40%" in matrix[2]["headline"]
    assert all(row["market"] != "A股" for row in matrix)


def test_reader_market_matrix_marks_isolated_zero_change_as_pending_verification():
    from src.report_artifact import _build_market_matrix

    matrix = _build_market_matrix([{
        "id": "hk",
        "metric": "main_indices",
        "market": "hk",
        "measurements": {
            "index_hsi_change_pct": -1.66,
            "index_hstech_change_pct": 0.0,
            "index_hscei_change_pct": -2.12,
        },
        "as_of": "2026-07-17",
    }], [])

    assert "恒生科技指数 涨跌待核验" in matrix[0]["headline"]
    assert "恒生科技指数 0.00%" not in matrix[0]["headline"]


def test_reader_cn_style_fact_reports_percentage_point_gaps_not_benchmark_decline():
    from src.report_artifact import _reader_cn_style_fact

    value = _reader_cn_style_fact([{
        "market": "A股",
        "scopeType": "market",
        "headline": "上证指数 -1.73%、创业板指 -4.66%、科创50 -3.51%、沪深300 -2.61%",
    }])

    assert "2.05" in value
    assert "0.90" in value
    assert "多跌 2.61" not in value


def test_reader_valuation_uses_generic_online_history_before_local_samples():
    from src.report_artifact import _reader_valuation_summary

    text = _reader_valuation_summary(
        {
            "trailing_pe": 18.94,
            "price_to_book": 5.78,
            "pe_history_percentile": 3.47,
            "pb_history_percentile": 2.74,
            "pe_history_sample_count": 1096,
            "pb_history_sample_count": 1096,
            "valuation_percentile_eligible": 1,
        },
        {},
    )

    assert "PE(TTM) 18.94" in text
    assert "近三年公开序列 1096 期" in text
    assert "PE 3.5% 分位" in text
    assert "PB 2.7% 分位" in text
    assert "历史分位样本不足" not in text


def test_fundamental_card_does_not_mark_online_valuation_history_as_missing():
    from src.report_artifact import _curate_reader_v3_cards

    cards = [{"agent": "FundamentalAgent"}]
    stock_matrix = [
        {"symbol": "600519", "name": "贵州茅台", "fundamental": "净利同比 10%", "valuation": "PE 18.94"},
        {"symbol": "AAPL", "name": "Apple", "fundamental": "营收同比 5%", "valuation": "PE 40.17"},
    ]
    evidence = [
        {
            "symbol": "600519",
            "metric": "fundamental_valuation",
            "measurements": {"valuation_percentile_eligible": 1},
        },
        {"symbol": "600519", "metric": "fundamental_history_comparison", "measurements": {"a": 1, "b": 2}},
        {"symbol": "AAPL", "metric": "fundamental_history_comparison", "measurements": {"a": 1, "b": 2}},
    ]

    _curate_reader_v3_cards(
        cards,
        market_matrix=[],
        stock_matrix=stock_matrix,
        evidence_rows=evidence,
        has_portfolio=False,
        portfolio_snapshot_available=True,
        adjudication={},
    )

    gaps = " ".join(cards[0]["dataGaps"])
    assert "Apple" in gaps
    assert "贵州茅台" not in gaps


def test_reader_v3_valuation_evidence_uses_product_copy():
    from src.report_artifact import _reader_v3_evidence_sample

    row = _reader_v3_evidence_sample({
        "id": "valuation",
        "metric": "fundamental_valuation",
        "label": "valuation available: trailing_pe=18.94, price_to_book=5.78",
        "measurements": {"trailing_pe": 18.94, "price_to_book": 5.78},
        "factType": "derived_fact",
    })

    assert row["label"].startswith("PE(TTM) 18.94，PB 5.78")
    assert "valuation available" not in row["label"]


def test_reader_portfolio_snapshot_label_is_human_readable():
    from src.report_artifact import _reader_evidence_label

    assert _reader_evidence_label(
        "portfolio_snapshot_status=not_connected holdings=0 watchlist=4"
    ) == "真实持仓快照未接入；观察清单 4 只"
