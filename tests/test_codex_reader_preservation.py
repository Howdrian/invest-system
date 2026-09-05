"""Reader must render real analysis, not substitute deterministic editor prose."""
from src import report_artifact as report
from src.daily_department_llm import _summarize_runs


def test_unknown_or_partial_usage_is_not_zero():
    assert _summarize_runs([{'status': 'success'}])['tokenUsage']['totalTokens'] is None
    assert _summarize_runs([{'status': 'success', 'usage': {'total_tokens': 42}}, {'status': 'success'}])['tokenUsage']['totalTokens'] is None
    assert _summarize_runs([{'status': 'success', 'usage': {'total_tokens': 0}}])['tokenUsage']['totalTokens'] == 0


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
