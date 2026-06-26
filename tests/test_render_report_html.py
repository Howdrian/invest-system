import json
import subprocess
from pathlib import Path


def test_render_report_html_builds_human_report_center_and_html_pages(tmp_path, monkeypatch):
    from src import render_report_html

    docs = tmp_path / "docs"
    mc = docs / "market_cycle" / "2026-06-17"
    heat = docs / "market_heat"
    daily = docs / "daily"
    mc.mkdir(parents=True)
    heat.mkdir(parents=True)
    daily.mkdir(parents=True)

    (daily / "2026-06-17.md").write_text(
        "# 投研日报 — 2026-06-17\n\n## 运行状态\n- Market cycle: `success`\n- Governed stock analysis: `success`\n",
        encoding="utf-8",
    )
    (docs / "report_20260617.md").write_text(
        "# 个股报告\n\n| 标的 | 结论 |\n|---|---|\n| 301013 | no_action |\n",
        encoding="utf-8",
    )
    (heat / "latest_market_heat.md").write_text("# 今日关注摘要\n\n## Watchlist\n- 301013\n", encoding="utf-8")
    for name in [
        "01_macro_review",
        "09_screening_funnel",
        "11_deep_review_queue",
        "12_preliminary_deep_review",
        "13_source_health",
        "14_market_strategy",
        "summary",
    ]:
        (mc / f"{name}.md").write_text(f"# {name}\n\n- readable\n", encoding="utf-8")
    (mc / "01_macro_review.json").write_text(
        json.dumps(
            {
                "status": "DEGRADED",
                "confidence": "LOW_TO_MEDIUM",
                "headline": "宏观中性，等待价格和证据共振；VIX neutral: 16.39",
                "six_factor_regime": {
                    "risk_state": "neutral",
                    "missing_factors": ["credit_conditions", "sector_rotation"],
                },
                "data_gaps": ["macro_context_not_refreshed"],
            }
        ),
        encoding="utf-8",
    )
    (mc / "13_source_health.json").write_text(
        json.dumps(
            {
                "macro_status": "DEGRADED",
                "usability_verdict": "degraded",
                "trade_review_usability": "usable_limited",
                "rows": [{"component": "macro_context", "status": "DEGRADED"}],
            }
        ),
        encoding="utf-8",
    )
    (mc / "11_deep_review_queue.json").write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "symbol": "SZ000725",
                        "name": "京东方Ａ",
                        "source": "hot_stocks",
                        "evidence": ["hot_stock_rank"],
                        "verdict": "DEEP_REVIEW_WAIT_ENTRY",
                        "price_risk": "OVERHEATED_WAIT_ENTRY",
                        "next_action": "读公告/研报和技术承接；不追高。",
                    }
                ],
                "auto_governed_candidates": [],
            }
        ),
        encoding="utf-8",
    )
    (mc / "14_market_strategy.json").write_text(
        json.dumps(
            {
                "regime": "NEUTRAL_WATCH",
                "confidence": "MEDIUM",
                "strategy": {
                    "headline": "宏观中性；维持观察，等待价格和证据共振。",
                    "actions": ["把热度和宏观作为候选发现，不直接触发交易"],
                    "avoid": ["只因热度高就追买"],
                },
            }
        ),
        encoding="utf-8",
    )
    (docs / "governed_results.json").write_text(
        json.dumps(
            [
                {
                    "run_date": "2026-06-17",
                    "code": "301013",
                    "name": "利和兴",
                    "cio_status": "BLOCKED_BY_FATAL",
                    "score": 0.5,
                    "headline": "技术严重超买且基本面亏损",
                    "trade_plan": {"action": "no_action", "target_pct": 0},
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    render_report_html.main(["--date", "2026-06-17", "--docs-dir", "docs"])

    center = docs / "reports" / "2026-06-17.html"
    assert center.exists()
    artifact_json = docs / "reports" / "2026-06-17.artifact.json"
    assert artifact_json.exists()
    artifact = json.loads(artifact_json.read_text(encoding="utf-8"))
    assert artifact["artifactType"] == "daily"
    assert artifact["sourceHealth"]["decisionImpact"] == "数据源降级，可观察，不可作为满血交易依据"
    center_html = center.read_text(encoding="utf-8")
    assert "统一 ReportArtifact 报告入口" in center_html
    assert "标准报告数据包" in center_html
    assert "数据源" in center_html
    assert "关键数据" in center_html
    assert "推论" in center_html
    assert "总结论" in center_html
    assert "下一步" in center_html
    assert "Agent 来源" in center_html
    assert "证据链" in center_html
    assert "原始报告（审计原文）" not in center_html
    assert "原始审计" not in center_html
    assert "N/A" not in center_html
    assert "云端报告" in center_html
    assert "Pages 不展示本地 live 目录" in center_html
    assert "静态 Pages Dashboard" not in center_html
    assert "展示系统" not in center_html
    assert "欠缺 / 低效" not in center_html
    assert "宏观降级" in center_html
    assert "report_20260617.html" in center_html
    assert "301013" in center_html
    assert "governed_results.json" in center_html
    assert "机器可读" in center_html
    assert "一页读懂" in center_html
    assert "宏观只可背景参考，不是满血 regime" in center_html
    assert "信息源" in center_html
    assert "关键数据" in center_html
    assert "推论" in center_html
    assert "分析结论" in center_html
    assert "下一步" in center_html
    assert "VIX neutral: 16.39" in center_html
    assert "京东方Ａ" in center_html
    assert "热榜只能做发现，不能做交易理由" in center_html
    assert "0.5/10" in center_html
    assert "阻断 / 不操作 / 0%" in center_html
    assert "评分 50" not in center_html
    assert "no_action" not in center_html
    assert "BLOCKED_BY_FATAL" not in center_html

    assert (daily / "2026-06-17.html").exists()
    assert (mc / "summary.html").exists()
    stock_html = (docs / "report_20260617.html").read_text(encoding="utf-8")
    assert "阅读摘要" in stock_html
    assert "查看模块正文" in stock_html
    assert "原始报告（审计原文）" not in stock_html
    assert "信息源" in stock_html
    assert "no_action" not in stock_html
    assert "BLOCKED_BY_FATAL" not in stock_html
    assert "RAW_AGENT" not in center_html
    assert "阻断 / 不操作 / 0%" in stock_html
    assert "0.5/10" in stock_html
    assert "评分 50" not in stock_html
    assert "<table>" in stock_html
    assert "301013" in stock_html
    macro_html = (mc / "01_macro_review.html").read_text(encoding="utf-8")
    assert "阅读摘要" in macro_html
    assert "宏观不满血" in macro_html
    assert (heat / "latest_market_heat.html").exists()


def test_daily_workflow_generates_html_report_center():
    workflow = Path(".github/workflows/00-daily-analysis.yml").read_text(encoding="utf-8")

    assert "python src/agent_memos.py" in workflow
    assert "docs/agent_memos/$TODAY" in workflow
    assert "rm -rf \"docs/daily/$TODAY\"" in workflow
    assert "cp -r \"reports/daily/$TODAY\"/* \"docs/daily/$TODAY\"/" not in workflow
    assert "docs/reports/$TODAY.artifact.json" in workflow
    assert "python src/render_report_html.py" in workflow
    assert "docs/reports/$TODAY.html" in workflow
    assert "report_${TODAY_COMPACT}.html" in workflow


def test_report_center_includes_agent_memo_dashboard_sections(tmp_path, monkeypatch):
    from src import render_report_html

    docs = tmp_path / "docs"
    base = docs / "agent_memos" / "2026-06-17"
    for rel in [
        "market/01_source_review.md",
        "market/02_macro_geopolitics.md",
        "market/03_market_strategy.md",
        "market/04_candidate_review.md",
        "market/05_portfolio_review.md",
        "sources/00_source_inventory.md",
        "sources/01_source_gap_plan.md",
        "stocks/301013/11_decision_report.md",
    ]:
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# memo\n\n事实 → 推理 → 结论\n", encoding="utf-8")
    (docs / "market_cycle" / "2026-06-17").mkdir(parents=True)
    (docs / "daily").mkdir()
    (docs / "daily" / "2026-06-17.md").write_text("# daily\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    render_report_html.main(["--date", "2026-06-17", "--docs-dir", "docs"])

    center_html = (docs / "reports" / "2026-06-17.html").read_text(encoding="utf-8")
    assert "统一 ReportArtifact 报告入口" in center_html
    assert "数据源" in center_html
    assert "关键数据" in center_html
    assert "推论" in center_html
    assert "总结论" in center_html
    assert "下一步" in center_html
    assert "Agent 来源" in center_html
    assert "证据链" in center_html
    assert "../agent_memos/2026-06-17/market/01_source_review.html" in center_html


def test_render_agent_memo_html_hides_engineering_fields_in_main_reading(tmp_path, monkeypatch):
    from src import render_report_html

    docs = tmp_path / "docs"
    memo = docs / "agent_memos" / "2026-06-17" / "market" / "01_source_review.md"
    memo.parent.mkdir(parents=True, exist_ok=True)
    memo.write_text(
        "# SourceReviewAgent — market\n\n"
        "## 一句话结论\n回填审计：本轮源状态可读但需降权。\n\n"
        "## 我看了什么\n- 源健康 JSON\n\n"
        "## 关键证据\n- 宏观源 DEGRADED\n\n"
        "## 审计详情\n- schema=agent_memo_v1\n",
        encoding="utf-8",
    )
    (docs / "market_cycle" / "2026-06-17").mkdir(parents=True)
    (docs / "daily").mkdir()
    (docs / "daily" / "2026-06-17.md").write_text("# daily\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    render_report_html.main(["--date", "2026-06-17", "--docs-dir", "docs"])

    html = (docs / "agent_memos" / "2026-06-17" / "market" / "01_source_review.html").read_text(
        encoding="utf-8"
    )
    assert "一句话结论" in html
    assert "审计详情" in html
    assert "Schema:" not in html
    assert "fatal_objection" not in html


def test_markdown_inline_markup_is_rendered_as_html():
    from src import render_report_html

    html = render_report_html.markdown_to_html("**结论**：看 `CIO`，详见 [日报](daily/2026-06-17.html)")

    assert "<strong>结论</strong>" in html
    assert "<code>CIO</code>" in html
    assert '<a href="daily/2026-06-17.html">日报</a>' in html


def test_report_center_path_is_not_gitignored():
    result = subprocess.run(
        ["git", "check-ignore", "-q", "docs/reports/2026-06-17.html"],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
    )

    assert result.returncode != 0


def test_blocked_stock_report_sanitizes_trade_action_phrases(tmp_path, monkeypatch):
    from src import render_report_html

    docs = tmp_path / "docs"
    date = "2026-06-19"
    compact = date.replace("-", "")
    (docs / "daily").mkdir(parents=True)
    (docs / "daily" / f"{date}.md").write_text("# daily", encoding="utf-8")
    (docs / f"report_{compact}.md").write_text(
        "# 个股报告\n\n**⛔ 阻断 / 不操作 / 0%**\n\n"
        "技术面出现强烈买入信号。\n\n"
        "operation_advice={has_position: 建议立即减仓或清仓止损}\n\n"
        "BLOCKED_BY_FATAL no_action",
        encoding="utf-8",
    )
    (docs / "governed_results.json").write_text(
        json.dumps([{
            "run_date": date,
            "code": "300308",
            "name": "中际旭创",
            "cio_status": "BLOCKED_BY_FATAL",
            "gate": "BLOCKED",
            "score": 0.5,
            "trade_plan": {"action": "no_action", "target_pct": 0},
        }], ensure_ascii=False),
        encoding="utf-8",
    )
    (docs / "market_cycle" / date).mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    render_report_html.main(["--date", date, "--docs-dir", "docs"])

    html = (docs / f"report_{compact}.html").read_text(encoding="utf-8")
    assert (docs / "reports" / f"{date}.artifact.json").exists()
    assert "强烈买入信号" not in html
    assert "立即减仓" not in html
    assert "清仓" not in html
    assert "止损" not in html
    assert "BLOCKED_BY_FATAL" not in html
    assert "no_action" not in html
    assert "阻断 / 不操作 / 0%" in html
