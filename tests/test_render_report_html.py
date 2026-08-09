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
    assert artifact["quality"]["completeness"] == "partial"
    assert artifact["sourceHealth"]["decisionImpact"] == "可形成有限复盘；细分结论需结合待确认项。"
    center_html = center.read_text(encoding="utf-8")
    assert "今日总判断" in center_html
    assert "报告阅读入口" not in center_html
    assert "多市场观察简报" in center_html
    assert '<span class="pill">投研日报</span>' not in center_html
    assert "<small>本轮状态</small>" not in center_html
    assert "部门研究摘要" in center_html
    assert "分部门分析" not in center_html
    assert "部门卷宗" not in center_html
    assert "各板块结论与下一步" not in center_html
    assert "核心理由" in center_html
    assert "研究边界" in center_html
    assert "下一步" in center_html
    assert center_html.count(">Diagnostics</a>") == 0
    assert "ReportArtifact" not in center_html
    assert "sourceHealthV2" not in center_html
    assert "providerMatrix" not in center_html
    assert "claimPolicy" not in center_html
    assert "artifactId" not in center_html
    assert "原始报告（审计原文）" not in center_html
    assert "原始审计" not in center_html
    assert "N/A" not in center_html
    assert "云端报告" not in center_html
    assert "Pages 不展示本地 live 目录" not in center_html
    assert "静态 Pages Dashboard" not in center_html
    assert "展示系统" not in center_html
    assert "欠缺 / 低效" not in center_html
    assert "301013" in center_html
    assert "governed_results.json" not in center_html
    assert "机器可读" not in center_html
    assert "一页读懂" not in center_html
    assert "../reports/2026-06-17/macro.html" in center_html
    assert "数据修复" not in center_html
    assert "关键数据缺失" not in center_html
    assert "分报告下钻" in center_html
    assert "下一步" in center_html
    assert "评分 50" not in center_html
    assert "no_action" not in center_html
    assert "BLOCKED_BY_FATAL" not in center_html
    diagnostics_html = (docs / "reports" / "2026-06-17.diagnostics.html").read_text(encoding="utf-8")
    assert "高级诊断" in diagnostics_html
    assert "Provider Matrix" in diagnostics_html
    assert "Run Matrix" in diagnostics_html

    assert (daily / "2026-06-17.html").exists()
    assert (mc / "summary.html").exists()
    stock_html = (docs / "report_20260617.html").read_text(encoding="utf-8")
    assert "个股投研结论" in stock_html
    assert "查看分析记录" in stock_html
    assert "原始报告（审计原文）" not in stock_html
    assert "信息源" in stock_html
    assert "no_action" not in stock_html
    assert "BLOCKED_BY_FATAL" not in stock_html
    assert "score=" not in stock_html
    assert "target_pct" not in stock_html
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
    for slug in ["macro", "market", "sectors", "candidates", "news", "stocks", "portfolio", "risk"]:
        section_html = (docs / "reports" / "2026-06-17" / f"{slug}.html").read_text(encoding="utf-8")
        assert "本环节结论" in section_html
        assert "分析结论" in section_html
        assert "核心依据" in section_html
        assert "风险和反证" in section_html
        assert "下一步" in section_html
        assert "证据与来源" in section_html
        assert "本页怎么读" not in section_html
        assert "原始阅读页" not in section_html


