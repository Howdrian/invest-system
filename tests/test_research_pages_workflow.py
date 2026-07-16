"""Static contract checks for the research report cloud workflow."""

from pathlib import Path


WORKFLOW = Path(".github/workflows/00-daily-analysis.yml").read_text(encoding="utf-8")


def _report_step() -> str:
    start = WORKFLOW.index("- name: 生成静态报告中心")
    end = WORKFLOW.index("- name: 上传分析报告", start)
    return WORKFLOW[start:end]


def test_report_step_receives_daily_universe_data_and_llm_config() -> None:
    step = _report_step()
    for required in (
        "STOCK_LIST:",
        "PORTFOLIO_HOLDINGS:",
        "TUSHARE_TOKEN:",
        "FRED_API_KEY:",
        "SEC_USER_AGENT:",
        "TAVILY_API_KEY:",
        "RELIEFWEB_APPNAME:",
        "GEMINI_API_KEY:",
        "LITELLM_MODEL:",
        "RESEARCH_AGENT_RUNTIME:",
    ):
        assert required in step


def test_report_step_fails_closed_on_agent_or_semantic_failure() -> None:
    step = _report_step()
    runner = Path("scripts/run_research_daily_local.sh").read_text(encoding="utf-8")
    assert "RESEARCH_AGENT_RUNTIME:-auto" not in step
    assert "RESEARCH_AGENT_RUNTIME || 'llm'" in step
    assert 'summary.get("allLlmSucceeded") is True' in step
    assert 'summary.get("fallbackCount")' in step
    assert "audit_semantic_quality.py" in runner
    assert "--fail-on-error" in runner
    assert "set -euo pipefail" in runner
    assert "|| true" not in step


def test_report_step_refreshes_only_required_fred_data_before_publish() -> None:
    step = _report_step()
    runner = Path("scripts/run_research_daily_local.sh").read_text(encoding="utf-8")
    assert "run_research_daily_local.sh" in step
    assert "src.macro.official_sources --refresh --fred-only" in runner
    assert runner.index("src.macro.official_sources --refresh --fred-only") < runner.index("run_daily_department_agents.py")
    assert runner.index("render_homepage.py") < runner.index("validate_pages_bundle.py")
    assert step.index("run_research_daily_local.sh") < step.index("publish_pages_bundle.py")


def test_report_step_uses_single_orchestrator_without_derived_memo_prefill() -> None:
    step = _report_step()
    runner = Path("scripts/run_research_daily_local.sh").read_text(encoding="utf-8")
    assert "collect_intelligence_evidence.py" in runner
    assert "src/agent_memos.py" not in step
    assert "render_report_html.py" not in step
    assert step.count("run_research_daily_local.sh") == 1


def test_pages_artifact_and_deploy_jobs_are_present() -> None:
    assert "actions/upload-pages-artifact@v4" in WORKFLOW
    assert "actions/deploy-pages@v4" in WORKFLOW
    assert "needs.analyze.result == 'success'" in WORKFLOW
