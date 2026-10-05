from src.daily_department_llm import DEPARTMENT_SPECS, _prompt_evidence_for_spec
from src.report_artifact import _reader_valuation_summary


def spec(name):
    return next(s for s in DEPARTMENT_SPECS if s.agent == name)


def fact(symbol, suffix, domain='price'):
    return {'id': f'subject:{symbol}:{suffix}:2026-09-05', 'symbol': symbol,
            'domain': domain, 'value': suffix, 'fact_type': 'derived_fact'}


def test_technical_keeps_each_subject_daily_and_comparison():
    rows = [fact(s, kind) for kind in ['quote', 'daily_data', 'price_history_comparison']
            for s in ['600519', '000001', 'HK00700', 'AAPL']]
    rows = [{'id': 'provider_run:test', 'domain': 'price', 'value': 'success'}] * 4 + rows
    selected = _prompt_evidence_for_spec({'evidence': rows}, spec('TechnicalAgent'), {})
    ids = {r['id'] for r in selected}
    assert not any(i.startswith('provider_run:') for i in ids)
    assert {r['id'] for r in rows if 'daily_data' in r['id']} <= ids


def test_fundamental_prioritizes_operating_metrics_over_provider_status():
    rows = [fact(s, 'fundamental:'+kind, 'fundamentals')
            for kind in ['valuation', 'growth', 'earnings', 'history_comparison']
            for s in ['600519', '000001', 'HK00700', 'AAPL']]
    selected = _prompt_evidence_for_spec({'evidence': rows}, spec('FundamentalAgent'), {})
    assert {r['id'] for r in rows} <= {r['id'] for r in selected}


def test_fundamental_core_packets_survive_disclosure_flood():
    symbols = ['600519', '000001', 'HK00700', 'AAPL']
    core = [fact(s, 'fundamental:' + kind, 'fundamentals')
            for kind in ['valuation', 'growth', 'earnings', 'history_comparison'] for s in symbols]
    core += [fact(s, 'daily_data') for s in symbols]
    disclosures = [fact(s, f'announcement_{i}', 'filings_events') for i in range(12) for s in symbols]
    selected = _prompt_evidence_for_spec({'evidence': disclosures + core}, spec('FundamentalAgent'), {})
    assert {r['id'] for r in core} <= {r['id'] for r in selected}
    assert len(selected) <= 32


def test_macro_keeps_history_comparisons_with_levels():
    rows = []
    for s in ['GDP', 'UNRATE', 'DFF', 'CPIAUCSL', 'DGS10', 'DGS2', 'VIXCLS', 'T10Y2Y']:
        rows += [dict(fact(s, k, 'macro'), id=f'fred:{s}:{k}:2026-09-05')
                 for k in ['level', 'history_comparison']]
    selected = _prompt_evidence_for_spec({'evidence': rows}, spec('MacroAgent'), {})
    assert len(selected) == 16


def test_reader_accepts_upstream_valuation_names():
    text = _reader_valuation_summary({'pe_ratio': 20.42, 'pb_ratio': 6.62}, {})
    assert '20.42' in text and '6.62' in text
    assert '当前估值待补' not in text


def test_twenty_day_extremes_use_high_low_not_close_extremes():
    from src.source_health.subject_evidence import _price_series_summary
    rows = [{'date': f'2026-08-{day:02d}', 'close': 100 + day, 'high': 105 + day, 'low': 95 + day}
            for day in range(1, 21)]
    text = _price_series_summary(rows, operation='daily_data')
    fields = dict(part.split('=', 1) for part in text.split() if '=' in part)
    assert fields['high20'] == '125'
    assert fields['low20'] == '96'
    assert fields['close_high20'] == '120'
    missing = _price_series_summary([{'date': row['date'], 'close': row['close']} for row in rows], operation='daily_data')
    assert ' high20=' not in missing
    assert ' low20=' not in missing


def test_reader_uses_bar_date_not_weekend_fetch_and_links_native_history():
    from src.report_artifact import _build_stock_matrix
    daily = dict(fact('AAPL', 'daily_data'), as_of='2026-09-04',
                 value='latest_close=240 sma5=235 sma20=230')
    quote = dict(fact('AAPL', 'quote'), metric='realtime_quote',
                 value='price=241 change_pct=1', session_phase='closed',
                 as_of='2026-09-06', fetched_at='2026-09-06T03:00:00Z')
    row = _build_stock_matrix([daily, quote], universe={'subjectSymbols': ['AAPL']},
                             original_analysis_snapshot={'records': [{'code': 'AAPL', 'recordId': 7}]})[0]
    assert row['asOf'] == '2026-09-04'
    assert row['lastPrice'] == 240
    assert row['historyRecordId'] == 7


