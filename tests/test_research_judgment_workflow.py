"""Research opinions survive transport; numerical assertions still need evidence."""
import json

from src.daily_department_llm import DEPARTMENT_SPECS, _department_prompt, _compact_evidence_row, _compact_memo
from src.research_core import validate_claim_dicts, ClaimStatus
from src.source_health.daily_universe import build_daily_universe


def _spec(agent):
    return next(spec for spec in DEPARTMENT_SPECS if spec.agent == agent)


def test_report_window_looks_back_one_month_and_forward_two(tmp_path, monkeypatch):
    monkeypatch.setattr('src.source_health.daily_universe._read_env_values', lambda: {})
    universe = build_daily_universe(tmp_path, '2026-09-07', symbols=['AAPL'], market='cn,hk,us')
    assert universe['researchWindow']['lookbackStart'] == '2026-08-07'
    assert universe['researchWindow']['outlookEnd'] == '2026-11-07'
    prompt = json.loads(_department_prompt(_spec('CIOAgent'), {
        'runDate': '2026-09-07', 'universe': universe, 'health': {'overallMode': 'LIMITED_REVIEW'},
        'evidence': [],
    }, {}, set(), previous_error=''))
    assert prompt['researchWindow'] == universe['researchWindow']
    assert '现在建议' in prompt['outputContract']['jsonExample']['next_action']
    assert '买入' in prompt['modeGuidance']['instruction']


def test_market_count_parser_does_not_steal_limit_up_count():
    text = '不能机械全面看空：上证50上涨、涨停41家多于跌停9家。'
    rows = [{'id': 'stats', 'fact_type': 'derived_fact', 'domain': 'price', 'value': 'market stats',
             'measurements': {'up_count': 2444, 'down_count': 2913, 'limit_up_count': 41, 'limit_down_count': 9}}]
    good = validate_claim_dicts([{'claim': text, 'claimType': 'interpretation', 'evidence_ids': ['stats']}], rows)[0]
    assert good.status != ClaimStatus.REJECTED
    assert good.safe_text == text
    wrong = validate_claim_dicts([{'claim': '上涨41家。', 'claimType': 'fact', 'evidence_ids': ['stats']}], rows)[0]
    assert wrong.status == ClaimStatus.REJECTED


def test_opinion_and_future_condition_are_not_rewritten_as_generic_caution():
    text = '我看好未来两个月的行业修复；只有后续市场宽度持续改善，才扩大参与范围。'
    rows = [{'id': 'idx', 'fact_type': 'derived_fact', 'domain': 'price', 'value': 'main_indices 沪深300=4000'}]
    result = validate_claim_dicts([{'claim': text, 'claimType': 'recommendation', 'evidence_ids': ['idx']}], rows)[0]
    assert result.status != ClaimStatus.REJECTED
    assert result.safe_text == text


def test_financial_context_keeps_periods_history_and_document_explanation():
    row = {'id': 'financial', 'domain': 'fundamentals', 'value': '经营现金流增长',
           'period_start': '2025-09-28', 'period_end': '2026-06-27', 'unit': 'USD',
           'history': [{'report_date': '2026-03-31', 'revenue': 100}],
           'source_url': 'https://example.com/report.pdf',
           'document_excerpt': '变动主要来自财务子公司存款，并非主营回款改善。'}
    compact = _compact_evidence_row(row, domain='fundamentals')
    assert compact['period_start'] == row['period_start']
    assert compact['period_end'] == row['period_end']
    assert compact['history'] == row['history']
    assert compact['document_excerpt'] == row['document_excerpt']


def test_downstream_context_carries_claim_id_and_all_of_its_direct_refs():
    memo = {'agent': 'FundamentalAgent', 'claim_evidence': [
        {'claimId': 'FundamentalAgent:4', 'claim': '公司现金流来源变化，不代表主营利润改善。',
         'claimType': 'interpretation', 'subject': 'AAPL', 'evidence_ids': ['a','b','c','d','e']},
    ]}
    compact = _compact_memo(memo)
    assert compact['key_claims'][0]['claimId'] == 'FundamentalAgent:4'
    assert compact['key_claims'][0]['evidence_ids'] == ['a','b','c','d','e']


