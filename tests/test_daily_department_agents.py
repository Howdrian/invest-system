from pathlib import Path
import json
import os
from types import SimpleNamespace

import pytest

from src.daily_department_agents import run_daily_department_agents
from src.daily_department_llm import (
    DEPARTMENT_SPECS,
    _build_context,
    _apply_semantic_gate_to_memo,
    _compact_universe_for_spec,
    _compact_evidence_row,
    _call_litellm_inline,
    _department_prompt,
    _evidence_for_spec,
    _fill_missing_memo_fields,
    _load_lightweight_llm_config,
    _model_preflight_error,
    _normalize_next_action,
    _parse_agent_output,
    _prompt_evidence_for_spec,
    _select_agent_model,
    _sanitize_data_gaps,
    _stock_summaries_for_spec,
    _valid_refs_for_spec,
    run_llm_daily_department_agents,
)
from src.cio_enrichment import run_cio_enrichment
from src.llm.generation_backend import GenerationCapabilities, GenerationResult
from src.report_artifact import build_daily_report_artifact


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')


def _append_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')


class FakeDepartmentBackend:
    backend_id = 'fake'
    capabilities = GenerationCapabilities(
        supports_json=True,
        supports_tools=False,
        supports_stream=False,
        supports_vision=False,
        supports_health_check=False,
        supports_smoke_test=False,
    )

    def __init__(self, *, hallucinate: bool = False):
        self.hallucinate = hallucinate
        self.calls = []
        self.generation_configs = []

    def generate(self, prompt, generation_config, *, system_prompt=None, stream=False, stream_progress_callback=None, response_validator=None, audit_context=None):
        payload = json.loads(prompt)
        agent = payload['agent']
        self.calls.append(agent)
        self.generation_configs.append(dict(generation_config or {}))
        refs = payload.get('allowedEvidenceRefs') or []
        evidence_rows = [row for row in payload.get('evidence') or [] if isinstance(row, dict) and row.get('id')]
        evidence_refs = [str(row.get('id')) for row in evidence_rows]
        ref = 'missing:evidence' if self.hallucinate else (evidence_refs[0] if evidence_refs else (refs[0] if refs else ''))
        evidence_value = str(evidence_rows[0].get('value') or '本轮直接证据已更新') if evidence_rows else '本轮直接证据已更新'
        supported_claim = f'本轮直接证据记录：{evidence_value}。'
        output = {
            'agent': agent,
            'summary_for_reader': f'本部门复核到{supported_claim}在其他直接证据形成一致方向前，本轮维持分层观察。',
            'key_claims': [
                {'claim': supported_claim, 'evidence_ids': [ref]},
                {'claim': '当前证据只支持观察，不足以外推为跨市场一致方向。', 'evidence_ids': [ref]},
            ],
            'evidence_ids': [ref],
            'counterpoints': ['若证据过时或公告缺失，结论需要下调置信度'],
            'data_gaps': [],
            'confidence': 'medium',
            'next_action': '下一轮继续核对证据、反证和触发条件。',
        }
        if agent == 'RedTeamAgent':
            output['challenges'] = [{
                'targetClaimId': 'MacroAgent:1',
                'issueType': 'alternative_cause',
                'opposingScenario': '若宏观证据发生变化，当前分层观察判断需要重评。',
                'evidence_ids': [ref],
                'falsifier': '新的官方宏观事实继续确认当前判断。',
            }]
        if agent == 'CIOAgent':
            output['adjudication'] = {
                'sharedFacts': ['现有证据支持分层观察。'],
                'baseCase': '当前维持震荡观察。',
                'strongestAlternative': '若关键证据变化，结论需要重评。',
                'judgment': '当前保持观察并等待触发条件。',
                'why': '直接证据仍支持克制判断。',
                'invalidationTriggers': ['若价格与公告同时转强。'],
            }
            output['next_action'] = {
                '不做什么': '不把单股变化外推为市场整体结论。',
                '看什么': '观察价格、公告和风险信号是否共振。',
                '下次复核什么': '复核市场宽度和关键公告。',
            }
        text = json.dumps(output, ensure_ascii=False)
        return GenerationResult(text=text, model='fake/model', provider='fake', backend='fake', usage={'total_tokens': 42})


def _daily_agent_fixture(tmp_path):
    docs = tmp_path / 'docs'
    date = '2026-07-01'
    run = docs / 'run_status' / date
    _write_json(run / 'daily_universe.json', {
        'mode': 'multi_subject_daily',
        'subjectSymbols': ['600519', 'AAPL'],
        'groups': [{'name': 'watchlist', 'symbols': ['600519', 'AAPL']}, {'name': 'market'}, {'name': 'macro'}],
    })
    _write_json(run / 'source_health_v2.json', {
        'schema': 'source_health_v2',
        'overallMode': 'FULL_REVIEW',
        'overallScore': 0.9,
        'domains': {'macro': {'status': 'available'}, 'portfolio': {'status': 'partial'}},
        'claimPolicy': {'canScore': True, 'canActionableAdvice': True, 'canPositionSizing': True, 'mustShowCaveat': False},
        'evidenceStats': {'verifiedFacts': 2, 'derivedFacts': 2, 'discoveryItems': 0, 'missingFacts': 0, 'missingCriticalFacts': 0},
        'blockingReasons': [],
    })
    _append_jsonl(run / 'evidence_ledger.jsonl', [
        {'id': 'fred:DGS10:2026-06-29', 'domain': 'macro', 'fact_type': 'verified_fact', 'value': 'DGS10=4.38'},
        {'id': 'fred:VIXCLS:2026-06-30', 'domain': 'macro', 'fact_type': 'verified_fact', 'value': 'VIXCLS=16.45'},
        {'id': 'subject:600519:quote', 'domain': 'price', 'fact_type': 'derived_fact', 'symbol': '600519', 'value': 'quote price=1193'},
        {'id': 'subject:AAPL:fundamental', 'domain': 'fundamentals', 'fact_type': 'derived_fact', 'symbol': 'AAPL', 'value': 'valuation available'},
        {'id': 'official:AAPL:sec', 'domain': 'filings_events', 'fact_type': 'verified_fact', 'symbol': 'AAPL', 'value': 'SEC filing'},
        {'id': 'subject:market:hot_stocks', 'domain': 'news_sentiment', 'fact_type': 'derived_fact', 'value': 'hot stocks available'},
        {'id': 'subject:portfolio:empty', 'domain': 'portfolio', 'fact_type': 'derived_fact', 'value': 'portfolio empty'},
    ])
    _append_jsonl(run / 'provider_runs.jsonl', [{'provider': 'FRED', 'operation': 'macro_context', 'success': True, 'record_count': 2}])
    _write_json(docs / 'official_events' / f'{date}.json', {'evidenceFacts': [{'provider': 'SEC', 'symbol': 'AAPL'}]})
    reports = tmp_path / 'reports'
    reports.mkdir()
    (reports / 'report_20260701.md').write_text('''# 决策仪表盘\n⚪ **贵州茅台(600519)**: 观望 | 评分 45 | 震荡偏空\n⚪ **Apple Inc.(AAPL)**: 观望 | 评分 36 | 看空\n''', encoding='utf-8')
    (reports / 'market_review_20260701.md').write_text('''# 🎯 大盘复盘\n\n## 2026-07-01 大盘复盘 📈\n今日市场结构性分化，沪指小幅上涨但成长指数回落。\n\n#### 行业板块领涨 Top 5\n| 排名 | 行业板块 | 涨跌幅 |\n|---|---|---|\n| 1 | 氟化工 | +9.38% |\n''', encoding='utf-8')
    return docs, reports, date


def test_run_daily_department_agents_writes_raw_cio_and_departments(tmp_path):
    docs, reports, date = _daily_agent_fixture(tmp_path)

    result = run_daily_department_agents(docs, date, runtime_reports_dir=reports)

    assert result['memoCount'] == 11
    geo = json.loads((docs / 'agent_memos' / date / 'market' / '03_geo_policy.json').read_text(encoding='utf-8'))
    assert geo['agent'] == 'GeoPolicyAgent'
    cio = json.loads((docs / 'agent_memos' / date / 'market' / '11_cio_report.json').read_text(encoding='utf-8'))
    assert cio['origin'] == 'RAW_AGENT'
    assert cio['agentRuntime'] == 'RULE'
    assert cio['agent'] == 'CIOAgent'
    assert '今日结论' in cio['summary_for_reader']
    sector = json.loads((docs / 'agent_memos' / date / 'market' / '04_candidate_review.json').read_text(encoding='utf-8'))
    assert sector['agent'] == 'SectorAgent'


