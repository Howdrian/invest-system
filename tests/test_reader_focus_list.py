from src.report_artifact import build_reader_focus_list


def test_cio_compound_sector_rating_replaces_department_draft_for_same_market():
    departments = [
        {'agent': 'CIOAgent', 'claimEvidence': [
            {'claimId': 'cio:cn', 'subject': 'market_cn', 'target': 'A股行业',
             'rating': '油气看好；农业中性', 'claim': '油气优先，农业不追涨。', 'evidence_ids': ['oil']}],
         'semanticValidation': {'claims': [{'claimId': 'cio:cn', 'status': 'hypothesis'}]}},
        {'agent': 'SectorAgent', 'claimEvidence': [
            {'claimId': 'sector:cn', 'subject': 'market_cn', 'target': '农业',
             'rating': '看好', 'claim': '农业排名第一。', 'evidence_ids': ['cn']},
            {'claimId': 'sector:hk', 'subject': 'market_hk', 'target': '银行',
             'rating': '看好', 'claim': '银行相对强势。', 'evidence_ids': ['hk']}],
         'semanticValidation': {'claims': [{'claimId': 'sector:cn', 'status': 'hypothesis'},
                                          {'claimId': 'sector:hk', 'status': 'hypothesis'}]}},
    ]
    focus = build_reader_focus_list(stock_matrix=[], departments=departments, evidence_facts=[])
    assert focus['sectors'][0]['priority'] == '油气看好；农业中性'
    assert focus['sectors'][0]['basis'] == '油气优先，农业不追涨。'
    assert '农业排名第一' not in str(focus)
    assert any(row['market'] == '港股' for row in focus['sectors'])


def test_candidate_name_uses_actual_universe_discovery_not_bare_symbol():
    focus = build_reader_focus_list(stock_matrix=[{'symbol': '000592', 'name': '000592', 'market': 'cn'}],
        departments=[], evidence_facts=[], universe={'groups': [
            {'name': 'candidates', 'discoveries': [{'symbol': '000592', 'name': '平潭发展'}]}]})
    assert focus['stocks'][0]['name'] == '平潭发展'


def test_focus_list_uses_subject_specific_cio_priority_and_does_not_invent_sector_members():
    result = build_reader_focus_list(
        stock_matrix=[{'symbol': 'AAPL', 'name': 'Apple', 'market': 'US', 'asOf': '2026-09-04', 'historyRecordId': 6},
                      {'symbol': 'HK00700', 'name': '腾讯', 'market': 'HK', 'asOf': '2026-09-04'}],
        departments=[
            {'agent': 'CIOAgent', 'claimEvidence': [
                {'claimId': 'c1', 'subject': 'AAPL', 'claim': '苹果值得优先研究盈利持续性。', 'evidence_ids': ['a1']},
                {'claimId': 'c2', 'subject': 'HK00700', 'claim': '腾讯目前仍属反弹观察。', 'evidence_ids': ['h1']}],
             'semanticValidation': {'claims': [{'claimId': 'c1', 'status': 'supported'}, {'claimId': 'c2', 'status': 'hypothesis'}]}},
            {'agent': 'SectorAgent', 'summaryForReader': '渔业相对偏强。', 'keyClaims': ['渔业相对偏强。'],
             'nextAction': '观察后续相对强弱是否延续。', 'evidenceIds': ['sector1']},
            {'agent': 'TechnicalAgent', 'nextAction': 'AAPL看100美元，HK00700看200港元。'},
        ],
        evidence_facts=[{'id': 'sector1', 'metric': 'sector_history_comparison', 'market': 'cn',
                         'observed_dates': ['2026-09-05', '2026-09-06'],
                         'history': [{'name': '渔业', 'top': 2}, {'name': '未被部门选中的行业', 'top': 2}]}],
    )
    assert result['stocks'][0]['priority'] == '优先研究'
    assert result['stocks'][1]['priority'] == '跟踪观察'
    assert result['stocks'][0]['watchFor'] == 'AAPL看100美元'
    assert result['stocks'][1]['watchFor'] == 'HK00700看200港元'
    assert result['sectors'][0]['targets'] == ['渔业']
    assert '本地快照' in result['sectors'][0]['basis']
    assert '港股、美股' in result['sectorCoverage']
    assert result['stocks'][0]['historyRecordId'] == 6