def test_explicit_single_watchlist_is_respected_and_calendar_window_clamps(tmp_path, monkeypatch):
    from src.source_health.daily_universe import research_window
    monkeypatch.setenv('STOCK_LIST', '600519')
    universe = build_daily_universe(tmp_path, '2026-03-31')
    assert universe['subjectSymbols'] == ['600519']
    assert research_window('2026-03-31')['lookbackStart'] == '2026-02-28'
    assert research_window('2026-12-31')['outlookEnd'] == '2027-02-28'


def test_discovered_candidates_do_not_mutate_watchlist_or_accept_stale_leads(tmp_path, monkeypatch):
    from src.source_health.daily_universe import integrate_discovered_candidates
    monkeypatch.setattr('src.source_health.daily_universe._read_env_values', lambda: {})
    universe = build_daily_universe(tmp_path, '2026-09-07', symbols=['AAPL'])
    original = json.dumps(universe, sort_keys=True)
    fact = {'id': 'hot:cn', 'as_of': '2026-09-04', 'metric': 'hot_stocks',
            'records': [{'code': 'SH600036'}, {'symbol': '002594'}, {'symbol': '300750'}]}
    result = integrate_discovered_candidates(universe, [fact], per_market=2)
    assert result['subjectSymbols'] == ['AAPL', '600036', '002594']
    assert next(g for g in result['groups'] if g['name'] == 'watchlist')['symbols'] == ['AAPL']
    assert json.dumps(universe, sort_keys=True) == original
    for change in ({'as_of': '2020-01-01'}, {'as_of': '2026-09-08'}, {'evidence_scope': 'source_smoke'}):
        assert integrate_discovered_candidates(universe, [{**fact, **change}])['subjectSymbols'] == ['AAPL']


def test_fundamental_technical_intel_follow_sector_and_prompt_is_business_first():
    from src.daily_department_llm import DEPARTMENT_PLAYBOOKS, AGENT_ANALYSIS_RULES
    for agent in ('FundamentalAgent', 'TechnicalAgent', 'IntelAgent'):
        assert _spec(agent).depends_on == ('SectorAgent',)
    sop = str(DEPARTMENT_PLAYBOOKS['FundamentalAgent']) + str(AGENT_ANALYSIS_RULES['FundamentalAgent'])
    assert '现金流' in sop and '利润' in sop and '报告期' in sop
    assert '过度悲观' in str(DEPARTMENT_PLAYBOOKS['RedTeamAgent'])


def test_downstream_prompt_never_transmits_claim_with_lost_direct_evidence():
    refs = ['f1', 'f2', 'f3', 'f4', 'f5']
    memo = {'agent': 'FundamentalAgent', 'summary_for_reader': '投资判断', 'claim_evidence': [
        {'claimId': 'fund:1', 'claim': '经营现金流与利润变化不同。', 'evidence_ids': refs,
         'subject': 'AAPL', 'rating': '买入', 'timeScope': '未来两个月'}]}
    context = {'runDate': '2026-09-07', 'universe': {}, 'health': {}, 'evidence': [
        {'id': ref, 'domain': 'fundamentals', 'symbol': 'AAPL', 'fact_type': 'derived_fact',
         'value': '利润与现金流', 'as_of': '2026-09-04'} for ref in refs]}
    prompt = json.loads(_department_prompt(_spec('CIOAgent'), context, {'FundamentalAgent': memo}, set(refs), previous_error=''))
    deps = prompt['previousDepartmentOutputs']
    # Use the actual named transport field rather than a mocked runtime result.
    assert deps is not None, prompt.keys()
    transported = next(iter(deps.values())) if isinstance(deps, dict) else deps[0]
    claim = transported['key_claims'][0]
    assert set(claim['evidence_ids']) == set(refs)
    assert set(refs) <= {r['id'] for r in prompt['evidence']}
    assert claim['rating'] == '买入' and claim['claimId'] == 'fund:1'