def test_report_center_keeps_one_collapsed_department_summary_and_one_diagnostics_link(tmp_path):
    from src.render_report_html import build_report_center

    docs = tmp_path / "docs"
    artifact = {
        "runDate": "2026-07-10",
        "readerV3": {
            "timing": {
                "reportDate": "2026-07-10",
                "dataAsOf": "2026-07-10T02:30:00Z",
                "generatedAt": "2026-07-10T02:37:45Z",
            },
            "hero": {
                "action": "观察",
                "status": "完整复盘",
                "confidence": "可用，含待确认情景",
                "oneLine": "市场处于观察窗口。",
                "maxLimitation": "仍需人工复核。",
                "marketStance": "A 股偏弱，海外样本仅作观察。",
                "portfolioAction": "保持防御，不新增风险暴露。",
                "validity": "下一交易日开盘前有效。",
                "dataCoverage": "A股核心指数 + 4 个跨市场样本。",
            },
            "keyReasons": ["市场宽度尚未确认。"],
            "counterpoints": ["若成交恢复，结论需要重评。"],
            "nextSteps": ["继续观察。"],
            "marketMatrix": [
                {
                    "market": "US",
                    "scopeLabel": "美股观察样本",
                    "scopeType": "sample",
                    "state": "观察样本走强",
                    "headline": "Apple +1.76%（1日）",
                    "scopeNote": "仅代表本轮观察标的，不代表美股整体。",
                }
            ],
            "stockMatrix": [
                {
                    "symbol": "AAPL",
                    "name": "Apple Inc.",
                    "lastPrice": 333.26,
                    "currency": "USD",
                    "return1dPct": 1.76,
                    "return20dPct": 11.37,
                    "trend": "短中期趋势向上",
                    "fundamental": "营收同比 +16.60%",
                    "valuation": "PE(TTM) 31.20；历史分位样本不足",
                    "latestEvent": "SEC 10-Q",
                    "eventDate": "2026-05-01",
                    "eventUrl": "https://sec.example/aapl",
                    "stance": "趋势跟踪",
                    "watchLevels": "5日线 321.65 / 20日线 303.63",
                }
            ],
            "reportSections": [
                {"key": "market", "title": "市场状态", "body": "市场处于观察窗口。"},
            ],
            "departmentCards": [
                {
                    "agent": "MarketAgent",
                    "label": "市场部门",
                    "conclusion": "市场处于观察窗口。",
                    "keyClaims": ["市场宽度尚未确认。"],
                    "counterpoints": ["成交恢复会改变判断。"],
                    "challengedClaims": [
                        {
                            "claim": "当前反弹必然延续。",
                            "status": "存在有效反证，未作为确定依据",
                            "opposingScenario": "若成交继续萎缩，反弹可能失败。",
                            "falsifier": "成交量连续回到均值上方。",
                        }
                    ],
                    "nextAction": "继续观察。",
                    "evidenceSamples": [
                        {
                            "label": "rows=12; symbol=AAPL; close=333.26; raw_payload=hidden",
                            "provider": "InternalQuoteProvider",
                            "factType": "verified_fact",
                            "publishedAt": "2026-07-10T02:00:00Z",
                            "sourceUrl": "https://www.sec.gov/Archives/example",
                        }
                    ],
                },
                {
                    "agent": "FundamentalAgent",
                    "conclusion": "originalAnalysisRefs 中的 portfolio_snapshot 尚未提供完整持仓。",
                    "keyClaims": ["sector_rankings 与 hot_stocks 只支持观察。"],
                    "nextAction": "补 quantity、market_value 与 cost_basis 后复核。",
                },
            ],
            "evidenceSummary": {
                "verifiedFacts": 3,
                "derivedFacts": 2,
                "discoveryItems": 1,
                "missingCriticalFacts": 0,
                "departmentGapItems": 1,
            },
        },
        "evidenceItems": [],
        "sourceHealthV2": {"overallMode": "FULL_REVIEW", "overallScore": 0.9},
    }

    html = build_report_center(docs, "2026-07-10", [], artifact=artifact)

    assert "综合数据截至 2026-07-10 10:30（北京时间）" in html
    assert "生成于 10:37" in html
    assert "2026-07-10T02:30:00Z" not in html
    assert "部门研究摘要" in html
    assert "<details class='department-card'>" in html
    assert "-webkit-line-clamp:2" in html
    assert "<summary>" in html
    assert "市场处于观察窗口。" in html
    assert "市场范围与样本表现" in html
    assert "美股观察样本" in html
    assert "不代表美股整体" in html
    assert "重点标的跟踪" in html
    assert "Apple Inc." in html
    assert "PE(TTM) 31.20；历史分位样本不足" in html
    assert "研究立场" in html
    assert "A 股偏弱，海外样本仅作观察。" in html
    assert "组合动作" in html
    assert "保持防御，不新增风险暴露。" in html
    assert "可信度" in html
    assert "可用，含待确认情景" in html
    assert "时效" in html
    assert "下一交易日开盘前有效。" in html
    assert "覆盖" in html
    assert "A股核心指数 + 4 个跨市场样本。" in html
    assert "<div class='table-wrap reader-matrix-table'>" in html
    assert "<div class='reader-matrix-cards'>" in html
    assert "<article class='matrix-card'>" in html
    assert "<article class='matrix-card stock-matrix-card'>" in html
    assert "@media(max-width:700px){.reader-matrix-table{display:none}.reader-matrix-cards{display:grid" in html
    assert "SEC 官方披露" in html
    assert "已验证事实" in html
    assert "发布时间 2026-07-10 10:00（北京时间）" in html
    assert "href='https://www.sec.gov/Archives/example'" in html
    for eyebrow in (
        "MARKET SCOPE",
        "SECURITY MONITOR",
        "EVIDENCE",
        "CHALLENGE",
        "WATCH",
        "SCENARIO ADJUDICATION",
        "MACRO & GEOPOLITICS",
        "DEPARTMENT NOTES",
    ):
        assert f">{eyebrow}<" not in html
    assert "已识别的争议结论" in html
    assert "存在有效反证，未作为确定依据" in html
    assert "可用，含待确认情景" in html
    assert "<span>高可信</span>" not in html
    assert "分部门分析" not in html
    assert "部门卷宗" not in html
    assert "各板块结论与下一步" not in html
    assert html.count(">Diagnostics</a>") == 0
    assert ">行业 / 风格</a>" in html
    assert ">候选观察</a>" in html
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
        assert field not in html
    engineering_fields = (
        "providerMatrix",
        "sourceHealthV2",
        "claimPolicy",
        "artifactId",
        "record_count",
        "rows=",
        "raw_payload",
        "InternalQuoteProvider",
    )
    assert sum(html.count(field) for field in engineering_fields) == 0