def test_rejected_cio_buy_claim_is_not_restored_as_focus_reason_or_priority():
    result = build_reader_focus_list(
        stock_matrix=[{'symbol': 'AAPL', 'name': 'Apple', 'market': 'US'}],
        departments=[{'agent': 'CIOAgent', 'claimEvidence': [
            {'claimId': 'bad', 'subject': 'AAPL', 'claim': '优先买入保证上涨。'}],
            'semanticValidation': {'claims': [{'claimId': 'bad', 'status': 'rejected'}]}}],
        evidence_facts=[],
    )
    assert result['stocks'][0]['priority'] == '未排序'
    assert '保证上涨' not in str(result)
    assert result['sectors'] == []


def test_static_reader_shares_focus_and_claim_assessments_and_escapes_text():
    from src.render_report_html import _reader_v3_html
    reader = {
        'focusList': {'sectors': [], 'stocks': [{'symbol': 'AAPL', 'name': 'Apple',
            'priority': '优先研究', 'reason': '<script>not executable</script>', 'watchFor': '盈利持续性'}],
            'note': '来自现有研究', 'sectorCoverage': '港美板块未覆盖'},
        'departmentCards': [{'label': '基本面部门', 'claimAssessment': {
            'summary': '1条有据支持', 'claims': [{'text': '经营改善', 'label': '有据支持'}]}}],
    }
    html = _reader_v3_html({'runDate': '2026-09-06'}, reader)
    assert '本期关注清单' in html
    assert '优先研究' in html and '盈利持续性' in html
    assert '1条有据支持' in html and '经营改善' in html
    assert '<script>not executable</script>' not in html


def test_validated_red_team_challenge_stays_disputed_in_assessment_and_focus():
    from src.research_core import build_claim_assessment, build_challenge_verdicts
    from src.report_artifact import _reader_v3_department_card
    cio = {'agent': 'CIOAgent', 'claimEvidence': [
        {'claimId': 'c1', 'subject': 'AAPL', 'claim': 'AAPL值得优先研究。', 'evidenceIds': ['e1']}],
        'semanticValidation': {'claims': [{'claimId': 'c1', 'status': 'supported'}]}}
    red = {'agent': 'RedTeamAgent', 'challenges': [
        {'targetClaimId': 'c1', 'validationStatus': 'supported', 'opposingScenario': '盈利下修'}]}
    verdicts = build_challenge_verdicts([cio, red])
    assert build_claim_assessment(cio, challenge_verdicts=verdicts)['claims'][0]['label'] == '存在争议'
    card = _reader_v3_department_card(cio, [], [], challenge_verdicts=verdicts)
    assert card['claimAssessment']['summary'] == '1条存在争议'
    focus = build_reader_focus_list(stock_matrix=[{'symbol': 'AAPL', 'name': 'Apple', 'market': 'US'}],
                                    departments=[cio, red], evidence_facts=[])
    assert focus['stocks'][0]['priority'] == '优先研究'
    assert focus['stocks'][0]['evidenceLabel'] == '存在争议'


def test_department_drilldown_uses_same_per_claim_assessment(tmp_path):
    import json
    from src.render_report_html import build_section_report
    reports = tmp_path / 'reports'
    reports.mkdir()
    (reports / '2026-09-06.artifact.json').write_text(json.dumps({'readerV3': {'departmentCards': [
        {'agent': '宏观部门', 'conclusion': '融资条件与估值约束并存。',
         'keyClaims': ['旧版无标签条目'], 'claimAssessment': {'summary': '1条有据支持', 'claims': [
             {'claimId': 'm1', 'text': '信用利差处于样本低位。', 'label': '有据支持', 'evidenceIds': []}]}}
    ]}}, ensure_ascii=False))
    html = build_section_report(tmp_path, '2026-09-06', slug='macro', title='宏观', source_rel='', summary='宏观研究')
    assert '有据支持：信用利差处于样本低位。' in html
    assert '旧版无标签条目' not in html


def test_sector_performance_is_factual_observation_not_fabricated_agent_recommendation():
    result = build_reader_focus_list(stock_matrix=[], departments=[], evidence_facts=[{
        'id': 'sector:us', 'metric': 'sector_performance', 'market': 'us', 'scope': '标普500行业代理',
        'as_of': '2026-09-04', 'benchmark': 'SPY', 'records': [
            {'name': '金融', 'code': 'XLF', 'relative_20d_pp': 0, 'return_20d_pct': -2},
            {'name': '科技', 'code': 'XLK', 'relative_20d_pp': 2, 'return_20d_pct': -1,
             'source_url': 'javascript:alert(1)'}]}])
    assert result['sectors'] == []  # No invented Agent selection.
    data = result['sectorPerformance'][0]
    assert data['rows'][0]['name'] == '科技'
    assert data['rows'][1]['relative20dPp'] == 0
    assert not data['rows'][0]['sourceUrl']
    from src.render_report_html import _reader_focus_html
    html = _reader_focus_html(result)
    assert '美股 · 行业动态' in html and '标普500行业代理' in html
    assert '相对居前不等于绝对上涨' in html
    assert 'javascript:' not in html