def test_ratings_and_user_vs_system_lists_survive_reader_projection():
    from src.report_artifact import build_reader_focus_list
    result = build_reader_focus_list(
        stock_matrix=[{'symbol': 'AAPL', 'market': 'US'}, {'symbol': '600036', 'market': 'CN'}],
        departments=[{'agent': 'CIOAgent', 'claimEvidence': [
            {'claimId': 'buy', 'subject': 'AAPL', 'claim': '盈利改善值得参与。', 'rating': '买入',
             'timeScope': '未来两个月', 'entryCondition': '分批参与；利润下修则退出', 'evidence_ids': ['f1']}],
            'semanticValidation': {'claims': [{'claimId': 'buy', 'status': 'hypothesis'}]}}],
        evidence_facts=[], universe={'groups': [{'name': 'watchlist', 'symbols': ['AAPL']}],
                                    'researchWindow': {'label': '回看近1个月 · 研判未来1–2个月'}})
    assert result['stocks'][0]['priority'] == '买入'
    assert result['stocks'][0]['listOrigin'] == '我的自选'
    assert result['stocks'][1]['listOrigin'] == '系统研究候选'
    assert result['stocks'][0]['horizon'] == '未来两个月'
    from src.render_report_html import _reader_focus_html
    html = _reader_focus_html(result)
    for text in ('买入', '我的自选', '系统研究候选', '未来两个月', '参与节奏与改判条件'):
        assert text in html


def test_official_text_excerpt_retains_cashflow_cause_not_only_growth():
    from src.source_health.filing_content import extract_filing_text, financial_excerpt
    text = extract_filing_text(('<html><script>BAD_SCRIPT</script><p>半年报</p><p>' + '普通内容\n' * 1200
                               + '</p><p>现金流量变动原因</p><p>主要来自成员单位存款增加，而非主营回款改善。</p></html>').encode())
    excerpt = financial_excerpt(text)
    assert '成员单位存款' in excerpt and 'BAD_SCRIPT' not in excerpt
    assert len(excerpt) <= 4000


def test_official_document_fetch_rejects_unapproved_urls_and_redirects():
    import urllib.request
    import pytest
    from src.source_health.official_event_sources import OfficialEventSourceClient, _OfficialDocumentRedirect
    client = OfficialEventSourceClient()
    for url in ('http://127.0.0.1/admin', 'file:///etc/hosts', 'https://www.sec.gov.evil.example/a.pdf'):
        with pytest.raises(ValueError):
            client._get_document(url)
    with pytest.raises(ValueError):
        _OfficialDocumentRedirect().redirect_request(urllib.request.Request('https://www.sec.gov/test'), None,
                                                     302, 'Found', {}, 'http://127.0.0.1/private')


def test_cio_now_recommendations_survive_next_steps_without_invented_prohibition():
    from src.report_artifact import _reader_next_steps, _split_reader_steps
    from src.daily_department_llm import _normalize_next_action
    actions = {'现在建议': '买入盈利改善的公司，分批参与', '改变意见的条件': '盈利指引下修则退出',
               '下次复核什么': '两周后复核订单与估值'}
    expected = [f'{k}：{v}' for k, v in actions.items()]
    assert _split_reader_steps(actions) == expected
    assert _reader_next_steps(_normalize_next_action(actions), ['不做什么：继续观察']) == expected


def test_sec_financial_filing_is_not_crowded_out_by_recent_form4():
    from src.source_health.official_event_sources import _sec_recent_filings
    forms = ['4'] * 12 + ['10-Q', '10-K']
    payload = {'filings': {'recent': {'form': forms, 'filingDate': ['2026-09-04'] * 12 + ['2026-08-01', '2027-01-01'],
        'accessionNumber': [f'000000-26-{i:06}' for i in range(14)], 'primaryDocument': [f'doc{i}.htm' for i in range(14)]}}}
    rows = _sec_recent_filings(payload, symbol='AAPL', cik='320193', run_date='2026-09-07', limit=3)
    assert len(rows) == 3
    assert any(r['form'] == '10-Q' for r in rows)
    assert not any(r['form'] == '10-K' for r in rows)


