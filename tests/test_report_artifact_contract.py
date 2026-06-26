from api.v1.schemas.history import AnalysisReport, ReportMeta, ReportSummary
import json


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
    from api.v1.router import router

    paths = {route.path for route in router.routes}

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


def test_daily_report_artifact_writes_source_health_and_agent_origins(tmp_path):
    from src.report_artifact import validate_report_artifact, write_daily_report_artifact

    docs = tmp_path / "docs"
    date = "2026-06-19"
    mc = docs / "market_cycle" / date
    memo = docs / "agent_memos" / date / "stocks" / "300308"
    mc.mkdir(parents=True)
    memo.mkdir(parents=True)
    (docs / "daily").mkdir(parents=True)
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
    assert artifact["agentOrigins"] == {"raw": 1, "derived": 0, "missing": 0}
    assert artifact["decision"]["score"] == 0
    assert artifact["decision"]["targetPct"] == 0
    assert artifact["decision"]["gateStatus"] == "blocked"
    ok, errors = validate_report_artifact(artifact)
    assert ok, errors


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