def test_daily_workflow_generates_html_report_center_through_shared_runner():
    workflow = Path(".github/workflows/00-daily-analysis.yml").read_text(encoding="utf-8")
    runner = Path("scripts/run_research_daily_local.sh").read_text(encoding="utf-8")

    assert "scripts/run_research_daily_local.sh" in workflow
    assert "src/agent_memos.py" not in workflow
    assert "cp -r \"reports/daily/$TODAY\"/* \"docs/daily/$TODAY\"/" not in workflow
    assert "docs/reports/$TODAY.artifact.json" in workflow
    assert "scripts/write_source_health_ledgers.py" in runner
    assert "src/render_report_html.py" in runner
    assert "src/render_homepage.py" in runner
    assert "python scripts/publish_pages_bundle.py" in workflow
    assert 'SYMBOLS="${SYMBOLS:-600519,000001,AAPL,HK00700}"' not in runner
    assert "docs/reports/$TODAY.html" in workflow
    assert "report_${TODAY_COMPACT}.html" in workflow
    assert runner.index("scripts/write_source_health_ledgers.py") < runner.index("src/render_report_html.py")
    assert runner.index("src/render_homepage.py") < runner.index("scripts/validate_pages_bundle.py")
    assert workflow.index("scripts/run_research_daily_local.sh") < workflow.index("python scripts/publish_pages_bundle.py")


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
    assert "今日总判断" in center_html
    assert "报告阅读入口" not in center_html
    assert "ReportArtifact" not in center_html
    assert "sourceHealthV2" not in center_html
    assert "providerMatrix" not in center_html
    assert "claimPolicy" not in center_html
    assert "核心理由" in center_html
    assert "多市场观察简报" in center_html
    assert "下一步" in center_html
    assert "分报告下钻" in center_html
    assert "../reports/2026-06-17/macro.html" in center_html
    assert center_html.count(">Diagnostics</a>") == 0


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


def test_render_markdown_file_does_not_rewrite_source_markdown(tmp_path):
    from src.render_report_html import render_markdown_file

    source = tmp_path / "report_20260619.md"
    source.write_text("# Report\n\n| 标的 | 动作 |\n|---|---|\n| 300308 | no_action |\n", encoding="utf-8")
    before = source.read_text(encoding="utf-8")

    assert render_markdown_file(source, tmp_path / "report.html", "Report") is True

    assert source.read_text(encoding="utf-8") == before
    assert "no_action" not in (tmp_path / "report.html").read_text(encoding="utf-8")


