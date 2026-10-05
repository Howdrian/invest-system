"""Reader must render real analysis, not substitute deterministic editor prose."""
from src import report_artifact as report
from src.daily_department_llm import _summarize_runs


def test_unknown_or_partial_usage_is_not_zero():
    assert _summarize_runs([{'status': 'success'}])['tokenUsage']['totalTokens'] is None
    assert _summarize_runs([{'status': 'success', 'usage': {'total_tokens': 42}}, {'status': 'success'}])['tokenUsage']['totalTokens'] is None
    assert _summarize_runs([{'status': 'success', 'usage': {'total_tokens': 0}}])['tokenUsage']['totalTokens'] == 0


def test_native_history_does_not_render_missing_volume_as_none_percent():
    from datetime import datetime
    from types import SimpleNamespace
    from src.analyzer import AnalysisResult
    from src.services.history_service import HistoryService
    result = AnalysisResult(code='AAPL', name='Apple', sentiment_score=50,
                            trend_prediction='震荡', operation_advice='观望', analysis_summary='测试',
                            dashboard={'data_perspective': {'volume_analysis': {
                                'volume_ratio': None, 'turnover_rate': None,
                            }}})
    record = SimpleNamespace(created_at=datetime(2026, 9, 6), context_snapshot=None)
    text = HistoryService.__new__(HistoryService)._generate_single_stock_markdown(result, record)
    assert 'None%' not in text
    assert '量比 数据缺失' in text
    assert '换手率 数据缺失' in text


def test_index_headline_does_not_invent_synchronized_decline():
    mixed = report._reader_cn_headline_short('上证50 +0.15%、科创50 -2.10%、创业板指 -0.79%')
    assert '分化' in mixed
    assert '同步下跌' not in mixed
    rising = report._reader_cn_headline_short('科创50 +2.10%、创业板指 +0.79%')
    assert '同步上涨' in rising
    assert '领跌' not in rising


def test_reader_does_not_curate_over_llm_analysis(monkeypatch):
    monkeypatch.setattr(report, '_reader_scope_adjudication', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('CIO replaced')))
    def only_fallback_cards(cards, **kwargs):
        assert cards == []
    monkeypatch.setattr(report, '_curate_reader_v3_cards', only_fallback_cards)
    monkeypatch.setattr(report, '_rebind_curated_reader_evidence', only_fallback_cards)
    result = report._build_reader_v3(
        run_date='2026-09-05', generated_at='2026-09-05T10:00:00Z', data_as_of='2026-09-04',
        reader_brief={}, department_reports=[{
            'agent': 'CIOAgent', 'readerVisible': True, 'agentRuntime': 'LLM', 'llmStatus': 'success',
            'summaryForReader': '盈利改善尚未得到现金流确认。', 'keyClaims': ['盈利与现金流需要联合判断。'],
            'label': '综合判断', 'counterpoints': [], 'dataGaps': [],
        }], department_inputs=[], evidence_items=[], source_health_v2={'overallMode': 'LIMITED_REVIEW'},
        evidence_stats={}, decision={}, scenario_adjudication={
            'judgment': '盈利改善尚未得到现金流确认。', 'sharedFacts': [], 'baseCase': '需要现金流印证',
            'strongestAlternative': '营运资本变化也可能解释差异', 'why': '现金与盈利的确认时点不同', 'invalidationTriggers': [],
        },
    )
    assert '盈利改善尚未得到现金流确认' in result['adjudication']['judgment']
    assert '盈利改善尚未得到现金流确认' in result['departmentCards'][0]['conclusion']


def test_no_holdings_label_survives_public_projection():
    card = report._public_reader_v3_department_card({
        "agent": "PortfolioAgent", "label": "自选股观察（未接入持仓）",
    })
    assert card["label"] == "自选股观察（未接入持仓）"


def test_reader_leads_with_validated_cio_summary_not_editor_meeting():
    result = report._build_reader_v3(
        run_date='2026-09-06', reader_brief={},
        department_reports=[{
            'agent': 'CIOAgent', 'readerVisible': True, 'agentRuntime': 'LLM',
            'summaryForReader': 'A股内部表现分化，港股上涨尚待宽度确认，维持选择性观察。',
            'keyClaims': [], 'label': '综合判断', 'counterpoints': [], 'dataGaps': [],
        }],
        department_inputs=[], evidence_items=[], source_health_v2={},
        evidence_stats={}, decision={},
        research_reliability={'headlineSafe': True, 'label': '中等可信'},
        scenario_adjudication={'judgment': '当前采纳基准情景，保留风险部门意见。'},
    )
    assert 'A股内部表现分化' in result['hero']['oneLine']
    assert '风险部门意见' not in result['hero']['oneLine']


def test_static_reader_does_not_rewrite_holdings_advice_when_new_positions_watch():
    from src.render_report_html import _reader_v3_html
    judgment = '新仓不操作，已有持仓跌破100止损；反弹至120分批减仓。'
    html = _reader_v3_html({'runDate': '2026-09-06'}, {
        'hero': {'oneLine': judgment}, 'nextSteps': [judgment],
        'departmentCards': [], 'evidenceSummary': {},
    })
    assert judgment in html
    assert '人工风险复核' not in html