def test_sec_cash_flow_and_profit_have_distinct_concepts_and_periods():
    from src.source_health.official_event_sources import _sec_companyfacts, OfficialEventSourceClient
    concepts = ['Revenues', 'NetIncomeLoss', 'NetCashProvidedByUsedInOperatingActivities', 'PaymentsToAcquirePropertyPlantAndEquipment']
    payload = {'facts': {'us-gaap': {c: {'units': {'USD': [{'start': '2025-09-28', 'end': '2026-06-27',
        'filed': '2026-08-01', 'val': i + 100, 'form': '10-Q'}]}} for i,c in enumerate(concepts)}}}
    rows = _sec_companyfacts(payload, symbol='AAPL', run_date='2026-09-07', limit=8)
    assert {row['concept'] for row in rows} == set(concepts)
    assert all(row['start'] == '2025-09-28' for row in rows)
    assert OfficialEventSourceClient.fetch_sec_companyfacts.__kwdefaults__['max_facts_per_symbol'] >= 6


def test_all_department_prompts_use_configured_horizon_and_relevant_history(tmp_path, monkeypatch):
    monkeypatch.setattr('src.source_health.daily_universe._read_env_values', lambda: {})
    monkeypatch.setenv('RESEARCH_RECENT_CHANGE_MONTHS', '3')
    monkeypatch.setenv('RESEARCH_OUTLOOK_MONTHS', '6')
    universe = build_daily_universe(tmp_path, '2026-09-08', symbols=['AAPL'])
    for spec in DEPARTMENT_SPECS:
        prompt = json.loads(_department_prompt(spec, {'runDate': '2026-09-08', 'universe': universe,
            'health': {}, 'evidence': []}, {}, set(), previous_error=''))
        assert prompt['researchWindow']['decisionHorizon']['months'] == 6
        assert prompt['departmentInputProfile']['historicalContext']
        assert '具体观点可采用不同期限' in prompt['researchWindow']['basis']
        assert not any(text in json.dumps(prompt, ensure_ascii=False) for text in
            ('未来两个月', '未来一至两个月', '最近一个月', '过去一个月', '回看一个月'))


def test_longer_thesis_survives_default_horizon_in_cio_context():
    memo = {'agent': 'FundamentalAgent', 'claim_evidence': [{
        'claimId': 'fund:long', 'claim': '盈利修复跨越多个季度，当前估值提供参与理由。',
        'timeScope': '未来6–12个月；本期分批参与', 'rating': '买入', 'evidence_ids': ['f1']}]}
    old_window = {'asOf': '2026-09-07', 'lookbackStart': '2026-08-07', 'outlookEnd': '2026-11-07'}
    context = {'runDate': '2026-09-07', 'universe': {'researchWindow': old_window}, 'health': {},
        'evidence': [{'id': 'f1', 'domain': 'fundamentals', 'value': '盈利历史', 'fact_type': 'derived_fact'}]}
    prompt = json.loads(_department_prompt(_spec('CIOAgent'), context, {'FundamentalAgent': memo}, {'f1'}, previous_error=''))
    assert prompt['researchWindow']['decisionHorizon']['flexible'] is True
    assert prompt['previousDepartmentOutputs']['FundamentalAgent']['key_claims'][0]['timeScope'] == '未来6–12个月；本期分批参与'
    assert 'schema' not in old_window  # Upgrading a new prompt never mutates stored historical reports.


def test_reader_displays_separate_windows_without_overwriting_claim_horizon():
    from src.source_health.daily_universe import research_window
    from src.report_artifact import build_reader_focus_list
    from src.render_report_html import _reader_focus_html
    window = research_window('2026-09-08', recent_change_months=3, outlook_months=6)
    value = build_reader_focus_list(stock_matrix=[], departments=[], evidence_facts=[], universe={'researchWindow': window})
    html = _reader_focus_html(value)
    for line in window['displayLines']:
        assert line in html
    assert '2026-06-08 至 2027-03-08' not in html
    assert '回看近1个月' not in html
    assert '研判未来1–2个月' not in value['note']