def test_run_llm_daily_department_agents_writes_llm_memos_and_runtime_ledger(tmp_path):
    docs, reports, date = _daily_agent_fixture(tmp_path)
    backend = FakeDepartmentBackend()

    result = run_llm_daily_department_agents(
        docs,
        date,
        runtime_reports_dir=reports,
        backend_factory=lambda: backend,
        require_all_llm=True,
    )

    assert result['allLlmSucceeded'] is True
    assert result['llmSuccessCount'] == 11
    assert result['fallbackCount'] == 0
    rows = [
        json.loads(line)
        for line in (docs / 'run_status' / date / 'llm_agent_runs.jsonl').read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]
    assert len(rows) == 11
    assert all(row['status'] == 'success' for row in rows)
    assert all('durationSeconds' in row for row in rows)
    assert all(row.get('attemptDurationsSeconds') for row in rows)
    assert result['totalAttempts'] == 11
    assert result['retryCount'] == 0
    assert result['llmElapsedSeconds'] >= 0
    assert result['tokenUsage']['totalTokens'] == 462
    # CIO may perform one controlled second pass after the department run.
    assert len(backend.generation_configs) >= 11
    assert all(config.get('response_format') == 'json_object' for config in backend.generation_configs)
    cio = json.loads((docs / 'agent_memos' / date / 'market' / '11_cio_report.json').read_text(encoding='utf-8'))
    assert cio['agentRuntime'] == 'LLM'
    assert cio['runtime_kind'] == 'llm_department_agent_v1'
    artifact = build_daily_report_artifact(docs, date)
    assert artifact['agentRuntimeSummary']['llm'] == 11
    assert artifact['agentRuntimeSummary']['ruleFallback'] == 0
    section_titles = [row['title'] for row in artifact['readerV3']['reportSections']]
    assert section_titles[:7] == ['市场状态', '宏观与地缘', '行业/风格', '候选观察', '重点个股', '持仓影响', '风险和反证']


