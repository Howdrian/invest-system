# -*- coding: utf-8 -*-
"""LLM-backed daily research department agents.

This module upgrades the deterministic A-roll department layer with an online
LLM runtime.  It does not replace the rule engine: the rule engine is run first
as a safe fallback, then validated LLM outputs overwrite the corresponding
department memos.  Failed LLM calls stay visible in ``llm_agent_runs.jsonl`` and
fallback memos are explicitly marked so they cannot be mistaken for LLM output.
"""

from __future__ import annotations

import json
import multiprocessing
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Protocol, Sequence, Set

from src.daily_department_agents import (
    AGENT_MEMO_SCHEMA,
    ORIGIN,
    _EvidenceView,
    _load_jsonl,
    _market_snapshot,
    _memo,
    _parse_stock_summaries,
    _read_json,
    _read_text_first,
    _write_memo,
    run_daily_department_agents,
)
from src.llm.backend_factory import create_generation_backend
from src.llm.backend_registry import LITELLM_BACKEND_ID, resolve_agent_generation_backend_id
from src.llm.generation_backend import GenerationBackend, GenerationError, GenerationErrorCode, GenerationResult
from src.cio_enrichment import run_cio_enrichment
from src.department_data_profiles import department_profile_payload, filter_original_refs_for_agent
from src.original_analysis_adapter import build_original_analysis_bundle, load_original_analysis, load_original_analysis_refs
from src.research_core import ClaimStatus, validate_claim_dicts
from src.safe_diagnostics import sanitize_diagnostic_text
from src.source_health.run_matrix import sha256_file, upsert_run_matrix_stage


LLM_RUNTIME_KIND = "llm_department_agent_v1"
RULE_FALLBACK_RUNTIME_KIND = "evidence_driven_department_agent_v1"
LLM_RUNS_SCHEMA = "llm_agent_runs_v1"
CONTEXT_REFS = {"sourceHealth", "dailyUniverse", "providerSummary"}
MODEL_SELECTION_SCHEMA = "agent_model_selection_v1"
DEFAULT_MODEL_CANDIDATES = (
    "gemini/gemini-3.5-flash",
    "vertex_ai/gemini-3.5-flash",
    "vertex_ai/gemini-2.5-pro",
    "vertex_ai/gemini-2.5-flash",
)

FORBIDDEN_READER_TERMS = (
    "ReportArtifact",
    "sourceHealthV2",
    "providerMatrix",
    "RAW_AGENT",
    "DERIVED_FROM_ARTIFACT",
    "claimPolicy",
    "artifactId",
    "errorType",
    "fallbackTo",
    "recordCount",
    "runMatrix",
    "evidence_ledger",
    "provider_runs",
    "range_position_pct",
    "rows=",
    "premarket",
    "采纳红队",
)


class LLMBackendFactory(Protocol):
    def __call__(self) -> GenerationBackend:
        ...


@dataclass(frozen=True)
class DepartmentSpec:
    rel: str
    agent: str
    label: str
    scope: str
    mission: str
    input_domains: tuple[str, ...]
    depends_on: tuple[str, ...] = ()


DEPARTMENT_SPECS: tuple[DepartmentSpec, ...] = (
    DepartmentSpec(
        "market/02_macro_geopolitics",
        "MacroAgent",
        "宏观部门",
        "daily",
        "判断利率、流动性、通胀、就业、信用和风险偏好对今日市场的影响；不替代地缘政策部门。",
        ("macro",),
    ),
    DepartmentSpec(
        "market/03_geo_policy",
        "GeoPolicyAgent",
        "地缘政策部门",
        "daily",
        "判断贸易、制裁、冲突、政策事件及其对市场、行业和标的的传导。",
        ("macro", "news_sentiment", "filings_events"),
    ),
    DepartmentSpec(
        "market/03_market_strategy",
        "MarketAgent",
        "市场部门",
        "daily",
        "判断已有市场级数据覆盖范围内的大盘结构、宽度、资金面、指数和风险偏好。",
        ("price", "news_sentiment", "macro"),
    ),
    DepartmentSpec(
        "market/04_candidate_review",
        "SectorAgent",
        "行业/风格部门",
        "daily",
        "判断行业、风格、热点和候选池持续性，避免把热点误当交易事实。",
        ("news_sentiment", "price", "filings_events"),
    ),
    DepartmentSpec(
        "market/05_portfolio_review",
        "PortfolioAgent",
        "持仓部门",
        "portfolio",
        "判断 watchlist/持仓对组合暴露的影响；已确认空仓时说明范围，不把空仓写成数据缺口。",
        ("portfolio", "price", "fundamentals"),
    ),
    DepartmentSpec(
        "market/06_fundamental_review",
        "FundamentalAgent",
        "基本面部门",
        "daily",
        "判断财务、估值、公告、SEC/CNINFO 等事实是否支持当前候选。",
        ("fundamentals", "filings_events"),
    ),
    DepartmentSpec(
        "market/07_technical_review",
        "TechnicalAgent",
        "技术面部门",
        "daily",
        "判断指数和重点标的的趋势、量价、支撑压力和风险节奏。",
        ("price",),
    ),
    DepartmentSpec(
        "market/08_intel_review",
        "IntelAgent",
        "新闻情报部门",
        "daily",
        "区分公告事实、新闻线索和搜索 discovery，提炼事件影响。",
        ("filings_events", "news_sentiment"),
    ),
    DepartmentSpec(
        "market/09_risk_review",
        "RiskAgent",
        "风险部门",
        "daily",
        "归纳风险、反向证据和不应行动的条件。",
        ("price", "fundamentals", "filings_events", "macro", "news_sentiment", "portfolio"),
        depends_on=("MacroAgent", "GeoPolicyAgent", "MarketAgent", "SectorAgent", "FundamentalAgent", "TechnicalAgent", "IntelAgent", "PortfolioAgent"),
    ),
    DepartmentSpec(
        "market/10_red_team",
        "RedTeamAgent",
        "红队反证",
        "daily",
        "专门反驳前面部门结论，找证据跳跃、单股污染、过度乐观和 discovery 误用。",
        ("price", "fundamentals", "filings_events", "macro", "news_sentiment", "portfolio"),
        depends_on=("MacroAgent", "GeoPolicyAgent", "MarketAgent", "SectorAgent", "FundamentalAgent", "TechnicalAgent", "IntelAgent", "PortfolioAgent", "RiskAgent"),
    ),
    DepartmentSpec(
        "market/11_cio_report",
        "CIOAgent",
        "CIO 总结",
        "daily",
        "把各部门和红队结论编辑成默认 Reader 使用的最终投研日报。",
        ("price", "fundamentals", "filings_events", "macro", "news_sentiment", "portfolio"),
        depends_on=("MacroAgent", "GeoPolicyAgent", "MarketAgent", "SectorAgent", "FundamentalAgent", "TechnicalAgent", "IntelAgent", "PortfolioAgent", "RiskAgent", "RedTeamAgent"),
    ),
)


DEPARTMENT_PLAYBOOKS: Dict[str, Dict[str, Any]] = {
    "MacroAgent": {
        "role": "宏观策略师，不做个股结论，只判断全球/中国市场所处宏观风向。",
        "mustAnswer": [
            "当前风险偏好、利率、信用、通胀、增长分别给市场什么约束",
            "哪些宏观信号适用于 A/H/US，哪些只能作为外部背景",
            "未来 1-3 个最重要的宏观触发条件",
        ],
        "avoid": [
            "不要把美国宏观指标直接等同于中国市场结论",
            "不要重复待确认项，必须先提炼可用信号",
        ],
        "readerStyle": "像晨会宏观策略摘要：短、锋利、讲传导链。",
    },
    "GeoPolicyAgent": {
        "role": "地缘政策分析师，负责贸易、制裁、冲突、监管、供应链和政策事件传导。",
        "mustAnswer": [
            "哪些事件是 verified fact，哪些只是 discovery 线索",
            "事件影响到哪些市场、行业、供应链或标的",
            "需要回跳哪个官方源或公司 IR 才能升级判断",
            "逐项回应上下文中的最新地缘 discovery；有事件线索时不得笼统写成“未见重大事件”",
        ],
        "avoid": [
            "没有重大事件时不要硬编地缘风险",
            "不要把与本轮市场、行业、标的或传导链无关的全球新闻塞进结论",
        ],
        "readerStyle": "像政策/地缘风险简报：事件事实 -> 传导机制 -> 受益/受损资产 -> 失效条件。",
    },
    "MarketAgent": {
        "role": "市场策略师，先看指数、宽度、资金面、风险偏好，再看个股异动。",
        "mustAnswer": [
            "今日市场是趋势、震荡、轮动还是风险收缩",
            "单股异动是否污染了市场结论",
        ],
        "avoid": ["不要让 AAPL 或单一股票主导日报总判断", "不要把热点等同于趋势"],
        "readerStyle": "像交易台市场复盘：结构判断优先，个股只作证据。",
    },
    "SectorAgent": {
        "role": "行业/风格研究员，负责行业强弱、风格、候选池和热点持续性。",
        "mustAnswer": [
            "哪些行业/风格正在占优，持续性证据是什么",
            "候选清单里哪些只是热度，哪些有公告/价格/基本面支撑",
            "下一步筛选条件是什么",
        ],
        "avoid": [
            "不要把 hot_stocks 当交易结论",
            "concept_rankings 为空时用已拿到的 sector/hot/candidate 证据分析，不要整段阻断",
        ],
        "readerStyle": "像行业晨会：强弱排序、为什么、持续性、触发条件。",
    },
    "FundamentalAgent": {
        "role": "基本面分析师，负责财报、估值、公告、SEC/CNINFO/HKEX 和公司质量。",
        "mustAnswer": [
            "哪些标的有可追源基本面/公告/法披证据",
            "基本面证据支持还是反驳价格表现",
            "缺的是结构化财务模型、估值同业，还是公告事实",
        ],
        "avoid": [
            "不要因为某个 provider not_supported 就否定已有 SEC/CNINFO/HKEX/YFinance 事实",
            "不要编盈利预测",
        ],
        "readerStyle": "像基本面 memo：事实、解释、估值约束、缺口分清。",
    },
    "TechnicalAgent": {
        "role": "技术交易员，负责趋势、量价、支撑压力、节奏和失效条件。",
        "mustAnswer": [
            "每个重点标的的短期结构和方向风险",
            "哪些信号需要成交量/后续 K 线确认",
            "最清晰的触发价位或观察条件；没有价位就给条件",
        ],
        "avoid": ["不要只说上涨/下跌，要说是否可持续", "不要把 40 日数据说成长期结论"],
        "readerStyle": "像交易员复盘：结构、触发、失效、等待什么。",
    },
    "IntelAgent": {
        "role": "新闻情报分析师，负责公告、新闻、搜索线索、催化剂和舆情噪音过滤。",
        "mustAnswer": [
            "官方公告/法披里有什么实质事件",
            "新闻/搜索里有什么线索但尚未证实",
            "哪些事件可能成为催化剂，哪些是噪音",
        ],
        "avoid": [
            "不要堆新闻标题",
            "过滤个人理财、健康、生活方式和与本轮 universe 无关的监管杂讯",
        ],
        "readerStyle": "像情报 brief：事实、线索、噪音、后续核验。",
    },
    "PortfolioAgent": {
        "role": "组合经理助理，负责持仓、自选股、候选池和组合暴露。",
        "mustAnswer": [
            "本轮真实持仓是否为空；若为空，明确只看 watchlist/候选",
            "观察标的对组合风格暴露的潜在影响",
            "如果要补持仓，需要什么字段",
        ],
        "avoid": [
            "不要假设用户真实持仓",
            "不要因为持仓为空否定日报价值",
        ],
        "readerStyle": "像组合复盘：持仓事实、观察池影响、待补字段。",
    },
    "RiskAgent": {
        "role": "风险负责人，负责把所有可用证据转成风险清单和不应行动条件。",
        "mustAnswer": [
            "最大风险是什么，为什么重要",
            "哪些乐观结论最容易错",
            "什么信号出现会让风险判断升级/解除",
        ],
        "avoid": ["不要只重复各部门待确认项", "不要把局部待确认项写成系统不可用", "不要替代红队编造相反叙事"],
        "readerStyle": "像风控会：主风险、反证、触发条件。",
    },
    "RedTeamAgent": {
        "role": "红队，提出能解释同一组事实的最强竞争假设，不负责给最终建议。",
        "mustAnswer": [
            "是否存在单股污染、跨市场错配、过度外推、discovery 误用",
            "最强竞争解释是什么，它能解释哪些相同事实",
            "哪条证据或触发条件可以区分基准判断与竞争解释",
            "CIO 写结论时必须避开的陷阱",
        ],
        "avoid": [
            "不要重写一遍日报",
            "不要把所有结论都否定成无效",
        ],
        "readerStyle": "像投资委员会反方：直接、尖锐、有证据。",
    },
    "CIOAgent": {
        "role": "CIO/主编，只写最终读者报告，不暴露工程字段。",
        "mustAnswer": [
            "今日一句话总判断，不能只是可用/中性",
            "3-5 条核心理由，覆盖宏观、市场、行业/风格、个股、风险",
            "最大反证、下一步触发条件、哪些事不要做",
        ],
        "avoid": [
            "不要写 provider/run/ledger/error_type 这类工程词",
        ],
        "readerStyle": "像资深投研负责人给老板的晨会摘要：结论先行、依据清楚、反证强、下一步可执行。",
    },
}


GLOBAL_ANALYSIS_RULES: tuple[str, ...] = (
    "只使用本次 Context Pack；事实、解释、情景和建议分开写，每条核心判断绑定直接 evidence id。",
    "verified_fact/derived_fact 可支持事实；discovery、研报和原系统分析只能提出待验证假设。",
    "数字、主体、单位、报告期和时点必须逐字对账；不得估算、换算或把盘中数据写成收盘事实。",
    "判断范围跟随 dailyUniverse 动态变化；观察标的不能外推为整个市场。",
    "结论可以明确，但因果必须写传导机制和失效条件，相关性不得冒充已证实因果。",
    "只有会改变当前结论且现有证据未覆盖的内容才进入 data_gaps；否则返回空数组。",
)


AGENT_ANALYSIS_RULES: Dict[str, tuple[str, ...]] = {
    "MacroAgent": (
        "收益率曲线只使用 10Y-3M、10Y-2Y 等可比期限；不得用 10 年期国债与联邦基金利率判断倒挂。",
        "高位、低位、走陡、走平、加速或放缓必须有历史分布或跨期比较。",
    ),
    "GeoPolicyAgent": (
        "逐项检查最新地缘 discovery，并回跳官方制裁、政策、公司或交易所来源。",
        "输出事件事实、传导链、受影响资产和失效条件；没有直接传导证据时不得解释价格。",
    ),
    "MarketAgent": (
        "整体市场判断必须引用市场指数、宽度、成交、资金或行业排行；只有观察池时必须明确范围。",
        "跨市场比较必须使用对应市场级证据，不能用单只股票代替市场。",
    ),
    "SectorAgent": (
        "单日行业排行和 hot_stocks 只能说明当日相对强弱；持续性必须引用多日历史、资金、基本面或催化证据。",
        "没有行业资金证据时不得使用资金抱团、主动流入等因果措辞。",
    ),
    "FundamentalAgent": (
        "财务判断必须标明报告期和比较期；只有单期同比时不得写加速、放缓、筑底或回暖。",
        "没有 PE/PB/股息率、历史分位或同业可比时，不得给高估、低估或安全边际结论。",
        "回购、分红和权益分派是公司行动事实，不能单独证明护盘、托底或价格支撑。",
    ),
    "TechnicalAgent": (
        "returned N rows 只证明数据存在；破位、突破、放量必须引用 OHLCV、均线、区间或量比。",
        "range_position_pct=100 只表示当前价格位于样本区间上沿，不是概率、估值分位或必然回吐信号。",
    ),
    "IntelAgent": (
        "先过滤与 universe 和传导链无关的标题；公告事实、新闻线索和噪音分开。",
        "未回跳权威源的搜索结果只能作为 discovery，不得进入确定性结论。",
    ),
    "PortfolioAgent": (
        "portfolio 为空时只描述观察池的假设性暴露，不得声称已经影响、对冲或改善真实组合。",
        "没有真实持仓快照时不得使用持有、加仓、减仓等用户动作。",
    ),
    "RiskAgent": (
        "系统性风险必须同时有市场宽度、流动性/成交、信用或跨市场共振中至少两类直接证据。",
        "区分主风险、竞争解释和升级/解除触发条件，不复读各部门待确认项。",
    ),
    "RedTeamAgent": (
        "红队不是强行给完全相反结论，而是提出能解释同一事实的最强竞争假设。",
        "缺少某个原因的证据只能削弱该原因，不能自动证明替代原因或支持交易动作。",
    ),
    "CIOAgent": (
        "先列双方共同事实，再裁决基准解释与最强竞争解释；红队不能因更悲观而自动胜出。",
        "必须消解部门冲突；当前更符合/基准解释是可以明确，但要写翻转条件。",
        "系统性风险需至少两类直接证据；session_phase=intraday 必须写盘中，range_position_pct=100 仅代表区间上沿。",
    ),
}


