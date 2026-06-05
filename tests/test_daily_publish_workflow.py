from pathlib import Path


def test_daily_workflow_publishes_market_cycle_without_docs_index_conflict():
    workflow = Path(".github/workflows/00-daily-analysis.yml").read_text(encoding="utf-8")

    assert "python -m src.market_cycle" in workflow
    assert "python -m src.prediction_market.polymarket" in workflow
    assert "reports/market_cycle/$TODAY" in workflow
    assert "docs/market_cycle/$TODAY" in workflow
    assert "docs/daily/$TODAY.md" in workflow
    assert "01_macro_review.html" in workflow
    assert "09_screening_funnel.md" in workflow
    assert "11_deep_review_queue.md" in workflow
    assert "docs/index.html" in workflow
    assert "投研日报 — $TODAY" in workflow
    assert "docs/index.md" not in workflow
    assert "macro status" in workflow.lower()
    assert "polymarket status" in workflow.lower()
    assert "Deep review candidates" in workflow
    assert "Macro context" in workflow
    assert "governed_parallel" in workflow
    assert "MARKET_HEAT_OUTPUT_DIR: ${{ vars.MARKET_HEAT_OUTPUT_DIR" in workflow
    assert "AGENT_GOVERNED_PARALLEL_MAX_WORKERS: ${{ vars.AGENT_GOVERNED_PARALLEL_MAX_WORKERS" in workflow
    assert "AGENT_GOVERNED_DAILY_LIMIT: ${{ vars.AGENT_GOVERNED_DAILY_LIMIT" in workflow
    assert "reports/run_status" in workflow
    assert "market_cycle_status.txt" in workflow
    assert "stock_analysis_status.txt" in workflow
    assert "governed_stock_list.txt" in workflow
    assert "governed_selection_reason.txt" in workflow
    assert "DEEP_REVIEW_NOW" in workflow
    assert "--stocks \"$GOVERNED_STOCK_LIST\"" in workflow

    assert workflow.index("python -m src.market_cycle") < workflow.index("python main.py --stocks")


def test_daily_workflow_does_not_touch_web_dashboard_layout():
    workflow = Path(".github/workflows/00-daily-analysis.yml").read_text(encoding="utf-8")

    assert "apps/dsa-web" not in workflow
    assert "npm run build" not in workflow