def test_single_cn_ranking_can_be_observed_without_inventing_repeated_history():
    result = build_reader_focus_list(stock_matrix=[], departments=[{
        'agent': 'SectorAgent', 'summaryForReader': '农业是单日观察方向。', 'evidenceIds': ['cn:ranking'],
    }], evidence_facts=[{'id': 'cn:ranking', 'metric': 'sector_rankings', 'market': 'cn', 'records': [
        {'name': '农业', 'rank_side': 'top'}, {'name': '渔业', 'rank_side': 'top'}]}])
    assert result['sectors'][0]['targets'] == ['农业']
    assert result['sectors'][0]['priority'] == '当日强势观察'
    assert '不代表多日持续性' in result['sectors'][0]['basis']
    assert 'A股' not in result['sectorCoverage']


def test_full_department_page_preserves_later_markets_and_long_arguments(tmp_path):
    import json
    from src.render_report_html import build_section_report
    reports = tmp_path / 'reports'
    reports.mkdir()
    claims = [{'claimId': f's{i}', 'text': ('行业比较与供需依据。' * 25) + f'美股末段观点{i}',
               'label': '研究判断', 'evidenceIds': []} for i in range(11)]
    risks = [('竞争格局与盈利风险。' * 25) + f'反证末段{i}' for i in range(6)]
    next_action = ('验证行业价格和利润变化。' * 25) + '完整改判条件'
    conclusion = ('行业与公司需要分别比较。' * 25) + '完整部门结论'
    (reports / '2026-09-08.artifact.json').write_text(json.dumps({'readerV3': {'departmentCards': [
        {'agent': '行业/风格部门', 'conclusion': conclusion, 'claimAssessment': {'claims': claims},
         'counterpoints': risks, 'nextAction': next_action}
    ]}}, ensure_ascii=False))
    html = build_section_report(tmp_path, '2026-09-08', slug='sectors', title='行业', source_rel='', summary='行业')
    for claim in claims:
        assert claim['text'] in html
    for text in risks + [next_action, conclusion]:
        assert text in html


def test_company_research_is_same_run_and_rejected_claim_is_not_restored():
    department = {'agent': 'FundamentalAgent', 'claimEvidence': [
        {'claimId': 'f1', 'subject': 'AAPL', 'claim': '现金流来自营运资本变化。', 'evidence_ids': ['e1']},
        {'claimId': 'f2', 'subject': 'OTHER', 'claim': '另一公司的数字不混入。', 'evidence_ids': ['e2']},
        {'claimId': 'f3', 'subject': 'AAPL', 'claim': '被撤回的错误数字。', 'evidence_ids': ['e3']},
    ], 'semanticValidation': {'claims': [
        {'claimId': 'f1', 'status': 'supported', 'acceptedEvidenceIds': ['e1']},
        {'claimId': 'f2', 'status': 'supported', 'acceptedEvidenceIds': ['e2']},
        {'claimId': 'f3', 'status': 'rejected', 'acceptedEvidenceIds': []},
    ]}}
    result = build_reader_focus_list(stock_matrix=[{'symbol': 'AAPL', 'market': 'US'}],
                                    departments=[department], evidence_facts=[], evidence_items=[
        {'id': 'e1', 'provider': 'SEC', 'sourceUrl': 'https://www.sec.gov/report',
         'value': '现金流解释', 'asOf': '2026-06-30', 'factType': 'verified_fact'}])
    research = result['stocks'][0]['research']
    assert len(research) == 1
    assert research[0]['text'] == '现金流来自营运资本变化'
    assert research[0]['evidenceSamples'][0]['sourceUrl'] == 'https://www.sec.gov/report'


