from pathlib import Path


def test_daily_workflow_publishes_market_cycle_without_docs_index_conflict():
    workflow = Path(".github/workflows/00-daily-analysis.yml").read_text(encoding="utf-8")

    assert "python -m src.market_cycle" in workflow
    assert "reports/market_cycle/$TODAY" in workflow
    assert "docs/market_cycle/$TODAY" in workflow
    assert "docs/daily/$TODAY.md" in workflow
    assert "docs/index.md" not in workflow
    assert "macro status" in workflow.lower()
    assert "Macro context" in workflow
    assert "governed_parallel" in workflow
    assert "MARKET_HEAT_OUTPUT_DIR: ${{ vars.MARKET_HEAT_OUTPUT_DIR" in workflow
    assert "AGENT_GOVERNED_PARALLEL_MAX_WORKERS: ${{ vars.AGENT_GOVERNED_PARALLEL_MAX_WORKERS" in workflow