def test_run_llm_daily_department_agents_resumes_only_failed_downstream_agents(tmp_path):
    docs, reports, date = _daily_agent_fixture(tmp_path)
    first_backend = FakeDepartmentBackend()
    run_llm_daily_department_agents(
        docs,
        date,
        runtime_reports_dir=reports,
        backend_factory=lambda: first_backend,
        require_all_llm=True,
    )

    run_path = docs / 'run_status' / date / 'llm_agent_runs.jsonl'
    run_rows = [json.loads(line) for line in run_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    failed_agents = {'RiskAgent', 'RedTeamAgent', 'CIOAgent'}
    for row in run_rows:
        if row['agent'] in failed_agents:
            row['status'] = 'fallback'
    _append_jsonl(run_path, run_rows)
    for spec in DEPARTMENT_SPECS:
        if spec.agent not in failed_agents:
            continue
        memo_path = docs / 'agent_memos' / date / f'{spec.rel}.json'
        memo = json.loads(memo_path.read_text(encoding='utf-8'))
        memo['agentRuntime'] = 'RULE_FALLBACK'
        memo['llm_status'] = 'fallback'
        _write_json(memo_path, memo)

    retry_backend = FakeDepartmentBackend()
    result = run_llm_daily_department_agents(
        docs,
        date,
        runtime_reports_dir=reports,
        backend_factory=lambda: retry_backend,
        require_all_llm=True,
        resume_successful=True,
    )

    assert result['allLlmSucceeded'] is True
    assert result['resumedSuccessCount'] == 8
    assert retry_backend.calls[:2] == ['RiskAgent', 'RedTeamAgent']
    assert set(retry_backend.calls[2:]) == {'CIOAgent'}


def test_run_llm_daily_department_agents_rejects_hallucinated_evidence_and_marks_fallback(tmp_path):
    docs, reports, date = _daily_agent_fixture(tmp_path)

    result = run_llm_daily_department_agents(
        docs,
        date,
        runtime_reports_dir=reports,
        backend_factory=lambda: FakeDepartmentBackend(hallucinate=True),
        max_retries=0,
    )

    assert result['fallbackCount'] == 11
    cio = json.loads((docs / 'agent_memos' / date / 'market' / '11_cio_report.json').read_text(encoding='utf-8'))
    assert cio['origin'] == 'RAW_AGENT'
    assert cio['agentRuntime'] == 'RULE_FALLBACK'
    assert cio['llm_status'] == 'fallback'


def test_daily_artifact_prefers_raw_cio_department(tmp_path):
    docs = tmp_path / 'docs'
    date = '2026-07-01'
    mc = docs / 'market_cycle' / date
    mc.mkdir(parents=True)
    (docs / 'daily').mkdir(parents=True)
    (docs / 'daily' / f'{date}.md').write_text('# daily', encoding='utf-8')
    _write_json(mc / '13_source_health.json', {'usability_verdict': 'usable', 'trade_review_usability': 'usable', 'rows': []})
    _write_json(mc / '14_market_strategy.json', {'regime': 'NEUTRAL_WATCH'})
    run = docs / 'run_status' / date
    _write_json(run / 'daily_universe.json', {'mode': 'multi_subject_daily', 'subjectSymbols': ['600519', 'AAPL'], 'groups': []})
    _write_json(run / 'source_health_v2.json', {
        'schema': 'source_health_v2', 'overallMode': 'FULL_REVIEW', 'overallScore': 0.9,
        'domains': {}, 'claimPolicy': {'canScore': True, 'canActionableAdvice': True, 'canPositionSizing': True, 'mustShowCaveat': False},
        'evidenceStats': {'verifiedFacts': 1, 'derivedFacts': 1, 'discoveryItems': 0, 'missingFacts': 0, 'missingCriticalFacts': 0},
    })
    _append_jsonl(run / 'evidence_ledger.jsonl', [{'id': 'fred:DGS10', 'domain': 'macro', 'fact_type': 'verified_fact', 'source_url': 'https://fred.stlouisfed.org/series/DGS10'}])
    memo_dir = docs / 'agent_memos' / date / 'market'
    _write_json(memo_dir / '11_cio_report.json', {
        'schema': 'agent_memo_v1', 'agent': 'CIOAgent', 'origin': 'RAW_AGENT', 'scope': 'daily', 'subject': 'daily',
        'summary_for_reader': '今日结论：CIO 已完成汇总。', 'key_claims': ['宏观和市场已复核'], 'evidence_ids': ['fred:DGS10'],
        'counterpoints': ['不要用单股覆盖日报'], 'data_gaps': [], 'confidence': 'medium', 'next_action': '明日复核。',
    })

    artifact = build_daily_report_artifact(docs, date)

    assert artifact['agentOrigins']['raw'] == 1
    assert artifact['readerBrief']['finalConclusion'].rstrip('。') == '今日结论：CIO 已完成汇总'
    assert any(row['agent'] == 'CIOAgent' and row['readerVisible'] for row in artifact['departmentReports'])


def test_lightweight_llm_config_agent_model_overrides_global_model(tmp_path, monkeypatch):
    env_file = tmp_path / '.env'
    env_file.write_text(
        '\n'.join([
            'LITELLM_MODEL=vertex_ai/gemini-2.5-flash',
            'AGENT_LITELLM_MODEL=vertex_ai/gemini-2.5-pro',
            'GEMINI_API_KEY=placeholder-key',
        ]) + '\n',
        encoding='utf-8',
    )
    monkeypatch.setenv('ENV_FILE', str(env_file))
    for key in ('LITELLM_MODEL', 'AGENT_LITELLM_MODEL', 'GEMINI_API_KEY', 'GEMINI_API_KEYS'):
        monkeypatch.delenv(key, raising=False)

    config = _load_lightweight_llm_config()

    assert config.agent_litellm_model == 'vertex_ai/gemini-2.5-pro'
    assert config.litellm_model == 'vertex_ai/gemini-2.5-pro'


@pytest.mark.parametrize(
    ("provider_env", "expected_model", "key_attr", "expected_base"),
    [
        ({"GEMINI_API_KEY": "gemini-only-key", "GEMINI_MODEL": "gemini-only"}, "gemini/gemini-only", "gemini_api_keys", None),
        ({"ANTHROPIC_API_KEY": "anthropic-only-key", "ANTHROPIC_MODEL": "claude-only"}, "anthropic/claude-only", "anthropic_api_keys", None),
        ({"DEEPSEEK_API_KEY": "deepseek-only-key"}, "deepseek/deepseek-chat", "deepseek_api_keys", None),
        ({"OPENAI_API_KEY": "openai-only-key", "OPENAI_MODEL": "gpt-only", "OPENAI_BASE_URL": "https://openai.example/v1"}, "openai/gpt-only", "openai_api_keys", "https://openai.example/v1"),
        ({"AIHUBMIX_KEY": "aihubmix-only-key", "OPENAI_MODEL": "mix-only"}, "openai/mix-only", "openai_api_keys", "https://aihubmix.com/v1"),
        ({"ANSPIRE_API_KEYS": "anspire-only-key", "ANSPIRE_LLM_MODEL": "anspire-only", "ANSPIRE_LLM_BASE_URL": "https://anspire.example/v6"}, "openai/anspire-only", "openai_api_keys", "https://anspire.example/v6"),
    ],
)
def test_lightweight_llm_config_resolves_only_legacy_provider_without_env_pollution(
    tmp_path,
    monkeypatch,
    provider_env,
    expected_model,
    key_attr,
    expected_base,
):
    legacy_keys = {
        "GEMINI_API_KEY", "GEMINI_API_KEYS", "GEMINI_MODEL", "GEMINI_MODEL_FALLBACK",
        "ANTHROPIC_API_KEY", "ANTHROPIC_API_KEYS", "ANTHROPIC_MODEL",
        "DEEPSEEK_API_KEY", "DEEPSEEK_API_KEYS", "OPENAI_API_KEY", "OPENAI_API_KEYS",
        "OPENAI_MODEL", "OPENAI_BASE_URL", "AIHUBMIX_KEY", "ANSPIRE_API_KEYS",
        "ANSPIRE_LLM_MODEL", "ANSPIRE_LLM_BASE_URL", "ANSPIRE_LLM_ENABLED",
        "LITELLM_MODEL", "LITELLM_FALLBACK_MODELS", "LLM_CHANNELS",
    }
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(f"{key}={value}" for key, value in provider_env.items()) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ENV_FILE", str(env_file))
    for key in legacy_keys:
        monkeypatch.delenv(key, raising=False)

    config = _load_lightweight_llm_config()

    assert config.litellm_model == expected_model
    assert getattr(config, key_attr) == [next(iter(value for key, value in provider_env.items() if key.endswith("KEY") or key == "ANSPIRE_API_KEYS"))]
    assert config.openai_base_url == expected_base
    assert all(key not in os.environ for key in provider_env)


def test_lightweight_llm_config_forwards_vertex_adc_project_and_global_location(tmp_path, monkeypatch):
    env_file = tmp_path / '.env'
    env_file.write_text(
        '\n'.join([
            'AGENT_LITELLM_MODEL=vertex_ai/gemini-3.5-flash',
            'VERTEXAI_PROJECT=project-test',
            'VERTEXAI_LOCATION=global',
        ]) + '\n',
        encoding='utf-8',
    )
    monkeypatch.setenv('ENV_FILE', str(env_file))
    for key in ('AGENT_LITELLM_MODEL', 'VERTEXAI_PROJECT', 'VERTEXAI_LOCATION'):
        monkeypatch.delenv(key, raising=False)

    config = _load_lightweight_llm_config()

    assert config.agent_litellm_model == 'vertex_ai/gemini-3.5-flash'
    assert config.runtime_env['VERTEXAI_PROJECT'] == 'project-test'
    assert config.runtime_env['VERTEXAI_LOCATION'] == 'global'


def test_lightweight_llm_config_preserves_responses_channel_router_config(tmp_path, monkeypatch):
    env_file = tmp_path / '.env'
    env_file.write_text(
        '\n'.join([
            'LLM_CHANNELS=reports',
            'LLM_REPORTS_PROTOCOL=openai',
            'LLM_REPORTS_API_SURFACE=responses',
            'LLM_REPORTS_BASE_URL=https://responses.example.test/v1',
            'LLM_REPORTS_API_KEY=sk-reports-channel-test',
            'LLM_REPORTS_MODELS=gpt-5.6-sol',
            'AGENT_LITELLM_MODEL=openai/gpt-5.6-sol',
        ]) + '\n',
        encoding='utf-8',
    )
    monkeypatch.setenv('ENV_FILE', str(env_file))
    for key in (
        'LLM_CHANNELS', 'LLM_REPORTS_PROTOCOL', 'LLM_REPORTS_API_SURFACE',
        'LLM_REPORTS_BASE_URL', 'LLM_REPORTS_API_KEY', 'LLM_REPORTS_MODELS',
        'AGENT_LITELLM_MODEL', 'OPENAI_API_KEY', 'OPENAI_API_KEYS',
    ):
        monkeypatch.delenv(key, raising=False)

    config = _load_lightweight_llm_config()

    assert all(
        key not in os.environ
        for key in (
            'LLM_CHANNELS', 'LLM_REPORTS_PROTOCOL', 'LLM_REPORTS_API_SURFACE',
            'LLM_REPORTS_BASE_URL', 'LLM_REPORTS_API_KEY', 'LLM_REPORTS_MODELS',
            'AGENT_LITELLM_MODEL',
        )
    )
    assert config.agent_litellm_model == 'openai/gpt-5.6-sol'
    assert config.llm_channel_config_issues == []
    assert config.llm_model_list == [{
        'model_name': 'openai/gpt-5.6-sol',
        'litellm_params': {
            'model': 'openai/responses/gpt-5.6-sol',
            'api_key': 'sk-reports-channel-test',
            'api_base': 'https://responses.example.test/v1',
        },
        'model_info': {'dsa_api_surface': 'responses'},
    }]
    assert _model_preflight_error('openai/gpt-5.6-sol', config) == ''


def test_lightweight_llm_config_uses_yaml_responses_routes_without_mutating_env(tmp_path, monkeypatch):
    config_yaml = tmp_path / 'litellm.yaml'
    config_yaml.write_text(
        '\n'.join([
            'model_list:',
            '  - model_name: reports-sol',
            '    litellm_params:',
            '      model: openai/responses/gpt-5.6-sol',
            '      api_key: os.environ/REPORTS_API_KEY',
            '      api_base: https://responses.example.test/v1',
            '    model_info:',
            '      dsa_api_surface: responses',
            '  - model_name: reports-terra',
            '    litellm_params:',
            '      model: openai/responses/gpt-5.6-terra',
            '      api_key: os.environ/REPORTS_API_KEY',
        ]) + '\n',
        encoding='utf-8',
    )
    env_file = tmp_path / '.env'
    env_file.write_text(
        f'LITELLM_CONFIG={config_yaml}\nREPORTS_API_KEY=sk-yaml-reports-test\n',
        encoding='utf-8',
    )
    monkeypatch.setenv('ENV_FILE', str(env_file))
    for key in (
        'LITELLM_CONFIG', 'REPORTS_API_KEY', 'LLM_CHANNELS',
        'AGENT_LITELLM_MODEL', 'LITELLM_MODEL', 'LITELLM_FALLBACK_MODELS',
        'OPENAI_API_KEY', 'OPENAI_API_KEYS',
    ):
        monkeypatch.delenv(key, raising=False)

    config = _load_lightweight_llm_config()

    assert all(
        key not in os.environ
        for key in ('LITELLM_CONFIG', 'REPORTS_API_KEY', 'AGENT_LITELLM_MODEL', 'LITELLM_MODEL')
    )
    assert config.llm_models_source == 'litellm_config'
    assert config.litellm_model == 'reports-sol'
    assert config.litellm_fallback_models == ['reports-terra']
    assert config.llm_model_list[0]['litellm_params'] == {
        'model': 'openai/responses/gpt-5.6-sol',
        'api_key': 'sk-yaml-reports-test',
        'api_base': 'https://responses.example.test/v1',
    }
    assert config.llm_model_list[0]['model_info'] == {'dsa_api_surface': 'responses'}
    assert _model_preflight_error('reports-sol', config) == ''


@pytest.mark.parametrize("yaml_kind", ["missing", "empty"])
def test_lightweight_llm_config_invalid_explicit_yaml_fails_closed_without_lower_priority_fallback(
    tmp_path,
    monkeypatch,
    yaml_kind,
):
    config_yaml = tmp_path / 'litellm.yaml'
    if yaml_kind == "empty":
        config_yaml.write_text('model_list: []\n', encoding='utf-8')
    env_file = tmp_path / '.env'
    env_file.write_text(
        '\n'.join([
            f'LITELLM_CONFIG={config_yaml}',
            'LLM_CHANNELS=reports',
            'LLM_REPORTS_PROTOCOL=openai',
            'LLM_REPORTS_API_SURFACE=responses',
            'LLM_REPORTS_API_KEY=sk-reports-channel-test',
            'LLM_REPORTS_MODELS=gpt-5.6-sol',
            'AGENT_LITELLM_MODEL=gemini/gemini-3-flash-preview',
            'GEMINI_API_KEY=sk-gemini-legacy-test',
        ]) + '\n',
        encoding='utf-8',
    )
    monkeypatch.setenv('ENV_FILE', str(env_file))
    for key in (
        'LITELLM_CONFIG', 'LLM_CHANNELS', 'LLM_REPORTS_PROTOCOL',
        'LLM_REPORTS_API_SURFACE', 'LLM_REPORTS_API_KEY', 'LLM_REPORTS_MODELS',
        'AGENT_LITELLM_MODEL', 'GEMINI_API_KEY', 'GEMINI_API_KEYS',
        'OPENAI_API_KEY', 'OPENAI_API_KEYS',
    ):
        monkeypatch.delenv(key, raising=False)

    config = _load_lightweight_llm_config()

    assert config.llm_models_source == 'litellm_config'
    assert config.llm_model_list == []
    assert config.llm_channels == []
    assert config.llm_blocks_legacy_fallback is True
    assert [issue['code'] for issue in config.llm_channel_config_issues] == [
        'invalid_litellm_config'
    ]
    assert config.gemini_api_keys == ['sk-gemini-legacy-test']
    assert _model_preflight_error(config.litellm_model, config) == 'llm_channel_config_invalid'


def test_lightweight_llm_config_invalid_surface_fails_closed(tmp_path, monkeypatch):
    env_file = tmp_path / '.env'
    env_file.write_text(
        '\n'.join([
            'LLM_CHANNELS=reports',
            'LLM_REPORTS_PROTOCOL=openai',
            'LLM_REPORTS_API_SURFACE=respones',
            'LLM_REPORTS_API_KEY=sk-reports-channel-test',
            'LLM_REPORTS_MODELS=gpt-5.6-sol',
            'AGENT_LITELLM_MODEL=gemini/gemini-3-flash-preview',
            'GEMINI_API_KEY=sk-gemini-legacy-test',
        ]) + '\n',
        encoding='utf-8',
    )
    monkeypatch.setenv('ENV_FILE', str(env_file))
    for key in (
        'LLM_CHANNELS', 'LLM_REPORTS_PROTOCOL', 'LLM_REPORTS_API_SURFACE',
        'LLM_REPORTS_API_KEY', 'LLM_REPORTS_MODELS', 'AGENT_LITELLM_MODEL',
        'GEMINI_API_KEY', 'GEMINI_API_KEYS',
        'OPENAI_API_KEY', 'OPENAI_API_KEYS',
    ):
        monkeypatch.delenv(key, raising=False)

    config = _load_lightweight_llm_config()

    assert config.llm_model_list == []
    assert [issue['code'] for issue in config.llm_channel_config_issues] == ['invalid_api_surface']
    assert config.gemini_api_keys == ['sk-gemini-legacy-test']
    assert _model_preflight_error('gemini/gemini-3-flash-preview', config) == 'llm_channel_config_invalid'


def test_responses_alias_uses_router_deployment(monkeypatch):
    import litellm

    captured = {}

    class FakeRouter:
        def __init__(self, *, model_list, num_retries):
            captured['model_list'] = model_list
            captured['num_retries'] = num_retries

        def completion(self, **kwargs):
            captured['kwargs'] = kwargs
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
            )

    model_list = [{
        'model_name': 'openai/gpt-5.6-sol',
        'litellm_params': {
            'model': 'openai/responses/gpt-5.6-sol',
            'api_key': 'sk-router-test',
            'api_base': 'https://responses.example.test/v1',
        },
        'model_info': {'dsa_api_surface': 'responses'},
    }]
    monkeypatch.setattr(litellm, 'Router', FakeRouter)

    text, usage = _call_litellm_inline(
        {'model': 'openai/gpt-5.6-sol', 'messages': [{'role': 'user', 'content': 'test'}]},
        model_list,
        {},
    )

    assert text == '{"ok": true}'
    assert usage['total_tokens'] == 3
    assert captured['model_list'] == model_list
    assert captured['kwargs']['model'] == 'openai/gpt-5.6-sol'