def test_history_market_is_not_disguised_as_stock_daily():
    from src.report_artifact import build_stock_artifact_from_history_detail
    row = build_stock_artifact_from_history_detail({
        'id': 7, 'stock_code': 'MARKET', 'stock_name': '大盘',
        'report_type': 'market_review', 'created_at': '2026-09-05T22:00:00Z',
        'analysis_summary': '三地指数分化。',
    })
    assert row['artifactType'] == 'market_summary'
    assert row['title'] == '市场复盘'
    assert row['generatedAt'] == '2026-09-05T22:00:00Z'
    assert not row['quality']['validationErrors']


def test_market_snapshot_labels_fetch_time_when_provider_omits_trade_time():
    from src.report_artifact import _build_market_matrix
    row = dict(fact('market', 'main_indices'), market='cn', metric='main_indices',
               subject='market', measurements={'index_000001_change_pct': -0.4},
               as_of='2026-09-05', time_basis='fetched', fetched_at='2026-09-06T03:00:00Z')
    matrix = _build_market_matrix([row], [])
    assert matrix[0]['timeLabel'] == '采集时间（行情时点未提供）'
    assert matrix[0]['asOf'] == '2026-09-06T03:00:00Z'


def test_context_pack_preserves_fundamental_period_and_time_basis():
    from src.daily_department_llm import _compact_evidence_row
    row = _compact_evidence_row(dict(fact('AAPL', 'fundamental_growth', 'fundamentals'),
        report_period='2026-06-30', comparison_period='2025-06-30', time_basis='source'), domain='fundamentals')
    assert row['report_period'] == '2026-06-30'
    assert row['comparison_period'] == '2025-06-30'
    assert row['time_basis'] == 'source'


def test_geo_prefers_fresh_asset_transmission_to_routine_monthly_digest():
    rows = [dict(fact('geo_policy', 'old', 'news_sentiment'), provider='ReliefWeb', fact_type='discovery',
                 value='Ukraine telecommunications monthly situation report', published_at='2026-08-01'),
            dict(fact('geo_policy', 'new', 'news_sentiment'), provider='Tavily', fact_type='discovery',
                 value='New semiconductor export controls and tariff policy', published_at='2026-09-06')]
    selected = _prompt_evidence_for_spec({'evidence': rows}, spec('GeoPolicyAgent'), {})
    assert selected[0]['id'] == rows[1]['id']
    assert selected[0]['fact_type'] == 'discovery'


def test_fundamental_history_and_financial_explanations_reach_actual_prompt():
    import json
    from src.daily_department_llm import _department_prompt
    symbols = ['600519', '000001', '000592', '600108', 'HK00700', 'AAPL']
    core = [fact(s, 'fundamental:' + kind, 'fundamentals')
            for kind in ['history_comparison', 'valuation', 'earnings', 'growth'] for s in symbols]
    history = [{'report_date': f'{2026-i//4}-{(4-i%4)*3:02d}-28', 'revenue': 100-i}
               for i in range(12)]
    for r in core:
        if 'history_comparison' in r['id']:
            r['history'] = history
    core += [fact(s, 'daily_data') for s in symbols]
    docs = [dict(fact(s, f'announcement_{i}', 'filings_events'),
        document_excerpt='现金流与利润差异来自金融子公司存款；不能当成主营回款。' if i == 9 else '',
        value='半年度报告全文' if i == 9 else '常规股权申报') for i in range(10) for s in symbols]
    context = {'runDate': '2026-09-08', 'universe': {'subjectSymbols': symbols}, 'health': {}, 'evidence': docs + core}
    prompt = json.loads(_department_prompt(spec('FundamentalAgent'), context, {}, set(), previous_error=''))
    selected = prompt['evidence']
    assert len(selected) <= 32
    for symbol in symbols:
        packet = [row for row in selected if row['symbol'] == symbol]
        assert any(row.get('document_excerpt') for row in packet)
        assert next(row['history'] for row in packet if 'history_comparison' in row['id']) == history


def test_macro_context_samples_long_history_with_actual_dates_not_false_year_claim():
    from datetime import date, timedelta
    from src.daily_department_llm import _compact_evidence_row
    from src.source_health.daily_evidence import _macro_history_comparison
    history = [{'date': str(date(2026, 9, 8) - timedelta(days=i)), 'value': 4+i/100} for i in range(260)]
    compact = _compact_evidence_row({'id': 'fred:test', 'domain': 'macro', 'history': history}, domain='macro')
    assert len(compact['history']) == 24
    assert compact['history'][:8] == history[:8]
    assert compact['history'][-1] == history[-1]
    assert compact['historyCoverage']['availableObservations'] == 260
    assert compact['historyCoverage']['sampled'] is True
    assert compact['historyCoverage']['sampleStart'] == history[-1]['date']
    assert compact['historyCoverage']['sampleEnd'] == history[0]['date']
    comparison = _macro_history_comparison('test', history)
    assert comparison['sample_start'] == history[-1]['date']
    assert comparison['sample_end'] == history[0]['date']
    assert comparison['history_observations'] == 260
    assert 'delta_12_observations' in comparison
    assert '同比' not in str(comparison)