def test_markdown_inline_markup_is_rendered_as_html():
    from src import render_report_html

    html = render_report_html.markdown_to_html(
        "**结论**：看 `CIO`，详见 [日报](daily/2026-06-17.html)\n\n1. 先看源健康"
    )

    assert "<strong>结论</strong>" in html
    assert "<code>CIO</code>" in html
    assert '<a href="daily/2026-06-17.html">日报</a>' in html
    assert "<li>先看源健康</li>" in html


def test_markdown_tables_scroll_inside_the_report_instead_of_widening_the_page():
    from src import render_report_html

    html = render_report_html.markdown_to_html(
        "| 超长标题 | 结论 |\n|---|---|\n| uninterrupted_identifier_that_must_not_widen_the_page | 观察 |"
    )

    assert '<div class="table-wrap" role="region" tabindex="0">' in html
    assert "</table></div>" in html


def test_agent_memos_do_not_import_report_html_cli():
    source = Path("src/agent_memos.py").read_text(encoding="utf-8")

    assert "from src.render_report_html import" not in source


def test_ci_syntax_gate_compileall_covers_report_renderer():
    script = Path("scripts/ci_gate.sh").read_text(encoding="utf-8")

    assert "compileall -q main.py server.py api bot data_provider scripts src" in script


def test_generated_report_center_path_is_gitignored():
    result = subprocess.run(
        ["git", "check-ignore", "-q", "docs/reports/2026-06-17.html"],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
    )

    assert result.returncode == 0


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
    assert "个股投研结论" in html
    assert "查看分析记录" in html
    assert "强烈买入信号" not in html
    assert "立即减仓" not in html
    assert "清仓" not in html
    assert "止损" not in html
    assert "BLOCKED_BY_FATAL" not in html
    assert "score=" not in html
    assert "target_pct" not in html
    assert "no_action" not in html
    assert "阻断 / 不操作 / 0%" in html


def test_department_decision_card_does_not_repeat_identical_conclusion_as_inference():
    from src.render_report_html import _department_decision_card

    html = _department_decision_card(
        {
            "status": "部门 Agent 已完成",
            "source": "同一份报告数据",
            "conclusion": "地缘风险需要继续跟踪。",
            "inference": "地缘风险需要继续跟踪。",
            "reasons": ["存在最新事件线索。"],
            "risks": ["线索尚待官方核验。"],
            "next_steps": ["继续跟踪；；待验证情景：同时核验官方公告。"],
        }
    )

    assert html.count("地缘风险需要继续跟踪。") == 1
    assert "；；" not in html


def test_reader_datetime_does_not_invent_time_for_date_only_value():
    from src.render_report_html import _reader_datetime

    assert _reader_datetime("2026-07-17") == "2026-07-17"


def test_public_reader_source_urls_strip_credentials_before_rendering():
    from src.render_report_html import _evidence_sample_bullets, _valid_http_url

    canary = "CANARY_PUBLIC_SECRET_9f2a7"
    raw_url = (
        f"https://reader:{canary}@EXAMPLE.test/news"
        f"?lang=zh&api_key={canary}&key={canary}&signature={canary}"
        f"&X-Amz-Credential={canary}&page=2#access_token={canary}"
    )

    sanitized = _valid_http_url(raw_url)
    html = _evidence_sample_bullets(
        [
            {
                "provider": "ExampleProvider",
                "factType": "verified_fact",
                "sourceUrl": raw_url,
            }
        ]
    )

    assert sanitized == "https://example.test/news?lang=zh&page=2"
    assert "https://example.test/news?lang=zh&amp;page=2" in html
    assert canary not in html
    assert "api_key" not in html
    assert "signature" not in html
    assert "X-Amz-Credential" not in html
    assert "access_token" not in html
    assert "reader:" not in html


def test_public_reader_source_url_rejects_webhooks_and_token_shaped_paths():
    from src.render_report_html import _valid_http_url

    assert _valid_http_url("https://hooks.slack.com/services/T000/B000/secret") == ""
    assert _valid_http_url("https://example.test/source/sk-abcdefghijklmnop") == ""