def test_department_prompt_is_scoped_to_agent_domain(tmp_path):
    docs, reports, date = _daily_agent_fixture(tmp_path)
    (reports / 'report_20260701.md').write_text('STOCK_ONLY_SECRET_PRICE_CONTEXT', encoding='utf-8')
    (reports / 'market_review_20260701.md').write_text('MARKET_ONLY_SECRET_CONTEXT', encoding='utf-8')
    context = _build_context(docs, date, reports)
    macro = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'MacroAgent')
    refs = _valid_refs_for_spec(context, macro, {})

    prompt = json.loads(_department_prompt(macro, context, {}, refs, previous_error=''))

    for removed_key in (
        'providerSummary',
        'upstreamStockSummaries',
        'marketSnapshot',
        'officialEventsSummary',
        'reportExcerpts',
        'qualityBar',
    ):
        assert removed_key not in prompt
    assert 'MARKET_ONLY_SECRET_CONTEXT' not in json.dumps(prompt, ensure_ascii=False)
    assert 'STOCK_ONLY_SECRET_PRICE_CONTEXT' not in json.dumps(prompt, ensure_ascii=False)
    assert 'subject:600519:quote' not in prompt['allowedEvidenceRefs']
    assert 'dailyUniverse' not in prompt['allowedEvidenceRefs']
    assert not any(ref.startswith('kind:') for ref in prompt['allowedEvidenceRefs'])
    assert all(ref in {row['id'] for row in prompt['evidence']} for ref in prompt['allowedEvidenceRefs'])
    assert set(prompt['sourceHealth']['domains']).issubset({'macro'})
    assert prompt['departmentInputProfile']['inputProfile'] == 'macro'
    rules = '\n'.join(prompt['analysisRules'])
    assert '10Y-3M' in rules
    assert '联邦基金利率' in rules
    assert prompt['outputContract']['format'] == 'json_object'


def test_technical_prompt_requires_actual_structure_not_row_count(tmp_path):
    docs, reports, date = _daily_agent_fixture(tmp_path)
    context = _build_context(docs, date, reports)
    technical = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'TechnicalAgent')
    refs = _valid_refs_for_spec(context, technical, {})

    prompt = json.loads(_department_prompt(technical, context, {}, refs, previous_error=''))

    rules = '\n'.join(prompt['analysisRules'])
    assert 'returned N rows' in rules
    assert '破位' in rules
    assert '10Y-3M' not in rules


def test_cio_prompt_calibrates_systemic_risk_and_intraday_language(tmp_path):
    docs, reports, date = _daily_agent_fixture(tmp_path)
    context = _build_context(docs, date, reports)
    cio = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'CIOAgent')
    refs = _valid_refs_for_spec(context, cio, {})

    prompt = json.loads(_department_prompt(cio, context, {}, refs, previous_error=''))

    rules = '\n'.join(prompt['analysisRules'])
    assert '至少两类直接证据' in rules
    assert '红队不能因更悲观而自动胜出' in rules
    assert 'session_phase=intraday' in rules
    assert '当前更符合/基准解释是' in rules
    assert 'range_position_pct=100' in rules
    assert '必须消解部门冲突' in rules
    assert 'originalAnalysisRefs' not in prompt
    assert 'originalAnalysisSummary' not in prompt


