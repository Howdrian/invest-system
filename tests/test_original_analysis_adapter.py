from pathlib import Path
import json
from datetime import datetime
from types import SimpleNamespace

from src.original_analysis_adapter import (
    build_original_analysis_bundle,
    export_original_analysis_snapshot,
    load_original_analysis_refs,
)


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')


def _append_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')


def test_original_analysis_adapter_builds_department_refs(tmp_path):
    docs = tmp_path / 'docs'
    runtime_reports = tmp_path / 'reports'
    date = '2026-07-02'
    run = docs / 'run_status' / date
    _write_json(run / 'daily_universe.json', {
        'mode': 'multi_subject_daily',
        'subjectSymbols': ['600519', 'AAPL'],
        'groups': [{'name': 'watchlist', 'symbols': ['600519', 'AAPL']}, {'name': 'portfolio', 'symbols': []}],
    })
    _write_json(run / 'source_health_v2.json', {'schema': 'source_health_v2', 'domains': {'portfolio': {'status': 'partial'}}})
    _append_jsonl(run / 'evidence_ledger.jsonl', [
        {'id': 'subject:market:main_indices:2026-07-02', 'domain': 'price', 'fact_type': 'derived_fact', 'subject': 'market', 'value': 'main_indices returned 5 records'},
        {'id': 'subject:market:market_stats:2026-07-02', 'domain': 'price', 'fact_type': 'derived_fact', 'subject': 'market', 'value': 'market_stats returned 6 records'},
        {'id': 'subject:market:sector_rankings:2026-07-02', 'domain': 'news_sentiment', 'fact_type': 'derived_fact', 'subject': 'market', 'value': 'sector_rankings returned 16 records'},
        {'id': 'subject:600519:quote:2026-07-02', 'domain': 'price', 'fact_type': 'derived_fact', 'symbol': '600519', 'subject': '600519', 'value': 'quote price=1193'},
        {'id': 'subject:600519:daily_data:2026-07-02', 'domain': 'price', 'fact_type': 'derived_fact', 'symbol': '600519', 'subject': '600519', 'value': 'daily data returned 40 rows'},
        {'id': 'subject:AAPL:fundamental:valuation:2026-07-02', 'domain': 'fundamentals', 'fact_type': 'derived_fact', 'symbol': 'AAPL', 'subject': 'AAPL', 'value': 'valuation available'},
        {'id': 'sec:AAPL:filing', 'domain': 'filings_events', 'fact_type': 'verified_fact', 'symbol': 'AAPL', 'subject': 'AAPL', 'value': 'SEC filing'},
        {'id': 'fred:DCOILWTICO:2026-06-22', 'domain': 'macro', 'fact_type': 'verified_fact', 'symbol': 'DCOILWTICO', 'value': 'oil'},
    ])
    _append_jsonl(run / 'subject_provider_runs.jsonl', [
        {'operation': 'main_indices', 'success': True, 'record_count': 5, 'symbol': 'market'},
        {'operation': 'market_stats', 'success': True, 'record_count': 6, 'symbol': 'market'},
        {'operation': 'sector_rankings', 'success': True, 'record_count': 16, 'symbol': 'market'},
        {'operation': 'realtime_quote', 'success': True, 'record_count': 1, 'symbol': '600519'},
        {'operation': 'daily_data', 'success': True, 'record_count': 40, 'symbol': '600519'},
        {'operation': 'fundamental_context', 'success': False, 'error_type': 'failed', 'record_count': 0, 'symbol': '600519'},
        {'operation': 'fundamental_context', 'success': True, 'record_count': 3, 'symbol': 'AAPL'},
    ])
    runtime_reports.mkdir()
    (runtime_reports / 'market_review_20260702.md').write_text('# 市场复盘\n市场震荡。', encoding='utf-8')
    (runtime_reports / 'report_20260702.md').write_text('# 个股分析\n600519 观察；AAPL 观察。', encoding='utf-8')
    records = [
        SimpleNamespace(
            id=1,
            query_id='q-market',
            created_at=datetime(2026, 7, 2, 8, 0),
            code='market_review',
            name='市场复盘',
            report_type='market_review',
            sentiment_score=None,
            operation_advice='',
            trend_prediction='',
            analysis_summary='A股结构分化。',
            raw_result=json.dumps({'analysis_summary': 'A股结构分化。', 'model_used': 'fake/model'}),
        ),
        SimpleNamespace(
            id=2,
            query_id='q-600519',
            created_at=datetime(2026, 7, 2, 8, 5),
            code='600519',
            name='贵州茅台',
            report_type='detailed',
            sentiment_score=58,
            operation_advice='观察',
            trend_prediction='震荡',
            analysis_summary='等待量价确认。',
            raw_result=json.dumps({
                'code': '600519',
                'name': '贵州茅台',
                'analysis_summary': '等待量价确认。',
                'risk_warning': '行业资金仍待确认。',
                'sentiment_score': 58,
                'operation_advice': '观察',
                'model_used': 'fake/model',
            }),
        ),
        SimpleNamespace(
            id=3,
            query_id='q-aapl',
            created_at=datetime(2026, 7, 2, 8, 10),
            code='AAPL',
            name='Apple',
            report_type='detailed',
            sentiment_score=62,
            operation_advice='持有',
            trend_prediction='震荡偏强',
            analysis_summary='基本面稳定，估值需复核。',
            raw_result=json.dumps({'analysis_summary': '基本面稳定，估值需复核。', 'model_used': 'fake/model'}),
        ),
    ]
    snapshot = export_original_analysis_snapshot(docs, date, symbols=['600519', 'AAPL'], records=records)

    payload = build_original_analysis_bundle(docs, date, runtime_reports_dir=runtime_reports)
    refs = load_original_analysis_refs(docs, date)

    assert payload['marketReviewAvailable'] is True
    assert payload['marketContextAvailable'] is True
    assert payload['stockContextCount'] >= 3
    assert payload['stockAnalysisCount'] == 2
    assert payload['structuredSnapshotAvailable'] is True
    assert payload['structuredSnapshotSha256'] == snapshot['sha256']
    assert payload['portfolioSnapshotAvailable'] is False
    assert (run / 'original_analysis.json').exists()
    assert (run / 'original_analysis_refs.jsonl').exists()
    assert any(row['kind'] == 'market_review' and 'MarketAgent' in row['agentTargets'] for row in refs)
    assert any(row['kind'] == 'market_snapshot' and 'MarketAgent' in row['agentTargets'] for row in refs)
    assert any(row['kind'] == 'technical_context' and row['symbols'] == ['600519'] for row in refs)
    assert any(row['kind'] == 'fundamental_context' and row['symbols'] == ['AAPL'] for row in refs)
    assert any(row['kind'] == 'geo_policy_seed' and 'GeoPolicyAgent' in row['agentTargets'] for row in refs)
    stock_ref = next(row for row in refs if row['kind'] == 'stock_analysis_output' and row['symbols'] == ['600519'])
    assert stock_ref['sourceKind'] == 'analysis_history_snapshot'
    assert stock_ref['recordId'] == 2
    assert stock_ref['analysis']['riskWarning'] == '行业资金仍待确认。'
    assert stock_ref['contentSha256']


def test_markdown_without_same_day_snapshot_is_not_treated_as_original_ai_output(tmp_path):
    docs = tmp_path / 'docs'
    runtime_reports = tmp_path / 'reports'
    date = '2026-07-02'
    run = docs / 'run_status' / date
    _write_json(run / 'daily_universe.json', {'subjectSymbols': ['600519'], 'groups': []})
    _write_json(run / 'source_health_v2.json', {'domains': {}})
    runtime_reports.mkdir()
    (runtime_reports / 'report_20260702.md').write_text('# 600519\n旧结论。', encoding='utf-8')

    payload = build_original_analysis_bundle(docs, date, runtime_reports_dir=runtime_reports)
    refs = load_original_analysis_refs(docs, date)

    assert payload['stockAnalysisCount'] == 0
    ref = next(row for row in refs if row['kind'] == 'stock_analysis_output')
    assert ref['status'] == 'empty'
    assert ref['sourceKind'] == 'legacy_report_file_only'
    assert '不作为 Agent 分析输入' in ref['summary']