def test_financial_evidence_sample_renders_values_and_periods_not_wire_keys():
    from src.report_artifact import _reader_v3_evidence_sample
    row = _reader_v3_evidence_sample({
        'metric': 'fundamental_history_comparison',
        'label': 'periods=12 latest_report=2026-06-30 comparison_report=2025-06-30 net_profit_parent_transition=loss_widened operating_cash_flow_transition=turned_positive',
        'measurements': {'period_count': 12, 'revenue_yoy_pct': 1.3},
    })
    assert '覆盖 12 个报告期' in row['label']
    assert '2026-06-30 对 2025-06-30' in row['label']
    assert '1.30%' in row['label']
    assert '净利润亏损扩大' in row['label']
    assert '经营现金流由净流出转为净流入' in row['label']
    assert '=' not in row['label'] and 'yoy' not in row['label']
    positive = _reader_v3_evidence_sample({'metric': 'fundamental_history_comparison',
        'measurements': {'operating_cash_flow_yoy_pct': 438.84}})
    assert '经营现金流同比 +438.84%' in positive['label']


def test_cross_market_timing_does_not_imply_us_close_from_shanghai_clock():
    from src.report_artifact import _reader_timing_context
    value = _reader_timing_context(run_date='2026-09-08', generated_at='2026-09-08T14:20:00Z',
        data_as_of='2026-09-08', market_matrix=[
            {'market': 'A股', 'scopeType': 'market', 'asOf': '2026-09-08'},
            {'market': 'US', 'scopeType': 'market', 'asOf': '2026-09-08'},
        ], stock_matrix=[])
    assert value['validity'].startswith('A股时段：收盘后简报')
    assert '数据按各自标注时点' in value['validity']


def test_evidence_labels_present_known_records_without_corrupting_source_titles():
    from src.report_artifact import _reader_evidence_label
    assert _reader_evidence_label("belong_boards available: boards={'name': '银行', 'code': 'BK1'}") == '所属行业与概念：银行'
    assert _reader_evidence_label('belong_boards available: boards=malformed') == '所属行业与概念快照'
    assert _reader_evidence_label('CN_PMI_MANUFACTURING=49.8 @ 2026年08月份') == '中国制造业 PMI 49.8（2026年08月份）'
    text = _reader_evidence_label('observations=3 latest=2026-09-08 previous=2026-09-07 advancers_pct=61.59 total_amount_100m_cny=19778.9107 total_amount_100m_cny_delta_previous=19589.0809')
    assert '上涨家数占比 61.59%' in text and '19778.91 亿元' in text
    assert '=' not in text and '19589' not in text and '可比交易日' in text
    assert 'Oil prices' in _reader_evidence_label('Oil prices extend gains amid macroeconomic uncertainty')


def test_stock_department_page_distinguishes_draft_rating_from_cio_final(tmp_path):
    import json
    from src.render_report_html import build_section_report
    (tmp_path / 'reports').mkdir()
    (tmp_path / 'reports/2026-09-08.artifact.json').write_text(json.dumps({'readerV3': {
        'adjudication': {'judgment': '比亚迪由卖出改为中性，暂不新增。'},
        'departmentCards': [{'agent': '基本面部门', 'conclusion': '比亚迪卖出。',
            'keyClaims': ['估值未提供足够补偿'], 'counterpoints': ['第二季度盈利修复']}],
    }}, ensure_ascii=False))
    html = build_section_report(tmp_path, '2026-09-08', slug='stocks', title='个股', source_rel='', summary='公司研究')
    assert 'CIO 最终取舍' in html and '比亚迪由卖出改为中性' in html
    assert '部门研究结论' in html and '比亚迪卖出' in html
    assert html.index('CIO 最终取舍') < html.index('部门研究结论')


def test_stock_snapshot_uses_discovered_names_and_has_no_competing_rule_rating():
    from src.report_artifact import _build_stock_matrix
    from src.render_report_html import _reader_stock_matrix_html
    rows = _build_stock_matrix(
        [{'id': 'subject:600036:daily_data:2026-09-08', 'symbol': '600036', 'domain': 'price',
          'fact_type': 'derived_fact', 'as_of': '2026-09-08', 'value': 'latest_close=40.9'}],
        universe={'subjectSymbols': ['600036'], 'groups': [
            {'name': 'candidates', 'discoveries': [{'symbol': '600036', 'name': '招商银行'}]}]},
        original_analysis_snapshot={},
    )
    assert rows[0]['name'] == '招商银行'
    html = _reader_stock_matrix_html([{**rows[0], 'stance': 'OLD_RULE_RATING'}])
    assert '招商银行' in html
    assert 'OLD_RULE_RATING' not in html
    assert '<th>定位</th>' not in html
    assert '研究评级与入场节奏见上方公司研究' in html