def test_department_prompt_does_not_repeat_role_avoid_rules_in_analysis_rules(tmp_path):
    docs, reports, date = _daily_agent_fixture(tmp_path)
    context = _build_context(docs, date, reports)
    sector = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'SectorAgent')
    refs = _valid_refs_for_spec(context, sector, {})

    prompt = json.loads(_department_prompt(sector, context, {}, refs, previous_error=''))

    assert prompt['rolePlaybook']['avoid']
    assert set(prompt['rolePlaybook']['avoid']).isdisjoint(prompt['analysisRules'])
    assert len(prompt['analysisRules']) == len(set(prompt['analysisRules']))


def test_first_wave_prompt_never_receives_unrelated_previous_department_outputs(tmp_path):
    docs, reports, date = _daily_agent_fixture(tmp_path)
    context = _build_context(docs, date, reports)
    technical = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'TechnicalAgent')
    previous = {
        'MacroAgent': {
            'agent': 'MacroAgent',
            'summary_for_reader': '不应进入技术部门的宏观结论',
            'key_claims': ['不应进入技术部门的宏观结论'],
        },
    }
    refs = _valid_refs_for_spec(context, technical, previous)

    prompt = json.loads(_department_prompt(technical, context, previous, refs, previous_error=''))

    assert prompt['previousDepartmentOutputs'] == {}
    assert '不应进入技术部门' not in json.dumps(prompt, ensure_ascii=False)


def test_cio_adjudication_uses_red_team_competing_scenario_when_model_omits_it():
    from src.daily_department_llm import _complete_cio_adjudication

    memo = {
        'summary_for_reader': '当前更符合结构分化，维持观察。',
        'key_claims': ['指数普遍承压，但信用利差未恶化。'],
        'adjudication': {
            'baseCase': '结构分化',
            'judgment': '维持观察',
            'why': '指数与信用证据更支持结构分化。',
        },
    }
    previous = {
        'RedTeamAgent': {
            'challenges': [{
                'opposingScenario': '若市场宽度和信用同步恶化，可能转为系统性收缩。',
                'falsifier': '市场宽度持续改善。',
            }],
        },
    }

    _complete_cio_adjudication(memo, previous)

    assert memo['adjudication']['strongestAlternative'].startswith('若市场宽度')
    assert memo['adjudication']['invalidationTriggers'] == ['市场宽度持续改善。']
    assert 'strongestAlternative' in memo['adjudicationNormalizedFields']


def test_department_evidence_selection_balances_domains_and_symbols():
    market = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'MarketAgent')
    rows = [
        {
            'id': f'subject:600519:price:{index}',
            'domain': 'price',
            'symbol': '600519',
            'fact_type': 'derived_fact',
            'provider': 'DataFetcherManager',
            'value': f'600519 price row {index}',
        }
        for index in range(30)
    ]
    rows.extend(
        [
            {'id': 'subject:AAPL:quote', 'domain': 'price', 'symbol': 'AAPL', 'fact_type': 'derived_fact', 'provider': 'YfinanceFetcher', 'value': 'AAPL quote'},
            {'id': 'subject:HK00700:quote', 'domain': 'price', 'symbol': 'HK00700', 'fact_type': 'derived_fact', 'provider': 'AkshareFetcher', 'value': 'HK quote'},
            {'id': 'subject:market:stats', 'domain': 'price', 'subject': 'market', 'fact_type': 'derived_fact', 'provider': 'DataFetcherManager', 'value': 'up=100 down=50'},
            {'id': 'fred:VIXCLS', 'domain': 'macro', 'symbol': 'VIXCLS', 'fact_type': 'verified_fact', 'provider': 'FRED', 'value': 'VIX=16'},
        ]
    )

    selected = _evidence_for_spec(rows, market, limit=8)
    selected_ids = {row['id'] for row in selected}

    assert {'subject:AAPL:quote', 'subject:HK00700:quote', 'subject:market:stats', 'fred:VIXCLS'} <= selected_ids


def test_department_evidence_selection_balances_markets_when_a_shares_arrive_first():
    technical = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'TechnicalAgent')
    rows = [
        {
            'id': f'subject:{symbol}:daily_data',
            'domain': 'price',
            'symbol': symbol,
            'fact_type': 'derived_fact',
            'provider': 'DataFetcherManager',
            'value': f'{symbol} close=10 volume_vs_avg20=1.0',
        }
        for symbol in [f'{index:06d}' for index in range(1, 16)]
    ]
    rows.extend([
        {
            'id': 'subject:AAPL:daily_data',
            'domain': 'price',
            'symbol': 'AAPL',
            'fact_type': 'derived_fact',
            'provider': 'YfinanceFetcher',
            'value': 'AAPL close=220 volume_vs_avg20=1.1',
        },
        {
            'id': 'subject:HK00700:daily_data',
            'domain': 'price',
            'symbol': 'HK00700',
            'fact_type': 'derived_fact',
            'provider': 'YfinanceFetcher',
            'value': 'HK00700 close=500 volume_vs_avg20=0.9',
        },
    ])

    selected = _evidence_for_spec(rows, technical, limit=12)
    selected_symbols = {str(row.get('symbol') or '') for row in selected}

    assert 'AAPL' in selected_symbols
    assert 'HK00700' in selected_symbols
    assert any(symbol.isdigit() and len(symbol) == 6 for symbol in selected_symbols)


def test_department_universe_and_stock_summaries_balance_markets():
    fundamental = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'FundamentalAgent')
    symbols = [f'{index:06d}' for index in range(1, 16)] + ['AAPL', 'MSFT', 'HK00700']
    universe = {
        'mode': 'multi_subject_daily',
        'subjectSymbols': symbols,
        'groups': [{'name': 'watchlist', 'symbols': symbols}],
    }
    summaries = [{'code': symbol, 'name': symbol, 'summary': f'{symbol} summary'} for symbol in symbols]

    compact = _compact_universe_for_spec(universe, fundamental)
    selected_summaries = _stock_summaries_for_spec(summaries, fundamental)
    selected_symbols = set(compact['subjectSymbols'])
    summary_symbols = {str(row.get('code') or row.get('symbol') or '') for row in selected_summaries}

    assert {'AAPL', 'HK00700'} <= selected_symbols
    assert {'AAPL', 'HK00700'} <= summary_symbols


def test_missing_evidence_ids_are_not_silently_invented():
    technical = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'TechnicalAgent')
    memo = {
        'counterpoints': ['若量价结构变化，当前判断需要复核。'],
        'next_action': '观察成交量与区间边界。',
        'evidence_ids': [],
    }

    _fill_missing_memo_fields(memo, technical, {'subject:600519:daily_data'})

    assert memo['evidence_ids'] == []


def test_cio_next_action_mapping_is_rendered_as_clean_reader_text():
    value = _normalize_next_action({
        '不做什么': '不要追高；；',
        '看什么': '1. 看成交额；；2. 看市场宽度',
        '下次复核什么': '复核公告；',
    })

    assert "{'" not in value
    assert '；；' not in value
    assert value.startswith('不做什么：不要追高')


def test_existing_direct_spread_series_removes_false_dgs2_gap():
    gaps = _sanitize_data_gaps(
        ['缺少当日DGS2，导致无法计算最新10Y-2Y利差。', '缺少持仓快照。'],
        evidence_rows=[{
            'id': 'fred:T10Y2Y:2026-07-13',
            'metric': 'T10Y2Y',
            'value': 'T10Y2Y=0.36',
        }],
    )

    assert gaps == ['缺少持仓快照。']


def test_downstream_agent_cannot_cite_evidence_omitted_from_its_prompt():
    risk = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'RiskAgent')
    rows = [
        {
            'id': f'subject:{symbol}:quote',
            'domain': 'price',
            'symbol': symbol,
            'fact_type': 'derived_fact',
            'provider': 'DataFetcherManager',
            'value': f'{symbol} price=10',
        }
        for symbol in [f'{index:06d}' for index in range(1, 31)] + ['AAPL', 'HK00700']
    ]
    context = {'evidence': rows, 'originalAnalysisRefs': []}

    selected_ids = {
        str(row['id'])
        for row in _evidence_for_spec(rows, risk, limit=24)
    }
    valid_refs = _valid_refs_for_spec(context, risk, {})
    omitted_ids = {str(row['id']) for row in rows} - selected_ids

    assert omitted_ids
    assert omitted_ids.isdisjoint(valid_refs)


