from api.v1.schemas.history import AnalysisReport, ReportMeta, ReportSummary
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
    assert artifact["sourceHealth"]["decisionImpact"] == "数据源降级，可观察，不可作为满血交易依据"
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
    artifact = {
        "schemaVersion": "report_artifact_v1",
        "artifactId": "daily:2026-06-19",
        "runDate": "2026-06-19",
        "generatedAt": "2026-06-19T08:00:00Z",
        "artifactType": "daily",
        "audience": "reader",
        "title": "静态日报",
        "summary": {
            "oneLine": "静态日报优先",
            "keyFacts": ["事实"],
            "analysis": "推论",
            "finalConclusion": "结论",
            "nextSteps": ["下一步"],
        },
        "sections": [
            {"key": "source", "title": "数据源", "kind": "source", "contentMarkdown": "DB"},
            {"key": "facts", "title": "关键数据", "kind": "facts", "contentMarkdown": "事实"},
            {"key": "analysis", "title": "推论", "kind": "analysis", "contentMarkdown": "分析"},
            {"key": "final", "title": "总结论", "kind": "final_conclusion", "contentMarkdown": "结论"},
            {"key": "next", "title": "下一步", "kind": "next_steps", "contentMarkdown": "复核"},
        ],
        "provenance": {"origin": "invest-system.static", "sourceFiles": [], "generatedBy": "test"},
        "publish": {},
        "quality": {"completeness": "complete", "missingFields": [], "validationErrors": []},
    }
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
    assert artifact["readerBrief"]["finalConclusion"] == "市场层面等待价格和证据共振。"


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