def run_llm_daily_department_agents(
    docs_dir: str | Path,
    run_date: str,
    *,
    runtime_reports_dir: str | Path = "reports",
    backend_factory: Optional[LLMBackendFactory] = None,
    max_retries: int = 1,
    require_all_llm: bool = False,
    progress_callback: Optional[Callable[[Mapping[str, Any]], None]] = None,
    max_concurrency: int = 3,
    model_policy: str = "best",
    resume_successful: bool = False,
) -> Dict[str, Any]:
    """Run LLM department agents with deterministic fallback memos."""

    stage_started = time.perf_counter()
    docs = Path(docs_dir)
    runtime_reports = Path(runtime_reports_dir)
    out = docs / "agent_memos" / run_date
    run_status = docs / "run_status" / run_date
    run_status.mkdir(parents=True, exist_ok=True)
    resumed = _load_resumable_successes(out, run_status) if resume_successful else {}
    fallback_result = run_daily_department_agents(docs, run_date, runtime_reports_dir=runtime_reports)

    context = _build_context(docs, run_date, runtime_reports)
    previous_outputs: Dict[str, Dict[str, Any]] = {}
    runs: List[Dict[str, Any]] = []
    rerun_agents: Set[str] = set()

    backend: Optional[GenerationBackend] = None
    backend_error: Optional[str] = None
    model_selection: Dict[str, Any] = {
        "schema": MODEL_SELECTION_SCHEMA,
        "policy": "injected_backend",
        "selectedModel": "",
        "candidates": [],
    }
    try:
        if backend_factory is not None:
            backend = backend_factory()
        else:
            backend, model_selection = build_default_llm_backend_with_selection(model_policy=model_policy)
    except Exception as exc:  # noqa: BLE001 - recorded as diagnostics, fallback handles report
        backend_error = _error_text(exc)
    model_selection.update({"runDate": run_date})
    (run_status / "agent_model_selection.json").write_text(
        json.dumps(model_selection, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    partial_path = run_status / "llm_agent_runs.partial.jsonl"
    if partial_path.exists():
        partial_path.unlink()

    first_wave = [spec for spec in DEPARTMENT_SPECS if not spec.depends_on]
    downstream = [spec for spec in DEPARTMENT_SPECS if spec.depends_on and spec.agent != "CIOAgent"]
    cio_spec = next(spec for spec in DEPARTMENT_SPECS if spec.agent == "CIOAgent")

    def record(result: Mapping[str, Any]) -> None:
        memo = result["memo"]
        run_row = result["run"]
        spec = result["spec"]
        _write_memo(out, spec.rel, memo)
        previous_outputs[spec.agent] = memo
        runs.append(run_row)
        _append_llm_run(partial_path, run_row)
        _emit_progress(progress_callback, run_row)

    def restore(spec: DepartmentSpec) -> bool:
        state = resumed.get(spec.agent)
        if not state:
            return False
        if any(dependency in rerun_agents for dependency in spec.depends_on):
            rerun_agents.add(spec.agent)
            return False
        memo = dict(state["memo"])
        try:
            _apply_semantic_gate_to_memo(memo, spec, context.get("evidence") or [])
            _validate_memo(memo, spec, _valid_refs_for_spec(context, spec, previous_outputs))
        except ValueError:
            rerun_agents.add(spec.agent)
            return False
        run_row = dict(state["run"])
        run_row["resumed"] = True
        record({"memo": memo, "run": run_row, "spec": spec})
        return True

    if first_wave:
        for spec in first_wave:
            restore(spec)
        pending_first_wave = [spec for spec in first_wave if spec.agent not in previous_outputs]
        workers = max(1, min(int(max_concurrency or 1), len(pending_first_wave)))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(
                    _run_department_spec,
                    spec,
                    out,
                    backend,
                    backend_error,
                    context,
                    {},
                    max_retries,
                )
                for spec in pending_first_wave
            ]
            for future in as_completed(futures):
                result = future.result()
                record(result)
                rerun_agents.add(str(result["spec"].agent))

    for spec in downstream:
        if restore(spec):
            continue
        result = _run_department_spec(spec, out, backend, backend_error, context, previous_outputs, max_retries)
        record(result)
        rerun_agents.add(spec.agent)

    if restore(cio_spec):
        enrichment_summary = dict(previous_outputs[cio_spec.agent].get("cioEnrichment") or {})
        initial_cio = None
    else:
        initial_cio = _run_department_spec(cio_spec, out, backend, backend_error, context, previous_outputs, max_retries)
        enrichment_summary = run_cio_enrichment(docs, run_date, initial_cio["memo"])
    if initial_cio is not None and enrichment_summary.get("requested"):
        context = _build_context(docs, run_date, runtime_reports)
        final_cio = _run_department_spec(cio_spec, out, backend, backend_error, context, previous_outputs, max_retries)
        final_cio["memo"]["cioEnrichment"] = enrichment_summary
        record(final_cio)
    elif initial_cio is not None:
        initial_cio["memo"]["cioEnrichment"] = enrichment_summary
        record(initial_cio)

    runs = _sort_runs_by_spec(runs)
    _write_llm_runs(run_status / "llm_agent_runs.jsonl", runs)
    summary = _summarize_runs(runs)
    summary.update(
        {
            "schema": "llm_department_agents_result_v1",
            "runDate": run_date,
            "totalElapsedSeconds": _round_seconds(time.perf_counter() - stage_started),
            "fallbackRuleResult": fallback_result,
            "llmRuns": f"run_status/{run_date}/llm_agent_runs.jsonl",
            "selectedModel": model_selection.get("selectedModel") or "",
            "modelSelection": model_selection,
            "cioEnrichment": enrichment_summary,
            "maxConcurrency": max_concurrency,
            "resumedSuccessCount": sum(1 for row in runs if row.get("resumed")),
        }
    )
    (run_status / "llm_agent_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _upsert_llm_stage(docs, run_date, summary)
    if require_all_llm and summary.get("fallbackCount"):
        raise RuntimeError(f"LLM department agents incomplete: fallbackCount={summary.get('fallbackCount')}")
    return summary


def _load_resumable_successes(out: Path, run_status: Path) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Load explicitly requested same-date LLM successes for a failed local rerun.

    Resume is opt-in because the caller owns the guarantee that universe/evidence
    inputs have not changed since the interrupted attempt.
    """

    run_rows = {
        str(row.get("agent") or ""): row
        for row in _load_jsonl(run_status / "llm_agent_runs.jsonl")
        if row.get("status") == "success"
    }
    states: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for spec in DEPARTMENT_SPECS:
        run_row = run_rows.get(spec.agent)
        memo = _read_json(out / f"{spec.rel}.json")
        if not run_row or memo.get("agent") != spec.agent:
            continue
        if memo.get("agentRuntime") != "LLM" or memo.get("llm_status") != "success":
            continue
        states[spec.agent] = {"memo": memo, "run": dict(run_row)}
    return states


def build_default_llm_backend() -> GenerationBackend:
    """Create a lightweight configured Agent generation backend lazily.

    Do not import ``src.analyzer`` here.  The analyzer imports the full data
    stack (pandas/provider packages), while department report generation only
    needs text generation.
    """

    config = _load_lightweight_llm_config()
    backend_id = resolve_agent_generation_backend_id(config)
    if backend_id != LITELLM_BACKEND_ID:
        raise GenerationError(
            error_code=GenerationErrorCode.BACKEND_NOT_CONFIGURED,
            stage="configuration",
            retryable=False,
            fallbackable=False,
            backend=backend_id,
            provider=backend_id,
            details={"reason": "research_department_agents_require_litellm"},
        )
    return create_generation_backend(
        backend_id,
        config=config,
        litellm_completion_callable=_build_litellm_completion_callable(config),
    )


def build_default_llm_backend_with_selection(*, model_policy: str = "best") -> tuple[GenerationBackend, Dict[str, Any]]:
    """Select the best usable Agent model, then build the LiteLLM backend."""

    base_config = _load_lightweight_llm_config()
    selection = _select_agent_model(base_config, model_policy=model_policy)
    selected = str(selection.get("selectedModel") or "").strip()
    if not selected:
        raise GenerationError(
            error_code=GenerationErrorCode.BACKEND_NOT_CONFIGURED,
            stage="configuration",
            retryable=False,
            fallbackable=True,
            backend=LITELLM_BACKEND_ID,
            provider=LITELLM_BACKEND_ID,
            details={"reason": "no_agent_model_smoke_succeeded"},
        )
    config = _load_lightweight_llm_config(agent_model_override=selected, fallback_models_override=[])
    backend_id = resolve_agent_generation_backend_id(config)
    if backend_id != LITELLM_BACKEND_ID:
        raise GenerationError(
            error_code=GenerationErrorCode.BACKEND_NOT_CONFIGURED,
            stage="configuration",
            retryable=False,
            fallbackable=False,
            backend=backend_id,
            provider=backend_id,
            details={"reason": "research_department_agents_require_litellm"},
        )
    return create_generation_backend(
        backend_id,
        config=config,
        litellm_completion_callable=_build_litellm_completion_callable(config),
    ), selection


def _select_agent_model(config: Any, *, model_policy: str = "best") -> Dict[str, Any]:
    policy = (model_policy or "best").strip().lower()
    configured = str(getattr(config, "agent_litellm_model", "") or getattr(config, "litellm_model", "") or "").strip()
    if policy in {"configured", "strict"}:
        candidates = [configured] if configured else []
    else:
        candidates = list(DEFAULT_MODEL_CANDIDATES)
        if configured and configured not in candidates:
            candidates.append(configured)
    rows: List[Dict[str, Any]] = []
    selected = ""
    for model in [item for item in candidates if item]:
        row = _smoke_agent_model(model, config)
        rows.append(row)
        if row.get("status") == "success":
            selected = model
            break
    return {
        "schema": MODEL_SELECTION_SCHEMA,
        "policy": policy,
        "selectedModel": selected,
        "candidates": rows,
    }


def _smoke_agent_model(model: str, base_config: Any) -> Dict[str, Any]:
    start = time.perf_counter()
    config = _load_lightweight_llm_config(agent_model_override=model, fallback_models_override=[])
    try:
        _call_litellm_direct(
            "只输出一个 JSON object：{\"ok\": true}",
            {"temperature": 0, "max_output_tokens": 48, "response_format": "json_object", "timeout": 45},
            system_prompt="只输出 JSON。",
            response_validator=None,
            config=config,
        )
        return {
            "model": model,
            "status": "success",
            "durationSeconds": _round_seconds(time.perf_counter() - start),
        }
    except Exception as exc:  # noqa: BLE001 - model selection diagnostics only
        return {
            "model": model,
            "status": "failed",
            "durationSeconds": _round_seconds(time.perf_counter() - start),
            "error": _clip(_error_text(exc), 260),
        }


def _load_lightweight_llm_config(
    *,
    agent_model_override: str = "",
    fallback_models_override: Optional[Sequence[str]] = None,
) -> Any:
    """Load only text-generation fields without mutating ``os.environ``.

    The full ``setup_env()`` call writes project ``.env`` keys into process-wide
    environment.  That is unsafe in the report path because later tests and
    services rely on clean env isolation.  Read the local ``.env`` as a mapping
    instead and pass only the LLM runtime variables to the child process.
    """

    from src.config import (
        Config,
        get_configured_llm_models,
        normalize_agent_litellm_model,
        resolve_legacy_llm_config,
    )

    env_values = _load_lightweight_env_values()

    # Process values override the dotenv mapping without publishing dotenv keys
    # into process-wide state.  The shared Config channel parser then preserves
    # aliases, API surfaces, bases, keys and headers exactly as the main runtime.
    merged_env: Dict[str, str] = dict(env_values)
    merged_env.update({str(key): str(value) for key, value in os.environ.items()})

    def env(name: str, default: str = "") -> str:
        value = merged_env.get(name, default)
        return "" if value is None else str(value)

    legacy_llm = resolve_legacy_llm_config(merged_env)
    raw_agent_model = agent_model_override or env("AGENT_LITELLM_MODEL")
    explicit_primary_model = legacy_llm.explicit_primary_model
    explicit_fallback_models = list(legacy_llm.explicit_fallback_models)
    channels_str = env("LLM_CHANNELS").strip()
    llm_channels: List[Dict[str, Any]] = []
    llm_channel_config_issues: List[Dict[str, str]] = []
    llm_model_list: List[Dict[str, Any]] = []
    llm_blocks_legacy_fallback = False
    llm_models_source = "legacy_env"
    litellm_config_path = env("LITELLM_CONFIG").strip()
    if litellm_config_path:
        llm_models_source = "litellm_config"
        try:
            llm_model_list = Config._parse_litellm_yaml(litellm_config_path, env=merged_env)
        except Exception:  # noqa: BLE001 - explicit YAML must fail closed below
            llm_model_list = []
        has_valid_deployment = any(
            isinstance(entry, Mapping)
            and isinstance(entry.get("litellm_params"), Mapping)
            and bool(str(entry["litellm_params"].get("model") or "").strip())
            for entry in llm_model_list
        )
        if not has_valid_deployment:
            llm_model_list = []
            llm_blocks_legacy_fallback = True
            llm_channel_config_issues = [{
                "field": "LITELLM_CONFIG",
                "code": "invalid_litellm_config",
                "message": (
                    "Explicit LITELLM_CONFIG did not yield a valid model deployment; "
                    "lower-priority Channels and legacy providers are disabled."
                ),
                "severity": "error",
            }]
    if not litellm_config_path and not llm_model_list and channels_str:
        llm_channels, channel_issues, llm_blocks_legacy_fallback, _blocked_routes = Config._parse_llm_channels_with_issues(
            channels_str,
            env=merged_env,
        )
        llm_channel_config_issues = [issue.as_dict() for issue in channel_issues]
        if channel_issues:
            llm_blocks_legacy_fallback = True
        llm_model_list = Config._channels_to_model_list(llm_channels)
        if llm_model_list:
            llm_models_source = "llm_channels"
    route_models = get_configured_llm_models(llm_model_list)
    agent_model = normalize_agent_litellm_model(
        raw_agent_model,
        configured_models=set(route_models),
    )
    primary_model = agent_model or explicit_primary_model or (route_models[0] if route_models else "")
    legacy_fallback_allowed = not llm_blocks_legacy_fallback and not llm_channel_config_issues
    if not primary_model and not llm_model_list and legacy_fallback_allowed:
        primary_model = legacy_llm.primary_model
    if fallback_models_override is None:
        fallback_models = explicit_fallback_models
        if not fallback_models and route_models and primary_model:
            fallback_models = [model for model in route_models if model != primary_model]
        elif not fallback_models and not llm_model_list and legacy_fallback_allowed:
            fallback_models = list(legacy_llm.fallback_models)
    else:
        fallback_models = [str(item).strip() for item in fallback_models_override if str(item).strip()]
    runtime_env = {
        key: env(key).strip()
        for key in (
            "GOOGLE_APPLICATION_CREDENTIALS",
            "GOOGLE_CLOUD_PROJECT",
            "GOOGLE_CLOUD_LOCATION",
            "VERTEXAI_PROJECT",
            "VERTEXAI_LOCATION",
            "VERTEX_PROJECT",
            "VERTEX_LOCATION",
            "GOOGLE_API_KEY",
            "GEMINI_API_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "DEEPSEEK_API_KEY",
        )
        if env(key).strip()
    }
    return SimpleNamespace(
        agent_generation_backend=env("AGENT_GENERATION_BACKEND", "auto").strip().lower() or "auto",
        agent_litellm_model=agent_model,
        litellm_model=primary_model,
        litellm_fallback_models=fallback_models,
        litellm_config_path=litellm_config_path or None,
        llm_models_source=llm_models_source,
        llm_channels=llm_channels,
        llm_channel_names=[item.strip().lower() for item in channels_str.split(",") if item.strip()],
        llm_channel_config_issues=llm_channel_config_issues,
        llm_blocks_legacy_fallback=llm_blocks_legacy_fallback,
        llm_model_list=llm_model_list,
        openai_api_keys=legacy_llm.openai_api_keys,
        deepseek_api_keys=legacy_llm.deepseek_api_keys,
        gemini_api_keys=legacy_llm.gemini_api_keys,
        anthropic_api_keys=legacy_llm.anthropic_api_keys,
        openai_base_url=legacy_llm.openai_base_url,
        research_agent_llm_timeout_seconds=env("RESEARCH_AGENT_LLM_TIMEOUT_SECONDS", "90").strip(),
        runtime_env=runtime_env,
    )


def _load_lightweight_env_values() -> Dict[str, str]:
    env_file = os.getenv("ENV_FILE")
    env_path = Path(env_file) if env_file else Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return {}
    try:
        from dotenv import dotenv_values  # noqa: WPS433 - optional lightweight parser

        return {str(k): "" if v is None else str(v) for k, v in dotenv_values(env_path, interpolate=False).items() if k}
    except Exception:
        values: Dict[str, str] = {}
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip().strip("'\"")
        return values


def _build_litellm_completion_callable(config: Any):
    def _call(
        prompt: str,
        generation_config: Mapping[str, Any],
        *,
        system_prompt: Optional[str] = None,
        stream: bool = False,
        stream_progress_callback: Any = None,
        response_validator: Any = None,
        audit_context: Optional[Dict[str, Any]] = None,
    ):
        if stream:
            raise GenerationError(
                error_code=GenerationErrorCode.CAPABILITY_UNSUPPORTED,
                stage="generation",
                retryable=False,
                fallbackable=True,
                backend=LITELLM_BACKEND_ID,
                provider=LITELLM_BACKEND_ID,
                details={"reason": "stream_not_used_for_department_agents"},
            )
        return _call_litellm_direct(prompt, generation_config, system_prompt=system_prompt, response_validator=response_validator, config=config)

    return _call


def _call_litellm_direct(
    prompt: str,
    generation_config: Mapping[str, Any],
    *,
    system_prompt: Optional[str],
    response_validator: Any,
    config: Any,
):
    try:
        import litellm  # noqa: WPS433 - optional runtime dependency
    except Exception as exc:  # noqa: BLE001
        raise GenerationError(
            error_code=GenerationErrorCode.BACKEND_NOT_CONFIGURED,
            stage="configuration",
            retryable=False,
            fallbackable=True,
            backend=LITELLM_BACKEND_ID,
            provider=LITELLM_BACKEND_ID,
            details={
                "reason": "litellm_not_installed",
                "error": sanitize_diagnostic_text(exc, max_len=120),
            },
        ) from exc

    from src.config import extra_litellm_params, get_api_keys_for_model, get_effective_agent_models_to_try

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    max_tokens = generation_config.get("max_output_tokens") or generation_config.get("max_tokens") or 1800
    temperature = generation_config.get("temperature", 0.2)
    timeout = _llm_timeout_seconds(generation_config, config)
    models = get_effective_agent_models_to_try(config)
    if not models:
        raise GenerationError(
            error_code=GenerationErrorCode.BACKEND_NOT_CONFIGURED,
            stage="configuration",
            retryable=False,
            fallbackable=True,
            backend=LITELLM_BACKEND_ID,
            provider=LITELLM_BACKEND_ID,
            details={"reason": "no_agent_litellm_model"},
        )
    preflight_error = _model_preflight_error(models[0], config)
    if preflight_error:
        raise GenerationError(
            error_code=GenerationErrorCode.BACKEND_NOT_CONFIGURED,
            stage="configuration",
            retryable=False,
            fallbackable=True,
            backend=LITELLM_BACKEND_ID,
            provider=LITELLM_BACKEND_ID,
            details={"reason": preflight_error, "model_provider": _provider_from_model(models[0])},
        )

    router = None
    if getattr(config, "llm_model_list", None):
        router = litellm.Router(model_list=config.llm_model_list, num_retries=0)

    last_error: Optional[BaseException] = None
    for model in models:
        try:
            kwargs: Dict[str, Any] = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "timeout": timeout,
            }
            response_format = generation_config.get("response_format")
            if response_format:
                kwargs["response_format"] = {"type": str(response_format)}
            if router is None:
                params = extra_litellm_params(model, config)
                keys = get_api_keys_for_model(model, config)
                if keys and "api_key" not in params:
                    params["api_key"] = keys[0]
                kwargs.update(params)
                text, usage = _call_litellm_with_process_timeout(kwargs, None, timeout, getattr(config, "runtime_env", {}))
            else:
                text, usage = _call_litellm_with_process_timeout(kwargs, config.llm_model_list, timeout, getattr(config, "runtime_env", {}))
            if response_validator:
                response_validator(text)
            return text, model, usage
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
    raise GenerationError(
        error_code=GenerationErrorCode.UNKNOWN_BACKEND_ERROR,
        stage="generation",
        retryable=True,
        fallbackable=True,
        backend=LITELLM_BACKEND_ID,
        provider=LITELLM_BACKEND_ID,
        details={"reason": "all_agent_models_failed", "last_error": _error_text(last_error)},
    )


def _llm_timeout_seconds(generation_config: Mapping[str, Any], config: Any) -> float:
    value = generation_config.get("timeout") or getattr(config, "research_agent_llm_timeout_seconds", "") or os.getenv("RESEARCH_AGENT_LLM_TIMEOUT_SECONDS", "90")
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        timeout = 90.0
    return max(5.0, min(timeout, 180.0))


def _call_litellm_with_process_timeout(
    kwargs: Mapping[str, Any],
    model_list: Optional[Sequence[Mapping[str, Any]]],
    timeout: float,
    runtime_env: Optional[Mapping[str, str]] = None,
) -> tuple[str, Dict[str, Any]]:
    """Run LiteLLM in a child process so stuck sockets cannot hang the report."""

    start_methods = multiprocessing.get_all_start_methods()
    if "spawn" not in start_methods:
        return _call_litellm_inline(dict(kwargs), list(model_list or []), runtime_env or {})

    # Vertex/Gemini and several HTTP stacks can crash after ``fork`` because
    # worker threads / gRPC state are inherited half-initialized.  ``spawn`` is
    # slower but safe, and the timeout below still prevents stuck sockets from
    # hanging report generation.
    ctx = multiprocessing.get_context("spawn")
    queue: Any = ctx.Queue(maxsize=1)
    proc = ctx.Process(target=_litellm_worker, args=(queue, dict(kwargs), list(model_list or []), dict(runtime_env or {})))
    proc.start()
    proc.join(timeout)
    if proc.is_alive():
        proc.terminate()
        proc.join(2)
        if proc.is_alive():
            proc.kill()
            proc.join(2)
        raise TimeoutError(f"llm_request_timeout_after_{int(timeout)}s")
    if queue.empty():
        raise RuntimeError(f"litellm_worker_exit_{proc.exitcode}")
    result = queue.get()
    if result.get("ok"):
        return str(result.get("text") or ""), dict(result.get("usage") or {})
    raise RuntimeError(str(result.get("error") or "litellm_worker_failed"))


def _litellm_worker(queue: Any, kwargs: Dict[str, Any], model_list: Sequence[Mapping[str, Any]], runtime_env: Mapping[str, str]) -> None:
    try:
        text, usage = _call_litellm_inline(kwargs, list(model_list or []), runtime_env)
        queue.put({"ok": True, "text": text, "usage": usage})
    except BaseException as exc:  # noqa: BLE001 - child process reports to parent
        queue.put({"ok": False, "error": _error_text(exc)})


def _call_litellm_inline(kwargs: Dict[str, Any], model_list: Sequence[Mapping[str, Any]], runtime_env: Optional[Mapping[str, str]] = None) -> tuple[str, Dict[str, Any]]:
    import litellm  # noqa: WPS433 - optional runtime dependency

    with _temporary_environ(runtime_env or {}):
        if model_list:
            router = litellm.Router(model_list=list(model_list), num_retries=0)
            response = router.completion(**kwargs)
        else:
            response = litellm.completion(**kwargs)
    return _extract_litellm_text(response), _extract_litellm_usage(response, str(kwargs.get("model") or ""))


@contextmanager
def _temporary_environ(values: Mapping[str, str]):
    previous: Dict[str, Optional[str]] = {}
    for key, value in values.items():
        previous[key] = os.environ.get(key)
        os.environ[key] = str(value)
    try:
        yield
    finally:
        for key, old_value in previous.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


def _model_preflight_error(model: str, config: Any) -> str:
    # Router deployments own their credentials.  In particular an OpenAI
    # Responses alias must not also require the unrelated legacy OPENAI_API_KEY.
    if any(
        str(entry.get("model_name") or "").strip() == str(model or "").strip()
        for entry in (getattr(config, "llm_model_list", None) or [])
        if isinstance(entry, Mapping)
    ):
        return ""
    if (
        (getattr(config, "llm_channel_config_issues", None) or [])
        or bool(getattr(config, "llm_blocks_legacy_fallback", False))
    ):
        return "llm_channel_config_invalid"
    provider = _provider_from_model(model)
    if provider in {"vertex_ai", "vertexai"}:
        try:
            import google.auth  # noqa: F401,WPS433
        except Exception:
            return "vertex_ai_google_dependency_missing"
    provider_keys = {
        "gemini": getattr(config, "gemini_api_keys", []) or [],
        "anthropic": getattr(config, "anthropic_api_keys", []) or [],
        "deepseek": getattr(config, "deepseek_api_keys", []) or [],
        "openai": getattr(config, "openai_api_keys", []) or [],
    }
    required_key = {
        "gemini": "GEMINI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "openai": "OPENAI_API_KEY",
    }.get(provider)
    runtime_env = getattr(config, "runtime_env", {}) or {}
    if required_key and not provider_keys.get(provider) and not runtime_env.get(required_key) and not os.getenv(required_key, "").strip() and not os.getenv(f"{required_key}S", "").strip():
        return f"{required_key.lower()}_missing"
    return ""


def _provider_from_model(model: str) -> str:
    text = str(model or "").strip()
    if "/" in text:
        return text.split("/", 1)[0].lower()
    return "openai"


def _extract_litellm_text(response: Any) -> str:
    try:
        text = response.choices[0].message.content
    except Exception:
        text = ""
    if not str(text or "").strip():
        raise ValueError("empty LLM response")
    return str(text).strip()


def _extract_litellm_usage(response: Any, model: str) -> Dict[str, Any]:
    usage = getattr(response, "usage", None)
    out: Dict[str, Any] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = getattr(usage, key, None) if usage is not None else None
        if value is not None:
            out[key] = value
    out["provider"] = model.split("/", 1)[0] if "/" in model else "openai"
    return out



def _build_context(docs: Path, run_date: str, runtime_reports: Path) -> Dict[str, Any]:
    compact = run_date.replace("-", "")
    evidence = _load_jsonl(docs / "run_status" / run_date / "evidence_ledger.jsonl")
    providers = _load_jsonl(docs / "run_status" / run_date / "provider_runs.jsonl")
    health = _read_json(docs / "run_status" / run_date / "source_health_v2.json")
    universe = _read_json(docs / "run_status" / run_date / "daily_universe.json")
    official = _read_json(docs / "official_events" / f"{run_date}.json")
    stock_md = _read_text_first(runtime_reports / f"report_{compact}.md", docs / f"report_{compact}.md")
    market_md = _read_text_first(runtime_reports / f"market_review_{compact}.md", docs / f"market_review_{compact}.md")
    # Rebuild on every run: provider/evidence ledgers and runtime reports may
    # have changed even when a same-date manifest already exists.
    build_original_analysis_bundle(docs, run_date, runtime_reports_dir=runtime_reports)
    original_analysis = load_original_analysis(docs, run_date)
    original_refs = load_original_analysis_refs(docs, run_date)
    return {
        "runDate": run_date,
        "evidence": evidence,
        "providers": providers,
        "health": health,
        "universe": universe,
        "official": official,
        "stockSummaries": [vars(item) for item in _parse_stock_summaries(stock_md)],
        "marketSnapshot": _market_snapshot(market_md),
        "stockReportExcerpt": _clip(stock_md, 2000),
        "marketReportExcerpt": _clip(market_md, 2000),
        "evidenceView": _EvidenceView(evidence),
        "originalAnalysis": original_analysis,
        "originalAnalysisRefs": original_refs,
    }


def _generate_validated_memo(
    backend: GenerationBackend,
    spec: DepartmentSpec,
    context: Mapping[str, Any],
    previous_outputs: Mapping[str, Mapping[str, Any]],
    valid_refs: Set[str],
    *,
    max_retries: int,
) -> Dict[str, Any]:
    agent_started = time.perf_counter()
    prompt = _department_prompt(spec, context, previous_outputs, valid_refs, previous_error="")
    system_prompt = _system_prompt()
    last_error = ""
    attempt_durations: List[float] = []
    for attempt in range(max(0, max_retries) + 1):
        attempt_started = time.perf_counter()
        try:
            generation = backend.generate(
                prompt,
                {"temperature": 0.1, "max_output_tokens": 4000, "response_format": "json_object"},
                system_prompt=system_prompt,
                audit_context={
                    "run_date": context.get("runDate"),
                    "agent": spec.agent,
                    "stage": "daily_department_llm",
                },
            )
            attempt_durations.append(_round_seconds(time.perf_counter() - attempt_started))
            payload = _parse_agent_output(generation.text, spec)
            memo = _payload_to_memo(spec, str(context.get("runDate") or ""), payload, generation)
            _fill_missing_memo_fields(memo, spec, valid_refs)
            if spec.agent == "CIOAgent":
                _complete_cio_adjudication(memo, previous_outputs)
            _apply_semantic_gate_to_memo(memo, spec, context.get("evidence") or [])
            _validate_memo(memo, spec, valid_refs)
            return {
                "status": "success",
                "memo": memo,
                "run": _run_row(
                    spec,
                    status="success",
                    model=generation.model,
                    provider=generation.provider,
                    backend=generation.backend,
                    usage=generation.usage,
                    attempt=attempt + 1,
                    duration_seconds=_round_seconds(time.perf_counter() - agent_started),
                    attempt_durations=attempt_durations,
                ),
            }
        except Exception as exc:  # noqa: BLE001 - retry/fallback path
            attempt_durations.append(_round_seconds(time.perf_counter() - attempt_started))
            last_error = _error_text(exc)
            prompt = _department_prompt(spec, context, previous_outputs, valid_refs, previous_error=last_error)

    return {
        "status": "fallback",
        "error": last_error,
        "run": _run_row(
            spec,
            status="fallback",
            error_type="generation_failed",
            error=last_error,
            attempt=max_retries + 1,
            duration_seconds=_round_seconds(time.perf_counter() - agent_started),
            attempt_durations=attempt_durations,
        ),
    }


def _run_department_spec(
    spec: DepartmentSpec,
    out: Path,
    backend: Optional[GenerationBackend],
    backend_error: Optional[str],
    context: Mapping[str, Any],
    previous_outputs: Mapping[str, Mapping[str, Any]],
    max_retries: int,
) -> Dict[str, Any]:
    fallback_memo = _read_json(out / f"{spec.rel}.json")
    if not isinstance(fallback_memo, dict):
        fallback_memo = {}
    if backend is None:
        fallback = _mark_fallback(
            fallback_memo,
            reason=backend_error or "llm_backend_not_configured",
        )
        return {
            "spec": spec,
            "memo": fallback,
            "run": _run_row(
                spec,
                status="fallback",
                error_type="backend_not_configured",
                error=backend_error,
                duration_seconds=0.0,
            ),
        }
    valid_refs = _valid_refs_for_spec(context, spec, previous_outputs)
    result = _generate_validated_memo(
        backend,
        spec,
        context,
        previous_outputs,
        valid_refs,
        max_retries=max_retries,
    )
    if result.get("status") == "success":
        return {
            "spec": spec,
            "memo": result["memo"],
            "run": result["run"],
        }
    fallback = _mark_fallback(
        fallback_memo,
        reason=str(result.get("error") or "llm_generation_failed"),
    )
    return {
        "spec": spec,
        "memo": fallback,
        "run": result["run"],
    }


def _system_prompt() -> str:
    return (
        "你是机构投研部门 Agent。严格执行给定岗位、证据政策和输出合同。"
        "只输出一个面向投资研究读者的 JSON object。"
    )


def _department_prompt(
    spec: DepartmentSpec,
    context: Mapping[str, Any],
    previous_outputs: Mapping[str, Mapping[str, Any]],
    valid_refs: Set[str],
    *,
    previous_error: str,
) -> str:
    playbook = DEPARTMENT_PLAYBOOKS.get(spec.agent, {})
    evidence_rows = _prompt_evidence_for_spec(context, spec, previous_outputs)
    deps = {
        agent: _compact_memo(memo)
        for agent, memo in previous_outputs.items()
        if agent in spec.depends_on
    }
    payload = {
        "agent": spec.agent,
        "mission": spec.mission,
        "rolePlaybook": {
            "role": playbook.get("role"),
            "mustAnswer": list(playbook.get("mustAnswer") or []),
            "avoid": list(playbook.get("avoid") or []),
            "readerStyle": playbook.get("readerStyle"),
        },
        "analysisRules": [
            *GLOBAL_ANALYSIS_RULES,
            *AGENT_ANALYSIS_RULES.get(spec.agent, ()),
        ],
        "departmentInputProfile": department_profile_payload(spec.agent),
        "runDate": context.get("runDate"),
        "dailyUniverse": _compact_universe_for_spec(context.get("universe") or {}, spec),
        "sourceHealth": _compact_source_health(context.get("health") or {}, spec),
        "evidence": evidence_rows,
        # Only ids present in the department's evidence payload may be cited as
        # evidence.  Context handles (dailyUniverse/kind:*) and memo handles are
        # useful navigation aids, but presenting them as evidence ids causes the
        # model to create claims that the semantic gate can never substantiate.
        "allowedEvidenceRefs": sorted(_valid_evidence_ids(evidence_rows))[:80],
        "allowedMemoRefs": sorted(ref for ref in valid_refs if str(ref).startswith("memo:"))[:20],
        "previousDepartmentOutputs": deps,
        "modeGuidance": _mode_guidance(context.get("health") or {}),
        "outputContract": {
            "format": "json_object",
            "requiredKeys": [
                "agent",
                "summary_for_reader",
                "key_claims",
                "evidence_ids",
                "counterpoints",
                "data_gaps",
                "next_action",
                "confidence",
            ],
            "readerTone": [
                "短、硬、专业",
                "先判断，后解释",
                "不要暴露工程字段",
                "不要堆 provider 状态；只讲这对投资判断意味着什么",
            ],
            "jsonExample": {
                "agent": spec.agent,
                "summary_for_reader": "一句或两句读者能看懂的专业结论，不得只写可用/中性",
                "key_claims": [
                    {
                        "claim": "3-5 条核心依据之一；每条要有驱动或传导链",
                        "claimType": "fact|interpretation|scenario|recommendation",
                        "subject": "market|macro|标的代码",
                        "domain": "price|fundamentals|filings_events|macro|news_sentiment|portfolio",
                        "metric": "可选；只有明确指标时填写",
                        "evidence_ids": ["该条依据直接使用的 allowedEvidenceRefs"],
                    }
                ],
                "evidence_ids": ["必须来自 allowedEvidenceRefs，可用 memo:Agent 引用已验证部门输出"],
                "counterpoints": ["最强反证或风险，不要泛泛而谈"],
                "data_gaps": ["只写会改变结论的待确认项；没有就空数组"],
                "confidence": "low|medium|high",
                "next_action": (
                    {
                        "不做什么": "当前最应避免的误判或动作",
                        "看什么": "1-2 个可观察信号及其风险含义",
                        "下次复核什么": "下次报告要重新核对的数据或判断",
                    }
                    if spec.agent == "CIOAgent"
                    else "下一步看什么信号，触发后如何改变判断"
                ),
            },
        },
    }
    if not spec.depends_on:
        payload["originalAnalysisSummary"] = _compact_original_analysis(context.get("originalAnalysis") or {}, spec)
        payload["originalAnalysisRefs"] = _compact_original_refs_for_prompt(
            filter_original_refs_for_agent(context.get("originalAnalysisRefs") or [], spec.agent, limit=8)
        )
    if spec.agent == "RedTeamAgent":
        payload["outputContract"]["redTeamContract"] = {
            "challenges": [
                {
                    "targetClaimId": "被挑战的 claimId；没有则写部门名",
                    "issueType": "overreach|stale|alternative_cause|missing_evidence|scope_mismatch",
                    "opposingScenario": "最强竞争情景，必须能解释同一组事实并以条件式表述",
                    "evidence_ids": ["支持竞争情景的直接 evidence id"],
                    "falsifier": "什么新事实会否定这个竞争情景",
                }
            ],
            "discipline": (
                "竞争情景必须用“若/如果”表述，并给出能区分基准与竞争情景的可观察信号；"
                "不得机械唱反调。"
            ),
        }
    if spec.agent == "CIOAgent":
        payload["outputContract"]["cioAdjudicationContract"] = {
            "adjudication": {
                "sharedFacts": ["正反双方都承认的已验证事实，最多 3 条"],
                "baseCase": "基准情景",
                "strongestAlternative": "最强竞争情景，不是机械唱反调或泛泛风险",
                "judgment": "CIO 当前裁决",
                "why": "为何采用该裁决；必须说明证据权重",
                "invalidationTriggers": ["哪些信号会推翻当前裁决"],
            },
            "discipline": (
                "adjudication 不得引入 key_claims 之外的新事实或数字；"
                "why 只解释已验证的 key_claims，并明确采用基准情景的证据权重。"
            ),
        }
    if previous_error:
        payload["previousValidationError"] = previous_error
        payload["repairInstruction"] = "修复上面的错误并只输出 JSON object；evidence id 必须存在于 allowedEvidenceRefs。"
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _payload_to_memo(
    spec: DepartmentSpec,
    run_date: str,
    payload: Mapping[str, Any],
    generation: GenerationResult,
) -> Dict[str, Any]:
    summary = str(payload.get("summary_for_reader") or "").strip()
    key_claims, claim_evidence, claim_refs = _claim_payload(payload.get("key_claims"))
    # A readable department conclusion is itself a claim. Some otherwise valid
    # model responses provide the conclusion plus citations/counterpoints but
    # omit a separate ``key_claims`` array. Keep the LLM-authored conclusion
    # instead of replacing the whole department with a rule fallback; evidence
    # validation below still requires real, allowed references.
    key_claims = key_claims or ([summary] if summary else [])
    if len(summary) < 20 and key_claims:
        summary = f"{spec.label}结论：{key_claims[0]}"
    next_action = _normalize_next_action(payload.get("next_action"))
    if not next_action and payload.get("_parse_status") == "parse_partial":
        next_action = "继续复核证据、反证和触发条件。"
    memo = _memo(
        run_date,
        agent=spec.agent,
        label=spec.label,
        scope=spec.scope,
        summary=summary,
        key_claims=key_claims,
        evidence_ids=_dedupe_strings([*_string_list(payload.get("evidence_ids")), *claim_refs]),
        counterpoints=_counterpoints_for_payload(spec, payload),
        data_gaps=_string_list(payload.get("data_gaps")),
        next_action=next_action,
        confidence=_normalize_confidence(payload.get("confidence")),
    )
    memo.update(
        {
            "runtime_kind": LLM_RUNTIME_KIND,
            "agentRuntime": "LLM",
            "origin": ORIGIN,
            "origin_label": "LLM 部门 Agent 输出",
            "llm_status": "success",
            "llm_parse_status": str(payload.get("_parse_status") or "structured"),
            "llm_raw_output_excerpt": _clip(str(payload.get("_raw_output") or ""), 600) if payload.get("_parse_status") == "parse_partial" else "",
            "llm_backend": generation.backend,
            "llm_model": generation.model,
            "llm_provider": generation.provider,
            "llm_usage": _safe_usage(generation.usage),
            "claim_evidence": claim_evidence,
        }
    )
    if spec.agent == "RedTeamAgent":
        memo["challenges"] = _normalize_red_team_challenges(payload.get("challenges"))
    if spec.agent == "CIOAgent":
        memo["adjudication"] = _normalize_cio_adjudication(payload.get("adjudication"))
    if spec.agent == "MacroAgent":
        _sanitize_macro_memo(memo)
    return memo


def _normalize_red_team_challenges(value: Any) -> List[Dict[str, Any]]:
    rows = value if isinstance(value, list) else []
    out: List[Dict[str, Any]] = []
    for row in rows[:5]:
        if not isinstance(row, Mapping):
            continue
        opposing = str(row.get("opposingScenario") or row.get("opposing_scenario") or row.get("alternative") or "").strip()
        if not opposing:
            continue
        out.append({
            "targetClaimId": str(row.get("targetClaimId") or row.get("target_claim_id") or ""),
            "issueType": str(row.get("issueType") or row.get("issue_type") or "alternative_cause"),
            "opposingScenario": opposing,
            "evidence_ids": _dedupe_strings(_string_list(row.get("evidence_ids") or row.get("evidenceIds")))[:8],
            "falsifier": str(row.get("falsifier") or row.get("invalidationTrigger") or "").strip(),
        })
    return out


def _normalize_cio_adjudication(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {
        "sharedFacts": _dedupe_strings(_string_list(
            value.get("sharedFacts") or value.get("shared_facts") or value.get("双方共同事实") or value.get("共同事实")
        ))[:3],
        "baseCase": str(value.get("baseCase") or value.get("base_case") or value.get("基准情景") or "").strip(),
        "strongestAlternative": str(
            value.get("strongestAlternative")
            or value.get("strongest_alternative")
            or value.get("最强竞争情景")
            or value.get("最强相反情景")
            or value.get("竞争情景")
            or value.get("替代情景")
            or value.get("反方情景")
            or ""
        ).strip(),
        "judgment": str(
            value.get("judgment") or value.get("adjudication") or value.get("CIO裁决") or value.get("当前裁决") or value.get("裁决") or ""
        ).strip(),
        "why": str(value.get("why") or value.get("reason") or value.get("裁决理由") or value.get("为什么") or "").strip(),
        "invalidationTriggers": _dedupe_strings(
            _string_list(
                value.get("invalidationTriggers")
                or value.get("invalidation_triggers")
                or value.get("翻转信号")
                or value.get("失效条件")
            )
        )[:3],
    }


def _complete_cio_adjudication(
    memo: Dict[str, Any],
    previous_outputs: Mapping[str, Mapping[str, Any]],
) -> None:
    """Normalize a useful CIO response without replacing it with rule prose."""

    adjudication = dict(memo.get("adjudication") or {})
    filled: List[str] = []
    summary = str(memo.get("summary_for_reader") or memo.get("conclusion") or "").strip()
    key_claims = _string_list(memo.get("key_claims"))
    red_team = previous_outputs.get("RedTeamAgent") or {}
    challenges = red_team.get("challenges") if isinstance(red_team.get("challenges"), list) else []

    if not adjudication.get("strongestAlternative"):
        alternatives = [
            str(item.get("opposingScenario") or item.get("opposing_scenario") or "").strip()
            for item in challenges
            if isinstance(item, Mapping)
        ]
        alternatives.extend(_string_list(red_team.get("counterpoints")))
        strongest = next((item for item in alternatives if item), "")
        if strongest:
            adjudication["strongestAlternative"] = strongest
            filled.append("strongestAlternative")
    if not adjudication.get("baseCase") and summary:
        adjudication["baseCase"] = summary
        filled.append("baseCase")
    if not adjudication.get("judgment") and summary:
        adjudication["judgment"] = summary
        filled.append("judgment")
    if not adjudication.get("why"):
        reason = next((item for item in key_claims if item and item != summary), "")
        if reason:
            adjudication["why"] = reason
            filled.append("why")
    if not adjudication.get("invalidationTriggers"):
        triggers = [
            str(item.get("falsifier") or "").strip()
            for item in challenges
            if isinstance(item, Mapping) and str(item.get("falsifier") or "").strip()
        ]
        if triggers:
            adjudication["invalidationTriggers"] = _dedupe_strings(triggers)[:3]
            filled.append("invalidationTriggers")
    memo["adjudication"] = adjudication
    if filled:
        memo["adjudicationNormalizedFields"] = filled


def _normalize_next_action(value: Any) -> str:
    if isinstance(value, Mapping):
        parts: List[str] = []
        for key in ("不做什么", "看什么", "下次复核什么"):
            text = str(value.get(key) or "").strip()
            if text:
                parts.append(f"{key}：{text}")
        for key, raw in value.items():
            if key in {"不做什么", "看什么", "下次复核什么"}:
                continue
            text = str(raw or "").strip()
            if text:
                parts.append(f"{key}：{text}")
        return _clean_reader_punctuation("；".join(parts))
    return _clean_reader_punctuation(str(value or "").strip())


def _clean_reader_punctuation(value: str) -> str:
    text = re.sub(r"[；;]{2,}", "；", str(value or "").strip())
    text = re.sub(r"\s*；\s*", "；", text)
    clauses: List[str] = []
    for clause in (item.strip() for item in text.strip("； ").split("；")):
        if clause and (
            not clauses
            or (clause != clauses[-1] and not clauses[-1].endswith(clause))
        ):
            clauses.append(clause)
    return "；".join(clauses)


def _mode_guidance(health: Mapping[str, Any]) -> Dict[str, Any]:
    mode = str(health.get("overallMode") or "OBSERVE_ONLY").upper()
    if mode == "FULL_REVIEW":
        instruction = (
            "数据条件支持完整复盘；必须给出明确但克制的投研结论、核心依据、反证和触发条件。"
            "不要把 FULL_REVIEW 写成数据阻断；不要说“所有结论均不可靠”。"
            "持仓为空、portfolio partial、publish_bundle missing、资金流缺项只能作为限制说明，不能否定行情、公告、基本面、宏观、新闻等已验证证据。"
        )
    elif mode == "LIMITED_REVIEW":
        instruction = (
            "数据条件支持有限复盘；必须输出可读的有限结论、可用依据、主要待确认项和下一步。"
            "不要把 LIMITED_REVIEW 写成 BLOCKED；除非没有任何有效证据，否则不要说“无法生成任何有效结论”或“所有结论均不可靠”。"
            "如果 evidenceStats 显示 missingCriticalFacts <= 1 且有 verified/derived evidence，必须保留有限但有用的市场/行业/标的观察。"
            "可以说公告/事件缺失限制交易动作，但不能否定行情、宏观、基本面等已经有证据的观察。"
        )
    elif mode == "SCREEN_ONLY":
        instruction = "只做筛选观察；可以给候选和风险排序，不给确定性行动口吻。"
    elif mode == "BLOCKED":
        instruction = "数据不足；只输出诊断和补数清单，不给投研结论。"
    else:
        instruction = "只做市场观察；给出能确认的观察和下一步，不要过度推断。"
    return {
        "analysisMode": mode,
        "evidenceStats": health.get("evidenceStats") if isinstance(health.get("evidenceStats"), Mapping) else {},
        "instruction": instruction,
    }


def _validate_memo(memo: Mapping[str, Any], spec: DepartmentSpec, valid_refs: Set[str]) -> None:
    if memo.get("schema") != AGENT_MEMO_SCHEMA:
        raise ValueError("schema must be agent_memo_v1")
    if memo.get("agent") != spec.agent:
        raise ValueError(f"agent mismatch: {memo.get('agent')} != {spec.agent}")
    summary = str(memo.get("summary_for_reader") or "").strip()
    if len(summary) < 20:
        raise ValueError("summary_for_reader too short")
    for field in ("key_claims", "counterpoints"):
        if not _string_list(memo.get(field)):
            semantic = memo.get("semantic_validation") if isinstance(memo.get("semantic_validation"), Mapping) else {}
            validation_key = "claims" if field == "key_claims" else "counterpoints"
            rows = semantic.get(validation_key) if isinstance(semantic.get(validation_key), list) else []
            reasons = _dedupe_strings(
                reason
                for row in rows
                if isinstance(row, Mapping)
                for reason in row.get("reasons") or []
            )
            detail = ",".join(reasons[:4])
            if detail:
                raise ValueError(
                    f"{field} missing after semantic gate ({detail}); "
                    "rewrite with only directly cited, subject-matched evidence"
                )
            raise ValueError(f"{field} missing")
    if not str(memo.get("next_action") or "").strip():
        raise ValueError("next_action missing")
    evidence_ids = _string_list(memo.get("evidence_ids"))
    if not evidence_ids:
        raise ValueError("evidence_ids missing")
    invalid = [item for item in evidence_ids if item not in valid_refs]
    if invalid:
        valid_items = [item for item in evidence_ids if item in valid_refs]
        if isinstance(memo, dict) and valid_items:
            memo["evidence_ids"] = valid_items
        elif isinstance(memo, dict) and valid_refs and all(_is_non_evidence_reference_noise(item) for item in invalid):
            fallback = [
                ref
                for ref in sorted(valid_refs)
                if ref not in CONTEXT_REFS and not ref.startswith("memo:")
            ] or sorted(valid_refs)
            memo["evidence_ids"] = [fallback[0]]
        else:
            raise ValueError(f"unknown evidence_ids: {', '.join(invalid[:5])}")
    for row in memo.get("claim_evidence") or []:
        if not isinstance(row, Mapping):
            raise ValueError("claim_evidence row must be object")
        claim = str(row.get("claim") or "").strip()
        refs = _string_list(row.get("evidence_ids"))
        if not claim or not refs:
            raise ValueError("claim_evidence requires claim and evidence_ids")
        invalid_claim_refs = [item for item in refs if item not in valid_refs]
        if invalid_claim_refs:
            raise ValueError(f"unknown claim evidence_ids: {', '.join(invalid_claim_refs[:5])}")
    combined_reader_text = "\n".join(
        [
            summary,
            *(_string_list(memo.get("key_claims"))),
            *(_string_list(memo.get("counterpoints"))),
            str(memo.get("next_action") or ""),
        ]
    )
    leaked = [term for term in FORBIDDEN_READER_TERMS if term in combined_reader_text]
    if leaked:
        raise ValueError(f"forbidden reader terms: {', '.join(leaked)}")
    semantic = memo.get("semantic_validation") if isinstance(memo.get("semantic_validation"), Mapping) else {}
    if semantic and int(semantic.get("readerClaimCount") or 0) <= 0:
        raise ValueError("semantic_gate: no safe reader claims")
    summary_semantic = semantic.get("summary") if isinstance(semantic.get("summary"), Mapping) else {}
    if str(summary_semantic.get("status") or "").lower() == "rejected":
        reasons = _dedupe_strings(
            reason
            for row in summary_semantic.get("sentences") or []
            if isinstance(row, Mapping)
            for reason in row.get("reasons") or []
        )
        detail = ",".join(reasons[:5])
        raise ValueError(
            "summary_for_reader rejected by semantic gate"
            + (f" ({detail})" if detail else "")
            + "; rewrite the conclusion using only supported department evidence"
        )
    if spec.agent == "MacroAgent":
        _validate_macro_claim_methodology(memo)
    if spec.agent == "CIOAgent":
        structural_evidence_errors = {
            "market_stat_not_supported_by_cited_evidence",
            "index_change_not_supported_by_cited_evidence",
            "market_stat_contradicted_by_evidence",
            "index_change_contradicted_by_evidence",
            "fundamental_metric_contradicted_by_evidence",
        }
        semantic_claims = semantic.get("claims") if isinstance(semantic.get("claims"), list) else []
        retained_claims = {
            str(text).strip()
            for text in _string_list(memo.get("key_claims"))
            if str(text).strip()
        }
        bad_claims = [
            row
            for row in semantic_claims
            if (
                isinstance(row, Mapping)
                and structural_evidence_errors.intersection(row.get("reasons") or [])
                and (
                    not str(row.get("text") or row.get("safeText") or "").strip()
                    or str(row.get("text") or "").strip() in retained_claims
                    or str(row.get("safeText") or "").strip() in retained_claims
                )
            )
        ]
        if bad_claims:
            raise ValueError("CIO claim citations do not cover every stated subject, domain and number")
        if str(memo.get("next_action") or "").strip() == "继续复核证据、反证和触发条件。":
            raise ValueError("CIO next_action must include do-not, watch and next-review guidance")
        if _string_list(memo.get("counterpoints")) == ["若证据过时、来源降级或关键事实缺失，结论需要下调置信度。"]:
            raise ValueError("CIO counterpoints must synthesize the strongest RedTeam challenge")
        adjudication = memo.get("adjudication") if isinstance(memo.get("adjudication"), Mapping) else {}
        if not str(adjudication.get("judgment") or "").strip():
            raise ValueError("CIO adjudication missing")
        if not str(adjudication.get("baseCase") or "").strip():
            raise ValueError("CIO base case missing after evidence validation")
        if not str(adjudication.get("strongestAlternative") or "").strip():
            raise ValueError("CIO strongest alternative missing")
        if not str(adjudication.get("why") or "").strip():
            raise ValueError("CIO evidence-weight explanation missing after validation")
    if spec.agent == "RedTeamAgent" and not list(memo.get("challenges") or []):
        raise ValueError("RedTeam challenges missing")


def _apply_semantic_gate_to_memo(
    memo: Dict[str, Any],
    spec: DepartmentSpec,
    evidence_rows: Sequence[Mapping[str, Any]],
) -> None:
    """Validate evidence relevance before a memo reaches downstream agents."""

    reference_date = str(memo.get("run_date") or "")
    raw_claims = [dict(row) for row in memo.get("claim_evidence") or [] if isinstance(row, Mapping)]
    if not raw_claims:
        refs = _string_list(memo.get("evidence_ids"))
        raw_claims = [
            {"claim": claim, "evidence_ids": refs}
            for claim in _string_list(memo.get("key_claims"))
        ]
    validations = validate_claim_dicts(
        raw_claims,
        list(evidence_rows),
        source_agent=spec.agent,
        reference_date=reference_date,
    )
    safe_claims: List[str] = []
    safe_mappings: List[Dict[str, Any]] = []
    validation_rows: List[Dict[str, Any]] = []
    warnings: List[str] = []
    for raw, validation in zip(raw_claims, validations):
        status = validation.normalized_status()
        validation_rows.append({
            "claimId": validation.claim_id,
            "text": str(raw.get("claim") or raw.get("text") or ""),
            "safeText": validation.safe_text,
            "status": status.value,
            "reasons": list(validation.reasons),
            "acceptedEvidenceIds": list(validation.accepted_evidence_ids),
            "rejectedEvidenceIds": list(validation.rejected_evidence_ids),
        })
        warnings.extend(validation.reasons)
        if status == ClaimStatus.REJECTED or not validation.safe_text:
            continue
        safe_claims.append(validation.safe_text)
        safe_mappings.append({
            "claimId": validation.claim_id,
            "claim": validation.safe_text,
            "claimType": str(raw.get("claimType") or raw.get("claim_type") or "interpretation"),
            "subject": str(raw.get("subject") or ""),
            "domain": str(raw.get("domain") or ""),
            "metric": str(raw.get("metric") or ""),
            "evidence_ids": list(validation.accepted_evidence_ids),
            "semanticStatus": status.value,
        })

    summary_validation: Dict[str, Any] = {}
    summary_text = str(memo.get("summary_for_reader") or "").strip()
    if summary_text:
        safe_summary_evidence_ids = _dedupe_strings(
            evidence_id
            for mapping in safe_mappings
            for evidence_id in mapping.get("evidence_ids") or []
        )
        summary_sentences = [
            sentence
            for sentence in _split_summary_sentences(summary_text)
            if _summary_sentence_matches_retained_claim(sentence, safe_claims)
        ]
        summary_claims = [
            {
                "claimId": f"{spec.agent}:summary:{index + 1}",
                "claim": sentence,
                "claimType": "interpretation",
                "evidence_ids": safe_summary_evidence_ids,
            }
            for index, sentence in enumerate(summary_sentences)
        ]
        summary_results = validate_claim_dicts(
            summary_claims,
            list(evidence_rows),
            source_agent=spec.agent,
            reference_date=reference_date,
        )
        if summary_results:
            status_order = {
                ClaimStatus.SUPPORTED: 0,
                ClaimStatus.PARTIAL: 1,
                ClaimStatus.HYPOTHESIS: 2,
                ClaimStatus.DISPUTED: 3,
                ClaimStatus.REJECTED: 4,
            }
            safe_sentences = [result.safe_text for result in summary_results if result.safe_text]
            composite_status = max(
                (result.normalized_status() for result in summary_results),
                key=lambda status: status_order[status],
            )
            summary_validation = {
                "status": composite_status.value if safe_sentences else ClaimStatus.REJECTED.value,
                "sentences": [
                    {
                        "claimId": result.claim_id,
                        "status": result.normalized_status().value,
                        "reasons": list(result.reasons),
                        "acceptedEvidenceIds": list(result.accepted_evidence_ids),
                        "rejectedEvidenceIds": list(result.rejected_evidence_ids),
                    }
                    for result in summary_results
                ],
            }
            for result in summary_results:
                warnings.extend(result.reasons)
            safe_summary = _clean_reader_punctuation(
                "".join(safe_sentences) or (safe_claims[0] if safe_claims else "")
            )
            if safe_summary:
                for field in ("summary_for_reader", "readable_summary", "conclusion"):
                    memo[field] = safe_summary
        elif safe_claims:
            for field in ("summary_for_reader", "readable_summary", "conclusion"):
                memo[field] = safe_claims[0]

    semantic_repairs: List[str] = []
    counterpoint_validations, safe_counterpoints = _validate_reader_claims(
        texts=_string_list(memo.get("counterpoints")),
        prefix=f"{spec.agent}:counterpoint",
        claim_type="scenario",
        evidence_ids=_string_list(memo.get("evidence_ids")),
        evidence_rows=evidence_rows,
        source_agent=spec.agent,
        reference_date=reference_date,
    )
    warnings.extend(
        reason
        for row in counterpoint_validations
        for reason in row.get("reasons") or []
    )
    if not safe_counterpoints and safe_claims and spec.agent != "RedTeamAgent":
        safe_counterpoints = [_neutral_counterpoint(spec)]
        semantic_repairs.append("neutral_counterpoint_after_rejected_counterpoints")
    memo["counterpoints"] = safe_counterpoints

    next_action_validations, safe_next_actions = _validate_reader_claims(
        texts=_split_summary_sentences(str(memo.get("next_action") or "")),
        prefix=f"{spec.agent}:next_action",
        claim_type="recommendation",
        evidence_ids=_string_list(memo.get("evidence_ids")),
        evidence_rows=evidence_rows,
        source_agent=spec.agent,
        reference_date=reference_date,
    )
    warnings.extend(
        reason
        for row in next_action_validations
        for reason in row.get("reasons") or []
    )
    memo["next_action"] = _clean_reader_punctuation("；".join(safe_next_actions))

    adjudication_validation: Dict[str, Any] = {}
    challenge_validation: Dict[str, Any] = {}
    if spec.agent == "RedTeamAgent" and isinstance(memo.get("challenges"), list):
        sanitized_challenges, challenge_validation = _validate_red_team_challenges(
            memo.get("challenges") or [],
            evidence_rows=evidence_rows,
            reference_date=reference_date,
        )
        memo["challenges"] = sanitized_challenges
        if (
            str(summary_validation.get("status") or "").lower() == ClaimStatus.REJECTED.value
            and sanitized_challenges
        ):
            repaired_summary = str(sanitized_challenges[0].get("opposingScenario") or "").strip()
            if repaired_summary:
                for field in ("summary_for_reader", "readable_summary", "conclusion"):
                    memo[field] = repaired_summary
                summary_validation = {
                    "status": ClaimStatus.HYPOTHESIS.value,
                    "sentences": [],
                    "repairedFrom": "validated_red_team_challenge",
                }
                semantic_repairs.append("summary_from_validated_red_team_challenge")
        if not _string_list(memo.get("counterpoints")) and sanitized_challenges:
            memo["counterpoints"] = _dedupe_strings(
                row.get("opposingScenario")
                for row in sanitized_challenges
                if isinstance(row, Mapping)
            )[:3]
            semantic_repairs.append("counterpoints_from_validated_challenges")
    if spec.agent == "CIOAgent" and isinstance(memo.get("adjudication"), Mapping):
        sanitized_adjudication, adjudication_validation = _validate_cio_adjudication(
            memo.get("adjudication") or {},
            evidence_ids=_string_list(memo.get("evidence_ids")),
            evidence_rows=evidence_rows,
            reference_date=reference_date,
        )
        memo["adjudication"] = sanitized_adjudication

    memo["key_claims"] = safe_claims
    memo["facts"] = list(safe_claims)
    memo["reasoning"] = list(safe_claims)
    memo["claim_evidence"] = safe_mappings
    sanitized_gaps = _sanitize_data_gaps(
        _string_list(memo.get("data_gaps")),
        evidence_rows=evidence_rows,
    )
    memo["data_gaps"] = sanitized_gaps
    memo["missing_data"] = list(sanitized_gaps)
    if not str(memo.get("next_action") or "").strip() and safe_claims:
        memo["next_action"] = _neutral_next_review_action(spec)
        semantic_repairs.append("neutral_next_action_after_rejected_recommendation")
    memo["semantic_validation"] = {
        "schema": "claim_semantic_validation_v1",
        "sourceAgent": spec.agent,
        "inputClaimCount": len(raw_claims),
        "readerClaimCount": len(safe_claims),
        "claims": validation_rows,
        "summary": summary_validation,
        "counterpoints": counterpoint_validations,
        "nextActions": next_action_validations,
        "challenges": challenge_validation,
        "adjudication": adjudication_validation,
    }
    memo["semantic_warnings"] = _dedupe_strings(warnings)
    memo["semantic_repairs"] = semantic_repairs
    statuses = {row["status"] for row in validation_rows}
    if statuses and statuses <= {ClaimStatus.HYPOTHESIS.value, ClaimStatus.DISPUTED.value}:
        memo["confidence"] = "low"
    elif ClaimStatus.HYPOTHESIS.value in statuses or ClaimStatus.REJECTED.value in statuses:
        memo["confidence"] = "medium"


def _neutral_next_review_action(spec: DepartmentSpec) -> str:
    if spec.agent == "GeoPolicyAgent":
        return "继续核验最新官方制裁、出口管制和冲突升级信息；出现直接传导证据时再调整判断。"
    if spec.agent == "IntelAgent":
        return "继续回跳交易所、监管机构与公司公告核验关键事件；未核实线索不进入核心结论。"
    if spec.agent == "PortfolioAgent":
        return "接入真实持仓后复核组合暴露；在此之前只跟踪观察池变化。"
    return "下一轮继续复核直接证据、主要反证和结论翻转条件。"


def _neutral_counterpoint(spec: DepartmentSpec) -> str:
    if spec.agent == "RiskAgent":
        return "若市场宽度、流动性或官方事件与当前价格及信用证据同步恶化，应上调风险等级。"
    if spec.agent == "PortfolioAgent":
        return "未接入真实持仓；观察池的风格分散不能代表实际组合已经获得对冲。"
    return "若后续直接证据与本轮判断反向变化，应降低置信度并重新评估。"


def _sanitize_data_gaps(
    gaps: Sequence[str],
    *,
    evidence_rows: Sequence[Mapping[str, Any]],
) -> List[str]:
    """Drop gaps that are already answered by a more direct registered series."""

    evidence_text = " ".join(
        f"{row.get('id', '')} {row.get('metric', '')} {row.get('value', '')}".upper()
        for row in evidence_rows
        if isinstance(row, Mapping)
    )
    out: List[str] = []
    for gap in gaps:
        text = str(gap or "").strip()
        upper = text.upper()
        if (
            "DGS2" in upper
            and ("10Y-2Y" in upper or "收益率曲线" in text or "利差" in text)
            and "T10Y2Y" in evidence_text
        ):
            continue
        out.append(text)
    return _dedupe_strings(out)


def _validate_red_team_challenges(
    values: Sequence[Mapping[str, Any]],
    *,
    evidence_rows: Sequence[Mapping[str, Any]],
    reference_date: str = "",
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    challenge_rows = [
        row
        for row in values
        if isinstance(row, Mapping) and str(row.get("opposingScenario") or "").strip()
    ]
    claims = [
        {
            "claimId": f"RedTeamAgent:challenge:{index + 1}",
            "claim": str(row.get("opposingScenario") or ""),
            "claimType": "scenario",
            "evidence_ids": list(row.get("evidence_ids") or []),
        }
        for index, row in enumerate(challenge_rows)
    ]
    results = validate_claim_dicts(
        claims,
        list(evidence_rows),
        source_agent="RedTeamAgent",
        reference_date=reference_date,
    )
    sanitized: List[Dict[str, Any]] = []
    audit_rows: List[Dict[str, Any]] = []
    for raw, result in zip(challenge_rows, results):
        status = result.normalized_status()
        audit_rows.append({
            "claimId": result.claim_id,
            "targetClaimId": str(raw.get("targetClaimId") or ""),
            "status": status.value,
            "reasons": list(result.reasons),
            "acceptedEvidenceIds": list(result.accepted_evidence_ids),
            "rejectedEvidenceIds": list(result.rejected_evidence_ids),
            "safeText": result.safe_text,
        })
        if status == ClaimStatus.REJECTED or not result.safe_text:
            continue
        sanitized.append({
            "targetClaimId": str(raw.get("targetClaimId") or ""),
            "issueType": str(raw.get("issueType") or "alternative_cause"),
            "opposingScenario": result.safe_text,
            "evidence_ids": list(result.accepted_evidence_ids),
            "falsifier": str(raw.get("falsifier") or "").strip(),
            "validationStatus": status.value,
        })
    return sanitized, {
        "schema": "red_team_challenge_semantic_v1",
        "inputChallengeCount": len(claims),
        "readerChallengeCount": len(sanitized),
        "challenges": audit_rows,
    }


def _validate_cio_adjudication(
    value: Mapping[str, Any],
    *,
    evidence_ids: Sequence[str],
    evidence_rows: Sequence[Mapping[str, Any]],
    reference_date: str = "",
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    field_contracts = {
        "sharedFacts": (value.get("sharedFacts") or [], "fact"),
        "baseCase": ([value.get("baseCase")] if value.get("baseCase") else [], "interpretation"),
        "strongestAlternative": ([value.get("strongestAlternative")] if value.get("strongestAlternative") else [], "scenario"),
        "judgment": ([value.get("judgment")] if value.get("judgment") else [], "recommendation"),
        "why": ([value.get("why")] if value.get("why") else [], "interpretation"),
        "invalidationTriggers": (value.get("invalidationTriggers") or [], "scenario"),
    }
    sanitized: Dict[str, Any] = {}
    audit: Dict[str, Any] = {"schema": "cio_adjudication_semantic_v1", "fields": {}}
    for field, (texts, claim_type) in field_contracts.items():
        rows, safe = _validate_reader_claims(
            texts=_string_list(texts),
            prefix=f"CIOAgent:adjudication:{field}",
            claim_type=claim_type,
            evidence_ids=evidence_ids,
            evidence_rows=evidence_rows,
            source_agent="CIOAgent",
            reference_date=reference_date,
        )
        if field == "sharedFacts":
            supported = [
                row.get("safeText")
                for row in rows
                if row.get("status") in {ClaimStatus.SUPPORTED.value, ClaimStatus.PARTIAL.value}
                and row.get("safeText")
            ]
            sanitized[field] = _dedupe_strings(supported)[:3]
        elif field == "invalidationTriggers":
            sanitized[field] = safe[:3]
        else:
            sanitized[field] = safe[0] if safe else ""
        audit["fields"][field] = rows
    audit["validated"] = all(
        bool(sanitized.get(field))
        for field in ("baseCase", "strongestAlternative", "judgment", "why")
    )
    return sanitized, audit


def _split_summary_sentences(text: str) -> List[str]:
    rows = [
        item.strip()
        for item in re.split(r"(?<=[。！？!?；;])", str(text or ""))
        if item.strip(" \t\r\n。！？!?；;")
    ]
    return rows or ([str(text).strip()] if str(text).strip() else [])


def _summary_sentence_matches_retained_claim(sentence: str, safe_claims: Sequence[str]) -> bool:
    """Prevent rejected detailed claims from resurfacing through a broad memo summary."""

    normalized = re.sub(r"[\s，。；：、！？!?;:]", "", str(sentence or ""))
    if not normalized:
        return False
    for claim in safe_claims:
        candidate = re.sub(r"[\s，。；：、！？!?;:]", "", str(claim or ""))
        if candidate and (normalized in candidate or candidate in normalized):
            return True
    return False


def _validate_reader_claims(
    *,
    texts: Sequence[str],
    prefix: str,
    claim_type: str,
    evidence_ids: Sequence[str],
    evidence_rows: Sequence[Mapping[str, Any]],
    source_agent: str,
    reference_date: str = "",
) -> tuple[List[Dict[str, Any]], List[str]]:
    claims = [
        {
            "claimId": f"{prefix}:{index + 1}",
            "claim": text,
            "claimType": claim_type,
            "evidence_ids": list(evidence_ids),
        }
        for index, text in enumerate(texts)
        if str(text).strip()
    ]
    results = validate_claim_dicts(
        claims,
        list(evidence_rows),
        source_agent=source_agent,
        reference_date=reference_date,
    )
    rows: List[Dict[str, Any]] = []
    safe: List[str] = []
    for claim, result in zip(claims, results):
        status = result.normalized_status()
        rows.append({
            "claimId": result.claim_id,
            "text": str(claim.get("claim") or ""),
            "safeText": result.safe_text,
            "status": status.value,
            "reasons": list(result.reasons),
            "acceptedEvidenceIds": list(result.accepted_evidence_ids),
            "rejectedEvidenceIds": list(result.rejected_evidence_ids),
        })
        if status != ClaimStatus.REJECTED and result.safe_text:
            safe.append(result.safe_text)
    return rows, _dedupe_strings(safe)


def _validate_macro_claim_methodology(memo: Mapping[str, Any]) -> None:
    rows = list(memo.get("claim_evidence") or [])
    if not rows:
        refs = _string_list(memo.get("evidence_ids"))
        rows = [
            {"claim": claim, "evidence_ids": refs}
            for claim in _string_list(memo.get("key_claims"))
        ]
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        claim = str(row.get("claim") or "")
        refs = [str(item).upper() for item in row.get("evidence_ids") or []]
        error = _macro_claim_methodology_error(claim, refs)
        if error:
            raise ValueError(error)


def _sanitize_macro_memo(memo: Dict[str, Any]) -> None:
    """Drop unsupported comparative claims while preserving useful LLM analysis."""

    all_refs = [str(item).upper() for item in _string_list(memo.get("evidence_ids"))]
    kept_claims: List[str] = []
    kept_mappings: List[Dict[str, Any]] = []
    warnings: List[str] = []
    mapping_by_claim = {
        str(row.get("claim") or ""): dict(row)
        for row in memo.get("claim_evidence") or []
        if isinstance(row, Mapping)
    }
    for claim in _string_list(memo.get("key_claims")):
        mapping = mapping_by_claim.get(claim)
        refs = [str(item).upper() for item in (mapping or {}).get("evidence_ids") or all_refs]
        error = _macro_claim_methodology_error(claim, refs)
        if error:
            warnings.append(error)
            continue
        kept_claims.append(claim)
        if mapping:
            kept_mappings.append(mapping)
    memo["key_claims"] = kept_claims
    memo["facts"] = list(kept_claims)
    memo["reasoning"] = list(kept_claims)
    memo["claim_evidence"] = kept_mappings
    summary_text = str(memo.get("summary_for_reader") or "")
    safe_summary = _drop_unsupported_macro_sentences(summary_text, all_refs)
    if safe_summary != summary_text.strip():
        warnings.append("macro_methodology: unsupported summary sentence removed")
    if warnings:
        memo["methodology_warnings"] = _dedupe_strings(warnings)
        if not safe_summary and kept_claims:
            safe_summary = kept_claims[0]
        if safe_summary:
            for field in ("summary_for_reader", "readable_summary", "conclusion"):
                memo[field] = safe_summary


def _macro_claim_methodology_error(claim: str, refs: Sequence[str]) -> str:
    if re.search(r"收益率曲线|倒挂|衰退警报", claim):
        has_short_treasury = any(
            token in ref
            for ref in refs
            for token in ("DGS2", "DGS3MO", "T10Y2Y", "T10Y3M")
        )
        if not has_short_treasury:
            return (
                "macro_methodology: yield-curve claims require comparable Treasury maturities; "
                "DGS10 versus DFF/FEDFUNDS is invalid"
            )
    if re.search(r"历史.{0,8}(?:低位|高位|分位)|极度.{0,5}(?:低位|高位)", claim):
        has_historical_context = any(
            token in ref
            for ref in refs
            for token in ("HISTORY", "PERCENTILE", "ZSCORE", "TIMESERIES")
        )
        if not has_historical_context:
            return "macro_methodology: historical-level claims require historical distribution evidence"
    if re.search(r"陡峭化|走陡|走平|趋陡|趋平", claim):
        has_spread_history = any(
            token in ref
            for ref in refs
            for token in ("T10Y2Y_HISTORY", "T10Y3M_HISTORY", "YIELD_CURVE_HISTORY", "TIMESERIES")
        )
        if not has_spread_history:
            return "macro_methodology: curve-change claims require historical spread comparison"
    return ""


def _drop_unsupported_macro_sentences(text: str, refs: Sequence[str]) -> str:
    sentences = [item.strip() for item in re.split(r"(?<=[。！？!?])", text) if item.strip()]
    kept = [sentence for sentence in sentences if not _macro_claim_methodology_error(sentence, refs)]
    return "".join(kept).strip()


def _fill_missing_memo_fields(memo: Dict[str, Any], spec: DepartmentSpec, valid_refs: Set[str]) -> None:
    if not _string_list(memo.get("counterpoints")):
        if spec.agent == "IntelAgent":
            memo["counterpoints"] = ["新闻和搜索线索必须回跳公告、交易所、SEC 或公司 IR 后才能升级为事实。"]
        elif spec.agent == "RedTeamAgent":
            memo["counterpoints"] = ["需持续检查结论是否被单一信号、过期证据或 discovery 线索带偏。"]
        else:
            memo["counterpoints"] = ["若证据过时、来源降级或关键事实缺失，结论需要下调置信度。"]
    if not str(memo.get("next_action") or "").strip():
        memo["next_action"] = "继续复核证据、反证和触发条件。"
    # Never manufacture a citation on behalf of the model.  A department that
    # omitted evidence must fail validation and retry/fallback explicitly.


def _is_non_evidence_reference_noise(value: str) -> bool:
    text = str(value or "").strip().lower()
    return (
        text.startswith("kind:")
        or text.startswith("originalanalysisrefs:")
        or text.startswith("error_type:")
        or text.startswith("providersummary")
        or text.startswith("sourcehealth")
    )


def _counterpoints_for_payload(spec: DepartmentSpec, payload: Mapping[str, Any]) -> List[str]:
    counterpoints = _string_list(payload.get("counterpoints"))
    if counterpoints:
        return counterpoints
    if spec.agent == "PortfolioAgent":
        gaps = _string_list(payload.get("data_gaps"))
        if gaps:
            return [f"组合/持仓口径限制：{gaps[0]}"]
        return ["当前结构化持仓为空，组合影响只能作为观察，不能外推到真实账户。"]
    if spec.agent == "RedTeamAgent":
        claims = _string_list(payload.get("key_claims"))
        if claims:
            return claims
    return []


def _mark_fallback(memo: Mapping[str, Any], *, reason: str) -> Dict[str, Any]:
    out = dict(memo)
    out.update(
        {
            "origin": ORIGIN,
            "origin_label": "规则部门 Agent fallback",
            "runtime_kind": RULE_FALLBACK_RUNTIME_KIND,
            "agentRuntime": "RULE_FALLBACK",
            "llm_status": "fallback",
            "llm_error": _clip(reason, 300),
        }
    )
    return out


def _write_llm_runs(path: Path, runs: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in runs),
        encoding="utf-8",
    )


def _append_llm_run(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")


def _sort_runs_by_spec(runs: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    order = {spec.agent: idx for idx, spec in enumerate(DEPARTMENT_SPECS)}
    return [dict(row) for row in sorted(runs, key=lambda row: order.get(str(row.get("agent") or ""), 999))]


def _emit_progress(callback: Optional[Callable[[Mapping[str, Any]], None]], row: Mapping[str, Any]) -> None:
    if callback is None:
        return
    try:
        callback(row)
    except Exception:
        return


def _run_row(
    spec: DepartmentSpec,
    *,
    status: str,
    model: str = "",
    provider: str = "",
    backend: str = "litellm",
    usage: Optional[Mapping[str, Any]] = None,
    error_type: Optional[str] = None,
    error: Optional[str] = None,
    attempt: int | None = None,
    duration_seconds: float | None = None,
    attempt_durations: Optional[Sequence[float]] = None,
) -> Dict[str, Any]:
    row = {
        "schema": LLM_RUNS_SCHEMA,
        "agent": spec.agent,
        "label": spec.label,
        "status": status,
        "runtimeKind": LLM_RUNTIME_KIND if status == "success" else RULE_FALLBACK_RUNTIME_KIND,
        "backend": backend,
        "provider": provider,
        "model": model,
        "attempt": attempt,
        "usage": _safe_usage(usage or {}),
        "errorType": error_type,
        "error": _clip(error or "", 300),
        "durationSeconds": duration_seconds,
        "attemptDurationsSeconds": list(attempt_durations or []),
    }
    return {key: value for key, value in row.items() if value not in (None, "", {}, [])}


def _summarize_runs(runs: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    success = sum(1 for row in runs if row.get("status") == "success")
    fallback = sum(1 for row in runs if row.get("status") != "success")
    prompt_tokens = sum(_int_usage(row, "prompt_tokens") for row in runs)
    completion_tokens = sum(_int_usage(row, "completion_tokens") for row in runs)
    total_tokens = sum(_int_usage(row, "total_tokens") for row in runs)
    total_attempts = sum(int(row.get("attempt") or 1) for row in runs)
    llm_elapsed = sum(float(row.get("durationSeconds") or 0.0) for row in runs)
    return {
        "llmSuccessCount": success,
        "fallbackCount": fallback,
        "totalAgents": len(runs),
        "totalAttempts": total_attempts,
        "retryCount": max(0, total_attempts - len(runs)),
        "llmElapsedSeconds": _round_seconds(llm_elapsed),
        "tokenUsage": {
            "promptTokens": prompt_tokens,
            "completionTokens": completion_tokens,
            "totalTokens": total_tokens,
        },
        "allLlmSucceeded": fallback == 0 and len(runs) == len(DEPARTMENT_SPECS),
    }


def _upsert_llm_stage(docs: Path, run_date: str, summary: Mapping[str, Any]) -> None:
    llm_runs_path = docs / "run_status" / run_date / "llm_agent_runs.jsonl"
    status = "success" if summary.get("allLlmSucceeded") else "partial"
    upsert_run_matrix_stage(
        docs,
        run_date,
        {
            "name": "llm_department_agents",
            "status": status,
            "blocking": False,
            "inputs": [
                f"run_status/{run_date}/daily_universe.json",
                f"run_status/{run_date}/evidence_ledger.jsonl",
                f"run_status/{run_date}/source_health_v2.json",
            ],
            "outputs": [
                f"run_status/{run_date}/llm_agent_runs.jsonl",
                f"agent_memos/{run_date}/",
            ],
            "errorType": None if status == "success" else "llm_fallback",
            "sha256": sha256_file(llm_runs_path),
        },
    )


def _valid_evidence_ids(rows: Sequence[Mapping[str, Any]]) -> Set[str]:
    return {str(row.get("id")) for row in rows if isinstance(row, Mapping) and str(row.get("id") or "").strip()}


def _valid_refs_for_spec(
    context: Mapping[str, Any],
    spec: DepartmentSpec,
    previous_outputs: Mapping[str, Mapping[str, Any]],
) -> Set[str]:
    evidence_refs = _valid_evidence_ids(_prompt_evidence_for_spec(context, spec, previous_outputs))
    for ref in filter_original_refs_for_agent(context.get("originalAnalysisRefs") or [], spec.agent, limit=12):
        kind = str(ref.get("kind") or "").strip()
        if kind:
            evidence_refs.add(f"kind:{kind}")
            evidence_refs.add(f"kind: {kind}")
        for evidence_id in ref.get("evidenceIds") or []:
            if str(evidence_id):
                evidence_refs.add(str(evidence_id))
    memo_refs = {f"memo:{agent}" for agent in previous_outputs if not spec.depends_on or agent in spec.depends_on}
    return set(CONTEXT_REFS) | evidence_refs | memo_refs


def _evidence_limit_for_spec(spec: DepartmentSpec) -> int:
    if spec.agent in {"RiskAgent", "RedTeamAgent"}:
        return 8
    if spec.agent == "CIOAgent":
        return 12
    if spec.agent == "GeoPolicyAgent":
        return 18
    if spec.agent in {"MarketAgent", "SectorAgent", "IntelAgent"}:
        return 18
    return 12


_INTELLIGENCE_NOISE_MARKERS = (
    "social security",
    "dementia",
    "brain health",
    "financial adviser",
    "insurance settlement",
    "retirement income",
    "pension",
    "life expectancy",
    "tax bill",
    "my wife",
    "my husband",
    "my brother",
    "financially independent",
)
_INTELLIGENCE_MARKET_MARKERS = (
    "earnings",
    "inflation",
    "interest rate",
    "liquidity",
    "credit",
    "stock",
    "market",
    "etf",
    "ipo",
    "tariff",
    "sanction",
    "trade",
    "oil",
    "gas",
    "supply chain",
    "regulation",
    "财报",
    "通胀",
    "利率",
    "流动性",
    "信用",
    "股票",
    "市场",
    "公告",
    "制裁",
    "关税",
    "贸易",
    "供应链",
)
_INTELLIGENCE_GEO_MARKERS = (
    "war",
    "conflict",
    "attack",
    "strait",
    "hormuz",
    "sanction",
    "tariff",
    "export control",
    "trade restriction",
    "reliefweb",
    "ofac",
    "bis",
    "冲突",
    "战争",
    "袭击",
    "海峡",
    "制裁",
    "关税",
    "出口限制",
    "贸易限制",
)


def _intelligence_context_priority(item: Mapping[str, Any], agent: str) -> int:
    """Rank news for prompt context without deleting it from the ledger."""

    text = " ".join(str(item.get(key) or "").lower() for key in ("provider", "value", "id"))
    if any(marker in text for marker in _INTELLIGENCE_NOISE_MARKERS):
        return -20
    score = 0
    fact_type = str(item.get("fact_type") or "")
    if fact_type == "verified_fact":
        score += 8
    elif fact_type == "derived_fact":
        score += 5
    provider = str(item.get("provider") or "").lower()
    if any(marker in provider for marker in ("cninfo", "sse", "szse", "hkex", "sec", "fred", "ofac", "bis")):
        score += 3
    markers = _INTELLIGENCE_GEO_MARKERS if agent == "GeoPolicyAgent" else _INTELLIGENCE_MARKET_MARKERS
    if any(marker in text for marker in markers):
        score += 6
    if str(item.get("symbol") or "").lower() not in {"", "market", "macro", "geo_policy"}:
        score += 4
    return score


def _evidence_for_spec(rows: Sequence[Mapping[str, Any]], spec: DepartmentSpec, *, limit: int = 12) -> List[Dict[str, Any]]:
    domains = set(spec.input_domains)
    buckets: Dict[tuple[str, str, str], List[Dict[str, Any]]] = {}
    seen_ids: Set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if str(row.get("evidence_scope") or row.get("evidenceScope") or "subject_evidence") != "subject_evidence":
            continue
        fact_type = str(row.get("fact_type") or row.get("factType") or "").lower()
        if fact_type == "missing":
            continue
        if fact_type == "verified_fact" and not (
            row.get("source_url")
            or row.get("sourceUrl")
            or row.get("raw_path")
            or row.get("rawPath")
        ):
            continue
        domain = str(row.get("domain") or "")
        if domains and domain not in domains:
            continue
        fact_id = str(row.get("id") or "").strip()
        if fact_id and fact_id in seen_ids:
            continue
        if fact_id:
            seen_ids.add(fact_id)
        symbol = str(row.get("symbol") or row.get("subject") or "market")
        item = _compact_evidence_row(row, domain=domain)
        if (
            domain == "news_sentiment"
            and spec.agent in {"GeoPolicyAgent", "IntelAgent", "MarketAgent", "SectorAgent"}
            and _intelligence_context_priority(item, spec.agent) < 0
        ):
            continue
        market_hint = str(row.get("market") or "").strip().lower()
        market = {"cn": "CN", "a": "CN", "ashare": "CN", "hk": "HK", "us": "US"}.get(
            market_hint,
            _research_market_bucket(symbol, domain=domain),
        )
        buckets.setdefault((market, domain, symbol), []).append(item)

    if spec.agent in {"GeoPolicyAgent", "IntelAgent", "MarketAgent", "SectorAgent"}:
        for bucket in buckets.values():
            bucket.sort(
                key=lambda item: (
                    _intelligence_context_priority(item, spec.agent),
                    str(item.get("published_at") or item.get("event_time") or item.get("as_of") or ""),
                ),
                reverse=True,
            )

    if spec.agent == "GeoPolicyAgent":
        all_items = [item for bucket in buckets.values() for item in bucket]
        official_markers = ("ofac", "bis", "eu sanctions", "sanctions map", "外交部", "商务部")
        discovery_markers = ("tavily", "gdelt", "reliefweb")

        def source_text(item: Mapping[str, Any]) -> str:
            return " ".join(
                str(item.get(key) or "").lower()
                for key in ("id", "provider", "value")
            )

        official_geo = [item for item in all_items if any(marker in source_text(item) for marker in official_markers)]
        discovery_geo = [
            item
            for item in all_items
            if any(marker in source_text(item) for marker in discovery_markers) and item not in official_geo
        ]
        macro = [item for item in all_items if item.get("domain") == "macro"]
        remaining = [
            item
            for item in all_items
            if item not in official_geo and item not in discovery_geo and item not in macro
        ]
        selected: List[Dict[str, Any]] = []
        for group, cap in ((official_geo, 3), (discovery_geo, 8), (macro, 6), (remaining, limit)):
            for item in group[:cap]:
                if item not in selected and len(selected) < limit:
                    selected.append(item)
        return selected

    selected: List[Dict[str, Any]] = []
    market_buckets: Dict[str, List[tuple[str, str, str]]] = {}
    for key in buckets:
        market_buckets.setdefault(key[0], []).append(key)
    market_order = [market for market in ("GLOBAL", "CN", "HK", "US", "OTHER") if market in market_buckets]
    bucket_positions = {market: 0 for market in market_order}
    while market_order and len(selected) < limit:
        remaining_markets: List[str] = []
        for market in market_order:
            keys = market_buckets[market]
            if not keys:
                continue
            position = bucket_positions[market] % len(keys)
            key = keys[position]
            bucket = buckets[key]
            if bucket and len(selected) < limit:
                selected.append(bucket.pop(0))
            if not bucket:
                keys.pop(position)
                if keys:
                    bucket_positions[market] = position % len(keys)
            else:
                bucket_positions[market] = (position + 1) % len(keys)
            if keys:
                remaining_markets.append(market)
        market_order = remaining_markets
    return selected


def _prompt_evidence_for_spec(
    context: Mapping[str, Any],
    spec: DepartmentSpec,
    previous_outputs: Mapping[str, Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    rows = context.get("evidence") or []
    limit = _evidence_limit_for_spec(spec)
    selected = _evidence_for_spec(rows, spec, limit=limit)
    if spec.agent in {"MarketAgent", "RiskAgent", "RedTeamAgent", "CIOAgent"}:
        priority_markers = (":market:market_stats:", ":market:main_indices:")
        priority = [
            _compact_evidence_row(row, domain=str(row.get("domain") or ""))
            for row in rows
            if isinstance(row, Mapping)
            and any(marker in str(row.get("id") or "") for marker in priority_markers)
        ]
        selected = [
            *priority,
            *[
                row
                for row in selected
                if str(row.get("id") or "") not in {str(item.get("id") or "") for item in priority}
            ],
        ][:limit]
    selected_ids = _valid_evidence_ids(selected)
    if not spec.depends_on:
        return selected

    by_id = {
        str(row.get("id") or ""): row
        for row in rows
        if isinstance(row, Mapping) and str(row.get("id") or "").strip()
    }
    for evidence_id in _dependency_evidence_ids(previous_outputs, spec, limit=24):
        if evidence_id in selected_ids or evidence_id not in by_id:
            continue
        row = by_id[evidence_id]
        selected.append(_compact_evidence_row(row, domain=str(row.get("domain") or "")))
        selected_ids.add(evidence_id)
    return selected


def _dependency_evidence_ids(
    previous_outputs: Mapping[str, Mapping[str, Any]],
    spec: DepartmentSpec,
    *,
    limit: int,
) -> List[str]:
    out: List[str] = []
    for agent in spec.depends_on:
        memo = previous_outputs.get(agent)
        if not isinstance(memo, Mapping):
            continue
        per_memo: List[str] = []
        for mapping in memo.get("claim_evidence") or []:
            if not isinstance(mapping, Mapping):
                continue
            per_memo.extend(_string_list(mapping.get("evidence_ids")))
            if len(_dedupe_strings(per_memo)) >= 4:
                break
        if not per_memo:
            per_memo.extend(_string_list(memo.get("evidence_ids"))[:4])
        for evidence_id in _dedupe_strings(per_memo)[:4]:
            if evidence_id.startswith("memo:") or evidence_id in out:
                continue
            out.append(evidence_id)
            if len(out) >= limit:
                return out
    return out


def _compact_evidence_row(row: Mapping[str, Any], *, domain: str) -> Dict[str, Any]:
    compact = {
        "id": row.get("id"),
        "domain": domain,
        "symbol": row.get("symbol") or row.get("subject"),
        "metric": row.get("metric"),
        "fact_type": row.get("fact_type") or row.get("factType"),
        "provider": row.get("provider"),
        "value": _clip(str(row.get("value") or row.get("id") or ""), 520),
        "measurements": dict(row.get("measurements") or {}),
        "unit": row.get("unit"),
        "as_of": row.get("as_of") or row.get("asOf"),
        "event_time": row.get("event_time") or row.get("eventTime"),
        "published_at": row.get("published_at") or row.get("publishedAt"),
        "fetched_at": row.get("fetched_at") or row.get("fetchedAt"),
        "market": row.get("market"),
        "session_phase": row.get("session_phase") or row.get("sessionPhase"),
        "is_partial_bar": row.get("is_partial_bar") if "is_partial_bar" in row else row.get("isPartialBar"),
    }
    return {key: value for key, value in compact.items() if value not in (None, "", {}, [])}


def _provider_summary(rows: Sequence[Mapping[str, Any]], spec: DepartmentSpec) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    domains = set(spec.input_domains)
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if domains and str(row.get("domain") or row.get("data_type") or "") not in domains:
            continue
        out.append(
            {
                "provider": row.get("provider"),
                "operation": row.get("operation"),
                "domain": row.get("domain") or row.get("data_type"),
                "success": bool(row.get("success")),
                "record_count": row.get("record_count"),
                "error_type": row.get("error_type"),
            }
        )
        if len(out) >= 20:
            break
    return out


def _compact_universe_for_spec(universe: Mapping[str, Any], spec: DepartmentSpec) -> Dict[str, Any]:
    groups = universe.get("groups") if isinstance(universe.get("groups"), list) else []
    symbols = list(universe.get("subjectSymbols") or [])
    if spec.agent == "MacroAgent":
        return {
            "mode": universe.get("mode"),
            "market": universe.get("market"),
            "macro": universe.get("macro") or universe.get("macroSubjects") or [],
        }
    if spec.agent == "GeoPolicyAgent":
        return {
            "mode": universe.get("mode"),
            "market": universe.get("market"),
            "macro": universe.get("macro") or universe.get("macroSubjects") or [],
            "subjectSymbols": _balanced_symbols(symbols, limit=12),
        }
    if spec.agent in {"MarketAgent", "SectorAgent", "IntelAgent", "RiskAgent", "RedTeamAgent", "CIOAgent"}:
        return {
            "mode": universe.get("mode"),
            "market": universe.get("market"),
            "subjectSymbols": _balanced_symbols(symbols, limit=20),
            "groups": groups[:8],
        }
    return {
        "mode": universe.get("mode"),
        "subjectSymbols": _balanced_symbols(symbols, limit=12),
        "groups": [
            row
            for row in groups
            if isinstance(row, Mapping) and str(row.get("name") or "") in {"watchlist", "portfolio", "candidates"}
        ][:6],
    }


def _stock_summaries_for_spec(rows: Sequence[Mapping[str, Any]], spec: DepartmentSpec) -> List[Mapping[str, Any]]:
    if spec.agent in {"MacroAgent", "GeoPolicyAgent", "IntelAgent"}:
        return []
    if spec.agent in {"RiskAgent", "RedTeamAgent", "CIOAgent"}:
        return _balanced_stock_summaries(rows, limit=8)
    return _balanced_stock_summaries(rows, limit=6)


def _research_market_bucket(symbol: Any, *, domain: str = "") -> str:
    value = str(symbol or "").strip().upper()
    if str(domain or "") == "macro" or value in {"", "MARKET", "MACRO", "PORTFOLIO", "DAILY", "GLOBAL"}:
        return "GLOBAL"
    if re.fullmatch(r"(?:SH|SZ|BJ)?\d{6}", value):
        return "CN"
    if re.fullmatch(r"HK\d{4,5}", value) or re.fullmatch(r"\d{4,5}\.HK", value):
        return "HK"
    if re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", value):
        return "US"
    return "OTHER"


def _balanced_symbols(symbols: Sequence[Any], *, limit: int) -> List[str]:
    buckets: Dict[str, List[str]] = {}
    seen: Set[str] = set()
    for raw in symbols:
        symbol = str(raw or "").strip()
        if not symbol or symbol.upper() in seen:
            continue
        seen.add(symbol.upper())
        buckets.setdefault(_research_market_bucket(symbol), []).append(symbol)
    out: List[str] = []
    order = [market for market in ("CN", "HK", "US", "OTHER") if market in buckets]
    while order and len(out) < limit:
        remaining: List[str] = []
        for market in order:
            bucket = buckets[market]
            if bucket and len(out) < limit:
                out.append(bucket.pop(0))
            if bucket:
                remaining.append(market)
        order = remaining
    return out


def _balanced_stock_summaries(rows: Sequence[Mapping[str, Any]], *, limit: int) -> List[Mapping[str, Any]]:
    buckets: Dict[str, List[Mapping[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        symbol = row.get("code") or row.get("symbol") or row.get("stock_code") or row.get("subject")
        buckets.setdefault(_research_market_bucket(symbol), []).append(row)
    out: List[Mapping[str, Any]] = []
    order = [market for market in ("CN", "HK", "US", "OTHER", "GLOBAL") if market in buckets]
    while order and len(out) < limit:
        remaining: List[str] = []
        for market in order:
            bucket = buckets[market]
            if bucket and len(out) < limit:
                out.append(bucket.pop(0))
            if bucket:
                remaining.append(market)
        order = remaining
    return out


def _report_excerpts_for_spec(context: Mapping[str, Any], spec: DepartmentSpec) -> Dict[str, str]:
    # Markdown reports are presentation artifacts, not stable analysis
    # contracts.  Same-run original analysis reaches agents only through the
    # bounded analysis_history snapshot in originalAnalysisRefs.
    return {}


def _compact_original_analysis(original: Mapping[str, Any], spec: DepartmentSpec) -> Dict[str, Any]:
    return {
        "available": bool(original),
        "runDate": original.get("runDate"),
        "marketReviewAvailable": bool(original.get("marketReviewAvailable")),
        "marketContextAvailable": bool(original.get("marketContextAvailable")),
        "stockContextCount": int(original.get("stockContextCount") or 0),
        "stockAnalysisCount": int(original.get("stockAnalysisCount") or 0),
        "decisionSignalCount": int(original.get("decisionSignalCount") or 0),
        "portfolioSnapshotAvailable": bool(original.get("portfolioSnapshotAvailable")),
        "structuredSnapshotAvailable": bool(original.get("structuredSnapshotAvailable")),
        "structuredSnapshotSha256": original.get("structuredSnapshotSha256"),
        "relevantProfile": department_profile_payload(spec.agent).get("inputProfile"),
        "notes": list(original.get("notes") or [])[:4],
    }


def _compact_source_health(health: Mapping[str, Any], spec: Optional[DepartmentSpec] = None) -> Dict[str, Any]:
    domains = health.get("domains") if isinstance(health.get("domains"), Mapping) else {}
    allowed_domains = set(spec.input_domains) if spec is not None else set(domains.keys())
    return {
        "overallMode": health.get("overallMode"),
        "overallScore": health.get("overallScore"),
        "claimPolicy": health.get("claimPolicy") if isinstance(health.get("claimPolicy"), Mapping) else {},
        "evidenceStats": health.get("evidenceStats") if isinstance(health.get("evidenceStats"), Mapping) else {},
        "blockingReasons": list(health.get("blockingReasons") or [])[:12],
        "domains": {
            key: {
                "status": row.get("status"),
                "coverage": row.get("coverage"),
                "confidence": row.get("confidence"),
                "blockers": list(row.get("blockers") or [])[:5],
            }
            for key, row in domains.items()
            if isinstance(row, Mapping) and (not allowed_domains or key in allowed_domains)
        },
    }


def _compact_official(official: Mapping[str, Any]) -> Dict[str, Any]:
    facts = official.get("evidenceFacts") if isinstance(official.get("evidenceFacts"), list) else []
    return {
        "symbols": list(official.get("symbols") or [])[:20],
        "factCount": len(facts),
        "providers": sorted({str(item.get("provider")) for item in facts if isinstance(item, Mapping) and item.get("provider")}),
    }


def _compact_memo(memo: Mapping[str, Any]) -> Dict[str, Any]:
    raw_claims = memo.get("claim_evidence") if isinstance(memo.get("claim_evidence"), list) else []
    compact_claims: List[Dict[str, Any]] = []
    for item in raw_claims[:3]:
        if not isinstance(item, Mapping):
            continue
        claim = _clip(str(item.get("claim") or ""), 360)
        if not claim:
            continue
        row = {
            "claim": claim,
            "evidence_ids": _string_list(item.get("evidence_ids"))[:4],
            "claimType": item.get("claimType") or item.get("claim_type"),
            "subject": item.get("subject"),
            "domain": item.get("domain"),
        }
        compact_claims.append({key: value for key, value in row.items() if value not in (None, "", [], {})})
    if not compact_claims:
        compact_claims = [
            {"claim": _clip(text, 360)}
            for text in _string_list(memo.get("key_claims"))[:3]
            if text
        ]
    compact = {
        "ref": f"memo:{memo.get('agent')}",
        "agent": memo.get("agent"),
        "summary_for_reader": _clip(str(memo.get("summary_for_reader") or ""), 600),
        "key_claims": compact_claims,
        "evidence_ids": _string_list(memo.get("evidence_ids"))[:6],
        "counterpoints": [_clip(text, 300) for text in _string_list(memo.get("counterpoints"))[:3]],
        "data_gaps": [_clip(text, 240) for text in _string_list(memo.get("data_gaps"))[:3]],
        "next_action": _compact_prompt_value(memo.get("next_action"), limit=360),
    }
    if memo.get("challenges"):
        compact["challenges"] = [
            _compact_prompt_mapping(item, text_limit=320)
            for item in list(memo.get("challenges") or [])[:3]
            if isinstance(item, Mapping)
        ]
    if memo.get("adjudication"):
        compact["adjudication"] = _compact_prompt_mapping(
            dict(memo.get("adjudication") or {}),
            text_limit=360,
        )
    return compact


def _compact_original_refs_for_prompt(refs: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Keep upstream conclusions usable without repeating hashes and raw adapter payloads."""

    out: List[Dict[str, Any]] = []
    analysis_fields = {
        "action",
        "analysisSummary",
        "confidenceLevel",
        "coreConclusion",
        "operationAdvice",
        "riskWarning",
        "keyPoints",
        "sentimentScore",
        "currentPrice",
        "changePct",
    }
    for ref in refs:
        analysis = ref.get("analysis") if isinstance(ref.get("analysis"), Mapping) else {}
        compact_analysis = {
            str(key): _compact_prompt_value(value, limit=420)
            for key, value in analysis.items()
            if str(key) in analysis_fields and value not in (None, "", [], {})
        }
        row = {
            "kind": ref.get("kind"),
            "status": ref.get("status"),
            "summary": _clip(str(ref.get("summary") or ""), 420),
            "analysis": compact_analysis,
            "evidenceIds": _string_list(ref.get("evidenceIds"))[:8],
            "symbols": _string_list(ref.get("symbols"))[:8],
        }
        out.append({key: value for key, value in row.items() if value not in (None, "", [], {})})
    return out


def _compact_prompt_mapping(value: Mapping[str, Any], *, text_limit: int) -> Dict[str, Any]:
    return {
        str(key): _compact_prompt_value(item, limit=text_limit)
        for key, item in value.items()
        if item not in (None, "", [], {})
    }


def _compact_prompt_value(value: Any, *, limit: int) -> Any:
    if isinstance(value, Mapping):
        return _compact_prompt_mapping(value, text_limit=limit)
    if isinstance(value, list):
        return [
            _compact_prompt_value(item, limit=limit)
            for item in value[:6]
            if item not in (None, "", [], {})
        ]
    if isinstance(value, str):
        return _clip(value, limit)
    return value


def _claim_payload(value: Any) -> tuple[List[str], List[Dict[str, Any]], List[str]]:
    raw = value if isinstance(value, list) else ([value] if value not in (None, "") else [])
    claims: List[str] = []
    mappings: List[Dict[str, Any]] = []
    refs: List[str] = []
    for item in raw:
        if isinstance(item, Mapping):
            claim = str(item.get("claim") or item.get("point") or item.get("summary") or "").strip()
            item_refs = _dedupe_strings(
                _string_list(
                    item.get("evidence_ids")
                    or item.get("supporting_evidence_ids")
                    or item.get("source_refs")
                )
            )
            if claim:
                claims.append(claim)
                if item_refs:
                    mapping = {"claim": claim, "evidence_ids": item_refs}
                    optional_fields = {
                        "claimId": item.get("claimId") or item.get("claim_id"),
                        "claimType": item.get("claimType") or item.get("claim_type"),
                        "subject": item.get("subject"),
                        "domain": item.get("domain"),
                        "metric": item.get("metric"),
                        "timeScope": item.get("timeScope") or item.get("time_scope"),
                    }
                    mapping.update({key: str(raw) for key, raw in optional_fields.items() if raw not in (None, "")})
                    mappings.append(mapping)
                    refs.extend(item_refs)
            continue
        text = str(item or "").strip()
        if text:
            claims.append(text)
    return _dedupe_strings(claims), mappings, _dedupe_strings(refs)


def _dedupe_strings(values: Iterable[Any]) -> List[str]:
    out: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _parse_json_object(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        try:
            from json_repair import repair_json  # noqa: WPS433 - optional parser repair

            payload = json.loads(repair_json(raw))
        except Exception:
            payload = None
        if isinstance(payload, dict):
            return payload
        match = re.search(r"\{.*\}", raw, re.S)
        if not match:
            raise
        snippet = match.group(0)
        try:
            payload = json.loads(snippet)
        except json.JSONDecodeError:
            try:
                from json_repair import repair_json  # noqa: WPS433 - optional parser repair

                payload = json.loads(repair_json(snippet))
            except Exception:
                raise
    if not isinstance(payload, dict):
        raise ValueError("LLM output must be a JSON object")
    return payload


def _parse_agent_output(text: str, spec: DepartmentSpec) -> Dict[str, Any]:
    """Parse LLM output without forcing JSON-only generation.

    The runtime still accepts JSON because fake/test backends and some models are
    better at it.  Product prompts, however, can return readable Markdown
    sections.  Parsed Markdown is marked ``parse_partial`` so diagnostics can
    distinguish it from strict structured output without pretending it was a
    perfect JSON response.
    """

    raw = str(text or "").strip()
    try:
        payload = _parse_json_object(raw)
        payload = _normalize_agent_payload(payload)
        payload.setdefault("_parse_status", "structured")
        return payload
    except Exception:
        pass

    sections = _parse_markdown_sections(raw)
    summary = _first_section(sections, "结论", "总结", "今日结论", "summary", "conclusion")
    next_action = _first_section(sections, "下一步", "next_action", "next action")
    confidence = _first_section(sections, "置信度", "confidence") or "medium"
    payload = {
        "agent": spec.agent,
        "summary_for_reader": summary or _clip(raw, 500),
        "key_claims": _markdown_items(_first_section(sections, "依据", "核心依据", "理由", "key_claims", "claims")),
        "evidence_ids": _extract_evidence_ids(
            _first_section(sections, "引用 evidence id", "证据", "evidence", "evidence_ids", "引用")
        ),
        "counterpoints": _markdown_items(_first_section(sections, "反证", "风险", "counterpoints", "risks")),
        "data_gaps": _markdown_items(_first_section(sections, "待确认项", "数据缺口", "缺口", "data_gaps", "gaps")),
        "confidence": confidence.strip().split()[0] if isinstance(confidence, str) else "medium",
        "next_action": next_action or "",
        "_parse_status": "parse_partial",
        "_raw_output": raw,
    }
    if spec.agent == "CIOAgent":
        payload["adjudication"] = {
            "sharedFacts": _markdown_items(_first_section(sections, "双方共同事实", "共同事实")),
            "baseCase": _first_section(sections, "基准情景"),
            "strongestAlternative": _first_section(sections, "最强竞争情景", "最强相反情景", "竞争情景", "替代情景", "反方情景"),
            "judgment": _first_section(sections, "CIO裁决", "当前裁决", "裁决"),
            "why": _first_section(sections, "裁决理由", "为什么"),
            "invalidationTriggers": _markdown_items(_first_section(sections, "翻转信号", "失效条件")),
        }
    return payload


def _normalize_agent_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Accept Chinese-keyed agent output without forcing JSON-only prompts.

    Some stronger models follow the reader-facing headings literally and return
    keys such as ``结论`` / ``依据`` / ``下一步`` even when the surrounding
    object is valid JSON.  The runtime contract stays English internally, but
    the parser should not downgrade a useful CIO memo just because the keys are
    localized.
    """

    data = dict(payload)
    normalized = dict(data)
    field_aliases = {
        "summary_for_reader": ("summary_for_reader", "readable_summary", "summary", "conclusion", "结论", "总结", "今日结论", "总判断"),
        "key_claims": ("key_claims", "claims", "facts", "reasoning", "依据", "核心依据", "理由", "核心理由"),
        "evidence_ids": ("evidence_ids", "source_refs", "evidence", "证据", "引用", "引用 evidence id", "证据 id", "证据ID"),
        "counterpoints": ("counterpoints", "risks", "反证", "风险", "最大反证", "风险和反证"),
        "data_gaps": ("data_gaps", "gaps", "missing_data", "待确认项", "数据缺口", "缺口"),
        "next_action": ("next_action", "next_step", "next", "下一步", "下一步行动", "触发条件"),
        "confidence": ("confidence", "置信度", "可信度"),
    }
    for target, aliases in field_aliases.items():
        if normalized.get(target) not in (None, "", []):
            continue
        for alias in aliases:
            if alias in data and data.get(alias) not in (None, "", []):
                normalized[target] = data.get(alias)
                break
    if normalized.get("adjudication") in (None, "", []):
        for alias in ("情景裁决", "CIO裁决", "裁决", "基准情景与竞争情景"):
            if isinstance(data.get(alias), Mapping):
                normalized["adjudication"] = data.get(alias)
                break
    if isinstance(normalized.get("evidence_ids"), str):
        extracted = _extract_evidence_ids(str(normalized.get("evidence_ids") or ""))
        normalized["evidence_ids"] = extracted or _string_list(normalized.get("evidence_ids"))
    return normalized


def _parse_markdown_sections(raw: str) -> Dict[str, str]:
    sections: Dict[str, str] = {}
    current = "body"
    buf: List[str] = []
    heading_re = re.compile(r"^\s{0,3}(?:#{1,4}\s*)?(结论|总结|今日结论|依据|核心依据|理由|引用 evidence id|证据|引用|反证|风险|待确认项|数据缺口|缺口|下一步|置信度|双方共同事实|共同事实|基准情景|最强竞争情景|最强相反情景|竞争情景|替代情景|反方情景|CIO裁决|当前裁决|裁决|裁决理由|为什么|翻转信号|失效条件|summary|conclusion|key_claims|claims|evidence|evidence_ids|counterpoints|risks|data_gaps|gaps|next_action|next action|confidence)\s*[:：]?\s*$", re.I)
    for line in str(raw or "").splitlines():
        match = heading_re.match(line.strip())
        if match:
            if buf:
                sections[current.lower()] = "\n".join(buf).strip()
            current = match.group(1).strip().lower()
            buf = []
        else:
            buf.append(line)
    if buf:
        sections[current.lower()] = "\n".join(buf).strip()
    if "body" not in sections and raw.strip():
        sections["body"] = raw.strip()
    return sections


def _first_section(sections: Mapping[str, str], *names: str) -> str:
    for name in names:
        value = sections.get(name.lower())
        if value:
            return str(value).strip()
    return ""


def _markdown_items(value: str) -> List[str]:
    text = str(value or "").strip()
    if not text:
        return []
    out: List[str] = []
    for line in text.splitlines():
        item = re.sub(r"^\s*(?:[-*•]|\d+[.)、])\s*", "", line).strip()
        if item and item.lower() not in {"无", "none", "n/a", "na", "暂无", "没有"}:
            out.append(item)
    if out:
        return out
    cleaned_text = re.sub(r"^\s*(?:[-*•]|\d+[.)、])\s*", "", text).strip().lower()
    return [] if cleaned_text in {"无", "none", "n/a", "na", "暂无", "没有"} else [text]


def _extract_evidence_ids(value: str) -> List[str]:
    text = str(value or "")
    items = _markdown_items(text)
    if not items and text:
        items = re.split(r"[,，;；\s]+", text)
    out: List[str] = []
    for item in items:
        raw = item.strip()
        for match in re.findall(r"`([^`]+)`", raw):
            cleaned = _clean_evidence_id(match)
            if cleaned:
                out.append(cleaned)
        if out and raw.startswith("`"):
            continue
        for match in re.findall(r"([A-Za-z_][A-Za-z0-9_.-]*(?::[^\s,，;；。)）`]+)+)", raw):
            cleaned = _clean_evidence_id(match)
            if cleaned:
                out.append(cleaned)
    return list(dict.fromkeys(out))


def _clean_evidence_id(value: str) -> str:
    cleaned = str(value or "").strip().strip("`'\"").rstrip("：:")
    if not cleaned or cleaned.lower() in {"无", "none", "n/a"}:
        return ""
    if ":" not in cleaned:
        return ""
    return cleaned


def _string_list(value: Any) -> List[str]:
    if isinstance(value, list):
        raw = value
    elif value in (None, ""):
        raw = []
    else:
        raw = [value]
    out: List[str] = []
    for item in raw:
        text = str(item).strip()
        if text:
            out.append(text)
    return out


def _normalize_confidence(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"low", "medium", "high"}:
        return text
    if text in {"低", "较低"}:
        return "low"
    if text in {"高", "较高"}:
        return "high"
    return "medium"


def _safe_usage(usage: Mapping[str, Any]) -> Dict[str, Any]:
    allowed = ("prompt_tokens", "completion_tokens", "total_tokens", "provider")
    return {key: usage.get(key) for key in allowed if usage.get(key) is not None}


def _int_usage(row: Mapping[str, Any], key: str) -> int:
    usage = row.get("usage") if isinstance(row.get("usage"), Mapping) else {}
    try:
        return int((usage or {}).get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _round_seconds(value: float) -> float:
    return round(float(value or 0.0), 3)


def _error_text(exc: BaseException | str | None) -> str:
    if exc is None:
        return ""
    if isinstance(exc, GenerationError):
        reason = str(exc.details.get("reason") or "")
        last_error = str(exc.details.get("last_error") or "")
        suffix = f":{last_error}" if last_error and last_error != reason else ""
        return sanitize_diagnostic_text(
            f"{exc.error_code.value}:{exc.stage}:{reason}{suffix}",
            max_len=500,
        )
    return sanitize_diagnostic_text(exc, max_len=500)


def _clip(text: str, limit: int) -> str:
    value = str(text or "")
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"