def test_downstream_prompt_includes_exact_evidence_used_by_dependencies():
    risk = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'RiskAgent')
    rows = [
        {
            'id': f'noise:{index}',
            'domain': 'macro',
            'subject': f'NOISE{index}',
            'fact_type': 'verified_fact',
            'provider': 'FRED',
            'value': f'noise={index}',
        }
        for index in range(20)
    ]
    rows.extend([
        {
            'id': 'fred:T10Y2Y:2026-07-14',
            'domain': 'macro',
            'subject': 'T10Y2Y',
            'fact_type': 'verified_fact',
            'provider': 'FRED',
            'value': 'T10Y2Y=0.36',
        },
        {
            'id': 'fred:DGS2:2026-07-14',
            'domain': 'macro',
            'subject': 'DGS2',
            'fact_type': 'verified_fact',
            'provider': 'FRED',
            'value': 'DGS2=4.21',
        },
    ])
    previous = {
        'MacroAgent': {
            'claim_evidence': [{
                'claim': '10Y-2Y 利差为正。',
                'evidence_ids': ['fred:T10Y2Y:2026-07-14', 'fred:DGS2:2026-07-14'],
            }],
            'evidence_ids': ['fred:T10Y2Y:2026-07-14', 'fred:DGS2:2026-07-14'],
        }
    }
    context = {'evidence': rows, 'originalAnalysisRefs': []}

    selected_ids = {
        str(row['id'])
        for row in _prompt_evidence_for_spec(context, risk, previous)
    }
    valid_refs = _valid_refs_for_spec(context, risk, previous)

    assert {'fred:T10Y2Y:2026-07-14', 'fred:DGS2:2026-07-14'} <= selected_ids
    assert selected_ids <= valid_refs


def test_compact_evidence_keeps_canonical_measurements_for_agent_prompt():
    row = _compact_evidence_row(
        {
            'id': 'subject:market:market_stats',
            'domain': 'price',
            'subject': 'market',
            'metric': 'market_stats',
            'fact_type': 'derived_fact',
            'measurements': {'up_count': 4211, 'total_amount_100m_cny': 27040},
            'value': 'market_stats',
        },
        domain='price',
    )

    assert row['metric'] == 'market_stats'
    assert row['measurements'] == {'up_count': 4211, 'total_amount_100m_cny': 27040}


def test_cio_context_always_contains_canonical_market_snapshot():
    cio = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'CIOAgent')
    rows = [
        {
            'id': f'fred:SERIES_{index}',
            'domain': 'macro',
            'subject': f'SERIES_{index}',
            'fact_type': 'verified_fact',
            'value': f'SERIES_{index}=1',
        }
        for index in range(20)
    ]
    rows.extend([
        {
            'id': 'subject:market:market_stats:2026-07-15',
            'domain': 'price',
            'subject': 'market',
            'metric': 'market_stats',
            'fact_type': 'derived_fact',
            'measurements': {'up_count': 3350, 'down_count': 2098},
            'value': 'up_count=3350 down_count=2098',
        },
        {
            'id': 'subject:market:main_indices:2026-07-15',
            'domain': 'price',
            'subject': 'market',
            'metric': 'main_indices',
            'fact_type': 'derived_fact',
            'measurements': {'index_sh000688_change_pct': -4.25},
            'value': 'index_sh000688_change_pct=-4.25',
        },
    ])

    selected = _prompt_evidence_for_spec({'evidence': rows}, cio, {})
    ids = {row['id'] for row in selected}

    assert 'subject:market:market_stats:2026-07-15' in ids
    assert 'subject:market:main_indices:2026-07-15' in ids


def test_market_prompt_prioritizes_each_available_market_index_scope():
    market = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'MarketAgent')
    rows = [
        {
            'id': f'subject:{subject}:main_indices:2026-07-17',
            'domain': 'price',
            'subject': subject,
            'market': region,
            'metric': 'main_indices',
            'fact_type': 'derived_fact',
            'value': f'{region} main indices',
        }
        for subject, region in (('market', 'cn'), ('market_hk', 'hk'), ('market_us', 'us'))
    ]
    selected = _prompt_evidence_for_spec({'evidence': rows}, market, {})

    assert {row['market'] for row in selected} == {'cn', 'hk', 'us'}


def test_rejected_detail_claim_cannot_reenter_public_summary_through_all_memo_refs():
    spec = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'GeoPolicyAgent')
    memo = {
        'summary_for_reader': '美国商务部发布出口限制公告。该限制将直接导致AAPL下跌。',
        'key_claims': ['美国商务部发布出口限制公告。', '该限制将直接导致AAPL下跌。'],
        'evidence_ids': ['official:bis:1', 'subject:AAPL:quote'],
        'claim_evidence': [
            {'claim': '美国商务部发布出口限制公告。', 'claimType': 'fact', 'subject': 'macro', 'domain': 'filings_events', 'evidence_ids': ['official:bis:1']},
            {'claim': '该限制将直接导致AAPL下跌。', 'claimType': 'interpretation', 'subject': 'MSFT', 'domain': 'price', 'evidence_ids': ['official:bis:1', 'subject:AAPL:quote']},
        ],
        'counterpoints': ['若公司供应链不受限制，价格影响可能很小。'],
        'next_action': '复核公司公告与供应链暴露。',
        'data_gaps': [],
    }
    evidence = [
        {'id': 'official:bis:1', 'fact_type': 'verified_fact', 'domain': 'filings_events', 'subject': 'macro', 'provider': 'BIS', 'value': '美国商务部发布出口限制公告', 'source_url': 'https://www.bis.gov/example'},
        {'id': 'subject:AAPL:quote', 'fact_type': 'derived_fact', 'domain': 'price', 'subject': 'AAPL', 'metric': 'realtime_quote', 'value': 'AAPL change_pct=-1.0', 'raw_path': 'raw.json'},
    ]

    _apply_semantic_gate_to_memo(memo, spec, evidence)

    assert '将直接导致' not in memo['summary_for_reader']
    assert '美国商务部发布出口限制公告' in memo['summary_for_reader']


def test_structured_claims_keep_claim_level_evidence_mapping():
    from src.daily_department_llm import GenerationResult, _payload_to_memo, _validate_memo

    spec = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'TechnicalAgent')
    payload = {
        'summary_for_reader': '技术结构保持震荡，现有证据不足以确认趋势性破位，需要等待量价共同确认。',
        'key_claims': [
            {
                'claim': '最新价格仍在观察区间内，不能仅凭单日跌幅认定破位。',
                'evidence_ids': ['subject:600519:daily_data'],
            }
        ],
        'evidence_ids': ['subject:600519:daily_data'],
        'counterpoints': ['若后续放量跌破区间下沿，震荡判断失效。'],
        'data_gaps': [],
        'confidence': 'medium',
        'next_action': '观察区间下沿和成交量是否同步失守。',
    }
    generation = GenerationResult(text='{}', model='fake/model', provider='fake', backend='fake', usage={})

    memo = _payload_to_memo(spec, '2026-07-09', payload, generation)
    _validate_memo(memo, spec, {'subject:600519:daily_data'})

    assert memo['key_claims'] == ['最新价格仍在观察区间内，不能仅凭单日跌幅认定破位。']
    assert memo['claim_evidence'] == [
        {
            'claim': '最新价格仍在观察区间内，不能仅凭单日跌幅认定破位。',
            'evidence_ids': ['subject:600519:daily_data'],
        }
    ]


def test_structured_llm_conclusion_can_supply_missing_claim_list():
    from src.daily_department_llm import GenerationResult, _payload_to_memo, _validate_memo

    spec = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'GeoPolicyAgent')
    payload = {
        'summary_for_reader': '地缘冲突暂未形成可验证的新增市场冲击，当前只保留能源和制裁升级的条件情景。',
        'evidence_ids': ['reliefweb:middle-east'],
        'counterpoints': ['若官方制裁或航运中断升级，风险传导判断需要立即上调。'],
        'data_gaps': [],
        'confidence': 'medium',
        'next_action': '继续核对官方制裁清单、航运和能源价格是否同步变化。',
    }
    generation = GenerationResult(text='{}', model='fake/model', provider='fake', backend='fake', usage={})

    memo = _payload_to_memo(spec, '2026-07-16', payload, generation)
    _validate_memo(memo, spec, {'reliefweb:middle-east'})

    assert memo['key_claims'] == [payload['summary_for_reader']]


def test_geo_policy_agent_gets_geo_policy_pack(tmp_path):
    docs, reports, date = _daily_agent_fixture(tmp_path)
    context = _build_context(docs, date, reports)
    geo = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'GeoPolicyAgent')
    refs = _valid_refs_for_spec(context, geo, {})

    prompt = json.loads(_department_prompt(geo, context, {}, refs, previous_error=''))

    assert prompt['departmentInputProfile']['inputProfile'] == 'geo_policy'
    assert any(row['kind'] == 'geo_policy_seed' for row in prompt['originalAnalysisRefs'])
    assert set(prompt['sourceHealth']['domains']).issubset({'macro', 'news_sentiment', 'filings_events'})


def test_geo_policy_pack_prioritizes_current_geo_discovery_and_keeps_time_labels():
    geo = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'GeoPolicyAgent')
    rows = [
        {
            'id': f'noise:{index}',
            'domain': 'news_sentiment',
            'subject': 'market',
            'fact_type': 'derived_fact',
            'provider': 'DataFetcherManager',
            'value': f'market noise {index}',
        }
        for index in range(30)
    ]
    rows.extend(
        [
            {
                'id': 'tavily:iran-oil',
                'domain': 'news_sentiment',
                'subject': 'market',
                'fact_type': 'discovery',
                'provider': 'Tavily',
                'value': 'Oil prices react to Iran conflict discovery',
                'published_at': '2026-07-13T12:00:00Z',
            },
            {
                'id': 'reliefweb:middle-east',
                'domain': 'news_sentiment',
                'subject': 'market',
                'fact_type': 'discovery',
                'provider': 'RELIEFWEB',
                'value': 'Middle East situation report',
                'published_at': '2026-07-12T00:00:00Z',
            },
            {
                'id': 'fred:vix',
                'domain': 'macro',
                'subject': 'VIXCLS',
                'fact_type': 'verified_fact',
                'provider': 'FRED',
                'value': 'VIX=15',
                'as_of': '2026-07-11',
            },
        ]
    )

    selected = _evidence_for_spec(rows, geo, limit=8)
    selected_by_id = {row['id']: row for row in selected}

    assert {'tavily:iran-oil', 'reliefweb:middle-east', 'fred:vix'} <= set(selected_by_id)
    assert selected_by_id['tavily:iran-oil']['published_at'] == '2026-07-13T12:00:00Z'


def test_intel_context_filters_personal_finance_noise_but_keeps_market_news():
    intel = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'IntelAgent')
    rows = [
        {
            'id': 'marketwatch:social-security',
            'domain': 'news_sentiment',
            'subject': 'market',
            'fact_type': 'discovery',
            'provider': 'MarketWatch Top Stories',
            'value': 'My brother claimed Social Security at 70. Why wait to claim?',
            'published_at': '2026-07-15T10:00:00Z',
        },
        {
            'id': 'marketwatch:inflation',
            'domain': 'news_sentiment',
            'subject': 'market',
            'fact_type': 'discovery',
            'provider': 'MarketWatch Top Stories',
            'value': 'Wholesale inflation falls as oil and gas prices decline.',
            'published_at': '2026-07-15T09:00:00Z',
        },
        {
            'id': 'cninfo:600519:notice',
            'domain': 'filings_events',
            'subject': '600519',
            'symbol': '600519',
            'fact_type': 'verified_fact',
            'provider': 'CNINFO',
            'value': '公司公告摘要',
            'as_of': '2026-07-15',
        },
    ]

    selected = _evidence_for_spec(rows, intel, limit=8)
    selected_ids = {row['id'] for row in selected}

    assert 'marketwatch:social-security' not in selected_ids
    assert {'marketwatch:inflation', 'cninfo:600519:notice'} <= selected_ids


def test_llm_agent_output_accepts_markdown_sections():
    spec = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'GeoPolicyAgent')

    payload = _parse_agent_output(
        '''## 结论
地缘政策风险中性偏观察。
## 依据
- GDELT 有事件线索
- OFAC 未发现关键命中
## 引用 evidence id
- gdelt:1
- memo:MacroAgent
## 反证
- 搜索线索不能当事实
## 数据缺口
- 无
## 下一步
继续跟踪制裁和能源价格。
## 置信度
medium
''',
        spec,
    )

    assert payload['_parse_status'] == 'parse_partial'
    assert payload['summary_for_reader'] == '地缘政策风险中性偏观察。'
    assert payload['evidence_ids'] == ['gdelt:1', 'memo:MacroAgent']
    assert payload['confidence'] == 'medium'


def test_llm_agent_output_accepts_pending_items_heading():
    spec = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'MacroAgent')

    payload = _parse_agent_output(
        '''## 结论
宏观风险偏好中性偏暖。
## 依据
- FRED 利率和信用利差已纳入。
## 引用 evidence id
- fred:DGS10:2026-06-29
## 反证
- 高利率仍压制估值。
## 待确认项
- 无
## 下一步
观察信用利差和 VIX 是否反向走阔。
## 置信度
medium
''',
        spec,
    )

    assert payload['_parse_status'] == 'parse_partial'
    assert payload['summary_for_reader'] == '宏观风险偏好中性偏暖。'
    assert payload['evidence_ids'] == ['fred:DGS10:2026-06-29']
    assert payload['data_gaps'] == []


def test_reader_punctuation_removes_adjacent_repeated_clause():
    from src.daily_department_llm import _clean_reader_punctuation

    assert _clean_reader_punctuation(
        '跨市场明显分化。A股风险偏好明显收缩；A股风险偏好明显收缩；仍需复核市场宽度'
    ) == '跨市场明显分化。A股风险偏好明显收缩；仍需复核市场宽度'


def test_summary_sentence_split_drops_punctuation_only_fragment():
    from src.daily_department_llm import _split_summary_sentences

    assert _split_summary_sentences('先看成交额。；2. 再看市场宽度。') == [
        '先看成交额。',
        '2. 再看市场宽度。',
    ]


def _macro_memo_with_claim(claim, refs):
    return {
        'schema': 'agent_memo_v1',
        'agent': 'MacroAgent',
        'summary_for_reader': '宏观部门已基于可比期限和当前证据完成复核，并保留必要的风险提示。',
        'key_claims': [claim],
        'claim_evidence': [{'claim': claim, 'evidence_ids': refs}],
        'evidence_ids': refs,
        'counterpoints': ['单点数据不能替代历史分布和跨期限比较。'],
        'data_gaps': [],
        'confidence': 'medium',
        'next_action': '继续观察利率、信用利差和波动率的同步变化。',
    }


def test_macro_agent_rejects_dgs10_vs_policy_rate_as_yield_curve():
    from src.daily_department_llm import _validate_memo

    spec = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'MacroAgent')
    refs = {'fred:DGS10:2026-06-29', 'fred:DFF:2026-06-29'}
    memo = _macro_memo_with_claim(
        '10年期美债收益率高于联邦基金利率，因此收益率曲线未倒挂。',
        list(refs),
    )

    with pytest.raises(ValueError, match='yield-curve claims require comparable Treasury maturities'):
        _validate_memo(memo, spec, refs)


def test_macro_agent_accepts_comparable_treasury_yield_curve_evidence():
    from src.daily_department_llm import _validate_memo

    spec = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'MacroAgent')
    refs = {'fred:DGS10:2026-06-29', 'fred:DGS2:2026-06-29'}
    memo = _macro_memo_with_claim(
        '10年期与2年期美债利差为正，当前收益率曲线未倒挂。',
        list(refs),
    )

    _validate_memo(memo, spec, refs)


def test_macro_agent_rejects_historical_level_claim_without_distribution_evidence():
    from src.daily_department_llm import _validate_memo

    spec = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'MacroAgent')
    refs = {'fred:BAMLH0A0HYM2:2026-06-30', 'fred:VIXCLS:2026-06-30'}
    memo = _macro_memo_with_claim(
        '高收益债信用利差和VIX均处于历史低位。',
        list(refs),
    )

    with pytest.raises(ValueError, match='historical-level claims require historical distribution evidence'):
        _validate_memo(memo, spec, refs)


def test_macro_agent_rejects_curve_change_without_spread_history():
    from src.daily_department_llm import _validate_memo

    spec = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'MacroAgent')
    refs = {'fred:T10Y2Y:2026-06-29'}
    memo = _macro_memo_with_claim('10Y-2Y利差为正，收益率曲线正在陡峭化。', list(refs))

    with pytest.raises(ValueError, match='curve-change claims require historical spread comparison'):
        _validate_memo(memo, spec, refs)


def test_cio_retries_when_claim_citations_do_not_cover_stated_numbers():
    from src.daily_department_llm import _validate_memo

    spec = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'CIOAgent')
    ref = 'subject:market:main_indices'
    memo = {
        'schema': 'agent_memo_v1',
        'agent': 'CIOAgent',
        'summary_for_reader': '今日市场结构分化，基准解释是局部科技去杠杆，整体流动性尚未转弱。',
        'key_claims': ['两市成交额为2.5万亿元。'],
        'claim_evidence': [{'claim': '两市成交额为2.5万亿元。', 'evidence_ids': [ref]}],
        'evidence_ids': [ref],
        'counterpoints': ['若市场宽度恶化，当前判断需要翻转。'],
        'next_action': '不做什么：不追高；看什么：市场宽度；下次复核什么：成交额。',
        'adjudication': {
            'baseCase': '结构分化',
            'judgment': '维持结构分化判断',
            'strongestAlternative': '系统性收缩',
            'why': '现有市场事实更支持结构分化。',
        },
        'semantic_validation': {
            'readerClaimCount': 1,
            'claims': [{'reasons': ['market_stat_not_supported_by_cited_evidence']}],
        },
    }

    with pytest.raises(ValueError, match='citations do not cover'):
        _validate_memo(memo, spec, {ref})


def test_cio_accepts_when_semantic_gate_dropped_bad_numeric_claim():
    from src.daily_department_llm import _validate_memo

    spec = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'CIOAgent')
    ref = 'subject:market:main_indices'
    retained = '市场宽度尚可，当前更符合结构性轮动，局部科技板块调整暂未扩散为全市流动性压力。'
    dropped = '两市成交额为2.5万亿元。'
    memo = {
        'schema': 'agent_memo_v1',
        'agent': 'CIOAgent',
        'summary_for_reader': retained,
        'key_claims': [retained],
        'claim_evidence': [{'claim': retained, 'evidence_ids': [ref]}],
        'evidence_ids': [ref],
        'counterpoints': ['若市场宽度恶化，当前判断需要翻转。'],
        'next_action': '不做什么：不追高；看什么：市场宽度；下次复核什么：成交额。',
        'adjudication': {
            'baseCase': '结构分化',
            'judgment': '维持结构分化判断',
            'strongestAlternative': '系统性收缩',
            'why': '现有市场事实更支持结构分化。',
        },
        'semantic_validation': {
            'readerClaimCount': 1,
            'claims': [
                {
                    'text': dropped,
                    'safeText': '',
                    'status': 'rejected',
                    'reasons': ['market_stat_not_supported_by_cited_evidence'],
                },
                {'text': retained, 'safeText': retained, 'status': 'supported', 'reasons': []},
            ],
        },
    }

    _validate_memo(memo, spec, {ref})


def test_macro_agent_rejects_invalid_methodology_for_markdown_without_claim_mapping():
    from src.daily_department_llm import _validate_memo

    spec = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'MacroAgent')
    refs = {'fred:DGS10:2026-06-29', 'fred:DFF:2026-06-29'}
    memo = _macro_memo_with_claim(
        '10年期美债收益率高于联邦基金利率，因此收益率曲线未倒挂。',
        list(refs),
    )
    memo['claim_evidence'] = []

    with pytest.raises(ValueError, match='yield-curve claims require comparable Treasury maturities'):
        _validate_memo(memo, spec, refs)


def test_macro_runtime_drops_unsupported_claim_but_keeps_valid_analysis():
    from src.daily_department_llm import _sanitize_macro_memo, _validate_memo

    spec = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'MacroAgent')
    refs = {'fred:DGS10:2026-06-29', 'fred:DFF:2026-06-29', 'fred:UNRATE:2026-05-01'}
    bad = '10年期美债收益率高于联邦基金利率，因此收益率曲线未倒挂。'
    good = '美国5月失业率为4.3%，劳动力市场尚未出现快速恶化。'
    memo = _macro_memo_with_claim(bad, list(refs))
    memo['summary_for_reader'] = f'{bad}{good}'
    memo['readable_summary'] = memo['summary_for_reader']
    memo['conclusion'] = memo['summary_for_reader']
    memo['key_claims'] = [bad, good]
    memo['claim_evidence'] = [
        {'claim': bad, 'evidence_ids': ['fred:DGS10:2026-06-29', 'fred:DFF:2026-06-29']},
        {'claim': good, 'evidence_ids': ['fred:UNRATE:2026-05-01']},
    ]

    _sanitize_macro_memo(memo)
    _validate_memo(memo, spec, refs)

    assert memo['key_claims'] == [good]
    assert '收益率曲线' not in memo['summary_for_reader']
    assert memo['methodology_warnings']


def test_llm_agent_output_accepts_chinese_keyed_json():
    spec = next(spec for spec in DEPARTMENT_SPECS if spec.agent == 'CIOAgent')

    payload = _parse_agent_output(
        json.dumps({
            '结论': '今日总判断：市场可以继续观察，但不能让单一股票覆盖全局结论。',
            '核心理由': ['宏观证据已刷新', '市场和行业需要分层看', '个股只进入下钻'],
            '引用 evidence id': ['fred:DGS10:2026-06-29', 'memo:RedTeamAgent'],
            '风险和反证': ['新闻发现不能直接当事实'],
            '数据缺口': [],
            '下一步': '明日先复核市场宽度、行业持续性和重点标的量价确认。',
            '置信度': 'medium',
        }, ensure_ascii=False),
        spec,
    )

    assert payload['_parse_status'] == 'structured'
    assert payload['summary_for_reader'].startswith('今日总判断')
    assert payload['key_claims'] == ['宏观证据已刷新', '市场和行业需要分层看', '个股只进入下钻']
    assert payload['evidence_ids'] == ['fred:DGS10:2026-06-29', 'memo:RedTeamAgent']
    assert payload['next_action'].startswith('明日先复核')
    assert payload['confidence'] == 'medium'


def test_model_selection_prefers_first_smoke_success(monkeypatch):
    config = object()
    calls = []

    def fake_smoke(model, _config):
        calls.append(model)
        return {
            'model': model,
            'status': 'success' if model == 'vertex_ai/gemini-2.5-pro' else 'failed',
            'error': '' if model == 'vertex_ai/gemini-2.5-pro' else 'not available',
        }

    monkeypatch.setattr('src.daily_department_llm._smoke_agent_model', fake_smoke)

    selection = _select_agent_model(config, model_policy='best')

    assert selection['selectedModel'] == 'vertex_ai/gemini-2.5-pro'
    assert calls[:3] == ['gemini/gemini-3.5-flash', 'vertex_ai/gemini-3.5-flash', 'vertex_ai/gemini-2.5-pro']


def test_cio_enrichment_reuses_existing_portfolio_evidence(tmp_path):
    docs, _reports, date = _daily_agent_fixture(tmp_path)
    run = docs / 'run_status' / date
    _write_json(run / 'source_health_v2.json', {
        'schema': 'source_health_v2',
        'overallMode': 'SCREEN_ONLY',
        'domains': {'portfolio': {'status': 'partial'}},
        'claimEvidence': {'claims': {'position_sizing': {'missingDomains': ['portfolio']}}},
    })
    memo = {
        'agent': 'CIOAgent',
        'data_gaps': ['缺少组合/持仓口径'],
    }

    summary = run_cio_enrichment(docs, date, memo)

    assert summary['requested'] is True
    assert summary['successCount'] == 0
    assert summary['reusedCount'] == 1
    assert summary['addedEvidenceIds'] == []
    assert summary['reusedEvidenceIds'] == ['subject:portfolio:empty']
    rows = [
        json.loads(line)
        for line in (run / 'evidence_ledger.jsonl').read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]
    assert not any(row.get('origin') == 'CIO_REQUESTED' for row in rows)
    assert (run / 'cio_data_requests.json').exists()
    assert (run / 'cio_enrichment_runs.jsonl').exists()
