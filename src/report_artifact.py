# -*- coding: utf-8 -*-
"""ReportArtifact v1 contract helpers.

One contract feeds both the Web/App report view and the static ``docs/``
publisher.  Keep this file framework-light so renderers, API endpoints and
tests can share the same validation rules.
"""

from __future__ import annotations

import ast
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from src.source_health.evidence_ledger import load_evidence_ledger, normalize_evidence_fact
from src.source_health.policy import build_source_health_v2
from src.source_health.provider_ledger import load_provider_ledger
from src.source_health.run_matrix import build_snapshot_refs, load_run_matrix, write_run_matrix
from src.source_health.temporal import iso_timestamp
from src.source_health.daily_universe import load_daily_universe
from src.report_policy import is_blocked_governed_row
from src.utils.sanitize import sanitize_public_http_url
from src.department_data_profiles import build_department_inputs
from src.original_analysis_adapter import (
    load_original_analysis,
    load_original_analysis_refs,
    load_original_analysis_snapshot,
)
from src.research_core import build_challenge_verdicts, build_research_reliability, build_scenario_adjudication
from src.research_core.semantic_gate import validate_claim_dicts


SCHEMA_VERSION = "report_artifact_v1"

ARTIFACT_TYPES = {
    "daily",
    "market_summary",
    "macro_review",
    "source_health",
    "screening_funnel",
    "deep_review_queue",
    "preliminary_review",
    "market_strategy",
    "stock_governed",
    "agent_memo",
    "run_status",
}

AUDIENCES = {"reader", "audit", "machine", "run_status"}
SECTION_KINDS = {
    "source",
    "facts",
    "analysis",
    "final_conclusion",
    "next_steps",
    "risk",
    "evidence",
    "raw",
}

READER_REQUIRED_SECTION_KINDS = {
    "source",
    "facts",
    "analysis",
    "final_conclusion",
    "next_steps",
}

_MISSING = object()


def validate_report_artifact(artifact: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Return ``(ok, errors)`` for a ReportArtifact v1 payload."""

    errors: List[str] = []
    if not isinstance(artifact, dict):
        return False, ["artifact must be an object"]

    required_top = [
        "schemaVersion",
        "artifactId",
        "runDate",
        "generatedAt",
        "artifactType",
        "audience",
        "title",
        "summary",
        "sections",
        "provenance",
        "publish",
        "quality",
    ]
    for key in required_top:
        if key not in artifact:
            errors.append(f"missing top-level field: {key}")

    if artifact.get("schemaVersion") != SCHEMA_VERSION:
        errors.append("schemaVersion must be report_artifact_v1")
    if artifact.get("artifactType") not in ARTIFACT_TYPES:
        errors.append("artifactType invalid")
    if artifact.get("audience") not in AUDIENCES:
        errors.append("audience invalid")

    summary = artifact.get("summary")
    if not isinstance(summary, dict):
        errors.append("summary must be an object")
    else:
        for key in ("oneLine", "keyFacts", "analysis", "finalConclusion", "nextSteps"):
            value = summary.get(key)
            if value is None or value == "" or value == []:
                errors.append(f"summary.{key} missing")

    sections = artifact.get("sections")
    if not isinstance(sections, list):
        errors.append("sections must be a list")
    else:
        kinds = set()
        for idx, section in enumerate(sections):
            if not isinstance(section, dict):
                errors.append(f"sections[{idx}] must be an object")
                continue
            kind = section.get("kind")
            if kind not in SECTION_KINDS:
                errors.append(f"sections[{idx}].kind invalid")
            else:
                kinds.add(kind)
            for key in ("key", "title"):
                if not section.get(key):
                    errors.append(f"sections[{idx}].{key} missing")
        if artifact.get("audience") == "reader":
            missing_kinds = sorted(READER_REQUIRED_SECTION_KINDS - kinds)
            for kind in missing_kinds:
                errors.append(f"reader artifact missing section kind: {kind}")

    provenance = artifact.get("provenance")
    if not isinstance(provenance, dict):
        errors.append("provenance must be an object")
    else:
        for key in ("origin", "sourceFiles", "generatedBy"):
            if key not in provenance:
                errors.append(f"provenance.{key} missing")

    quality = artifact.get("quality")
    if not isinstance(quality, dict):
        errors.append("quality must be an object")
    else:
        for key in ("completeness", "missingFields", "validationErrors"):
            if key not in quality:
                errors.append(f"quality.{key} missing")

    if "snapshotRefs" in artifact and not isinstance(artifact.get("snapshotRefs"), dict):
        errors.append("snapshotRefs must be an object")
    if "researchReliability" in artifact:
        reliability = artifact.get("researchReliability")
        if not isinstance(reliability, dict):
            errors.append("researchReliability must be an object")
        elif reliability.get("schema") != "research_reliability_v1":
            errors.append("researchReliability.schema must be research_reliability_v1")
    if "runMatrix" in artifact:
        run_matrix = artifact.get("runMatrix")
        if not isinstance(run_matrix, dict):
            errors.append("runMatrix must be an object")
        elif run_matrix.get("runDate") and run_matrix.get("runDate") != artifact.get("runDate"):
            errors.append("runMatrix.runDate must match artifact.runDate")

    if artifact.get("artifactType") == "daily" and artifact.get("audience") == "reader":
        _validate_daily_reader_v3(artifact, errors)

    return not errors, errors


def _validate_daily_reader_v3(artifact: Dict[str, Any], errors: List[str]) -> None:
    """Validate the product Reader contract and its evidence closure.

    Legacy history artifacts intentionally keep the v1 compatibility surface.
    A published daily Reader, however, must fail closed when the product view or
    a cited fact is absent.
    """

    reader = artifact.get("readerV3")
    if not isinstance(reader, dict):
        errors.append("daily reader artifact requires readerV3")
        return
    if reader.get("schema") != "reader_v3_v1":
        errors.append("readerV3.schema must be reader_v3_v1")
    if reader.get("runDate") != artifact.get("runDate"):
        errors.append("readerV3.runDate must match artifact.runDate")

    hero = reader.get("hero")
    if not isinstance(hero, dict):
        errors.append("readerV3.hero must be an object")
    else:
        for key in (
            "action",
            "status",
            "confidence",
            "oneLine",
            "maxLimitation",
            "marketStance",
            "portfolioAction",
            "validity",
            "dataCoverage",
        ):
            if not isinstance(hero.get(key), str) or not hero.get(key, "").strip():
                errors.append(f"readerV3.hero.{key} missing")

    for key in ("marketMatrix", "stockMatrix", "reportSections", "departmentCards"):
        rows = reader.get(key)
        if not isinstance(rows, list):
            errors.append(f"readerV3.{key} must be a list")
        else:
            for index, row in enumerate(rows):
                if not isinstance(row, dict):
                    errors.append(f"readerV3.{key}[{index}] must be an object")

    for key in ("keyReasons", "counterpoints", "nextSteps", "marketGeo"):
        _validate_reader_string_list(reader.get(key), f"readerV3.{key}", errors)
    _validate_reader_market_rows(reader.get("marketMatrix"), errors)
    _validate_reader_stock_rows(reader.get("stockMatrix"), errors)
    _validate_reader_sections(reader.get("reportSections"), errors)
    _validate_reader_department_cards(reader.get("departmentCards"), errors)

    timing = reader.get("timing")
    if timing is not None:
        if not isinstance(timing, dict):
            errors.append("readerV3.timing must be an object")
        else:
            _validate_reader_optional_strings(
                timing,
                ("reportDate", "generatedAt", "dataAsOf"),
                "readerV3.timing",
                errors,
            )

    assessment = reader.get("assessment")
    if assessment is not None:
        if not isinstance(assessment, dict):
            errors.append("readerV3.assessment must be an object")
        else:
            _validate_reader_optional_strings(
                assessment,
                ("dataCoverage", "conclusionConfidence"),
                "readerV3.assessment",
                errors,
            )

    if not isinstance(reader.get("adjudication"), dict):
        errors.append("readerV3.adjudication must be an object")
    else:
        adjudication = reader["adjudication"]
        _validate_reader_optional_strings(
            adjudication,
            ("baseCase", "strongestAlternative", "judgment", "why"),
            "readerV3.adjudication",
            errors,
        )
        for key in ("sharedFacts", "invalidationTriggers"):
            _validate_reader_string_list(
                adjudication.get(key),
                f"readerV3.adjudication.{key}",
                errors,
            )
    if not isinstance(reader.get("evidenceSummary"), dict):
        errors.append("readerV3.evidenceSummary must be an object")
    else:
        for key, value in reader["evidenceSummary"].items():
            if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool)):
                errors.append(f"readerV3.evidenceSummary.{key} must be a number")
    reader_reliability = reader.get("reliability")
    if not isinstance(reader_reliability, dict):
        errors.append("readerV3.reliability must be an object")
    else:
        if not isinstance(reader_reliability.get("headlineSafe"), bool):
            errors.append("readerV3.reliability.headlineSafe must be a boolean")
        elif not reader_reliability["headlineSafe"]:
            errors.append("readerV3 final headline failed evidence closure")
        if not isinstance(reader_reliability.get("headlineEvidenceSupported"), bool):
            errors.append("readerV3.reliability.headlineEvidenceSupported must be a boolean")
        elif not reader_reliability["headlineEvidenceSupported"]:
            errors.append("readerV3 final headline lacks evidence support")
        if "headlineDisplayable" in reader_reliability and not isinstance(
            reader_reliability.get("headlineDisplayable"), bool
        ):
            errors.append("readerV3.reliability.headlineDisplayable must be a boolean")
        _validate_reader_optional_strings(
            reader_reliability,
            ("label", "headlineStatus"),
            "readerV3.reliability",
            errors,
        )
        _validate_reader_string_list(
            reader_reliability.get("warnings"),
            "readerV3.reliability.warnings",
            errors,
        )
        for key in ("supportedClaims", "hypothesisClaims", "rejectedClaims"):
            value = reader_reliability.get(key)
            if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool)):
                errors.append(f"readerV3.reliability.{key} must be a number")
        if str(reader_reliability.get("headlineStatus") or "").lower() == "rejected":
            errors.append("readerV3 final headline was rejected")
    _validate_reader_optional_strings(
        reader,
        ("dataConfidence", "diagnosticsPath"),
        "readerV3",
        errors,
    )
    if reader.get("challengeVerdicts"):
        errors.append("readerV3 raw challenge verdicts must stay in diagnostics")

    evidence_items = artifact.get("evidenceItems")
    if not isinstance(evidence_items, list):
        errors.append("daily reader artifact requires evidenceItems list")
        return
    available_ids = {
        str(item.get("id") or "")
        for item in evidence_items
        if isinstance(item, dict) and str(item.get("id") or "")
    }
    referenced_ids = _collect_evidence_refs(
        artifact.get("departmentReports"),
        reader.get("marketMatrix"),
        reader.get("stockMatrix"),
        reader.get("departmentCards"),
        reader.get("reportSections"),
    )
    structural_prefixes = ("memo:", "kind:")
    structural_ids = {"dailyUniverse"}
    missing = sorted(
        evidence_id
        for evidence_id in referenced_ids
        if evidence_id not in available_ids
        and evidence_id not in structural_ids
        and not evidence_id.startswith(structural_prefixes)
    )
    for evidence_id in missing:
        errors.append(f"referenced evidence missing from evidenceItems: {evidence_id}")


def _validate_reader_optional_strings(
    row: Dict[str, Any],
    keys: Iterable[str],
    path: str,
    errors: List[str],
) -> None:
    for key in keys:
        value = row.get(key)
        if value is not None and not isinstance(value, str):
            errors.append(f"{path}.{key} must be a string")


def _validate_reader_string_list(value: Any, path: str, errors: List[str]) -> None:
    if value is None:
        return
    if not isinstance(value, list):
        errors.append(f"{path} must be a list")
        return
    for index, item in enumerate(value):
        if not isinstance(item, str):
            errors.append(f"{path}[{index}] must be a string")


def _validate_reader_evidence_samples(value: Any, path: str, errors: List[str]) -> None:
    if value is None:
        return
    if not isinstance(value, list):
        errors.append(f"{path} must be a list")
        return
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{item_path} must be an object")
            continue
        _validate_reader_optional_strings(
            item,
            ("id", "label", "sourceName", "provider", "factType", "asOf", "sourceUrl"),
            item_path,
            errors,
        )


def _validate_reader_market_rows(value: Any, errors: List[str]) -> None:
    if not isinstance(value, list):
        return
    for index, row in enumerate(value):
        if not isinstance(row, dict):
            continue
        path = f"readerV3.marketMatrix[{index}]"
        _validate_reader_optional_strings(
            row,
            ("market", "scopeLabel", "scopeType", "state", "headline", "scopeNote", "asOf"),
            path,
            errors,
        )
        breadth = row.get("breadthAvailable")
        if breadth is not None and not isinstance(breadth, bool):
            errors.append(f"{path}.breadthAvailable must be a boolean")
        _validate_reader_string_list(row.get("evidenceIds"), f"{path}.evidenceIds", errors)


def _validate_reader_stock_rows(value: Any, errors: List[str]) -> None:
    if not isinstance(value, list):
        return
    for index, row in enumerate(value):
        if not isinstance(row, dict):
            continue
        path = f"readerV3.stockMatrix[{index}]"
        _validate_reader_optional_strings(
            row,
            (
                "symbol", "name", "market", "stance", "currency", "trend", "fundamental",
                "valuation", "latestEvent", "eventDate", "eventUrl", "watchLevels", "asOf",
            ),
            path,
            errors,
        )
        for key in ("lastPrice", "return1dPct", "return20dPct"):
            number = row.get(key)
            if number is not None and (not isinstance(number, (int, float)) or isinstance(number, bool)):
                errors.append(f"{path}.{key} must be a number")
        _validate_reader_string_list(row.get("evidenceIds"), f"{path}.evidenceIds", errors)


def _validate_reader_sections(value: Any, errors: List[str]) -> None:
    if not isinstance(value, list):
        return
    for index, row in enumerate(value):
        if not isinstance(row, dict):
            continue
        path = f"readerV3.reportSections[{index}]"
        _validate_reader_optional_strings(row, ("key", "title", "body"), path, errors)
        for key in ("bullets", "counterpoints", "nextActions"):
            _validate_reader_string_list(row.get(key), f"{path}.{key}", errors)
        _validate_reader_evidence_samples(row.get("evidenceSamples"), f"{path}.evidenceSamples", errors)


def _validate_reader_department_cards(value: Any, errors: List[str]) -> None:
    if not isinstance(value, list):
        return
    for index, row in enumerate(value):
        if not isinstance(row, dict):
            continue
        path = f"readerV3.departmentCards[{index}]"
        _validate_reader_optional_strings(
            row,
            ("agent", "label", "conclusion", "nextAction", "confidence"),
            path,
            errors,
        )
        for key in (
            "keyClaims", "counterpoints", "dataGaps", "nextActions", "supportSignals", "evidenceIds",
        ):
            _validate_reader_string_list(row.get(key), f"{path}.{key}", errors)
        _validate_reader_evidence_samples(row.get("evidenceSamples"), f"{path}.evidenceSamples", errors)
        challenged = row.get("challengedClaims")
        if challenged is None:
            continue
        if not isinstance(challenged, list):
            errors.append(f"{path}.challengedClaims must be a list")
            continue
        for challenge_index, challenge in enumerate(challenged):
            challenge_path = f"{path}.challengedClaims[{challenge_index}]"
            if not isinstance(challenge, dict):
                errors.append(f"{challenge_path} must be an object")
                continue
            _validate_reader_optional_strings(
                challenge,
                ("claim", "status", "opposingScenario", "falsifier"),
                challenge_path,
                errors,
            )


def _collect_evidence_refs(*values: Any) -> List[str]:
    """Collect evidence IDs from all supported public and audit shapes."""

    evidence_keys = {
        "evidenceId",
        "evidenceIds",
        "evidence_id",
        "evidence_ids",
        "acceptedEvidenceIds",
    }
    out: List[str] = []

    def visit(value: Any, *, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                if child_key in evidence_keys:
                    visit(child, key=child_key)
                elif isinstance(child, (dict, list)):
                    visit(child, key=child_key)
            return
        if isinstance(value, list):
            for child in value:
                visit(child, key=key)
            return
        if key in evidence_keys and isinstance(value, (str, int, float)):
            text = str(value).strip()
            if text:
                out.append(text)

    for value in values:
        visit(value)
    return list(dict.fromkeys(out))


def build_daily_report_artifact(docs_dir: str | Path, run_date: str) -> Dict[str, Any]:
    """Build the canonical daily ReportArtifact from published docs artifacts."""

    docs_path = Path(docs_dir)
    compact = run_date.replace("-", "")
    market_cycle = docs_path / "market_cycle" / run_date

    macro = _read_json(market_cycle / "01_macro_review.json") or {}
    health = _read_json(market_cycle / "13_source_health.json") or {}
    queue = _read_json(market_cycle / "11_deep_review_queue.json") or {}
    strategy = _read_json(market_cycle / "14_market_strategy.json") or {}
    governed = _read_json(docs_path / "governed_results.json")
    governed_rows = [
        row
        for row in (governed if isinstance(governed, list) else [])
        if isinstance(row, dict) and str(row.get("run_date") or "") == run_date
    ]
    universe = load_daily_universe(docs_path, run_date)
    universe_subjects = [str(item) for item in universe.get("subjectSymbols") or [] if str(item)]
    universe_mode = str(universe.get("mode") or "")
    agent_counts = _agent_origin_counts(docs_path, run_date)
    agent_runtime_counts = _agent_runtime_counts(docs_path, run_date)
    cio_enrichment = _load_cio_enrichment(docs_path, run_date)
    agent_model_selection = _read_json(docs_path / "run_status" / run_date / "agent_model_selection.json") or {}
    original_analysis = load_original_analysis(docs_path, run_date)
    original_analysis_refs = load_original_analysis_refs(docs_path, run_date)
    original_analysis_snapshot = load_original_analysis_snapshot(docs_path, run_date)

    source_health = _daily_source_health(health)
    evidence_facts = _load_daily_evidence_facts(docs_path, run_date, health, source_health)
    source_health_v2 = _load_daily_source_health_v2_snapshot(docs_path, run_date) or build_source_health_v2(
        health,
        provider_runs=_load_daily_provider_runs(docs_path, run_date),
        evidence_facts=evidence_facts,
        agent_origin_counts=agent_counts,
    )
    department_reports = _department_reports(docs_path, run_date)
    _apply_daily_reader_scope(department_reports, universe)
    source_health_v2 = _align_source_health_with_agent_outputs(
        source_health_v2,
        department_reports=department_reports,
        has_governed_rows=bool(governed_rows),
        daily_universe_mode=universe_mode,
        daily_subject_count=len(universe_subjects),
    )
    source_health = _align_legacy_source_health(source_health, source_health_v2)
    research_reliability = build_research_reliability(department_reports)
    scenario_adjudication = build_scenario_adjudication(department_reports)
    candidate_count = len(queue.get("candidates") or []) if isinstance(queue, dict) else 0
    auto_governed_count = len(queue.get("auto_governed_candidates") or []) if isinstance(queue, dict) else 0
    blocked_count = sum(1 for row in governed_rows if _is_blocked_governed_row(row))
    macro_status = _first_text(macro.get("status"), health.get("macro_status"), default="未提供")
    trade_usability = _first_text(health.get("trade_review_usability"), default="未提供")
    regime = _first_text(strategy.get("regime"), default="未提供")
    headline = _first_text((strategy.get("strategy") or {}).get("headline") if isinstance(strategy.get("strategy"), dict) else None, macro.get("headline"), default="今日报告已生成。")

    if universe_subjects:
        one_line = f"今日覆盖 {len(universe_subjects)} 个观察标的，按市场、行业、候选和个股分层复核。"
    elif universe_mode == "market_and_candidates":
        one_line = "今日自选股为空；生成市场观察和候选池日报，不回退单只 600519。"
    elif governed_rows and blocked_count == len(governed_rows):
        one_line = "今日 governed 标的全部被门控阻断；最终动作是不操作。"
    elif governed_rows:
        one_line = "今日存在 governed 标的；按门控结果逐只复核，不自动交易。"
    else:
        one_line = "今日无 completed governed 个股报告；仅保留市场观察和候选池。"
    analysis_mode = str(source_health_v2.get("overallMode") or "BLOCKED")
    if analysis_mode != "FULL_REVIEW" and _is_limited_source_health(source_health):
        one_line += " 数据源有缺口，需要带限制阅读。"
    evidence_stats = source_health_v2.get("evidenceStats") if isinstance(source_health_v2.get("evidenceStats"), dict) else {"schema": "evidence_stats_v1"}
    one_line = f"{analysis_mode}：{one_line}"

    key_facts = [
        f"报告模式：{analysis_mode}",
        f"运行日期：{run_date}",
        f"宏观状态：{macro_status}",
        f"市场状态：{regime}",
        f"交易审查可用性：{trade_usability}",
        f"深评候选：{candidate_count}；自动 governed：{auto_governed_count}",
        f"日报 universe：{len(universe_subjects)} 个观察标的；模式：{universe_mode or '未提供'}",
        f"governed 完成：{len(governed_rows)}；阻断：{blocked_count}",
        f"Agent 来源：真实 {agent_counts.get('RAW_AGENT', 0)}；回填 {agent_counts.get('DERIVED_FROM_ARTIFACT', 0)}；缺失 {agent_counts.get('MISSING', 0)}",
        f"CIO 补数：请求 {cio_enrichment.get('requestCount', 0)}；成功 {cio_enrichment.get('successCount', 0)}；失败 {cio_enrichment.get('failedCount', 0)}",
        f"证据统计：verified {evidence_stats.get('verifiedFacts', 0)}；discovery {evidence_stats.get('discoveryItems', 0)}；missing critical {evidence_stats.get('missingCriticalFacts', 0)}",
    ]

    governed_lines = _governed_summary_lines(governed_rows)
    source_lines = _source_health_lines(health)
    candidate_lines = _candidate_lines(queue)
    missing_files = _missing_daily_source_files(docs_path, run_date)
    decision = _apply_claim_policy_to_decision(_daily_decision(governed_rows), source_health_v2)
    reader_brief = _build_reader_brief(
        run_date=run_date,
        mode=analysis_mode,
        headline=headline,
        governed_lines=governed_lines,
        candidate_lines=candidate_lines,
        source_health_v2=source_health_v2,
        evidence_stats=evidence_stats,
        decision=decision,
        department_reports=department_reports,
        universe=universe,
    )
    department_inputs = build_department_inputs(department_reports, original_refs=original_analysis_refs)
    preferred_evidence_ids = _collect_evidence_refs(department_reports)
    preferred_evidence_ids.extend(
        str(fact.get("id") or "")
        for fact in evidence_facts
        if (
            str(fact.get("metric") or "")
            in {
                "main_indices",
                "market_stats",
                "market_stats_history_comparison",
                "sector_history_comparison",
                "realtime_quote",
                "daily_data",
                "price_history_comparison",
                "fundamental_growth",
                "fundamental_valuation",
                "fundamental_history_comparison",
                "valuation_history_comparison",
                "CN_GDP_YOY",
                "CN_CPI_YOY",
                "CN_PMI_MANUFACTURING",
            }
            or any(
                marker in str(fact.get("id") or "")
                for marker in (
                    ":quote:",
                    ":daily_data:",
                    ":price_history_comparison:",
                    ":fundamental:growth:",
                    ":fundamental:valuation:",
                    ":fundamental:history_comparison:",
                    ":fundamental:valuation_history:",
                )
            )
        )
        and str(fact.get("id") or "")
    )
    preferred_evidence_ids = list(dict.fromkeys(preferred_evidence_ids))
    evidence_items = _evidence_items(evidence_facts, preferred_ids=preferred_evidence_ids)
    reader_v2 = _build_reader_v2(
        run_date=run_date,
        reader_brief=reader_brief,
        department_reports=department_reports,
        department_inputs=department_inputs,
        original_analysis_refs=original_analysis_refs,
        evidence_items=evidence_items,
        source_health_v2=source_health_v2,
    )
    generated_at = _now_iso()
    reader_v3 = _build_reader_v3(
        run_date=run_date,
        generated_at=generated_at,
        data_as_of=_latest_evidence_time(evidence_facts, fallback=run_date),
        reader_brief=reader_brief,
        department_reports=department_reports,
        department_inputs=department_inputs,
        evidence_items=evidence_items,
        source_health_v2=source_health_v2,
        evidence_stats=evidence_stats,
        decision=decision,
        research_reliability=research_reliability,
        scenario_adjudication=scenario_adjudication,
        universe=universe,
        evidence_facts=evidence_facts,
        original_analysis_snapshot=original_analysis_snapshot,
    )
    reader_reliability = reader_v3.get("reliability") if isinstance(reader_v3.get("reliability"), Mapping) else {}
    research_reliability = _finalize_research_reliability(
        research_reliability,
        reader_reliability,
    )
    if isinstance(reader_reliability, dict):
        reader_reliability["label"] = research_reliability["label"]
        reader_reliability["warnings"] = list(research_reliability.get("warnings") or [])
    data_coverage = {
        "mode": analysis_mode,
        "label": _reader_mode_label(analysis_mode),
        "score": source_health_v2.get("overallScore"),
        "missingCriticalFacts": int(evidence_stats.get("missingCriticalFacts") or 0),
    }
    conclusion_confidence = {
        "label": str(research_reliability.get("label") or "结论不足"),
        "headlineSafe": bool(research_reliability.get("headlineSafe")),
        "supportedClaims": int(research_reliability.get("supportedClaims") or 0),
        "hypothesisClaims": int(research_reliability.get("hypothesisClaims") or 0),
        "rejectedClaims": int(research_reliability.get("rejectedClaims") or 0),
    }

    sections = [
        {
            "key": "source",
            "title": "数据源",
            "kind": "source",
            "readerVisible": False,
            "contentMarkdown": "\n".join(source_lines) or "- 未提供数据源健康明细",
            "sourceRefs": _existing_source_refs(docs_path, run_date),
            "confidence": "medium" if source_lines else "low",
        },
        {
            "key": "facts",
            "title": "关键数据",
            "kind": "facts",
            "readerVisible": False,
            "contentMarkdown": "\n".join(f"- {item}" for item in key_facts),
            "confidence": "medium",
        },
        {
            "key": "analysis",
            "title": "推论",
            "kind": "analysis",
            "readerVisible": False,
            "contentMarkdown": _safe_reader_text(
                "\n".join(
                    [
                        headline,
                        "宏观和源健康只决定风险温度与阅读置信度，不能单独触发交易。",
                        "候选池用于发现机会；只有证据链、红蓝对抗、评分卡和 CIO 门控通过后才可进入交易前复核。",
                        "\n".join(candidate_lines),
                    ]
                )
            ),
            "confidence": "medium" if not _is_limited_source_health(source_health) else "low",
        },
        {
            "key": "final_conclusion",
            "title": "总结论",
            "kind": "final_conclusion",
            "readerVisible": False,
            "contentMarkdown": _safe_reader_text(
                "\n".join(
                    governed_lines
                    or ["- 今日没有 completed governed 个股；维持观察，不自动交易。"]
                )
            ),
            "confidence": "medium",
            "blocking": decision.get("gateStatus") == "blocked",
        },
        {
            "key": "next_steps",
            "title": "下一步",
            "kind": "next_steps",
            "readerVisible": False,
            "contentMarkdown": "\n".join(
                [
                    "- 先读总报告，再看源健康和 Agent 卷宗。",
                    "- 宏观源降级时，只做观察和候选筛选。",
                    "- blocked / 低分标的不交易；补公告、业绩、估值和催化剂后再审。",
                ]
            ),
            "confidence": "medium",
        },
        {
            "key": "department_summary",
            "title": "分部门摘要",
            "kind": "analysis",
            "readerVisible": False,
            "contentMarkdown": "\n".join(f"- {row['label']}：{row['summaryForReader']}" for row in _reader_department_reports(department_reports)[:8]) or "- 本轮未记录到分部门结论。",
            "confidence": "medium" if department_reports else "low",
        },
    ]

    run_matrix = load_run_matrix(docs_path, run_date)
    snapshot_refs = build_snapshot_refs(docs_path, run_date, agent_run_id=str(run_matrix.get("runId") or run_date))
    reader_hero = reader_v3.get("hero") if isinstance(reader_v3.get("hero"), Mapping) else {}
    reader_adjudication = reader_v3.get("adjudication") if isinstance(reader_v3.get("adjudication"), Mapping) else {}
    public_reader_brief = {
        **reader_brief,
        "oneLine": str(reader_hero.get("oneLine") or ""),
        "why": list(reader_v3.get("keyReasons") or []),
        "risks": list(reader_v3.get("counterpoints") or []),
        "analysis": str(reader_adjudication.get("baseCase") or ""),
        "finalConclusion": str(reader_adjudication.get("judgment") or reader_hero.get("oneLine") or ""),
        "nextSteps": list(reader_v3.get("nextSteps") or []),
        "dataConfidence": str(reader_v3.get("dataConfidence") or ""),
    }

    artifact = {
        "schemaVersion": SCHEMA_VERSION,
        "artifactId": f"daily:{run_date}",
        "runDate": run_date,
        "generatedAt": generated_at,
        "artifactType": "daily",
        "audience": "reader",
        "title": f"{run_date} 投研日报",
        "summary": {
            "oneLine": _safe_reader_text(public_reader_brief["oneLine"]),
            "keyFacts": [_safe_reader_text(item) for item in public_reader_brief["why"]],
            "analysis": _safe_reader_text(public_reader_brief["analysis"]),
            "finalConclusion": _safe_reader_text(public_reader_brief["finalConclusion"]),
            "nextSteps": [_safe_reader_text(item) for item in public_reader_brief["nextSteps"]],
        },
        "readerBrief": public_reader_brief,
        "dailyUniverse": universe,
        "sections": sections,
        "sourceHealth": source_health,
        "sourceHealthV2": source_health_v2,
        "analysisMode": analysis_mode,
        "dataCoverage": data_coverage,
        "conclusionConfidence": conclusion_confidence,
        "claimPolicy": source_health_v2.get("claimPolicy") if isinstance(source_health_v2.get("claimPolicy"), dict) else {},
        "claimEvidence": source_health_v2.get("claimEvidence") if isinstance(source_health_v2.get("claimEvidence"), dict) else {},
        "evidenceStats": evidence_stats,
        "evidenceItems": evidence_items,
        "runMatrix": {
            "runId": run_matrix.get("runId") or snapshot_refs.get("agentRunId") or run_date,
            "runDate": run_matrix.get("runDate") or run_date,
        },
        "snapshotRefs": snapshot_refs,
        "decision": decision,
        "cioEnrichment": cio_enrichment,
        "agentModelSelection": agent_model_selection,
        "originalAnalysis": _artifact_original_analysis(original_analysis, run_date),
        "departmentInputs": department_inputs,
        "readerV2": reader_v2,
        "readerV3": reader_v3,
        "researchReliability": research_reliability,
        "departmentReports": department_reports,
        "agentOrigins": {
            "raw": agent_counts.get("RAW_AGENT", 0),
            "derived": agent_counts.get("DERIVED_FROM_ARTIFACT", 0),
            "missing": agent_counts.get("MISSING", 0),
        },
        "agentRuntimeSummary": {
            "llm": agent_runtime_counts.get("LLM", 0),
            "rule": agent_runtime_counts.get("RULE", 0),
            "ruleFallback": agent_runtime_counts.get("RULE_FALLBACK", 0),
            "derivedDiagnostic": agent_runtime_counts.get("DERIVED_DIAGNOSTIC", 0),
            "unknown": agent_runtime_counts.get("unknown", 0),
        },
        "provenance": {
            "origin": "invest-system.static",
            "sourceFiles": _existing_source_refs(docs_path, run_date),
            "generatedBy": "src.report_artifact.build_daily_report_artifact",
            "runId": run_date,
        },
        "publish": {
            "docsPath": f"docs/reports/{run_date}.html",
            "jsonPath": f"docs/reports/{run_date}.artifact.json",
            "htmlPath": f"reports/{run_date}.html",
            "markdownPath": f"daily/{run_date}.md",
            "webPath": f"/reports/{run_date}",
        },
        "quality": {
            "completeness": _daily_completeness(missing_files, source_health, source_health_v2),
            "missingFields": missing_files,
            "validationErrors": [],
        },
    }
    ok, errors = validate_report_artifact(artifact)
    artifact["quality"]["validationErrors"] = errors
    if not ok:
        artifact["quality"]["completeness"] = "failed"
    return artifact


def write_daily_report_artifact(docs_dir: str | Path, run_date: str) -> Dict[str, Any]:
    """Build and persist ``docs/reports/{date}.artifact.json``."""

    docs_path = Path(docs_dir)
    artifact = build_daily_report_artifact(docs_path, run_date)
    _ensure_daily_snapshot_files(docs_path, run_date, artifact)
    artifact = build_daily_report_artifact(docs_path, run_date)
    ok, errors = validate_report_artifact(artifact)
    if not ok:
        raise ValueError("daily report artifact validation failed: " + "; ".join(errors))
    out = docs_path / "reports" / f"{run_date}.artifact.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    pending = out.with_suffix(out.suffix + ".tmp")
    pending.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(out)
    return artifact


def _ensure_daily_snapshot_files(docs_path: Path, run_date: str, artifact: Dict[str, Any]) -> None:
    """Persist the snapshot files needed for a publishable daily artifact.

    ``build_daily_report_artifact`` stays side-effect free so API/Web callers can
    inspect artifacts without mutating ``docs/``.  Publishing calls this helper
    before the final build so snapshot hashes are stable.
    """

    run_status_path = docs_path / "run_status" / run_date
    run_status_path.mkdir(parents=True, exist_ok=True)
    for ledger_name in ("provider_runs.jsonl", "evidence_ledger.jsonl"):
        ledger_path = run_status_path / ledger_name
        if not ledger_path.exists():
            ledger_path.write_text("", encoding="utf-8")

    source_health_v2 = artifact.get("sourceHealthV2") if isinstance(artifact.get("sourceHealthV2"), dict) else {}
    source_health_snapshot_path = run_status_path / "source_health_v2.json"
    source_health_snapshot_path.write_text(
        json.dumps(source_health_v2, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not (run_status_path / "run_matrix.json").exists():
        write_run_matrix(
            docs_path,
            run_date,
            stages=[
                {
                    "name": "report_artifact",
                    "status": "partial",
                    "blocking": True,
                    "outputs": [f"reports/{run_date}.artifact.json"],
                }
            ],
        )


def build_stock_artifact_from_history_detail(detail: Dict[str, Any]) -> Dict[str, Any]:
    """Build a reader-facing stock governed artifact from a history detail dict."""

    record_id = detail.get("id")
    query_id = detail.get("query_id") or ""
    stock_code = detail.get("stock_code") or ""
    stock_name = detail.get("stock_name") or stock_code or "未知标的"
    created_at = detail.get("created_at") or _now_iso()
    run_date = str(created_at)[:10] if created_at else _now_iso()[:10]
    raw_result = detail.get("raw_result") if isinstance(detail.get("raw_result"), dict) else {}
    dashboard = raw_result.get("dashboard") if isinstance(raw_result.get("dashboard"), dict) else raw_result
    governance = dashboard.get("governance") if isinstance(dashboard, dict) and isinstance(dashboard.get("governance"), dict) else {}
    trade_plan = governance.get("trade_plan") if isinstance(governance.get("trade_plan"), dict) else {}

    source_refs = _source_refs_from_detail(detail)
    score_value = _first_present(governance.get("score"), detail.get("sentiment_score"), "未知")
    key_facts = [
        f"标的：{stock_name}({stock_code})",
        f"趋势：{detail.get('trend_prediction') or '未给出'}",
        f"评分：{score_value}",
        f"门控：{governance.get('cio_status') or governance.get('gate') or '未给出'}",
    ]
    analysis = detail.get("analysis_summary") or "报告缺少可读分析摘要，需要回看原始记录。"
    operation = detail.get("operation_advice") or "未给出"
    final_conclusion = f"{operation}；最终动作：{trade_plan.get('action') or '需人工复核'}。"
    next_steps = _next_steps(governance, detail)

    artifact = {
        "schemaVersion": SCHEMA_VERSION,
        "artifactId": f"history:{record_id}" if record_id is not None else f"query:{query_id}",
        "runDate": run_date,
        "generatedAt": _now_iso(),
        "artifactType": "stock_governed",
        "audience": "reader",
        "title": f"{stock_name}({stock_code}) governed 报告",
        "summary": {
            "oneLine": str(operation),
            "keyFacts": key_facts,
            "analysis": str(analysis),
            "finalConclusion": final_conclusion,
            "nextSteps": next_steps,
        },
        "sections": [
            {
                "key": "sources",
                "title": "数据源",
                "kind": "source",
                "contentMarkdown": "\n".join(f"- {item}" for item in source_refs) or "- 来源未记录",
                "sourceRefs": source_refs,
                "confidence": "medium" if source_refs else "low",
            },
            {
                "key": "facts",
                "title": "关键数据",
                "kind": "facts",
                "contentMarkdown": "\n".join(f"- {item}" for item in key_facts),
            },
            {
                "key": "analysis",
                "title": "推论",
                "kind": "analysis",
                "contentMarkdown": str(analysis),
            },
            {
                "key": "final_conclusion",
                "title": "总结论",
                "kind": "final_conclusion",
                "contentMarkdown": final_conclusion,
                "blocking": _is_blocked(governance, operation),
            },
            {
                "key": "next_steps",
                "title": "下一步",
                "kind": "next_steps",
                "contentMarkdown": "\n".join(f"- {item}" for item in next_steps),
            },
        ],
        "decision": _decision_from_governance(governance, operation),
        "provenance": {
            "origin": "invest-system.history",
            "sourceFiles": [],
            "generatedBy": "src.report_artifact.build_stock_artifact_from_history_detail",
            "recordId": str(record_id) if record_id is not None else None,
            "queryId": query_id,
        },
        "publish": {},
        "quality": {
            "completeness": "partial" if not source_refs else "complete",
            "missingFields": [] if source_refs else ["sourceRefs"],
            "validationErrors": [],
        },
    }
    ok, errors = validate_report_artifact(artifact)
    artifact["quality"]["validationErrors"] = errors
    if not ok:
        artifact["quality"]["completeness"] = "failed"
    return artifact


def _source_refs_from_detail(detail: Dict[str, Any]) -> List[str]:
    refs: List[str] = []
    if detail.get("news_content"):
        refs.append("history.news_content")
    if detail.get("context_snapshot"):
        refs.append("history.context_snapshot")
    raw_result = detail.get("raw_result")
    if raw_result:
        refs.append("history.raw_result")
    return refs


def _decision_from_governance(governance: Dict[str, Any], operation: Any) -> Dict[str, Any]:
    trade_plan = governance.get("trade_plan") if isinstance(governance.get("trade_plan"), dict) else {}
    action = str(_first_present(trade_plan.get("action"), "")).strip().lower() or _operation_to_action(operation)
    blocked = _is_blocked(governance, operation)
    score_value = _first_present(governance.get("score"), governance.get("total_score"), None)
    target_value = _first_present(trade_plan.get("target_pct"), trade_plan.get("target_position_pct"), None)
    return {
        "action": "no_action" if blocked else action,
        "gateStatus": "blocked" if blocked else ("watch" if action in {"watch", "wait", "hold"} else "passed"),
        "score": _safe_float(score_value),
        "targetPct": 0 if blocked else _safe_float(target_value),
        "blockedReasons": list(governance.get("blocked_reasons") or []) if blocked else [],
    }


def _apply_claim_policy_to_decision(decision: Dict[str, Any], source_health_v2: Dict[str, Any]) -> Dict[str, Any]:
    """Attach evidence caveats without replacing the upstream decision.

    Source health describes how strongly a recommendation is supported.  It is
    not a second trading engine and must not silently turn an upstream
    recommendation into ``no_action`` or erase a suggested range.
    """

    policy = source_health_v2.get("claimPolicy") if isinstance(source_health_v2.get("claimPolicy"), dict) else {}
    out = dict(decision)
    caveats: List[str] = [
        str(item)
        for item in out.get("advisoryCaveats") or []
        if str(item).strip()
    ]
    if policy.get("canActionableAdvice") is False:
        caveats.append("actionable_advice_evidence_limited")
    if policy.get("canPositionSizing") is False:
        caveats.append("position_sizing_evidence_limited")
    out["advisoryCaveats"] = list(dict.fromkeys(caveats))
    return out


_AGENT_GAP_DOMAIN_KEYWORDS = {
    "price": (
        "历史日线",
        "ohclv",
        "ohlcv",
        "成交量",
        "技术指标",
        "支撑位",
        "压力位",
        "市场宽度",
        "涨跌家数",
        "成交额",
        "资金流",
        "资金面",
        "capital_flow",
        "market_stats",
        "main_indices",
    ),
    "fundamentals": (
        "财务",
        "财报",
        "估值",
        "基本面",
        "市盈率",
        "成长性",
        "收入增长",
        "腾讯控股",
        "平安银行",
    ),
    "filings_events": (
        "公告",
        "深交所",
        "港交所",
        "hkex",
        "szse",
        "form 4",
        "交易所",
    ),
    "macro": (
        "pmi",
        "社融",
        "cpi",
        "ppi",
        "中国本土关键宏观",
        "宏观经济指标",
    ),
    "news_sentiment": (
        "新闻",
        "舆情",
        "gdelt",
        "媒体叙事",
        "搜索",
    ),
    "portfolio": (
        "持仓",
        "组合",
        "portfolio holdings",
        "风险暴露",
        "集中度",
    ),
}

def _align_source_health_with_agent_outputs(
    source_health_v2: Dict[str, Any],
    *,
    department_reports: List[Dict[str, Any]],
    has_governed_rows: bool,
    daily_universe_mode: str = "",
    daily_subject_count: int = 0,
) -> Dict[str, Any]:
    """Attach department observations without rewriting data health.

    SourceHealth is a measurement of providers/evidence.  Agent uncertainty is
    a conclusion-quality signal and belongs to ``researchReliability``.  Older
    code mixed the two and could turn an Agent phrase into a fake provider
    outage.  Keep this compatibility seam, but make the dependency one-way.
    """

    health = json.loads(json.dumps(source_health_v2, ensure_ascii=False))
    reported_gap_domains = _agent_reported_gap_domains(department_reports)
    no_governed_blocks = not has_governed_rows and not _daily_can_use_department_report(daily_universe_mode, daily_subject_count)
    health["departmentObservations"] = {
        "reportedGapDomains": reported_gap_domains,
        "noCompletedGovernedReport": no_governed_blocks,
        "agentsRecommendNoDecision": _agents_say_no_decision(department_reports),
    }
    return health


def _agent_reported_gap_domains(department_reports: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    domains: Dict[str, List[str]] = {}
    for row in department_reports:
        texts = []
        texts.extend(str(item) for item in (row.get("dataGaps") or []) if str(item))
        texts.extend(str(item) for item in (row.get("counterpoints") or []) if str(item))
        agent = str(row.get("agent") or "")
        if agent in {"RiskAgent", "RiskPositionAgent", "RedTeamAgent", "RedBlueAgent", "CIOAgent", "DecisionReportAgent"}:
            texts.append(str(row.get("summaryForReader") or ""))
        blob = "\n".join(texts).lower()
        if not blob:
            continue
        for domain, keywords in _AGENT_GAP_DOMAIN_KEYWORDS.items():
            if any(keyword.lower() in blob for keyword in keywords):
                reason = _first_gap_reason(texts, keywords)
                domains.setdefault(domain, [])
                if reason and reason not in domains[domain]:
                    domains[domain].append(reason)
    return domains


def _daily_can_use_department_report(mode: str, subject_count: int) -> bool:
    return str(mode or "") in {"multi_subject_daily", "market_and_candidates"} or int(subject_count or 0) > 1


def _first_gap_reason(texts: List[str], keywords: tuple[str, ...]) -> str:
    lowered_keywords = [keyword.lower() for keyword in keywords]
    for text in texts:
        cleaned = str(text or "").strip()
        if cleaned and any(keyword in cleaned.lower() for keyword in lowered_keywords):
            return cleaned[:120]
    for text in texts:
        cleaned = str(text or "").strip()
        if cleaned:
            return cleaned[:120]
    return "Agent 报告存在数据缺口。"


def _agents_say_no_decision(department_reports: List[Dict[str, Any]]) -> bool:
    for row in department_reports:
        if str(row.get("agent") or "") not in {"RiskAgent", "RiskPositionAgent", "RedTeamAgent", "RedBlueAgent", "CIOAgent", "DecisionReportAgent"}:
            continue
        blob = "\n".join(
            [str(row.get("summaryForReader") or "")]
            + [str(item) for item in (row.get("counterpoints") or [])]
            + [str(item) for item in (row.get("dataGaps") or [])]
        )
        if any(token in blob for token in ("无法决策", "信息不足", "盲目下注", "等同于赌博", "无法评估任何潜在操作")):
            return True
    return False


def _operation_to_action(operation: Any) -> str:
    text = str(operation or "").lower()
    if "阻断" in text or "no_action" in text:
        return "no_action"
    if "买" in text or "buy" in text:
        return "buy"
    if "卖" in text or "减" in text or "sell" in text or "reduce" in text:
        return "sell"
    return "watch"


def _is_blocked(governance: Dict[str, Any], operation: Any) -> bool:
    status = str(governance.get("cio_status") or "").upper()
    gate = str(governance.get("gate") or governance.get("gate_result") or "").upper()
    score = _safe_float(_first_present(governance.get("score"), governance.get("total_score"), None))
    action = _operation_to_action(operation)
    return status in {"BLOCKED_BY_FATAL", "NEEDS_EVIDENCE"} or gate == "BLOCKED" or (score is not None and score < 6) or action == "no_action"


def _next_steps(governance: Dict[str, Any], detail: Dict[str, Any]) -> List[str]:
    if _is_blocked(governance, detail.get("operation_advice")):
        return ["补齐阻断证据", "重新运行 governed 审查", "人工复核持仓风险"]
    return ["人工复核数据源", "确认入场条件", "保持无自动交易"]


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _existing_source_refs(docs_dir: Path, run_date: str) -> List[str]:
    compact = run_date.replace("-", "")
    rels = [
        f"daily/{run_date}.md",
        f"governed_results.json",
        f"report_{compact}.md",
        f"market_cycle/{run_date}/01_macro_review.json",
        f"market_cycle/{run_date}/11_deep_review_queue.json",
        f"market_cycle/{run_date}/13_source_health.json",
        f"market_cycle/{run_date}/14_market_strategy.json",
        f"official_events/{run_date}.json",
        f"agent_memos/{run_date}/index.json",
    ]
    return [rel for rel in rels if (docs_dir / rel).exists()]


def _missing_daily_source_files(docs_dir: Path, run_date: str) -> List[str]:
    required = [
        f"daily/{run_date}.md",
        f"market_cycle/{run_date}/13_source_health.json",
        f"market_cycle/{run_date}/14_market_strategy.json",
    ]
    return [rel for rel in required if not (docs_dir / rel).exists()]


def _agent_origin_counts(docs_dir: Path, run_date: str) -> Dict[str, int]:
    counts = {"RAW_AGENT": 0, "DERIVED_FROM_ARTIFACT": 0, "MISSING": 0}
    base = docs_dir / "agent_memos" / run_date
    if not base.exists():
        return counts
    for path in base.rglob("*.json"):
        payload = _read_json(path)
        if not isinstance(payload, dict) or payload.get("schema") != "agent_memo_v1":
            continue
        origin = str(payload.get("origin") or "DERIVED_FROM_ARTIFACT")
        counts[origin] = counts.get(origin, 0) + 1
    return counts


def _agent_runtime_counts(docs_dir: Path, run_date: str) -> Dict[str, int]:
    counts = {"LLM": 0, "RULE": 0, "RULE_FALLBACK": 0, "DERIVED_DIAGNOSTIC": 0, "unknown": 0}
    base = docs_dir / "agent_memos" / run_date
    if not base.exists():
        return counts
    for path in base.rglob("*.json"):
        payload = _read_json(path)
        if not isinstance(payload, dict) or payload.get("schema") != "agent_memo_v1":
            continue
        runtime = str(payload.get("agentRuntime") or payload.get("agent_runtime") or "unknown").strip() or "unknown"
        counts[runtime] = counts.get(runtime, 0) + 1
    return counts


def _load_cio_enrichment(docs_dir: Path, run_date: str) -> Dict[str, Any]:
    payload = _read_json(docs_dir / "run_status" / run_date / "cio_data_requests.json")
    summary = payload.get("summary") if isinstance(payload, dict) and isinstance(payload.get("summary"), dict) else {}
    if not summary:
        return {
            "requested": False,
            "requestCount": 0,
            "successCount": 0,
            "failedCount": 0,
            "addedEvidenceIds": [],
            "remainingGaps": [],
        }
    return {
        "requested": bool(summary.get("requested")),
        "requestCount": int(summary.get("requestCount") or 0),
        "successCount": int(summary.get("successCount") or 0),
        "failedCount": int(summary.get("failedCount") or 0),
        "addedEvidenceIds": list(summary.get("addedEvidenceIds") or []),
        "remainingGaps": list(summary.get("remainingGaps") or []),
    }


def _artifact_original_analysis(original: Dict[str, Any], run_date: str) -> Dict[str, Any]:
    if not isinstance(original, dict) or original.get("schema") != "original_analysis_v1":
        return {
            "runDate": run_date,
            "marketContextAvailable": False,
            "marketReviewAvailable": False,
            "stockContextCount": 0,
            "stockAnalysisCount": 0,
            "decisionSignalCount": 0,
            "portfolioSnapshotAvailable": False,
            "structuredSnapshotAvailable": False,
            "refsPath": f"docs/run_status/{run_date}/original_analysis_refs.jsonl",
        }
    return {
        "runDate": original.get("runDate") or run_date,
        "marketContextAvailable": bool(original.get("marketContextAvailable")),
        "marketReviewAvailable": bool(original.get("marketReviewAvailable")),
        "stockContextCount": int(original.get("stockContextCount") or 0),
        "stockAnalysisCount": int(original.get("stockAnalysisCount") or 0),
        "decisionSignalCount": int(original.get("decisionSignalCount") or 0),
        "portfolioSnapshotAvailable": bool(original.get("portfolioSnapshotAvailable")),
        "structuredSnapshotAvailable": bool(original.get("structuredSnapshotAvailable")),
        "structuredSnapshotPath": original.get("structuredSnapshotPath"),
        "structuredSnapshotSha256": original.get("structuredSnapshotSha256"),
        "refsPath": original.get("refsPath") or f"docs/run_status/{run_date}/original_analysis_refs.jsonl",
        "refCount": int(original.get("refCount") or 0),
        "availableKinds": list(original.get("availableKinds") or []),
        "notes": list(original.get("notes") or [])[:4],
    }


def _build_reader_v2(
    *,
    run_date: str,
    reader_brief: Dict[str, Any],
    department_reports: List[Dict[str, Any]],
    department_inputs: List[Dict[str, Any]],
    original_analysis_refs: List[Dict[str, Any]],
    evidence_items: List[Dict[str, Any]],
    source_health_v2: Dict[str, Any],
) -> Dict[str, Any]:
    visible = _reader_department_reports(department_reports)
    cards = [_reader_v2_department_card(row, department_inputs, evidence_items) for row in visible]
    geo = _first_department(visible, {"GeoPolicyAgent"})
    market = _first_department(visible, {"MarketAgent", "MarketStrategyAgent"})
    risk = _first_department(visible, {"RiskAgent", "RiskPositionAgent", "RedTeamAgent", "RedBlueAgent"})
    evidence_stats = source_health_v2.get("evidenceStats") if isinstance(source_health_v2.get("evidenceStats"), dict) else {}
    risk_bullets = [_safe_reader_text(item) for item in (reader_brief.get("risks") or [])[:5]]
    if not risk_bullets and risk:
        risk_bullets = [_safe_reader_text(risk.get("summaryForReader"))]
    sections = [
        {
            "key": "today",
            "title": "今日总判断",
            "body": _safe_reader_text(reader_brief.get("finalConclusion") or reader_brief.get("oneLine") or "本轮未生成总判断。"),
        },
        {
            "key": "why",
            "title": "核心理由",
            "bullets": [_safe_reader_text(item) for item in (reader_brief.get("why") or [])[:5]],
        },
        {
            "key": "risk",
            "title": "最大风险 / 反证",
            "bullets": risk_bullets,
        },
        {
            "key": "market_geo",
            "title": "市场与地缘状态",
            "bullets": [
                _safe_reader_text(market.get("summaryForReader")) if market else "",
                _safe_reader_text(geo.get("summaryForReader")) if geo else "",
            ],
        },
        {
            "key": "next",
            "title": "下一步",
            "bullets": [_safe_reader_text(item) for item in (reader_brief.get("nextSteps") or [])[:5]],
        },
        {
            "key": "data_confidence",
            "title": "数据可信度",
            "body": _safe_reader_text(reader_brief.get("dataConfidence") or _reader_data_confidence(source_health_v2, evidence_stats)),
        },
    ]
    return {
        "schema": "reader_v2_v1",
        "runDate": run_date,
        "sections": _clean_reader_v2_sections(sections),
        "departmentCards": cards,
        "supportDrawers": _reader_v2_support_drawers(cards, original_analysis_refs, evidence_items),
    }


def _build_reader_v3(
    *,
    run_date: str,
    generated_at: str = "",
    data_as_of: str = "",
    reader_brief: Dict[str, Any],
    department_reports: List[Dict[str, Any]],
    department_inputs: List[Dict[str, Any]],
    evidence_items: List[Dict[str, Any]],
    source_health_v2: Dict[str, Any],
    evidence_stats: Dict[str, Any],
    decision: Dict[str, Any],
    research_reliability: Optional[Dict[str, Any]] = None,
    scenario_adjudication: Optional[Dict[str, Any]] = None,
    universe: Optional[Dict[str, Any]] = None,
    evidence_facts: Optional[List[Dict[str, Any]]] = None,
    original_analysis_snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    reliability_provided = research_reliability is not None
    research_reliability = research_reliability or build_research_reliability(department_reports)
    scenario_adjudication = scenario_adjudication or build_scenario_adjudication(department_reports)
    visible = _reader_department_reports(department_reports)
    cards = [_reader_v3_department_card(row, department_inputs, evidence_items) for row in visible]
    challenge_verdicts = build_challenge_verdicts(visible)
    _apply_challenge_verdicts(cards, challenge_verdicts)
    cio = _first_department(visible, {"CIOAgent", "DecisionReportAgent"})
    risk = _first_department(visible, {"RiskAgent", "RiskPositionAgent"})
    red_team = _first_department(visible, {"RedTeamAgent", "RedBlueAgent"})
    market = _first_department(visible, {"MarketAgent", "MarketStrategyAgent"})
    geo = _first_department(visible, {"GeoPolicyAgent"})

    # Curators may remove false gaps (for example a confirmed empty portfolio),
    # so the public count is calculated only after curation.
    total_gap_count = 0
    critical_gap_count = int(evidence_stats.get("missingCriticalFacts") or 0)
    if reliability_provided:
        raw_confidence_label = str(research_reliability.get("label") or "结论不足")
        confidence_label = {
            "可用，含待确认情景": "中等可信",
            "待语义复核": "待复核",
        }.get(raw_confidence_label, raw_confidence_label)
    else:
        score = _safe_float(source_health_v2.get("overallScore"))
        confidence_label = "高可信" if score is not None and score >= 0.85 else "中等可信" if score is not None and score >= 0.6 else "低可信"
        if critical_gap_count:
            confidence_label = f"{confidence_label}，带限制"
        elif total_gap_count:
            confidence_label = f"{confidence_label}，含待确认项"

    action_label = _reader_action_label(decision)
    stock_matrix = _build_stock_matrix(
        evidence_facts or evidence_items,
        universe=universe or {},
        original_analysis_snapshot=original_analysis_snapshot or {},
    )
    market_matrix = _build_market_matrix(evidence_facts or evidence_items, stock_matrix)
    if (
        str(scenario_adjudication.get("judgment") or "").strip("。")
        == "证据不足以形成最终裁决"
        and reader_brief.get("finalConclusion")
    ):
        scenario_adjudication = {
            **scenario_adjudication,
            "judgment": _product_copy(reader_brief.get("finalConclusion")),
        }
    scenario_adjudication = _reader_scope_adjudication(
        scenario_adjudication,
        market_matrix=market_matrix,
    )
    _curate_reader_v3_cards(
        cards,
        market_matrix=market_matrix,
        stock_matrix=stock_matrix,
        evidence_rows=evidence_facts or evidence_items,
        has_portfolio=bool(_reader_portfolio_symbols(universe or {})),
        portfolio_snapshot_available=bool((original_analysis_snapshot or {}).get("portfolioSnapshotAvailable")),
        adjudication=scenario_adjudication,
    )
    _rebind_curated_reader_evidence(
        cards,
        evidence_rows=evidence_facts or evidence_items,
        evidence_items=evidence_items,
    )
    timing = _reader_timing_context(
        run_date=run_date,
        generated_at=generated_at,
        data_as_of=data_as_of,
        market_matrix=market_matrix,
        stock_matrix=stock_matrix,
    )
    _align_reader_evidence_times(cards, timing)
    _align_reader_session_language(cards, timing)
    total_gap_count = sum(len(card.get("dataGaps") or []) for card in cards)
    if not reliability_provided and not critical_gap_count and total_gap_count and "待确认" not in confidence_label:
        confidence_label = f"{confidence_label}，含待确认项"
    if not _reader_portfolio_symbols(universe or {}):
        _align_reader_no_portfolio_language(cards)
        scenario_adjudication = _reader_no_portfolio_copy(scenario_adjudication)
    one_line = _reader_cio_headline(
        scenario_adjudication.get("judgment")
        or (cio or {}).get("summaryForReader")
        or reader_brief.get("finalConclusion")
        or reader_brief.get("oneLine")
        or "本轮未生成总判断。",
        shared_facts=(
            []
            if sum(1 for row in market_matrix if row.get("scopeType") == "market") >= 3
            else scenario_adjudication.get("sharedFacts")
        ),
    )
    supported_cio_claims, hypothesis_cio_claims = _reader_claims_by_semantic_status(cio or {})
    market_reason = _reader_market_reason(market_matrix)
    market_level_count = sum(1 for row in market_matrix if row.get("scopeType") == "market")
    key_reasons = _dedupe_nonempty(
        (
            [
                _reader_institutional_copy(item)
                for item in _product_list(scenario_adjudication.get("sharedFacts"), limit=3)
            ]
            if market_level_count >= 3
            else [
                *([market_reason] if market_reason else []),
                *[
                    _reader_institutional_copy(item)
                    for item in _product_list(scenario_adjudication.get("sharedFacts"), limit=2)
                ],
                *[_reader_institutional_copy(item) for item in _product_list(supported_cio_claims, limit=1)],
                *[
                    f"基准解释：{_reader_institutional_copy(item)}"
                    for item in _product_list(hypothesis_cio_claims, limit=1)
                ],
                *_product_list(reader_brief.get("why"), limit=2),
            ]
        ),
        limit=3,
    )
    strongest_alternative = _product_copy(scenario_adjudication.get("strongestAlternative"))
    risk_items = _dedupe_nonempty(
        (
            [f"竞争情景：{_reader_institutional_copy(strongest_alternative)}"]
            if strongest_alternative
            else _product_list((red_team or {}).get("counterpoints"), limit=2)
        ),
        limit=3,
    )
    next_steps = _reader_next_steps(
        (cio or {}).get("nextAction"),
        [
            *[
                f"下次复核什么：{item}"
                for item in _dedupe_nonempty(
                    [
                        gap
                        for raw_gap in (cio or {}).get("dataGaps") or []
                        for gap in [_reader_gap_text(raw_gap)]
                        if gap
                    ],
                    limit=3,
                )
            ],
            (risk or {}).get("nextAction"),
            (red_team or {}).get("nextAction"),
            *_product_list(reader_brief.get("nextSteps"), limit=3),
        ],
    )
    next_steps = [_reader_institutional_copy(item) for item in next_steps]
    if market_level_count >= 3:
        pressured_markets = [
            str(row.get("scopeLabel") or row.get("market") or "").replace("市场", "")
            for row in market_matrix
            if row.get("scopeType") == "market" and "承压" in str(row.get("state") or "")
        ]
        strong_markets = [
            str(row.get("scopeLabel") or row.get("market") or "").replace("市场", "")
            for row in market_matrix
            if row.get("scopeType") == "market" and "偏强" in str(row.get("state") or "")
        ]
        watch_copy = (
            f"观察{'、'.join(pressured_markets)}是否企稳、{'、'.join(strong_markets)}强势是否延续，并结合可用宽度与成交确认"
            if pressured_markets and strong_markets else
            "观察三地主要指数与已接入的市场宽度、成交是否同向修复"
        )
        next_steps = [
            "不做什么：不把单股强势当作市场转强信号，也不依据单日下跌直接判断中期趋势切换",
            f"看什么：{watch_copy}",
            "下次复核什么：信用利差、波动率与市场级价格信号是否一致",
        ]
    max_limitation = _max_reader_limitation(cards, source_health_v2, evidence_stats)
    card_by_agent = {str(card.get("agent") or ""): card for card in cards}
    market_geo = _dedupe_nonempty(
        [
            _reader_market_scope_summary(market_matrix),
            _reader_institutional_copy((card_by_agent.get("GeoPolicyAgent") or {}).get("conclusion") or ""),
        ],
        limit=2,
    )
    report_sections = _reader_v3_report_sections(cards, source_health_v2, evidence_stats)
    if not cards:
        legacy_stock_summary = _product_copy(
            reader_brief.get("finalConclusion") or reader_brief.get("analysis")
        )
        if legacy_stock_summary:
            for section in report_sections:
                if section.get("key") == "stocks":
                    section["body"] = legacy_stock_summary
                    break
    public_cards = [_public_reader_v3_department_card(card) for card in cards]
    mode_label = _reader_mode_label(str(source_health_v2.get("overallMode") or ""))
    headline_audit = _reader_headline_audit(
        one_line,
        market_matrix=market_matrix,
        evidence_rows=evidence_facts or evidence_items,
    )
    # The upstream CIO memo can fail semantic review while the deterministic
    # Reader headline, rebuilt from accepted market evidence, still closes its
    # own evidence chain.  Do not let the rejected raw memo overwrite the
    # product headline after curation; retain its warning in Diagnostics.
    if (
        reliability_provided
        and str(research_reliability.get("label") or "") == "结论不足"
        and headline_audit.get("headlineSafe")
    ):
        confidence_label = "中等可信，含待验证情景"
    coverage_copy = _reader_coverage_copy(universe or {}, cards)
    return {
        "schema": "reader_v3_v1",
        "runDate": run_date,
        "timing": timing,
        "hero": {
            "action": action_label,
            "status": _reader_scope_title(market_matrix),
            "confidence": confidence_label,
            "oneLine": one_line,
            "maxLimitation": max_limitation,
            "coverage": coverage_copy,
            "marketStance": _reader_market_stance(market_matrix),
            "portfolioAction": _reader_portfolio_action(universe or {}, action_label),
            "validity": str(timing.get("validity") or ""),
            "dataCoverage": coverage_copy or mode_label,
        },
        "assessment": {
            "dataCoverage": mode_label,
            "conclusionConfidence": confidence_label,
        },
        "keyReasons": key_reasons,
        "counterpoints": risk_items,
        "nextSteps": next_steps or ["等待下一次数据刷新后复核。"],
        "marketMatrix": market_matrix,
        "stockMatrix": stock_matrix,
        "marketGeo": market_geo,
        "adjudication": {
            "sharedFacts": [
                _reader_institutional_copy(item)
                for item in _product_list(scenario_adjudication.get("sharedFacts"), limit=3)
            ],
            "baseCase": _reader_institutional_copy(scenario_adjudication.get("baseCase")),
            "strongestAlternative": _reader_institutional_copy(scenario_adjudication.get("strongestAlternative")),
            "judgment": _reader_adjudication_judgment(scenario_adjudication.get("judgment")),
            "why": _reader_institutional_copy(scenario_adjudication.get("why")),
            "invalidationTriggers": [
                _reader_institutional_copy(item)
                for item in _product_list(scenario_adjudication.get("invalidationTriggers"), limit=3)
            ],
        },
        # Detailed raw challenge verdicts remain in departmentReports and
        # Diagnostics. Reader exposes only the curated RedTeam/CIO projection.
        "challengeVerdicts": [],
        "reliability": {
            "label": confidence_label,
            "headlineSafe": bool(headline_audit.get("headlineSafe")),
            "headlineDisplayable": bool(headline_audit.get("displayable")),
            "headlineEvidenceSupported": bool(headline_audit.get("evidenceSupported")),
            "headlineStatus": str(headline_audit.get("status") or ""),
            "warnings": _product_list(research_reliability.get("warnings"), limit=3),
            "supportedClaims": research_reliability.get("supportedClaims", 0),
            "hypothesisClaims": research_reliability.get("hypothesisClaims", 0),
            "rejectedClaims": research_reliability.get("rejectedClaims", 0),
        },
        "reportSections": report_sections,
        "dataConfidence": _reader_v3_confidence_copy(
            confidence_label,
            critical_gap_count=critical_gap_count,
            department_gap_count=total_gap_count,
            analysis_mode=str(source_health_v2.get("overallMode") or ""),
        ),
        "evidenceSummary": {
            "verifiedFacts": evidence_stats.get("verifiedFacts", 0),
            "derivedFacts": evidence_stats.get("derivedFacts", 0),
            "discoveryItems": evidence_stats.get("discoveryItems", 0),
            "missingCriticalFacts": evidence_stats.get("missingCriticalFacts", 0),
            "departmentGapItems": total_gap_count,
        },
        "departmentCards": public_cards,
        "diagnosticsPath": f"reports/{run_date}.diagnostics.html",
    }


def _reader_headline_audit(
    text: str,
    *,
    market_matrix: List[Dict[str, Any]],
    evidence_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Validate the final public headline, not merely the upstream CIO draft."""

    evidence_ids = list(dict.fromkeys(
        str(evidence_id)
        for row in market_matrix
        for evidence_id in row.get("evidenceIds") or []
        if str(evidence_id).strip()
    ))
    if not evidence_ids:
        conservative = any(
            marker in text
            for marker in (
                "观察", "等待", "不足", "未生成", "暂停", "阻断",
                "暂不行动", "不行动", "不操作",
            )
        )
        return {
            "headlineSafe": conservative,
            "displayable": conservative,
            # A conservative no-action headline is supported by the explicit
            # absence of market evidence; it does not claim a market fact.
            "evidenceSupported": conservative,
            "status": "supported_by_absence" if conservative else "insufficient_evidence",
            "acceptedEvidenceIds": [],
            "reasons": ["no_market_evidence"],
        }
    validations = validate_claim_dicts([{
        "claimId": "reader:hero",
        "claim": text,
        "claimType": "scenario",
        "domain": "price",
        "evidenceIds": evidence_ids,
    }], evidence_rows, source_agent="ReaderEditorialPolicy")
    if not validations:
        return {"headlineSafe": False, "displayable": False, "evidenceSupported": False, "status": "rejected"}
    validation = validations[0]
    status = validation.normalized_status().value
    reasons = [str(item) for item in validation.reasons]
    severe_markers = ("not_supported", "requires_", "missing", "no_direct", "strong_causal")
    evidence_supported = bool(validation.accepted_evidence_ids) and not any(
        marker in reason for reason in reasons for marker in severe_markers
    )
    displayable = status in {"supported", "partial", "hypothesis", "disputed"}
    return {
        "headlineSafe": bool(displayable and evidence_supported),
        "displayable": displayable,
        "evidenceSupported": evidence_supported,
        "status": status,
        "acceptedEvidenceIds": list(validation.accepted_evidence_ids),
        "reasons": reasons,
    }


def _finalize_research_reliability(
    upstream: Mapping[str, Any],
    reader: Mapping[str, Any],
) -> Dict[str, Any]:
    """Keep the raw CIO audit distinct from the final curated Reader audit."""

    result = dict(upstream)
    upstream_safe = bool(upstream.get("headlineSafe"))
    final_safe = bool(reader.get("headlineSafe"))
    result["upstreamLabel"] = str(upstream.get("label") or "")
    result["upstreamHeadlineSafe"] = upstream_safe
    result["upstreamHeadlineStatus"] = str(upstream.get("headlineStatus") or "")
    result["headlineSafe"] = final_safe
    result["headlineStatus"] = str(reader.get("headlineStatus") or "")

    has_uncertainty = any(
        int(upstream.get(key) or 0) > 0
        for key in ("hypothesisClaims", "disputedClaims", "rejectedClaims")
    ) or not upstream_safe
    if not final_safe:
        result["label"] = "结论不足"
    elif has_uncertainty:
        result["label"] = "中等可信，含待验证情景"
    else:
        reader_label = str(reader.get("label") or "").strip()
        result["label"] = reader_label if reader_label and reader_label != "结论不足" else "中等可信"

    warnings: List[str] = []
    for warning in upstream.get("warnings") or []:
        text = str(warning or "").strip()
        if not text:
            continue
        if final_safe and "CIO 总结尚未通过语义可靠性检查" in text:
            text = "原始 CIO 总结未通过语义检查；默认 Reader 已用通过核验的共同事实重建。"
        if text not in warnings:
            warnings.append(text)
    result["warnings"] = warnings
    return result


def _reader_market_coverage(universe: Mapping[str, Any]) -> str:
    counts = {"A股": 0, "港股": 0, "美股/ETF": 0}
    for raw in universe.get("subjectSymbols") or []:
        symbol = str(raw or "").strip().upper()
        if not symbol:
            continue
        if re.fullmatch(r"HK\d{4,5}", symbol):
            counts["港股"] += 1
        elif re.fullmatch(r"(?:SH|SZ|BJ)?\d{6}", symbol):
            counts["A股"] += 1
        else:
            counts["美股/ETF"] += 1
    parts = [f"{label} {count}" for label, count in counts.items() if count]
    return "覆盖范围：" + "、".join(parts) if parts else ""


def _reader_coverage_copy(universe: Mapping[str, Any], cards: List[Dict[str, Any]]) -> str:
    coverage = _reader_market_coverage(universe)
    macro = next((card for card in cards if str(card.get("agent") or "") == "MacroAgent"), None)
    sources = {
        str(item.get("sourceName") or item.get("provider") or "")
        for item in (macro or {}).get("evidenceSamples") or []
        if isinstance(item, dict) and str(item.get("sourceName") or item.get("provider") or "")
    }
    if sources and all("FRED" in source for source in sources):
        coverage = f"{coverage}；宏观量化证据以美国 FRED 指标为主" if coverage else "宏观量化证据以美国 FRED 指标为主"
    return coverage


def _reader_timing_context(
    *,
    run_date: str,
    generated_at: str,
    data_as_of: str,
    market_matrix: List[Dict[str, Any]],
    stock_matrix: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Describe report timing without presenting a pre-open snapshot as today's close."""

    session_label = "时点简报"
    try:
        parsed = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        shanghai = parsed.astimezone(ZoneInfo("Asia/Shanghai"))
        if shanghai.date().isoformat() == run_date and (shanghai.hour, shanghai.minute) < (9, 30):
            session_label = "盘前简报"
        elif shanghai.date().isoformat() == run_date and (shanghai.hour, shanghai.minute) < (15, 5):
            session_label = "盘中简报"
        else:
            session_label = "收盘后简报"
    except (TypeError, ValueError):
        pass

    completed_dates = sorted(
        {
            str(row.get("asOf") or "")[:10]
            for row in [*market_matrix, *stock_matrix]
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(row.get("asOf") or "")[:10])
            and str(row.get("asOf") or "")[:10] <= run_date
        }
    )
    # A global report timestamp is only a conservative common cut. Each
    # exchange keeps its own source date below; calendars and holidays differ.
    common_completed = completed_dates[0] if completed_dates else str(data_as_of or run_date)[:10]
    if session_label == "盘前简报":
        for row in market_matrix:
            if row.get("scopeType") != "market":
                continue
            note = str(row.get("scopeNote") or "").rstrip("。")
            session_note = "盘前涨跌按该市场标注的最近完整交易日解读。"
            row["scopeNote"] = f"{note}；{session_note}" if note else session_note
        validity = (
            f"{session_label} · 行情共同可比截面截至 {common_completed}；"
            "各市场、宏观与事件按各自标注时点"
        )
        display_as_of = common_completed
    else:
        validity = f"{session_label} · 数据按各自标注时点"
        display_as_of = str(data_as_of or common_completed or run_date)
    return {
        "reportDate": run_date,
        "generatedAt": generated_at,
        "dataAsOf": display_as_of,
        "sessionLabel": session_label,
        "validity": validity,
    }


def _reader_scope_title(market_matrix: List[Dict[str, Any]]) -> str:
    market_coverage = sum(1 for row in market_matrix if row.get("scopeType") == "market")
    return "跨市场研究简报" if market_coverage >= 2 else "多市场观察简报"


def _align_reader_evidence_times(cards: List[Dict[str, Any]], timing: Mapping[str, Any]) -> None:
    """Preserve source timestamps; the timing block explains cross-market cuts.

    This function remains as a compatibility hook for callers. A report-wide
    timestamp must never overwrite exchange-specific evidence provenance.
    """

    del cards, timing


def _align_reader_session_language(cards: List[Dict[str, Any]], timing: Mapping[str, Any]) -> None:
    """Calibrate product copy to the actual market session."""

    session_label = str(timing.get("sessionLabel") or "")
    run_date = str(timing.get("reportDate") or "").strip()

    def calibrate(value: Any) -> Any:
        if isinstance(value, list):
            return [calibrate(item) for item in value]
        if not isinstance(value, str):
            return value
        text = value
        replacements = {
            "A 股市场普跌": "A 股主要指数普遍下跌",
            "A股市场普跌": "A股主要指数普遍下跌",
            "全市场大跌": "主要指数普遍下跌",
            "在全市场大跌背景下": "在A股主要指数普遍下跌背景下",
            "市场宽度略微偏向空头": "市场宽度数据缺失，暂不能判断涨跌家数结构",
            "AAPL今日开盘": "AAPL下一美股交易时段开盘",
            "修复资金流数据接口": "补充资金流数据",
            "数据源返回为空": "本轮未返回有效结果",
        }
        if session_label == "盘前简报":
            replacements.update({
                "今日A股市场": "上一完整交易日A股市场",
                "当日主要指数": "上一完整交易日主要指数",
            })
        elif run_date:
            replacements.update({
                "今日A股市场": f"{run_date} A股市场",
                "当日主要指数": f"{run_date} 主要指数",
            })
        for old, new in replacements.items():
            text = text.replace(old, new)
        if session_label == "盘前简报":
            text = re.sub(
                r"\d{4}-\d{2}-\d{2}\s+A\s*股主要指数普遍下跌",
                "上一完整交易日 A 股主要指数普遍下跌",
                text,
            )
        return text

    for card in cards:
        for key in ("conclusion", "keyClaims", "counterpoints", "dataGaps", "nextAction", "nextActions"):
            if key in card:
                card[key] = calibrate(card[key])


def _reader_market_stance(market_matrix: List[Dict[str, Any]]) -> str:
    market_rows = [row for row in market_matrix if row.get("scopeType") == "market"]
    sample_rows = [row for row in market_matrix if row.get("scopeType") == "sample"]
    parts = [
        f"{row.get('scopeLabel') or row.get('market')}：{row.get('state') or '待确认'}"
        for row in market_rows
    ]
    if sample_rows:
        labels = "、".join(str(row.get("scopeLabel") or row.get("market") or "") for row in sample_rows)
        parts.append(f"{labels}仅作样本观察")
    return "；".join(parts) or "市场状态待确认"


def _reader_portfolio_action(universe: Mapping[str, Any], action_label: str) -> str:
    portfolio_symbols = _reader_portfolio_symbols(universe)
    if not portfolio_symbols:
        return "未接入真实持仓，不生成组合动作"
    return f"组合研究动作：{action_label}"


def _reader_portfolio_symbols(universe: Mapping[str, Any]) -> List[str]:
    return [
        str(symbol)
        for group in universe.get("groups") or []
        if isinstance(group, Mapping) and str(group.get("name") or "") == "portfolio"
        for symbol in group.get("symbols") or []
        if str(symbol).strip()
    ]


def _reader_no_portfolio_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _reader_no_portfolio_copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_reader_no_portfolio_copy(item) for item in value]
    if not isinstance(value, str):
        return value
    return (
        value.replace("持有观察", "观察")
        .replace("保守持有", "保守观察")
        .replace("维持持有", "维持观察")
        .replace("‘持有’", "‘观察’")
        .replace("“持有”", "“观察”")
    )


def _align_reader_no_portfolio_language(cards: List[Dict[str, Any]]) -> None:
    for card in cards:
        for key in ("conclusion", "keyClaims", "counterpoints", "dataGaps", "nextAction", "nextActions"):
            if key in card:
                card[key] = _reader_no_portfolio_copy(card[key])


def _build_market_matrix(
    evidence_rows: List[Dict[str, Any]],
    stock_matrix: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build a reader-facing market table without upgrading samples to markets."""

    rows = [normalize_evidence_fact(item) for item in evidence_rows if isinstance(item, dict)]
    out: List[Dict[str, Any]] = []
    index_rows = [
        item for item in rows
        if str(item.get("metric") or "") == "main_indices"
        and isinstance(item.get("measurements"), dict)
    ]
    market_specs = {
        "cn": ("A股", "A股市场", (
            "index_sh000001_change_pct", "index_sz399001_change_pct",
            "index_sz399006_change_pct", "index_sh000688_change_pct",
            "index_sh000016_change_pct", "index_sh000300_change_pct",
        )),
        "hk": ("HK", "港股市场", (
            "index_hsi_change_pct", "index_hstech_change_pct", "index_hscei_change_pct",
        )),
        "us": ("US", "美股市场", (
            "index_spx_change_pct", "index_ixic_change_pct", "index_dji_change_pct",
        )),
        "jp": ("JP", "日本市场", (
            "index_n225_change_pct", "index_topx_change_pct",
        )),
        "kr": ("KR", "韩国市场", (
            "index_ks11_change_pct", "index_kq11_change_pct",
        )),
        "tw": ("TW", "台湾市场", (
            "index_twii_change_pct", "index_twoii_change_pct",
        )),
    }
    breadth_by_region: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if str(row.get("metric") or "") != "market_stats":
            continue
        subject = str(row.get("subject") or row.get("symbol") or "market").lower()
        region = {"market": "cn", "market_cn": "cn", "market_hk": "hk", "market_us": "us"}.get(subject)
        if region:
            breadth_by_region[region] = row
    market_order = {"cn": 0, "hk": 1, "jp": 2, "kr": 3, "tw": 4, "us": 5}
    for index_row in sorted(
        index_rows,
        key=lambda row: market_order.get(str(row.get("market") or "cn").lower(), 9),
    ):
        region = str(index_row.get("market") or "").lower()
        if not region:
            subject = str(index_row.get("subject") or "").lower()
            region = "cn" if subject == "market" else subject.removeprefix("market_")
        measurements = dict(index_row.get("measurements") or {})
        if region not in market_specs:
            region = next(
                (
                    candidate
                    for candidate, (_market, _label, change_keys) in market_specs.items()
                    if any(key in measurements for key in change_keys)
                ),
                "",
            )
        if region not in market_specs:
            # Unknown rows must not silently become A-share evidence.
            continue
        market, scope_label, change_keys = market_specs[region]
        breadth_row = breadth_by_region.get(region, {})
        headline = _main_indices_measurement_label(measurements).replace("主要指数：", "")
        changes = [
            _safe_float(measurements.get(key))
            for key in change_keys
        ]
        valid_changes = [value for value in changes if value is not None]
        negative_count = sum(value < -0.05 for value in valid_changes)
        positive_count = sum(value > 0.05 for value in valid_changes)
        if valid_changes and negative_count >= max(1, len(valid_changes) - 1) and positive_count == 0:
            state = "主要指数普遍承压"
        elif valid_changes and min(valid_changes) < 0 < max(valid_changes):
            state = "主要指数分化"
        else:
            state = "主要指数偏强"
        out.append({
            "market": market,
            "scopeLabel": scope_label,
            "scopeType": "market",
            "state": state,
            "headline": headline,
            "scopeNote": (
                "基于主要宽基指数，并已纳入本市场宽度；不等同于个股普跌。"
                if breadth_row else
                "基于主要宽基指数；本轮不以个股样本替代市场宽度。"
            ),
            "breadthAvailable": bool(breadth_row),
            "asOf": index_row.get("as_of") or index_row.get("asOf") or "",
            "evidenceIds": [
                evidence_id for evidence_id in (index_row.get("id"), breadth_row.get("id")) if evidence_id
            ],
        })

    market_covered = {str(item.get("market") or "") for item in out if item.get("scopeType") == "market"}
    for market, label in (("HK", "港股观察样本"), ("US", "美股观察样本")):
        if market in market_covered:
            continue
        samples = [item for item in stock_matrix if item.get("market") == market]
        if not samples:
            continue
        daily_returns = [
            _safe_float(item.get("return1dPct"))
            for item in samples
            if _safe_float(item.get("return1dPct")) is not None
        ]
        if daily_returns and all(value >= 1 for value in daily_returns):
            state = "观察样本走强"
        elif daily_returns and all(value <= -1 for value in daily_returns):
            state = "观察样本走弱"
        else:
            state = "观察样本分化"
        headline = "；".join(
            f"{item.get('name') or item.get('symbol')} {_format_percent(float(item['return1dPct']))}（1日）"
            for item in samples
            if _safe_float(item.get("return1dPct")) is not None
        ) or "本轮样本已纳入个股观察。"
        out.append({
            "market": market,
            "scopeLabel": label,
            "scopeType": "sample",
            "state": state,
            "headline": headline,
            "scopeNote": f"仅代表本轮 {len(samples)} 只观察标的，不代表{label[:2]}整体。",
            "asOf": max((str(item.get("asOf") or "") for item in samples), default=""),
            "evidenceIds": list(dict.fromkeys([
                evidence_id
                for item in samples
                for evidence_id in item.get("evidenceIds") or []
            ]))[:4],
        })
    return out


def _reader_market_reason(market_matrix: List[Dict[str, Any]]) -> str:
    """Use audited market scope, not an Agent's cross-market extrapolation."""

    market = next((row for row in market_matrix if row.get("scopeType") == "market"), None)
    if not market:
        return ""
    return _product_copy(
        f"{market.get('scopeLabel') or market.get('market')}：{market.get('headline') or market.get('state')}；"
        f"{market.get('scopeNote') or ''}"
    )


def _reader_market_scope_summary(market_matrix: List[Dict[str, Any]]) -> str:
    rows: List[str] = []
    for item in market_matrix:
        label = str(item.get("scopeLabel") or item.get("market") or "").strip()
        headline = str(item.get("headline") or item.get("state") or "").strip()
        note = str(item.get("scopeNote") or "").strip()
        if label and headline:
            rows.append(f"{label}：{headline}" + (f"；{note}" if note else ""))
    return _product_copy("。".join(rows))


def _reader_scope_adjudication(
    source: Mapping[str, Any],
    *,
    market_matrix: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Create the public CIO block from market-level scope, not single-stock prose.

    The LLM adjudication remains in Diagnostics.  When only one market has
    market-level evidence, the Reader must not let overseas stock samples
    silently become US/HK market calls.
    """

    out = dict(source or {})
    market_rows = [row for row in market_matrix if row.get("scopeType") == "market"]
    sample_rows = [row for row in market_matrix if row.get("scopeType") == "sample"]
    if len(market_rows) >= 2:
        breadth_labels = [
            str(row.get("scopeLabel") or row.get("market") or "")
            for row in market_rows
            if row.get("breadthAvailable")
        ]
        confirmation = (
            f"主要指数与已接入的{'、'.join(breadth_labels)}市场宽度、成交"
            if breadth_labels else
            "主要指数后续表现与成交"
        )
        shared_facts = [f"{row.get('scopeLabel')}：{_reader_market_headline_short(row)}" for row in market_rows[:3]]
        detailed_facts = [f"{row.get('scopeLabel')}：{row.get('headline')}" for row in market_rows[:3]]
        pressured = [row for row in market_rows if "承压" in str(row.get("state") or "")]
        strong = [row for row in market_rows if "偏强" in str(row.get("state") or "")]
        synchronized_pressure = len(pressured) == len(market_rows)
        synchronized_strength = len(strong) == len(market_rows)
        market_labels = [
            str(row.get("scopeLabel") or row.get("market") or "").replace("市场", "")
            for row in market_rows
        ]
        market_copy = "、".join(label for label in market_labels if label)
        state_parts = [
            f"{str(row.get('scopeLabel') or row.get('market') or '').replace('市场', '')}{row.get('state')}"
            for row in market_rows
        ]
        if synchronized_pressure:
            base_case = (
                f"{market_copy}主要指数同步承压；当前更符合跨市场风险收缩的一日截面，"
                "但尚不足以确认中期风险环境切换。"
            )
            judgment = (
                f"跨市场主要指数同步承压；{confirmation}修复前，维持谨慎，"
                "不新增高波动风险暴露。"
            )
            strongest_alternative = (
                f"若{confirmation}随后同步修复，本轮下跌更可能是短期调整，"
                "而非持续的跨市场风险收缩。"
            )
        elif synchronized_strength:
            base_case = (
                f"{market_copy}主要指数整体偏强；当前只能确认跨市场同步走强的一日截面，"
                "尚不足以确认中期风险偏好切换。"
            )
            judgment = "跨市场主要指数整体偏强，维持观察；不把单日强势直接外推为中期趋势。"
            strongest_alternative = f"若{confirmation}随后同步转弱，本轮强势可能只是短期反弹。"
        else:
            base_case = "；".join(state_parts) + "；当前更符合区域与风格分化，尚未形成一致的跨市场方向。"
            judgment = (
                "市场间表现分化，维持观察：先用各市场主要指数、宽度与成交确认方向，"
                "不把单股强势外推为市场结论。"
            )
            strongest_alternative = (
                f"若{confirmation}随后转为同向，当前分化判断需要调整为一致的跨市场方向。"
            )
        out.update({
            "sharedFacts": shared_facts,
            "baseCase": base_case,
            "strongestAlternative": strongest_alternative,
            "judgment": judgment,
            "why": "；".join(detailed_facts) + "。单日指数截面只能确认当期表现，不能单独确认中期趋势。",
            "invalidationTriggers": [
                f"{confirmation}转为同向。",
                "信用利差、波动率与市场级价格信号共同改变当前判断。",
            ],
        })
        return out
    covered_market = market_rows[0] if len(market_rows) == 1 else None
    if (
        not covered_market
        or "承压" not in str(covered_market.get("state") or "")
        or not sample_rows
    ):
        return out

    market_label = str(covered_market.get("scopeLabel") or covered_market.get("market") or "已覆盖市场")
    market_short_label = market_label.replace("市场", "") or market_label
    market_headline = str(covered_market.get("headline") or covered_market.get("state") or "主要指数承压").strip("。")
    market_short = _reader_market_headline_short(covered_market)
    sample_labels = list(dict.fromkeys(
        str(row.get("scopeLabel") or row.get("market") or "观察样本").replace("观察样本", "").strip()
        for row in sample_rows
    ))
    sample_copy = "、".join(label for label in sample_labels if label) or "其他市场"
    sample_facts = [
        f"{row.get('scopeLabel')}：{row.get('headline')}；{row.get('scopeNote')}"
        for row in sample_rows[:2]
    ]
    out.update({
        "sharedFacts": [f"{market_label}：{market_short}", *sample_facts],
        "baseCase": (
            f"{market_label}主要指数承压；{sample_copy}目前只有单股观察样本。"
            f"基准情景是{market_short_label}局部风险释放，尚不能据此判断跨市场传导。"
        ),
        "strongestAlternative": (
            f"若{market_label}宽度与成交继续恶化，同时观察样本对应市场的主要指数和宽度转弱，"
            "局部调整可能扩展为跨市场风险收缩。"
        ),
        "judgment": (
            f"维持观察立场：在{market_label}宽度与成交确认企稳前，不新增高波动成长暴露；"
            "海外观察样本只用于个股跟踪，不外推为对应市场转强。"
        ),
        "why": (
            f"{market_label}宽基指数已确认承压（{market_headline}）；"
            f"{sample_copy}缺少主要指数与市场宽度证据，因此跨市场结论暂不成立。"
        ),
        "invalidationTriggers": [
            f"{market_label}上涨/下跌家数与成交额连续改善，主要指数止跌。",
            "观察样本对应市场的主要指数及宽度与样本同向转强或转弱。",
        ],
    })
    return out


def _curate_reader_v3_cards(
    cards: List[Dict[str, Any]],
    *,
    market_matrix: List[Dict[str, Any]],
    stock_matrix: List[Dict[str, Any]],
    evidence_rows: List[Dict[str, Any]],
    has_portfolio: bool,
    portfolio_snapshot_available: bool = False,
    adjudication: Mapping[str, Any],
) -> None:
    """Turn raw department memos into concise institutional Reader notes."""

    by_agent = {str(card.get("agent") or ""): card for card in cards}
    market_scope = _reader_market_scope_summary(market_matrix)
    market_rows = [row for row in market_matrix if row.get("scopeType") == "market"]
    market_labels = {str(row.get("market") or "") for row in market_rows}
    has_cross_market_scope = len(market_rows) >= 2
    market_scope_labels = [
        str(row.get("scopeLabel") or row.get("market") or "").replace("市场", "")
        for row in market_rows
    ]
    market_group = (
        "三地"
        if len(market_rows) == 3 and {"A股", "HK", "US"} <= market_labels
        else "、".join(label for label in market_scope_labels if label)
        or "已有市场"
    )
    pressured_rows = [row for row in market_rows if "承压" in str(row.get("state") or "")]
    strong_rows = [row for row in market_rows if "偏强" in str(row.get("state") or "")]
    synchronized_pressure = bool(market_rows) and len(pressured_rows) == len(market_rows)
    breadth_labels = [
        str(row.get("scopeLabel") or row.get("market") or "")
        for row in market_rows
        if row.get("breadthAvailable")
    ]
    confirmation_copy = (
        f"{market_group}主要指数、已接入的{'、'.join(breadth_labels)}宽度及成交"
        if market_rows and breadth_labels else
        f"{market_group}主要指数后续表现及成交"
        if market_rows else
        "市场级指数、可用宽度及成交"
    )
    pressured_copy = "、".join(
        str(row.get("scopeLabel") or row.get("market") or "").replace("市场", "")
        for row in pressured_rows
    )
    strong_copy = "、".join(
        str(row.get("scopeLabel") or row.get("market") or "").replace("市场", "")
        for row in strong_rows
    )
    mixed_market_scope = bool(pressured_rows and strong_rows and has_cross_market_scope)
    confirmation_check = (
        f"{pressured_copy}主要指数能否企稳、{strong_copy}强势能否延续，以及{market_group}成交是否改善"
        if mixed_market_scope else
        f"{confirmation_copy}是否同向确认"
    )
    improving_scenario = (
        f"{pressured_copy}企稳、{strong_copy}维持韧性且成交改善"
        if mixed_market_scope else
        f"{confirmation_copy}持续修复"
    )
    worsening_scenario = (
        f"{pressured_copy}继续转弱且{strong_copy}同步转弱"
        if mixed_market_scope else
        f"{confirmation_copy}继续恶化"
    )

    cio = by_agent.get("CIOAgent") or by_agent.get("DecisionReportAgent")
    if cio:
        cio["conclusion"] = _reader_institutional_copy(adjudication.get("judgment"))
        cio["keyClaims"] = [
            _reader_institutional_copy(item)
            for item in _product_list(adjudication.get("sharedFacts"), limit=3)
        ]
        cio["counterpoints"] = _product_list(adjudication.get("strongestAlternative"), limit=1)
        cio["dataGaps"] = []
        cio["nextAction"] = (
            "不做什么：不把单股强势当作市场转强信号；"
            f"看什么：观察{confirmation_check}；"
            "下次复核什么：信用利差、波动率与市场级价格信号是否一致。"
        )

    market = by_agent.get("MarketAgent") or by_agent.get("MarketStrategyAgent")
    if market:
        market["conclusion"] = market_scope
        market["keyClaims"] = [
            _product_copy(
                f"{row.get('scopeLabel')}：{row.get('headline')}；{row.get('scopeNote')}"
            )
            for row in market_matrix[:3]
        ]
        market["counterpoints"] = [
            (
                "单日主要指数同向下跌只能确认当期压力；若宽度与成交快速修复，不能据此外推为中期风险环境切换。"
                if synchronized_pressure else
                "当前跨市场表现分化；若承压市场企稳而强势市场维持韧性，不能把局部下跌外推为一致的中期风险收缩。"
            )
        ]
        market["dataGaps"] = []
        market["nextAction"] = f"复核{confirmation_check}，并对比信用与波动率变化。"

    risk = by_agent.get("RiskAgent") or by_agent.get("RiskPositionAgent")
    if risk:
        if synchronized_pressure and has_cross_market_scope:
            risk["conclusion"] = (
                f"当前主要风险是{market_group}主要指数的当期压力继续扩散。"
                f"本轮已确认跨市场指数同向承压，但仍需{confirmation_copy}与信用指标"
                "判断是否演变为中期风险环境切换。"
            )
        elif has_cross_market_scope:
            risk["conclusion"] = (
                f"当前主要风险是{pressured_copy or '承压市场'}的下跌继续扩散；"
                + (
                    f"{strong_copy}主要指数仍偏强，尚未形成一致的跨市场风险收缩。"
                    if strong_copy else
                    "跨市场尚未形成一致方向。"
                )
                + f"后续需观察{confirmation_check}，并结合信用指标判断风险是否升级。"
            )
        elif market_rows:
            only_market = str(market_rows[0].get("scopeLabel") or market_rows[0].get("market") or "已覆盖市场")
            risk["conclusion"] = (
                f"当前主要风险是{only_market}主要指数压力继续扩散。"
                "跨市场风险升级尚未获得其他市场级数据确认，需重点观察宽度、成交和信用指标。"
            )
        else:
            risk["conclusion"] = "本轮缺少市场级指数证据，暂不形成跨市场风险方向判断。"
        risk["keyClaims"] = [
            _reader_institutional_copy(adjudication.get("why")),
            _reader_institutional_copy(adjudication.get("strongestAlternative")),
        ]
        risk["counterpoints"] = [
            f"若{improving_scenario}，风险扩散判断应下调。"
        ]
        risk["dataGaps"] = []
        risk["nextAction"] = f"跟踪{confirmation_check}；未确认前维持观察。"

    red = by_agent.get("RedTeamAgent") or by_agent.get("RedBlueAgent")
    if red:
        observed_names = list(dict.fromkeys(
            str(row.get("name") or row.get("symbol") or "").strip()
            for row in stock_matrix
            if str(row.get("name") or row.get("symbol") or "").strip()
        ))[:2]
        if observed_names:
            observed_copy = "、".join(observed_names)
            red["conclusion"] = (
                f"最强反证是：{observed_copy}{'等' if len(stock_matrix) > len(observed_names) else ''}观察标的"
                "只代表单股，不能证明对应市场整体风险偏好；公司行动事实也不能单独证明价格支撑。"
            )
        else:
            red["conclusion"] = (
                "最强反证是：有限的指数截面不能单独确认中期趋势；"
                "公司行动事实也不能单独证明价格支撑。"
            )
        red["keyClaims"] = [
            "若观察样本对应市场的主要指数与样本走势背离，当前强弱可能只是个股效应。",
            f"若{worsening_scenario}，当前局部调整判断需要上调为更广泛的风险收缩。",
        ]
        red["counterpoints"] = [
            f"若{improving_scenario}，当前风险解释可能过度悲观。"
        ]
        red["dataGaps"] = []
        red["nextAction"] = f"用{confirmation_check}检验基准判断，不据单股样本调整组合。"

    portfolio = by_agent.get("PortfolioAgent") or by_agent.get("PortfolioReviewAgent")
    if portfolio and not has_portfolio:
        if portfolio_snapshot_available:
            portfolio["conclusion"] = "当前持仓快照确认组合为空，不作组合暴露、收益或对冲判断；观察池只用于候选跟踪。"
            portfolio["keyClaims"] = ["当前组合没有持仓；本轮只评估观察池，不生成组合动作。"]
            portfolio["dataGaps"] = []
            portfolio["nextAction"] = "后续新增持仓时，再计算市场、行业、币种和单一标的暴露。"
        else:
            portfolio["conclusion"] = "本轮未接入真实持仓快照，不作组合暴露、收益或对冲判断；观察池只用于候选跟踪。"
            portfolio["keyClaims"] = ["持仓状态未知；任何组合动作都需要在接入持仓、成本和规模后重新计算。"]
            portfolio["dataGaps"] = ["真实持仓快照尚未接入。"]
            portfolio["nextAction"] = "接入真实持仓后，再计算市场、行业、币种和单一标的暴露。"
        portfolio["counterpoints"] = []

    technical = by_agent.get("TechnicalAgent")
    if technical and stock_matrix:
        technical_rows = []
        for row in stock_matrix[:4]:
            one_day = _safe_float(row.get("return1dPct"))
            twenty_day = _safe_float(row.get("return20dPct"))
            performance = []
            if one_day is not None:
                performance.append(f"1日 {one_day:+.2f}%")
            if twenty_day is not None:
                performance.append(f"20日 {twenty_day:+.2f}%")
            technical_rows.append(
                f"{row.get('name')}（{row.get('symbol')}）：{row.get('trend')}"
                + (f"，{' / '.join(performance)}" if performance else "")
            )
        technical["conclusion"] = "；".join(technical_rows) + "。日线趋势基于各市场最近一个完整交易日。"
        technical["keyClaims"] = technical_rows
        technical["counterpoints"] = [
            "单股趋势不能替代市场宽度；均线与区间位置也不单独构成交易结论。"
        ]
        technical["dataGaps"] = []
        technical["nextAction"] = (
            f"复核{len(stock_matrix)}只观察标的的价格、成交与关键均线是否同向确认；"
            "失配时下调趋势置信度。"
        )

    fundamental = by_agent.get("FundamentalAgent")
    if fundamental and stock_matrix:
        fundamental_rows = [
            f"{row.get('name')}（{row.get('symbol')}）：{row.get('fundamental')}；估值：{row.get('valuation')}"
            for row in stock_matrix
        ]
        comparable_symbols = {
            str(item.get("symbol") or "").upper()
            for item in evidence_rows
            if str(item.get("metric") or "") == "fundamental_history_comparison"
            and len((item.get("measurements") or {})) > 1
        }
        missing_comparison = [
            row for row in stock_matrix
            if str(row.get("symbol") or "").upper() not in comparable_symbols
        ]
        fundamental["conclusion"] = (
            "本轮基本面按报告期和同比口径分标的展示。"
            "盈利增长不等于低估；历史估值分位和同业对比不足时，不直接给出高估或低估结论。"
        )
        fundamental["keyClaims"] = fundamental_rows[:4]
        fundamental["counterpoints"] = [
            "正增长不等于低估；缺少匹配期次、历史估值分位和同业比较时，不上调估值结论。"
        ]
        fundamental["dataGaps"] = []
        if missing_comparison:
            names = "、".join(str(row.get("name") or row.get("symbol")) for row in missing_comparison)
            fundamental["dataGaps"].append(
                f"{names}当前有结构化同比指标，但尚未形成同报告期多期可比序列。"
            )
        valuation_ready = {
            str(item.get("symbol") or "").upper()
            for item in evidence_rows
            if str(item.get("metric") or "") in {"fundamental_valuation", "valuation_history_comparison"}
            and (_safe_float((item.get("measurements") or {}).get("valuation_percentile_eligible")) or 0) >= 1
        }
        valuation_pending = [
            row for row in stock_matrix
            if str(row.get("symbol") or "").upper() not in valuation_ready
        ]
        if valuation_pending:
            names = "、".join(str(row.get("name") or row.get("symbol")) for row in valuation_pending)
            fundamental["dataGaps"].append(f"{names}尚缺可用的公开或本地历史估值序列，暂不计算历史分位。")
        if valuation_pending:
            fundamental["nextAction"] = "继续补齐同报告期财务与历史估值序列；样本满足门槛后再比较历史分位。"
        else:
            fundamental["nextAction"] = "继续积累同报告期财务数据，并用最新估值分位复核盈利与价格是否匹配。"

    macro = by_agent.get("MacroAgent")
    if macro:
        macro_rows = _dedupe_nonempty([
            *_reader_macro_history_levels(evidence_rows),
            *_reader_china_macro_levels(evidence_rows),
        ], limit=6) or _reader_macro_levels(evidence_rows)
        if macro_rows:
            macro["conclusion"] = "；".join(macro_rows) + "。分位基于本地缓存的近期观测窗口。"
            macro["keyClaims"] = macro_rows[:3]
            macro["counterpoints"] = [
                "近期分位不等于长周期历史极值；中国增长、通胀与 PMI 为公开二级数据，不冒充统计局直连。"
            ]
            macro["dataGaps"] = []
            macro["nextAction"] = "跟踪信用利差、VIX 和期限利差是否连续偏离当前分位，再判断环境是否切换。"

    geo = by_agent.get("GeoPolicyAgent")
    if geo:
        geo_rows = _reader_geo_discovery(evidence_rows)
        if geo_rows:
            geo["conclusion"] = (
                "本轮地缘线索包括：" + "；".join(geo_rows[:3]) + "。"
                "这些材料用于事件发现；本轮未发现其对观察标的形成直接传导的官方证据。"
            )
            geo["keyClaims"] = geo_rows[:3]
            geo["counterpoints"] = [
                "事件发现不等于资产传导；只有出现制裁、供应链、能源或公司经营的直接证据才调整标的判断。"
            ]
            geo["dataGaps"] = []
            geo["nextAction"] = "继续核验官方制裁、出口管制与冲突升级；出现直接传导证据时再调整判断。"

    intel = by_agent.get("IntelAgent")
    if intel:
        sector_fact = _reader_sector_ranking_fact(evidence_rows)
        verified_events = _reader_verified_event_facts(
            evidence_rows,
            stock_matrix=stock_matrix,
            limit=3,
        )
        event_copy = (
            "本轮已核验：" + "；".join(verified_events) + "。"
            if verified_events else
            "本轮未形成可核验的公司公告事件。"
        )
        intel["conclusion"] = event_copy + "行业排行仅说明当日价格强弱，不用于证明市场流动性状态。"
        intel["keyClaims"] = [*verified_events, *([sector_fact] if sector_fact else [])][:3]
        intel["counterpoints"] = [
            "公司行动与行业涨幅只说明已发生事实，不能单独证明估值改善、价格支撑或资金持续流入。"
        ]
        intel["dataGaps"] = [] if verified_events else ["本轮未形成可核验的公司公告事件。"]
        intel["nextAction"] = "继续回跳交易所、监管机构与公司公告核验关键事件；未核实线索不进入核心结论。"

    sector = by_agent.get("SectorAgent")
    if sector:
        style_fact = _reader_cn_style_fact(market_matrix)
        sector_fact = _reader_sector_ranking_fact(evidence_rows)
        has_market_breadth = any(str(item.get("metric") or "") == "market_stats" for item in evidence_rows)
        has_sector_history = any(str(item.get("metric") or "") == "sector_history_comparison" for item in evidence_rows)
        has_capital_flow = any(
            str(item.get("metric") or "") == "capital_flow"
            or ":capital_flow:" in str(item.get("id") or "")
            for item in evidence_rows
        )
        missing_dimensions = [
            label
            for available, label in (
                (has_market_breadth, "市场宽度"),
                (has_capital_flow, "主动资金流"),
                (has_sector_history, "多日行业相对表现"),
            )
            if not available
        ]
        sector["conclusion"] = (
            (style_fact + "。" if style_fact else "")
            + (sector_fact + "。" if sector_fact else "")
            + (
                f"{'、'.join(missing_dimensions)}尚未形成有效证据，暂不判断风格轮动的持续性。"
                if missing_dimensions else
                "市场宽度、资金与多日行业表现均已纳入，可用于判断风格持续性。"
            )
        )
        sector["keyClaims"] = [item for item in (style_fact, sector_fact) if item]
        sector["counterpoints"] = [
            "单日行业涨幅可能来自事件或样本波动；没有多日相对收益与资金流，不能确认风格轮动持续。"
        ]
        sector["dataGaps"] = [f"{'、'.join(missing_dimensions)}尚待补齐。"] if missing_dimensions else []
        sector["nextAction"] = "复核成长指数能否止跌，并观察行业强弱是否获得市场宽度、成交与多日表现确认。"

    # Curation replaces the raw memo action. Keep the list form in lockstep so
    # Reader renderers never fall back to stale pre-refresh Agent prose.
    for card in cards:
        next_actions = [
            _reader_institutional_copy(_concise_numbered_step(item))
            for item in _split_reader_steps(card.get("nextAction"))
        ][:3]
        card["nextAction"] = "；".join(next_actions)
        card["nextActions"] = next_actions


def _rebind_curated_reader_evidence(
    cards: List[Dict[str, Any]],
    *,
    evidence_rows: List[Dict[str, Any]],
    evidence_items: List[Dict[str, Any]],
) -> None:
    """Keep product evidence aligned with conclusions rewritten by curation."""

    by_agent = {str(card.get("agent") or ""): card for card in cards}
    normalized = [normalize_evidence_fact(row) for row in evidence_rows if isinstance(row, dict)]
    market_by_scope: Dict[str, str] = {}
    for row in normalized:
        if str(row.get("metric") or "") != "main_indices":
            continue
        market = str(row.get("market") or "").lower()
        scope = "cn" if market in {"cn", "a", "ashare", "a_share"} else market
        if scope in {"cn", "hk", "jp", "kr", "tw", "us"} and row.get("id"):
            market_by_scope.setdefault(scope, str(row.get("id")))
    market_ids = [
        market_by_scope[key]
        for key in ("cn", "hk", "jp", "kr", "tw", "us")
        if key in market_by_scope
    ]
    geo_ids = [str(row.get("id")) for row in _reader_geo_evidence_rows(evidence_rows) if row.get("id")]
    macro_risk_ids = [
        str(row.get("id"))
        for row in normalized
        if str(row.get("id") or "").startswith(("fred:BAMLH0A0HYM2:", "fred:VIXCLS:"))
    ][:2]

    def ids_for(*, metrics: Iterable[str] = (), domains: Iterable[str] = (), limit: int = 8) -> List[str]:
        metric_set = set(metrics)
        domain_set = set(domains)
        return [
            str(row.get("id"))
            for row in normalized
            if row.get("id")
            and (not metric_set or str(row.get("metric") or "") in metric_set)
            and (not domain_set or str(row.get("domain") or "") in domain_set)
        ][:limit]

    def balanced_ids(*, metrics: Iterable[str], per_symbol: int, limit: int) -> List[str]:
        metric_set = set(metrics)
        counts: Dict[str, int] = {}
        out: List[str] = []
        for row in normalized:
            if str(row.get("metric") or "") not in metric_set or not row.get("id"):
                continue
            symbol = str(row.get("symbol") or row.get("subject") or "GLOBAL").upper()
            if counts.get(symbol, 0) >= per_symbol:
                continue
            counts[symbol] = counts.get(symbol, 0) + 1
            out.append(str(row.get("id")))
            if len(out) >= limit:
                break
        return out

    def assign(agent_names: Iterable[str], evidence_ids: List[str], *, limit: int = 6) -> None:
        card = next((by_agent.get(name) for name in agent_names if by_agent.get(name)), None)
        ids = list(dict.fromkeys(item for item in evidence_ids if item))[:limit]
        if not card or not ids:
            return
        samples = [
            _reader_v3_evidence_sample(item)
            for item in _evidence_samples(evidence_items, ids, limit=limit)
        ]
        card["evidenceIds"] = [str(item.get("id")) for item in samples if item.get("id")]
        card["evidenceSamples"] = samples

    assign(("MarketAgent", "MarketStrategyAgent"), market_ids, limit=6)
    assign(("GeoPolicyAgent",), geo_ids, limit=3)
    assign(("MacroAgent", "MacroGeopoliticsAgent"), ids_for(domains=("macro",), limit=4), limit=4)
    assign(
        ("SectorAgent", "CandidateReviewAgent"),
        ids_for(metrics=("sector_rankings", "concept_rankings", "market_breadth", "sector_history_comparison"), limit=4),
        limit=4,
    )
    assign(
        ("FundamentalAgent", "FundamentalReportsAgent"),
        balanced_ids(metrics=("fundamental_growth", "fundamental_valuation"), per_symbol=2, limit=8),
        limit=8,
    )
    assign(
        ("TechnicalAgent",),
        balanced_ids(metrics=("daily_data", "price_history_comparison", "realtime_quote"), per_symbol=2, limit=8),
        limit=8,
    )
    assign(
        ("IntelAgent", "IntelCatalystAgent"),
        [str(row.get("id")) for row in _reader_verified_event_rows(evidence_rows, limit=5) if row.get("id")],
        limit=5,
    )
    assign(
        ("PortfolioAgent", "PortfolioReviewAgent"),
        ids_for(metrics=("portfolio_snapshot_status",), limit=2),
        limit=2,
    )
    assign(("CIOAgent", "DecisionReportAgent"), [*market_ids, *macro_risk_ids], limit=5)
    assign(("RiskAgent", "RiskPositionAgent"), [*market_ids, *macro_risk_ids], limit=5)
    assign(("RedTeamAgent", "RedBlueAgent"), [*market_ids, *macro_risk_ids], limit=5)


def _reader_cn_headline_short(headline: str) -> str:
    pairs = dict(re.findall(r"(上证指数|深证成指|创业板指|科创50|上证50|沪深300)\s*([+-]\d+(?:\.\d+)?)%", headline))
    growth = [f"{name} {pairs[name]}%" for name in ("科创50", "创业板指") if name in pairs]
    if growth:
        return "主要指数同步下跌，" + "、".join(growth) + "领跌"
    return headline


def _reader_market_headline_short(row: Mapping[str, Any]) -> str:
    """Keep hero market facts concise while preserving exact market-level moves."""

    headline = str(row.get("headline") or "").strip()
    market = str(row.get("market") or "")
    if market in {"A股", "CN"}:
        return _reader_cn_headline_short(headline)
    names = (
        ("HK", ("恒生指数", "恒生中国企业指数")),
        ("US", ("标普500", "纳斯达克综合指数")),
    )
    selected = next((items for code, items in names if market == code), ())
    values = dict(re.findall(r"(恒生指数|恒生中国企业指数|标普500|纳斯达克综合指数)\s*([+-]\d+(?:\.\d+)?)%", headline))
    parts = [f"{name} {values[name]}%" for name in selected if name in values]
    return "、".join(parts) or headline


def _reader_cn_style_fact(market_matrix: List[Dict[str, Any]]) -> str:
    cn = next((row for row in market_matrix if row.get("scopeType") == "market" and row.get("market") in {"A股", "CN"}), {})
    headline = str(cn.get("headline") or "")
    pairs = {name: float(value) for name, value in re.findall(
        r"(上证指数|创业板指|科创50|沪深300)\s*([+-]\d+(?:\.\d+)?)%",
        headline,
    )}
    if not {"创业板指", "科创50"} <= pairs.keys():
        return ""
    benchmark_name = "沪深300" if "沪深300" in pairs else "上证指数" if "上证指数" in pairs else ""
    broad = pairs.get(benchmark_name) if benchmark_name else None
    comparison = ""
    if broad is not None:
        cyb_gap = max(0.0, abs(pairs["创业板指"]) - abs(broad))
        star_gap = max(0.0, abs(pairs["科创50"]) - abs(broad))
        comparison = (
            f"；分别较{benchmark_name}多跌 {cyb_gap:.2f}、{star_gap:.2f} 个百分点"
        )
    return f"A股成长指数领跌：创业板指 {pairs['创业板指']:+.2f}%、科创50 {pairs['科创50']:+.2f}%{comparison}"


def _reader_sector_ranking_fact(evidence_rows: List[Dict[str, Any]]) -> str:
    row = next(
        (
            item for item in evidence_rows
            if isinstance(item, dict) and str(item.get("metric") or "") == "sector_rankings"
        ),
        None,
    )
    if not row:
        return ""
    return _reader_evidence_label(row.get("value") or "")


def _reader_macro_levels(evidence_rows: List[Dict[str, Any]]) -> List[str]:
    labels = {
        "BAMLH0A0HYM2": "美国高收益债利差",
        "VIXCLS": "VIX",
        "UNRATE": "美国失业率",
        "DFF": "联邦基金有效利率",
        "DGS2": "美国2年期国债收益率",
        "DGS10": "美国10年期国债收益率",
    }
    indexed = {
        str(item.get("metric") or item.get("symbol") or "").upper(): normalize_evidence_fact(item)
        for item in evidence_rows
        if isinstance(item, dict)
    }
    out: List[str] = []
    for metric, label in labels.items():
        row = indexed.get(metric)
        if not row:
            continue
        match = re.search(rf"{re.escape(metric)}=(-?\d+(?:\.\d+)?)", str(row.get("value") or ""), re.I)
        if not match:
            continue
        suffix = "%" if metric in {"BAMLH0A0HYM2", "UNRATE", "DFF", "DGS2", "DGS10"} else ""
        date = str(row.get("as_of") or "")[:10]
        out.append(f"{label} {match.group(1)}{suffix}" + (f"（{date}）" if date else ""))
    return out


def _reader_china_macro_levels(evidence_rows: List[Dict[str, Any]]) -> List[str]:
    labels = {
        "CN_GDP_YOY": ("中国 GDP 同比", "%"),
        "CN_CPI_YOY": ("中国 CPI 同比", "%"),
        "CN_PMI_MANUFACTURING": ("中国制造业 PMI", ""),
    }
    out: List[str] = []
    for item in evidence_rows:
        if not isinstance(item, Mapping):
            continue
        metric = str(item.get("metric") or item.get("symbol") or "").upper()
        if metric not in labels:
            continue
        match = re.search(rf"{re.escape(metric)}=(-?\d+(?:\.\d+)?)", str(item.get("value") or ""), re.I)
        if not match:
            continue
        label, suffix = labels[metric]
        date = str(item.get("as_of") or "")[:10]
        out.append(f"{label} {match.group(1)}{suffix}" + (f"（{date}）" if date else ""))
    return out


def _reader_macro_history_levels(evidence_rows: List[Dict[str, Any]]) -> List[str]:
    labels = {
        "BAMLH0A0HYM2": "美国高收益债利差",
        "VIXCLS": "VIX",
        "DGS10": "美国10年期国债收益率",
        "T10Y3M": "美国10年-3个月期限利差",
        "UNRATE": "美国失业率",
    }
    indexed: Dict[str, Dict[str, Any]] = {}
    for item in evidence_rows:
        if not isinstance(item, Mapping):
            continue
        comparison = item.get("comparison") if isinstance(item.get("comparison"), Mapping) else {}
        series = str(comparison.get("series") or item.get("symbol") or "").upper()
        if series in labels and "history_comparison" in str(item.get("metric") or ""):
            indexed[series] = dict(item)
    out: List[str] = []
    for series in labels:
        row = indexed.get(series)
        if not row:
            continue
        comparison = row.get("comparison") if isinstance(row.get("comparison"), Mapping) else {}
        latest = _safe_float(comparison.get("latest"))
        percentile = _safe_float(comparison.get("history_percentile_pct"))
        observations = int(_safe_float(comparison.get("history_observations")) or 0)
        if latest is None or percentile is None or observations <= 0:
            continue
        suffix = "" if series == "VIXCLS" else "%"
        text = f"{labels[series]} {latest:g}{suffix}，近{observations}期样本分位 {percentile:.1f}%"
        delta = _safe_float(comparison.get("delta_12_observations"))
        if delta is not None:
            text += f"，较12个观测值前 {delta:+.2f}"
        out.append(text)
    return out


def _reader_geo_evidence_rows(evidence_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    markers = ("RELIEFWEB", "TAVILY", "GDELT", "OFAC", "BIS")
    topic_pattern = re.compile(r"Ukraine|Lebanon|Sudan|Yemen|war|conflict|sanction|trade restriction|乌克兰|黎巴嫩|苏丹|也门|冲突|制裁", re.I)
    out: List[Dict[str, Any]] = []
    seen_topics: set[str] = set()
    candidates = sorted(
        [item for item in evidence_rows if isinstance(item, dict)],
        key=lambda item: (
            0 if "RELIEFWEB" in str(item.get("provider") or "").upper() else 1,
            str(item.get("as_of") or item.get("asOf") or ""),
        ),
    )
    for item in candidates:
        if not isinstance(item, dict) or str(item.get("domain") or "") != "news_sentiment":
            continue
        haystack = f"{item.get('provider')} {item.get('id')} {item.get('value')}"
        if not any(marker in haystack.upper() for marker in markers) or not topic_pattern.search(haystack):
            continue
        value = _product_copy(item.get("value"))
        topic_key = re.split(r"\s+[—-]\s+", value, maxsplit=1)[0].strip().lower()
        if value and topic_key and topic_key not in seen_topics:
            seen_topics.add(topic_key)
            out.append(item)
        if len(out) >= 3:
            break
    return out


def _reader_geo_discovery(evidence_rows: List[Dict[str, Any]]) -> List[str]:
    return [
        f"事件线索：{_product_copy(item.get('value'))[:120]}"
        for item in _reader_geo_evidence_rows(evidence_rows)
    ]


def _reader_verified_event_rows(
    evidence_rows: List[Dict[str, Any]],
    *,
    limit: int,
) -> List[Dict[str, Any]]:
    """Return current verified filings only, excluding provider-run telemetry."""

    candidates = [
        normalize_evidence_fact(item)
        for item in evidence_rows
        if isinstance(item, dict)
    ]
    candidates = [
        item
        for item in candidates
        if str(item.get("domain") or "") == "filings_events"
        and str(item.get("fact_type") or item.get("factType") or "") == "verified_fact"
        and str(item.get("value") or "").strip()
        and str(item.get("subject") or item.get("symbol") or "").strip()
    ]
    candidates.sort(
        key=lambda item: str(
            item.get("event_time")
            or item.get("published_at")
            or item.get("as_of")
            or item.get("asOf")
            or ""
        ),
        reverse=True,
    )
    out: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str]] = set()
    for item in candidates:
        subject = str(item.get("subject") or item.get("symbol") or "").strip().upper()
        value = _product_copy(item.get("value")).strip()
        key = (subject, value.casefold())
        if not value or key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _reader_verified_event_facts(
    evidence_rows: List[Dict[str, Any]],
    *,
    stock_matrix: List[Dict[str, Any]],
    limit: int,
) -> List[str]:
    names = {
        str(row.get("symbol") or "").strip().upper(): str(row.get("name") or row.get("symbol") or "").strip()
        for row in stock_matrix
        if str(row.get("symbol") or "").strip()
    }
    out: List[str] = []
    for item in _reader_verified_event_rows(evidence_rows, limit=limit):
        symbol = str(item.get("symbol") or item.get("subject") or "").strip().upper()
        name = next(
            (label for candidate, label in names.items() if _reader_symbols_equal(candidate, symbol)),
            symbol,
        )
        value = _product_copy(item.get("value"))[:120]
        label = value if name and name.casefold() in value.casefold() else f"{name}：{value}"
        date = str(
            item.get("event_time")
            or item.get("published_at")
            or item.get("as_of")
            or item.get("asOf")
            or ""
        )[:10]
        out.append(label + (f"（{date}）" if date else ""))
    return out


def _build_stock_matrix(
    evidence_rows: List[Dict[str, Any]],
    *,
    universe: Mapping[str, Any],
    original_analysis_snapshot: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    """Create a deterministic cross-market stock sheet from same-run evidence."""

    rows = [normalize_evidence_fact(item) for item in evidence_rows if isinstance(item, dict)]
    names: Dict[str, str] = {}
    actions: Dict[str, str] = {}
    for item in original_analysis_snapshot.get("records") or []:
        if not isinstance(item, Mapping):
            continue
        symbol = str(item.get("code") or "").strip().upper()
        if not symbol or symbol == "MARKET":
            continue
        names[symbol] = str(item.get("name") or symbol).strip()
        actions[symbol] = str(item.get("action") or "").strip().lower()

    symbols = [str(item).strip().upper() for item in universe.get("subjectSymbols") or [] if str(item).strip()]
    if not symbols:
        symbols = sorted({
            str(item.get("symbol") or "").strip().upper()
            for item in rows
            if str(item.get("symbol") or "").strip()
            and str(item.get("symbol") or "").strip().lower() != "market"
        })
    out: List[Dict[str, Any]] = []
    for symbol in dict.fromkeys(symbols):
        subject_rows = [
            item
            for item in rows
            if _reader_symbols_equal(str(item.get("symbol") or ""), symbol)
        ]
        if not subject_rows:
            continue
        daily = next((item for item in subject_rows if ":daily_data:" in str(item.get("id") or "")), {})
        history = next((item for item in subject_rows if str(item.get("metric") or "") == "price_history_comparison"), {})
        quote = next((item for item in subject_rows if str(item.get("metric") or "") == "realtime_quote"), {})
        growth = next((item for item in subject_rows if str(item.get("metric") or "") == "fundamental_growth"), {})
        valuation = next((item for item in subject_rows if str(item.get("metric") or "") == "fundamental_valuation"), {})
        valuation_history = next(
            (item for item in subject_rows if str(item.get("metric") or "") == "valuation_history_comparison"),
            {},
        )
        daily_fields = _reader_numeric_fields(daily)
        history_fields = _reader_numeric_fields(history)
        quote_fields = _reader_numeric_fields(quote)
        growth_fields = _reader_numeric_fields(growth)
        valuation_fields = _reader_numeric_fields(valuation)
        valuation_history_fields = _reader_numeric_fields(valuation_history)
        fundamental_history = next(
            (item for item in subject_rows if str(item.get("metric") or "") == "fundamental_history_comparison"),
            {},
        )
        quote_phase = str(quote.get("session_phase") or quote.get("sessionPhase") or "")
        use_quote = bool(quote_fields.get("price") is not None and quote_phase not in {"premarket", "lunch_break"})
        close = quote_fields.get("price") if use_quote else daily_fields.get("latest_close")
        if close is None:
            close = quote_fields.get("price") or daily_fields.get("latest_close")
        sma5 = daily_fields.get("sma5")
        sma20 = daily_fields.get("sma20")
        trend = _reader_trend_label(close, sma5, sma20)
        fundamental = _reader_fundamental_summary(
            growth_fields,
            report_period=str(growth.get("report_period") or fundamental_history.get("report_period") or ""),
            comparison_period=str(fundamental_history.get("comparison_period") or ""),
            same_period_comparison=len((fundamental_history.get("measurements") or {})) > 1,
        )
        valuation_summary = _reader_valuation_summary(valuation_fields, valuation_history_fields)
        event = _latest_verified_event(subject_rows)
        history_return = history_fields.get("return_1d_pct")
        quote_return = quote_fields.get("change_pct")
        return_1d = quote_return if use_quote and quote_phase in {"intraday", "closing_auction", "postmarket"} else history_return
        if return_1d is None:
            return_1d = quote_return
        out.append({
            "symbol": symbol,
            "name": names.get(symbol) or symbol,
            "market": _reader_symbol_market(symbol),
            "stance": _reader_stock_stance(actions.get(symbol), trend),
            "lastPrice": close,
            "currency": _reader_symbol_currency(symbol),
            "return1dPct": return_1d,
            "return20dPct": history_fields.get("return_20d_pct"),
            "trend": trend,
            "fundamental": fundamental or "结构化基本面待补强",
            "valuation": valuation_summary,
            "latestEvent": _reader_evidence_label(event.get("value") or "") if event else "暂无近期官方事件摘要",
            "eventDate": (event.get("event_time") or event.get("published_at") or event.get("as_of") or "")[:10] if event else "",
            "eventUrl": sanitize_public_http_url(event.get("source_url") or "") if event else "",
            "watchLevels": _reader_watch_levels(sma5, sma20, daily_fields.get("high20"), daily_fields.get("low20")),
            "asOf": (quote.get("as_of") if use_quote else None) or daily.get("as_of") or history.get("as_of") or quote.get("as_of") or "",
            "evidenceIds": list(dict.fromkeys([
                str(item.get("id") or "")
                for item in (quote, daily, history, growth, valuation, valuation_history, fundamental_history, event)
                if isinstance(item, Mapping) and item.get("id")
            ])),
        })
    return out


def _reader_numeric_fields(item: Mapping[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for key, value in (item.get("measurements") or {}).items() if isinstance(item.get("measurements"), Mapping) else []:
        number = _safe_float(value)
        if number is not None:
            out[str(key)] = number
    for key, raw in re.findall(r"([A-Za-z][A-Za-z0-9_.]*)=(-?\d+(?:\.\d+)?)", str(item.get("value") or "")):
        out.setdefault(key, float(raw))
    return out


def _reader_trend_label(close: Optional[float], sma5: Optional[float], sma20: Optional[float]) -> str:
    if close is None or sma20 is None:
        return "趋势数据待补"
    if sma5 is not None and close > sma5 > sma20:
        return "短中期趋势向上"
    if close >= sma20:
        return "中期趋势尚在，短线整理"
    return "趋势承压"


def _reader_fundamental_summary(
    fields: Mapping[str, float],
    *,
    report_period: str = "",
    comparison_period: str = "",
    same_period_comparison: bool = False,
) -> str:
    labels = (
        ("revenue_yoy", "营收同比"),
        ("revenue_yoy_pct", "营收同比"),
        ("net_profit_yoy", "净利同比"),
        ("net_profit_yoy_pct", "净利同比"),
        ("roe", "ROE"),
    )
    parts: List[str] = []
    seen: set[str] = set()
    for key, label in labels:
        if key in fields and label not in seen:
            parts.append(f"{label} {_format_percent(float(fields[key]))}")
            seen.add(label)
    if not parts:
        return ""
    period = str(report_period or "")[:10]
    comparison = str(comparison_period or "")[:10]
    if same_period_comparison and period and comparison:
        suffix = f"（{period} 对 {comparison}，同期口径）"
    elif period:
        suffix = f"（截至 {period}，供应商同比口径）"
    else:
        suffix = "（结构化同比快照）"
    return "，".join(parts) + suffix


def _reader_valuation_summary(
    current: Mapping[str, float],
    history: Mapping[str, float],
) -> str:
    """Render current valuation with online history first, then local run history."""

    labels = (
        ("pe_ttm", "PE(TTM)"),
        ("trailing_pe", "PE(TTM)"),
        ("pe", "PE"),
        ("forward_pe", "Forward PE"),
        ("pb", "PB"),
        ("price_to_book", "PB"),
        ("enterprise_to_ebitda", "EV/EBITDA"),
    )
    parts: List[str] = []
    seen: set[str] = set()
    for key, label in labels:
        value = _safe_float(current.get(key))
        if value is None or label in seen:
            continue
        parts.append(f"{label} {value:.2f}")
        seen.add(label)

    online_eligible = (_safe_float(current.get("valuation_percentile_eligible")) or 0) >= 1
    online_percentiles: List[str] = []
    online_sample_counts: List[int] = []
    if online_eligible:
        for metric, label in (("pe", "PE"), ("pb", "PB")):
            percentile = _safe_float(current.get(f"{metric}_history_percentile"))
            count = int(_safe_float(current.get(f"{metric}_history_sample_count")) or 0)
            if percentile is None or count < 20:
                continue
            online_percentiles.append(f"{label} {percentile:.1f}% 分位")
            online_sample_counts.append(count)

    sample_count = int(
        _safe_float(history.get("sample_count"))
        or _safe_float(history.get("observation_count"))
        or 0
    )
    percentile_eligible = (_safe_float(history.get("valuation_percentile_eligible")) or 0) >= 1
    percentile_parts: List[str] = []
    if percentile_eligible:
        for metric, label in (("pe", "PE"), ("pb", "PB")):
            value = _safe_float(history.get(f"{metric}_local_run_percentile"))
            if value is None:
                value = _safe_float(history.get(f"{metric}_percentile"))
            if value is not None:
                percentile_parts.append(f"{label} 分位 {value:.0f}%")

    if online_percentiles:
        online_count = min(online_sample_counts) if online_sample_counts else 0
        history_copy = f"近三年公开序列 {online_count} 期：" + "，".join(online_percentiles)
    elif percentile_parts:
        history_copy = f"近 {sample_count} 个本地日度样本：" + "，".join(percentile_parts)
    elif sample_count >= 2:
        history_copy = f"已累计 {sample_count} 个本地日度样本，暂不计算历史分位"
    else:
        history_copy = "历史分位样本不足"

    if parts:
        return "，".join(parts) + f"；{history_copy}"
    return f"当前估值待补；{history_copy}"


def _latest_verified_event(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    candidates = [
        item
        for item in rows
        if str(item.get("fact_type") or item.get("factType") or "") == "verified_fact"
        and str(item.get("domain") or "") == "filings_events"
    ]
    return max(
        candidates,
        key=lambda item: str(item.get("event_time") or item.get("published_at") or item.get("as_of") or ""),
        default={},
    )


def _reader_watch_levels(
    sma5: Optional[float],
    sma20: Optional[float],
    high20: Optional[float],
    low20: Optional[float],
) -> str:
    parts = []
    for label, value in (("5日线", sma5), ("20日线", sma20), ("20日高", high20), ("20日低", low20)):
        if value is not None:
            parts.append(f"{label} {value:.2f}")
    return " / ".join(parts[:4]) or "等待价格结构更新"


def _reader_symbol_market(symbol: str) -> str:
    if re.fullmatch(r"HK\d{4,5}", symbol):
        return "HK"
    if re.fullmatch(r"(?:SH|SZ|BJ)?\d{6}", symbol):
        return "CN"
    return "US"


def _reader_symbols_equal(left: str, right: str) -> bool:
    a, b = left.strip().upper(), right.strip().upper()
    if a == b:
        return True
    if re.fullmatch(r"(?:HK)?\d{4,5}", a) and re.fullmatch(r"(?:HK)?\d{4,5}", b):
        return a.removeprefix("HK").zfill(5) == b.removeprefix("HK").zfill(5)
    return False


def _reader_symbol_currency(symbol: str) -> str:
    return {"CN": "CNY", "HK": "HKD", "US": "USD"}[_reader_symbol_market(symbol)]


def _reader_stock_stance(_action: Optional[str], trend: str) -> str:
    """Describe evidence-backed price structure; upstream action is opinion only."""

    if "向上" in trend:
        return "趋势跟踪"
    if "承压" in trend:
        return "谨慎观察"
    return "观察"


def _public_reader_v3_department_card(card: Dict[str, Any]) -> Dict[str, Any]:
    """Remove internal Agent identifiers from the product-facing Reader v3."""

    row = dict(card)
    agent_key = str(card.get("agent") or "")
    label = _DEPARTMENT_LABELS.get(agent_key) or str(card.get("label") or "")
    if not label:
        label = re.sub(r"Agent$", "", agent_key) or "分析部门"
    row["agent"] = _product_copy(label)
    row["label"] = _product_copy(label)
    # Raw challenges preserve point-in-time figures for audit. The product
    # Reader uses the curated red-team card and CIO adjudication instead.
    row["challengedClaims"] = []
    return row


def _apply_challenge_verdicts(cards: List[Dict[str, Any]], verdicts: List[Dict[str, Any]]) -> None:
    cards_by_agent = {str(card.get("agent") or ""): card for card in cards}
    for verdict in verdicts:
        if str(verdict.get("verdict") or "") != "challenged":
            continue
        card = cards_by_agent.get(str(verdict.get("department") or ""))
        if not card:
            continue
        claim = _product_copy(verdict.get("claim"))
        claims = list(card.get("keyClaims") or [])
        if claim in claims:
            claims.remove(claim)
        else:
            match = re.search(r":(\d+)$", str(verdict.get("targetClaimId") or ""))
            index = int(match.group(1)) - 1 if match else -1
            if 0 <= index < len(claims):
                claim = claims.pop(index)
        card["keyClaims"] = claims
        challenged = list(card.get("challengedClaims") or [])
        challenged.append({
            "claim": claim,
            "status": "存在有效反证，未作为确定依据",
            "opposingScenario": _product_copy(verdict.get("opposingScenario")),
            "falsifier": _product_copy(verdict.get("falsifier")),
        })
        card["challengedClaims"] = challenged


def _public_challenge_verdict(value: Dict[str, Any]) -> Dict[str, Any]:
    department = str(value.get("department") or "")
    return {
        "department": _product_copy(_DEPARTMENT_LABELS.get(department) or re.sub(r"Agent$", "", department)),
        "claim": _reader_institutional_copy(value.get("claim")),
        "status": "原结论已撤回" if value.get("verdict") == "withdrawn" else "存在有效反证，待裁决",
        "opposingScenario": _reader_institutional_copy(value.get("opposingScenario")),
        "falsifier": _reader_institutional_copy(value.get("falsifier")),
    }


def _reader_v3_department_card(row: Dict[str, Any], department_inputs: List[Dict[str, Any]], evidence_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    card = _reader_v2_department_card(row, department_inputs, evidence_items)
    evidence_samples = [
        _reader_v3_evidence_sample(item)
        for item in card.get("evidenceSamples") or []
        if isinstance(item, dict)
    ]
    next_actions = [
        _reader_institutional_copy(_concise_numbered_step(item))
        for item in _split_reader_steps(card.get("nextAction"))
    ][:3]
    return {
        "agent": card.get("agent"),
        "label": _product_copy(card.get("label")),
        "conclusion": _reader_department_conclusion(row, card.get("conclusion")),
        "keyClaims": _reader_department_claims(row, card.get("keyClaims")),
        "counterpoints": [_reader_institutional_copy(item) for item in _product_list(card.get("counterpoints"), limit=2)],
        "dataGaps": [_reader_institutional_copy(item) for item in _product_list(card.get("dataGaps"), limit=2)],
        "nextAction": "；".join(next_actions),
        "nextActions": next_actions,
        "confidence": card.get("confidence") or "medium",
        "supportSignals": [_reader_institutional_copy(item) for item in _product_list(card.get("supportSignals"), limit=3)],
        "evidenceIds": [str(item.get("id")) for item in evidence_samples if item.get("id")],
        "evidenceSamples": evidence_samples,
    }


def _reader_department_conclusion(row: Dict[str, Any], value: Any) -> str:
    text = _reader_institutional_copy(value)
    text = re.sub(
        r"前序部门关于[“\"]防御板块价格表现相对抗跌；是否属于主动资金抱团仍待资金流与市场宽度验证、"
        r"跨市场联动减弱[”\"]的基准判断存在严重的[‘']单股污染[’']与[‘']时效错配[’']",
        "前序部门把少数防御样本的相对抗跌解释为资金抱团，并据此判断跨市场联动减弱；"
        "该结论存在单股污染与时效错配",
        text,
    )
    text = _dedupe_reader_sentences(text)
    semantic = row.get("semanticValidation") if isinstance(row.get("semanticValidation"), dict) else {}
    summary = semantic.get("summary") if isinstance(semantic.get("summary"), dict) else {}
    status = str(summary.get("status") or "").lower()
    if status in {"hypothesis", "disputed"} and text and not text.startswith("部门判断："):
        return f"部门判断：{text}"
    return text


def _reader_department_claims(row: Dict[str, Any], fallback: Any) -> List[str]:
    claims: List[str] = []
    for item in row.get("claimEvidence") or []:
        if not isinstance(item, dict):
            continue
        text = _reader_institutional_copy(item.get("claim") or item.get("text"))
        status = str(item.get("semanticStatus") or item.get("status") or "").lower()
        if not text or status == "rejected" or text.endswith(("：", ":")):
            continue
        if status in {"hypothesis", "disputed"} and not text.startswith("解释性判断："):
            text = f"解释性判断：{text}"
        claims.append(text)
    return _dedupe_nonempty(claims, limit=3) or _product_list(fallback, limit=3)


def _reader_v3_evidence_sample(item: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(item)
    source_url = sanitize_public_http_url(item.get("sourceUrl"))
    if str(item.get("metric") or "") == "main_indices" and isinstance(item.get("measurements"), dict):
        row["label"] = _main_indices_measurement_label(item.get("measurements") or {})
    elif str(item.get("metric") or "") == "fundamental_valuation" and isinstance(item.get("measurements"), dict):
        row["label"] = _reader_valuation_summary(item.get("measurements") or {}, {})
    else:
        row["label"] = _reader_evidence_label(item.get("label") or "")
    row["sourceName"] = _reader_source_name(
        item.get("provider"),
        source_url,
    )
    row["sourceUrl"] = source_url
    row["provider"] = row["sourceName"]
    row["factType"] = {
        "verified_fact": "已验证事实",
        "derived_fact": "推导事实",
        "discovery": "发现线索",
        "agent_opinion": "部门判断",
        "final_claim": "最终判断",
    }.get(str(item.get("factType") or ""), _product_copy(item.get("factType") or ""))
    row["asOf"] = item.get("asOf") or item.get("publishedAt") or item.get("eventTime") or ""
    return row


def _reader_source_name(provider: Any, source_url: Any = "") -> str:
    raw = str(provider or "").strip()
    upper = raw.upper()
    mappings = (
        (("DATAFETCHERMANAGER",), "原系统数据聚合"),
        (("TENCENT",), "腾讯行情"),
        (("AKSHARE", "EASTMONEY"), "公开市场与财务数据"),
        (("YFINANCE",), "Yahoo Finance 公开数据"),
        (("ALPHAVANTAGE",), "Alpha Vantage 行情"),
        (("FINNHUB",), "Finnhub 行情"),
        (("TUSHARE",), "Tushare 行情"),
        (("BAOSTOCK",), "Baostock 行情"),
        (("PYTDX",), "通达信行情"),
        (("SEC",), "SEC 官方披露"),
        (("CNINFO",), "巨潮资讯官方公告"),
        (("HKEX",), "港交所官方披露"),
        (("SSE",), "上交所官方公告"),
        (("SZSE",), "深交所官方公告"),
        (("FRED",), "FRED 官方宏观数据"),
        (("TAVILY",), "Tavily 新闻检索"),
        (("GDELT",), "GDELT 全球事件"),
        (("RELIEFWEB",), "ReliefWeb 人道事件"),
        (("OFAC",), "美国财政部制裁信息"),
        (("BIS",), "美国商务部出口管制信息"),
        (("DAILYUNIVERSE",), "本轮观察清单"),
    )
    for tokens, label in mappings:
        if any(token in upper for token in tokens):
            return label
    try:
        hostname = (urlsplit(sanitize_public_http_url(source_url)).hostname or "").lower()
    except ValueError:
        hostname = ""
    if _reader_hostname_matches(hostname, "sec.gov"):
        return "SEC 官方披露"
    if _reader_hostname_matches(hostname, "hkex.com.hk"):
        return "港交所官方披露"
    if _reader_hostname_matches(hostname, "cninfo.com.cn"):
        return "巨潮资讯官方公告"
    if not raw:
        return "公开数据源"
    if re.search(r"(?:FETCHER|ADAPTER|MANAGER)$", upper):
        return "公开数据源"
    return _product_copy(raw)


def _reader_hostname_matches(hostname: str, domain: str) -> bool:
    return hostname == domain or hostname.endswith(f".{domain}")


def _reader_v3_confidence_copy(
    confidence_label: str,
    *,
    critical_gap_count: int,
    department_gap_count: int,
    analysis_mode: str = "",
) -> str:
    if critical_gap_count:
        return f"{confidence_label}；仍有 {critical_gap_count} 个关键证据缺口，结论需带限制阅读。"
    if str(analysis_mode or "").upper() != "FULL_REVIEW":
        suffix = f"；另有 {department_gap_count} 个部门待确认项影响细分判断" if department_gap_count else ""
        return f"{confidence_label}；已引用证据不存在关键断点，但整体覆盖仍为有限复盘{suffix}。"
    if department_gap_count:
        return (
            f"{confidence_label}；核心证据链完整，"
            f"另有 {department_gap_count} 个部门待确认项影响细分判断。"
        )
    return f"{confidence_label}；核心证据链完整。"


def _reader_evidence_label(value: Any) -> str:
    """Turn ledger payloads into concise reader copy.

    Raw field names and complete provider payloads stay available in
    Diagnostics.  Reader evidence is a short, human-readable citation.
    """
    text = _product_copy(value)
    if not text:
        return ""

    if "main_indices records=" in text or text.startswith("主要指数行情"):
        items = _name_change_items(text, limit=6)
        return f"主要指数：{'、'.join(items)}" if items else "主要指数行情快照"
    if text.startswith("日线数据 rows=") or text.startswith("daily_data rows="):
        fields = _named_number_fields(text)
        latest_date = re.search(r"latest_date=([^ ]+)", text)
        parts = []
        for key, label in (("latest_close", "收盘"), ("sma5", "5日线"), ("sma20", "20日线")):
            if key in fields:
                parts.append(f"{label} {fields[key]:.2f}")
        date_text = latest_date.group(1)[:10] if latest_date else ""
        suffix = f"（{date_text}）" if date_text else ""
        return f"日线结构：{'，'.join(parts)}{suffix}" if parts else f"日线结构快照{suffix}"
    if "行业强弱排行 records=" in text:
        items = _name_change_items(text, limit=5)
        return f"行业强弱：{'、'.join(items)}" if items else "行业强弱排行快照"
    if "热门标的列表 records=" in text:
        items = _name_change_items(text, limit=6)
        return f"热门标的：{'、'.join(items)}" if items else "热门标的快照"
    if (
        "market_stats records=" in text
        or text.startswith("市场统计 records=")
        or text.startswith("市场宽度")
    ):
        fields = _named_number_fields(text)
        labels = (
            ("up_count", "上涨"),
            ("down_count", "下跌"),
            ("flat_count", "平盘"),
            ("limit_up_count", "涨停"),
            ("limit_down_count", "跌停"),
        )
        parts = [f"{label} {int(fields[key])}" for key, label in labels if key in fields]
        return f"市场宽度：{'，'.join(parts)}" if parts else "市场宽度快照"
    if text.startswith("growth available:") or text.startswith("增长 available:"):
        fields = _named_number_fields(text)
        labels = (
            ("revenue_yoy", "营收同比"),
            ("net_profit_yoy", "净利润同比"),
            ("roe", "ROE"),
            ("gross_margin", "毛利率"),
        )
        parts = [f"{label} {_format_percent(fields[key])}" for key, label in labels if key in fields]
        return f"基本面增长：{'，'.join(parts)}" if parts else "基本面增长快照"
    if text.startswith("earnings available:") or text.startswith("财报 available:"):
        date = _regex_group(text, r"report_date=([^,\]]+)")
        currency = _regex_group(text, r"currency=([^,\]]+)")
        fields = _named_number_fields(text)
        parts = []
        if date:
            parts.append(f"报告期 {date}")
        for key, label in (
            ("revenue", "营收"),
            ("net_profit_parent", "归母净利润"),
            ("operating_cash_flow", "经营现金流"),
        ):
            if key in fields:
                parts.append(f"{label} {_format_amount(fields[key], currency)}")
        if "roe" in fields:
            parts.append(f"ROE {_format_percent(fields['roe'])}")
        return f"财报快照：{'，'.join(parts)}" if parts else "财报与分红快照"
    if text.startswith("quote ") or text.startswith("行情 "):
        fields = _named_number_fields(text)
        price = fields.get("行情") or fields.get("price") or fields.get("current")
        change = fields.get("change_pct")
        parts = []
        if price is not None:
            parts.append(f"现价 {price:g}")
        if change is not None:
            parts.append(f"涨跌幅 {_format_percent(change)}")
        return f"行情快照：{'，'.join(parts)}" if parts else "行情快照"
    if re.match(r"^4\s+\d{4}-\d{2}-\d{2}\s+", text):
        date = _regex_group(text, r"^4\s+(\d{4}-\d{2}-\d{2})")
        return f"SEC Form 4 高管持股变动披露 · {date}" if date else "SEC Form 4 高管持股变动披露"
    if "delta_prev_observation=" in text and "series=" in text:
        fields = _named_number_fields(text)
        series = _regex_group(text, r"series=([A-Z0-9]+)")
        names = {
            "GDP": "美国名义 GDP",
            "CPIAUCSL": "美国 CPI 指数",
            "UNRATE": "美国失业率",
        }
        parts = []
        if "latest" in fields:
            parts.append(f"最新值 {fields['latest']:g}")
        if "delta_prev_observation" in fields:
            parts.append(f"较前值 {fields['delta_prev_observation']:+g}")
        if "history_percentile_pct" in fields:
            parts.append(f"历史分位 {fields['history_percentile_pct']:.0f}%")
        return f"{names.get(series, series or '宏观指标')}趋势快照：{'，'.join(parts)}"
    if text.startswith("universe=") and "positive_20d_pct=" in text:
        fields = _named_number_fields(text)
        count = int(fields.get("universe", 0))
        positive = fields.get("positive_20d_pct")
        leaders = _regex_group(text, r"leaders=([^;]+)")
        parts = [f"观察池 {count} 只"] if count else ["观察池"]
        if positive is not None:
            parts.append(f"20日上涨占比 {positive:.0f}%")
        if leaders:
            parts.append(f"阶段领先：{leaders}")
        return "；".join(parts)
    if text.startswith("portfolio_snapshot_status=") or text.startswith("持仓快照_status="):
        fields = _named_number_fields(text)
        holdings = int(fields.get("holdings", 0))
        watchlist = int(fields.get("watchlist", 0))
        if "not_connected" in text:
            return f"真实持仓快照未接入；观察清单 {watchlist} 只"
        return f"持仓快照：持仓 {holdings} 只，观察清单 {watchlist} 只"
    if re.match(r"^(?:(?:portfolio|持仓/组合)/)?watchlist symbols:\s*", text, flags=re.I):
        symbols = re.sub(r"^(?:(?:portfolio|持仓/组合)/)?watchlist symbols:\s*", "", text, flags=re.I)
        return f"观察清单：{symbols}"
    fred_match = re.match(r"^([A-Z0-9]+)=([^@]+)@\s*(\d{4}-\d{2}-\d{2})$", text)
    if fred_match:
        code, value, date = fred_match.groups()
        names = {
            "DGS10": "美国10年期国债收益率",
            "VIXCLS": "VIX 波动率指数",
            "BAMLH0A0HYM2": "美国高收益债利差",
            "DCOILWTICO": "WTI 原油现货价格",
            "CPIAUCSL": "美国 CPI 指数",
            "UNRATE": "美国失业率",
            "GDP": "美国名义 GDP",
        }
        return f"{names.get(code, code)} {value.strip()}（{date}）"
    if "return_1d_pct=" in text or "range_position_pct=" in text:
        fields = _named_number_fields(text)
        parts = []
        for key, label in (
            ("return_1d_pct", "1日"),
            ("return_5d_pct", "5日"),
            ("return_20d_pct", "20日"),
            ("return_60d_pct", "60日"),
            ("return_120d_pct", "120日"),
            ("return_252d_pct", "252日"),
        ):
            if key in fields:
                parts.append(f"{label} {_format_percent(fields[key])}")
        if "range_position_pct" in fields:
            parts.append(f"区间位置 {fields['range_position_pct']:.0f}%")
        return f"区间表现：{'，'.join(parts)}" if parts else "区间表现快照"

    cleaned = re.sub(r"\brecords=\d+;?\s*", "", text)
    cleaned = re.sub(r"\b(code|change_pct|report_date)=", "", cleaned)
    return cleaned[:220].rstrip("；;，, ") + ("…" if len(cleaned) > 220 else "")


def _name_change_items(text: str, *, limit: int) -> List[str]:
    out: List[str] = []
    for chunk in text.split("|"):
        name = _regex_group(chunk, r"name=([^,|]+)")
        change = _regex_group(chunk, r"change_pct=(-?\d+(?:\.\d+)?)")
        if not name:
            continue
        out.append(f"{name.strip()} {_format_percent(float(change))}" if change else name.strip())
        if len(out) >= limit:
            break
    return out


def _named_number_fields(text: str) -> Dict[str, float]:
    return {
        key: float(raw)
        for key, raw in re.findall(
            r"([A-Za-z_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff]*)=(-?\d+(?:\.\d+)?)",
            text,
        )
    }


def _regex_group(text: str, pattern: str) -> str:
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""


def _format_percent(value: float) -> str:
    return f"{value:+.2f}%" if value != 0 else "0.00%"


def _main_indices_measurement_label(measurements: Dict[str, Any]) -> str:
    names = (
        ("index_sh000001_change_pct", "上证指数"),
        ("index_sz399001_change_pct", "深证成指"),
        ("index_sz399006_change_pct", "创业板指"),
        ("index_sh000688_change_pct", "科创50"),
        ("index_sh000016_change_pct", "上证50"),
        ("index_sh000300_change_pct", "沪深300"),
        ("index_hsi_change_pct", "恒生指数"),
        ("index_hstech_change_pct", "恒生科技指数"),
        ("index_hscei_change_pct", "恒生中国企业指数"),
        ("index_spx_change_pct", "标普500"),
        ("index_ixic_change_pct", "纳斯达克综合指数"),
        ("index_dji_change_pct", "道琼斯工业指数"),
        ("index_vix_change_pct", "VIX"),
        ("index_n225_change_pct", "日经225"),
        ("index_topx_change_pct", "东证指数"),
        ("index_ks11_change_pct", "KOSPI"),
        ("index_kq11_change_pct", "KOSDAQ"),
        ("index_twii_change_pct", "台湾加权指数"),
        ("index_twoii_change_pct", "台湾柜买指数"),
    )
    observed_changes: List[float] = []
    for key, _name in names:
        try:
            observed_changes.append(float(measurements[key]))
        except (KeyError, TypeError, ValueError):
            continue
    peers_moved = any(abs(value) > 0.05 for value in observed_changes)
    parts: List[str] = []
    for key, name in names:
        try:
            value = float(measurements[key])
        except (KeyError, TypeError, ValueError):
            continue
        if value == 0 and peers_moved:
            parts.append(f"{name} 涨跌待核验")
        else:
            parts.append(f"{name} {_format_percent(value)}")
    return f"主要指数：{'、'.join(parts)}" if parts else "主要指数行情快照"


def _format_amount(value: float, currency: str) -> str:
    unit = currency or ""
    if abs(value) >= 100_000_000:
        return f"{value / 100_000_000:.2f} 亿 {unit}".strip()
    if abs(value) >= 10_000:
        return f"{value / 10_000:.2f} 万 {unit}".strip()
    return f"{value:g} {unit}".strip()


def _reader_v3_report_sections(
    cards: List[Dict[str, Any]],
    source_health_v2: Dict[str, Any],
    evidence_stats: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Build the fixed product report structure for Web and static Reader.

    Department cards remain the detailed drawer.  These sections are the
    reader-facing outline the user asked for: market first, then macro/geo,
    sector, candidates, stocks, portfolio, risk, confidence and next action.
    """

    section_specs = [
        ("market_status", "市场状态", {"MarketAgent"}),
        ("macro_geo", "宏观与地缘", {"MacroAgent", "GeoPolicyAgent"}),
        ("sector_style", "行业/风格", {"SectorAgent"}),
        ("candidates", "候选观察", {"SectorAgent", "IntelAgent"}),
        ("stocks", "重点个股", {"FundamentalAgent", "TechnicalAgent"}),
        ("portfolio", "持仓影响", {"PortfolioAgent"}),
        ("risk", "风险和反证", {"RiskAgent", "RedTeamAgent"}),
    ]
    sections: List[Dict[str, Any]] = []
    for key, title, agents in section_specs:
        rows = _reader_cards_for_agents(cards, agents)
        sections.append(
            {
                "key": key,
                "title": title,
                "body": _section_body(rows, title),
                "bullets": _section_bullets(rows),
                "counterpoints": _section_counterpoints(rows),
                "nextActions": _section_next_actions(rows),
                "evidenceSamples": _section_evidence_samples(rows),
            }
        )
    critical = int(evidence_stats.get("missingCriticalFacts") or 0)
    mode = str(source_health_v2.get("overallMode") or "").upper()
    sections.append(
        {
            "key": "data_confidence",
            "title": "数据可信度",
            "body": (
                "核心证据链完整；部门待确认项只作为人工复核提示。"
                if critical == 0 and mode == "FULL_REVIEW"
                else "已引用证据不存在关键断点；整体覆盖仍为有限复盘，细分判断需结合待确认项。"
                if critical == 0
                else f"仍有 {critical} 个关键证据缺口，结论需要降级阅读。"
            ),
            "bullets": [
                f"已验证事实 {evidence_stats.get('verifiedFacts', 0)}",
                f"推导事实 {evidence_stats.get('derivedFacts', 0)}",
                f"发现线索 {evidence_stats.get('discoveryItems', 0)}",
                _reader_mode_label(str(source_health_v2.get("overallMode") or "")),
            ],
            "counterpoints": [],
            "nextActions": [],
            "evidenceSamples": [],
        }
    )
    return sections


def _reader_cards_for_agents(cards: List[Dict[str, Any]], agents: set[str]) -> List[Dict[str, Any]]:
    return [card for card in cards if str(card.get("agent") or "") in agents]


def _section_body(rows: List[Dict[str, Any]], fallback_title: str) -> str:
    conclusions = _dedupe_nonempty(
        [_reader_institutional_copy(row.get("conclusion")) for row in rows],
        limit=2,
    )
    if conclusions:
        return " ".join(conclusions)
    return f"{fallback_title}本轮未形成独立结论。"


def _section_bullets(rows: List[Dict[str, Any]]) -> List[str]:
    values: List[str] = []
    for row in rows:
        values.extend(_reader_institutional_copy(item) for item in _product_list(row.get("keyClaims"), limit=3))
        values.extend(_reader_institutional_copy(item) for item in _product_list(row.get("supportSignals"), limit=2))
    return _dedupe_nonempty(values, limit=5)


def _section_counterpoints(rows: List[Dict[str, Any]]) -> List[str]:
    values: List[str] = []
    for row in rows:
        values.extend(_reader_institutional_copy(item) for item in _product_list(row.get("counterpoints"), limit=2))
        values.extend(_reader_institutional_copy(item) for item in _product_list(row.get("dataGaps"), limit=1))
    return _dedupe_nonempty(values, limit=4)


def _section_next_actions(rows: List[Dict[str, Any]]) -> List[str]:
    return _dedupe_nonempty(
        [_reader_institutional_copy(row.get("nextAction")) for row in rows],
        limit=3,
    )


def _section_evidence_samples(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    samples: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        for item in row.get("evidenceSamples") or []:
            if not isinstance(item, dict):
                continue
            key = str(item.get("id") or item.get("label") or "")
            if key in seen:
                continue
            seen.add(key)
            samples.append(item)
            if len(samples) >= 5:
                return samples
    return samples


def _reader_action_label(decision: Dict[str, Any]) -> str:
    action = str(decision.get("action") or "watch").lower()
    gate = str(decision.get("gateStatus") or "").lower()
    if gate == "blocked" or action == "no_action":
        return "不操作"
    if action in {"buy", "sell", "hold"}:
        return _human_action(action)
    return "观察"


def _reader_mode_label(mode: str) -> str:
    return {
        "FULL_REVIEW": "完整复盘",
        "LIMITED_REVIEW": "有限复盘",
        "SCREEN_ONLY": "仅筛选观察",
        "OBSERVE_ONLY": "市场观察",
        "BLOCKED": "数据不足",
    }.get(str(mode or "").upper(), "投研复盘")


def _max_reader_limitation(cards: List[Dict[str, Any]], source_health_v2: Dict[str, Any], evidence_stats: Dict[str, Any]) -> str:
    critical = evidence_stats.get("missingCriticalFacts") or 0
    if critical:
        return f"仍有 {critical} 个关键证据缺口，结论需要降级阅读。"
    blockers = source_health_v2.get("blockingReasons") if isinstance(source_health_v2.get("blockingReasons"), list) else []
    mode = str(source_health_v2.get("overallMode") or "").upper()
    if blockers and mode != "FULL_REVIEW":
        return _product_copy(_human_blocking_reason(str(blockers[0])))
    department_gaps = sum(len(card.get("dataGaps") or []) for card in cards)
    if department_gaps:
        gaps = [str(gap) for card in cards for gap in card.get("dataGaps") or [] if str(gap).strip()]
        joined = " ".join(gaps)
        items: List[str] = []
        if any(token in joined for token in ("氦气", "霍尔木兹", "美伊", "商务部", "海关总署")):
            items.append("地缘与贸易传闻仍需官方原文核验")
        if any(token in joined for token in ("真实持仓", "持仓标的", "成本价", "total_aum")):
            items.append("未接入真实持仓快照")
        if not items:
            items.append(f"仍有 {department_gaps} 个部门待确认项影响细分判断")
        prefix = "核心证据链完整" if mode == "FULL_REVIEW" else "整体覆盖仍为有限复盘"
        return f"{prefix}；{'；'.join(items)}。"
    if mode == "FULL_REVIEW":
        return "核心证据链完整；结论仍需人工复核，不自动执行交易。"
    return "已引用证据不存在关键断点；整体覆盖仍为有限复盘，结论需结合细分待确认项。"


def _split_reader_steps(value: Any) -> List[str]:
    if isinstance(value, str):
        raw = value.strip()
        if raw.startswith("{") and raw.endswith("}"):
            try:
                parsed = ast.literal_eval(raw)
            except (SyntaxError, ValueError):
                parsed = None
            if isinstance(parsed, dict):
                value = parsed
    if isinstance(value, dict):
        aliases = {
            "不做什么": ("不做什么", "不要做", "禁止操作", "操作纪律", "do_not", "avoid"),
            "看什么": (
                "看什么", "观察信号", "核心观察信号", "风险升级触发条件",
                "风险缓解触发条件", "风险升级信号", "风险解除信号", "watch", "signals",
            ),
            "下次复核什么": ("下次复核什么", "下次复核", "review", "next_review"),
        }
        rows: List[str] = []
        for label, keys in aliases.items():
            bodies = [_product_copy(value.get(key)) for key in keys if value.get(key)]
            clean = _clean_step_body("；".join(bodies))
            if clean:
                rows.append(f"{label}：{clean}")
        return rows[:3]
    text = _product_copy(value)
    if not text:
        return []
    text = re.sub(r"\s+", " ", text)
    marker_pattern = (
        r"(?:^|[\s；;*])(?:\d{1,2}[.)、）]\s*)?"
        r"(操作纪律|禁止操作|不做之事|不做什么|不要做|核心观察信号|观察信号|风险升级触发条件|风险缓解触发条件|风险升级信号|风险解除信号|风险降级信号|看什么|数据修复后行动|数据恢复后行动|数据补齐后行动|下次复核什么|下次复核)"
        r"(?:（[^）]*）|\([^)]*\))?\s*[:：]"
    )
    parts = re.split(marker_pattern, text)
    if len(parts) > 1:
        grouped: Dict[str, List[str]] = {
            "不做什么": [],
            "看什么": [],
            "下次复核什么": [],
        }
        for idx in range(1, len(parts), 2):
            marker = (parts[idx] or "").strip()
            body = (parts[idx + 1] if idx + 1 < len(parts) else "").strip(" *；;")
            if not body:
                continue
            if marker in {"操作纪律", "禁止操作", "不做之事", "不做什么", "不要做"}:
                label = "不做什么"
            elif marker in {
                "核心观察信号",
                "观察信号",
                "风险升级触发条件",
                "风险缓解触发条件",
                "风险升级信号",
                "风险解除信号",
                "看什么",
            }:
                label = "看什么"
            else:
                label = "下次复核什么"
            numbered = [
                item.strip(" *；;。")
                for item in re.split(r"(?:^|[；;\n]\s*)\d{1,2}[.)、）]\s*", body)
                if item.strip(" *；;。")
            ]
            if not numbered:
                numbered = [body]
            grouped[label].append(_clean_step_body(_product_copy(numbered[0])))
            for extra in numbered[1:]:
                target = "下次复核什么" if re.search(r"复核|补充|核对|下次", extra) else "看什么"
                grouped[target].append(_clean_step_body(_product_copy(extra)))
        sections = [
            _product_copy(f"{label}：{_clean_step_body('；'.join(_dedupe_nonempty(grouped[label], limit=3)))}")
            for label in ("不做什么", "看什么", "下次复核什么")
            if grouped[label]
        ]
        if sections:
            return _dedupe_nonempty(sections, limit=3)
    parts = re.split(
        r"(?:\n+|\n\s*[-•]\s+|(?:^|[；;]\s*)\d{1,2}[.)、）]\s*)",
        text,
    )
    rows = [part.strip(" -•；;") for part in parts if part and part.strip(" -•；;")]
    return _dedupe_nonempty(rows, limit=3) if rows else [text]


def _reader_next_steps(primary: Any, fallback: Any) -> List[str]:
    grouped: Dict[str, List[str]] = {
        "不做什么": [],
        "看什么": [],
        "下次复核什么": [],
    }
    for row in _split_reader_steps(primary):
        matched = False
        for label in grouped:
            prefix = f"{label}："
            if row.startswith(prefix):
                grouped[label].append(row[len(prefix):])
                matched = True
                break
        if not matched:
            grouped["看什么"].append(row)
    for row in _product_list(fallback, limit=3):
        matched = False
        for label in grouped:
            prefix = f"{label}："
            if row.startswith(prefix):
                if not grouped[label]:
                    grouped[label].append(row[len(prefix):])
                matched = True
                break
        if not matched:
            normalized = re.sub(r"^下次复核(?:什么)?\s*[:：]?\s*", "", row).strip()
            if not grouped["下次复核什么"]:
                grouped["下次复核什么"].append(normalized or row)
    if not grouped["不做什么"]:
        grouped["不做什么"].append("不要把单一标的或单日波动直接外推为全市场结论")
    return [
        _product_copy(f"{label}：{_clean_step_body(grouped[label][0])}")
        for label in ("不做什么", "看什么", "下次复核什么")
        if grouped[label]
    ][:3]


def _first_numbered_item(text: str) -> str:
    parts = [
        part.strip(" ；;。")
        for part in re.split(r"(?:^|\s+)\d{1,2}[.)、）]\s*", str(text or ""))
        if part.strip(" ；;。")
    ]
    return parts[0] if parts else str(text or "").strip()


def _clean_step_body(text: str) -> str:
    value = re.sub(r"[；;]{2,}", "；", str(text or "")).strip(" ；;。")
    value = re.sub(r"(?:^|[；;])\s*(?:待验证情景|情景判断)\s*[:：]\s*", "；", value).strip(" ；;。")
    numbered = [
        part.strip(" ；;。")
        for part in re.split(r"(?:^|[；;\s])\d{1,2}[.)、）]\s*", value)
        if part.strip(" ；;。")
    ]
    if len(numbered) > 1:
        return "；".join(_dedupe_nonempty(numbered, limit=2))
    clauses = [part.strip() for part in value.split("；") if part.strip()]
    return "；".join(_dedupe_nonempty(clauses, limit=3))


def _concise_numbered_step(text: str) -> str:
    value = str(text or "").strip()
    for label in ("不做什么", "看什么", "下次复核什么"):
        prefix = f"{label}："
        if value.startswith(prefix):
            return f"{prefix}{_first_numbered_item(value[len(prefix):])}"
    return _first_numbered_item(value)


def _reader_claims_by_semantic_status(card: Dict[str, Any]) -> tuple[List[str], List[str]]:
    """Keep facts/partial claims ahead of hypotheses in the executive summary."""

    supported: List[str] = []
    hypotheses: List[str] = []
    for row in card.get("claimEvidence") or []:
        if not isinstance(row, dict):
            continue
        claim = _product_copy(row.get("claim") or row.get("text"))
        status = str(row.get("semanticStatus") or row.get("status") or "").lower()
        if not claim:
            continue
        if status in {"supported", "partial"}:
            supported.append(claim)
        elif status in {"hypothesis", "disputed"}:
            hypotheses.append(claim)
    if not supported and not hypotheses:
        supported = _product_list(card.get("keyClaims"), limit=3)
    return _dedupe_nonempty(supported, limit=3), _dedupe_nonempty(hypotheses, limit=3)


def _product_list(value: Any, *, limit: int) -> List[str]:
    if isinstance(value, list):
        raw = value
    elif value:
        raw = [value]
    else:
        raw = []
    return _dedupe_nonempty([_product_copy(item) for item in raw], limit=limit)


def _dedupe_nonempty(items: List[str], *, limit: int) -> List[str]:
    out: List[str] = []
    for item in items:
        text = _product_copy(item)
        if not text or any(_reader_texts_overlap(text, existing) for existing in out):
            continue
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _reader_texts_overlap(left: str, right: str) -> bool:
    """Remove near-duplicate reader bullets without hiding distinct claims."""

    def compact(value: str) -> str:
        value = re.sub(r"^(?:事实|基准解释|解释性判断|竞争情景|当前判断)[:：]", "", value)
        return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", value).lower()

    a, b = compact(left), compact(right)
    if not a or not b:
        return False
    if a == b:
        return True
    if min(len(a), len(b)) >= 18 and (a in b or b in a):
        return True
    if min(len(a), len(b)) < 12:
        return False
    a_grams = {a[index:index + 2] for index in range(len(a) - 1)}
    b_grams = {b[index:index + 2] for index in range(len(b) - 1)}
    if not a_grams or not b_grams:
        return False
    overlap = len(a_grams & b_grams) / min(len(a_grams), len(b_grams))
    return overlap >= 0.82


def _product_value_to_text(value: Any) -> str:
    if isinstance(value, dict):
        parts: List[str] = []
        claim = value.get("claim") or value.get("point")
        basis = value.get("basis") or value.get("reason") or value.get("rationale")
        if claim:
            claim_text = _product_value_to_text(claim)
            basis_text = _product_value_to_text(basis) if basis else ""
            return f"{claim_text}。依据：{basis_text}" if basis_text else claim_text
        value_type = str(value.get("type") or "").strip()
        description = value.get("description") or value.get("summary") or value.get("message") or value.get("reason")
        if value_type and description:
            parts.append(f"{value_type}：{_product_value_to_text(description)}")
        elif description:
            parts.append(_product_value_to_text(description))
        elif value_type:
            parts.append(value_type)

        do_not = value.get("do_not") or value.get("avoid")
        if do_not:
            parts.append(f"不要做：{_product_value_to_text(do_not)}")

        conditions = value.get("conditions")
        if conditions:
            parts.append(f"触发条件：{_product_value_to_text(conditions)}")

        triggers = value.get("triggers")
        if isinstance(triggers, list):
            for trigger in triggers[:3]:
                trigger_text = _product_value_to_text(trigger)
                if trigger_text:
                    parts.append(trigger_text)

        if not parts:
            for key in ("value", "label", "title", "next_action", "next_step"):
                if value.get(key):
                    parts.append(_product_value_to_text(value.get(key)))
                    break
        if not parts:
            parts = [
                f"{key}：{_product_value_to_text(item)}"
                for key, item in value.items()
                if item not in (None, "", [])
            ][:4]
        return "；".join(part for part in parts if part)
    if isinstance(value, list):
        return "；".join(_product_value_to_text(item) for item in value if item not in (None, "", []))
    return str(value or "")


def _product_copy(value: Any) -> str:
    if isinstance(value, str):
        raw = value.strip()
        if raw and raw[0] in "{[" and raw[-1] in "}]":
            try:
                parsed = ast.literal_eval(raw)
            except (SyntaxError, ValueError):
                parsed = None
            if isinstance(parsed, (dict, list)):
                return _product_copy(parsed)
    text = _safe_reader_text(_product_value_to_text(value))
    replacements = {
        "跨市场结构性分化。海外信用环境未见系统性收缩，港美股观察样本相对较强，A股呈现局部获利回吐与主要指数深度调整，暂未演变成系统性流动性危机": "A股主要指数普遍下跌，港美仅有单股样本相对较强。基准情景是局部市场调整；是否向跨市场压力扩散，需用美港主要指数、市场宽度和信用指标变化验证",
        "RedTeamAgent": "红队",
        "RiskAgent": "风险部门",
        "MarketAgent": "市场部门",
        "SectorAgent": "行业部门",
        "TechnicalAgent": "技术部门",
        "FundamentalAgent": "基本面部门",
        "MacroAgent": "宏观部门",
        "GeoPolicyAgent": "地缘政策部门",
        "CIOAgent": "CIO",
        "capital_flow": "资金流",
        "concept_rankings": "概念主题排行",
        "sector_rankings": "行业强弱排行",
        "hot_stocks": "热门标的列表",
        "originalAnalysisRefs": "上游分析材料",
        "portfolio_snapshot": "持仓快照",
        "quantity": "持仓数量",
        "market_value": "持仓市值",
        "cost_basis": "成本价",
        "fundamental_context": "结构化基本面上下文",
        "subject_fundamental_depth_incomplete": "部分标的基本面深度不足",
        "realtime_quote": "实时行情",
        "daily_data": "日线数据",
        "not_supported": "暂未适配",
        "rate_limited": "限流",
        "auth_missing": "缺授权",
        "provider_run": "数据源记录",
        "record_count": "记录数",
        "sourceHealthV2": "数据健康",
        "providerMatrix": "数据源矩阵",
        "claimPolicy": "结论规则",
        "artifactId": "报告编号",
        "Tavily": "第三方搜索线索",
        "RAW_AGENT": "真实分析",
        "DERIVED_FROM_ARTIFACT": "历史材料整理",
        "FULL_REVIEW": "完整复盘",
        "LIMITED_REVIEW": "有限复盘",
        "verified_fact": "已验证事实",
        "verified fact": "已验证事实",
        "derived_fact": "推导事实",
        "discovery": "发现线索",
        "Discovery": "搜索线索",
        "main_indices": "主要指数行情",
        "market_stats": "市场宽度",
        "agent_opinion": "部门判断",
        "final_claim": "最终判断",
        "待验证情景：": "情景判断：",
        "关键数据缺失": "关键待确认项",
        "关键数据缺口": "关键待确认项",
        "关键待确认项修复前": "关键待确认项补齐前",
        "数据修复": "下次复核",
        "数据恢复后": "下次复核后",
        "数据缺口": "待确认项",
        "指数崩塌": "指数大幅下跌",
        "崩塌式下跌": "大幅下跌",
        "暴跌": "大幅下跌",
        "高位科技股在结构性多头踩踏": "高位科技股出现结构性多头踩踏",
        "个股虚涨": "个股上涨持续性存疑",
        "虚假繁荣": "上涨持续性存疑",
        "高危": "高风险",
        "禁止追涨": "不要追涨",
        "禁止基于": "不应仅基于",
        "不能再将": "不宜继续将",
        "法批公告": "法披公告",
        "原系统市场分析层：主要指数行情 ；市场宽度": "已纳入主要指数与市场宽度",
        "第三方搜索线索 网页抓取的媒体传闻": "媒体报道线索",
        "第三方搜索线索 媒体发现线索": "媒体线索",
        "第三方搜索线索 发现线索": "媒体线索",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    if text.startswith("情景判断："):
        text = "情景判断：" + text[len("情景判断："):].replace("情景判断：", "")
    text = re.sub(
        r"\s*[（(][^（）()]{0,240}(?:subject|fred|sec|cninfo|intelligence):[^（）()]{0,240}[）)]",
        "",
        text,
        flags=re.I,
    )
    text = _strip_reader_raw_fields(text)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = text.replace("*", "")
    text = text.replace("`", "")
    text = re.sub(r"\bpartial\b", "部分可用", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(success|failed|empty)\s*\(\d+\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+-\s+", "；", text)
    text = re.sub(r"^\s*[-•]\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -•；;")
    return text


def _reader_cio_headline(value: Any, *, shared_facts: Any = None) -> str:
    """Keep the hero decisive, short and explicitly framed as adjudication."""

    text = _reader_adjudication_judgment(value)
    if not text:
        return "当前基准判断：本轮未生成总判断。"
    sentences = [
        item.strip().rstrip("。！？!?")
        for item in re.split(r"(?<=[。！？!?])", text)
        if item.strip()
    ]
    generic = re.compile(r"^(?:当前)?(?:采纳|维持|沿用)(?:当前)?基准情景$|^基准情景成立$")
    sentences = [item for item in sentences if not generic.fullmatch(item)]

    facts = [
        _reader_institutional_copy(item).rstrip("。！？!?")
        for item in _product_list(shared_facts, limit=2)
        if _reader_institutional_copy(item)
    ]
    selected: List[str] = []
    if facts:
        selected.append(facts[0])
    max_items = 2 if facts else 1
    for sentence in sentences:
        if any(_reader_texts_overlap(sentence, existing) for existing in selected):
            continue
        selected.append(sentence)
        if len(selected) >= max_items:
            break
    if not selected:
        selected = ["本轮未生成总判断"]
    headline = "；".join(selected).rstrip("。！？!?") + "。"
    if headline.startswith(("当前基准判断：", "当前判断：", "今日结论：")):
        return headline
    return f"当前基准判断：{headline}"


def _reader_adjudication_judgment(value: Any) -> str:
    """Render a decision, not an alarmist summary of both sides."""

    text = _reader_institutional_copy(value)
    if not text:
        return ""
    match = re.search(
        r"(?:当前)?裁决偏向基准情景(?:，即)?[“\"]?([^”\"，。；]+)[”\"]?"
        r"，但必须对最强竞争情景[（(]([^）)]+)[）)]保持高度警惕",
        text,
    )
    if match:
        return (
            f"当前基准判断：{match.group(1).strip()}；"
            f"{match.group(2).strip()}仅作为竞争情景，出现翻转信号时再切换判断"
        )
    return text.replace("最强相反情景", "最强竞争情景")


def _reader_institutional_copy(value: Any) -> str:
    """Keep the decision firm while removing unsupported causal or crisis wording."""

    text = _product_copy(value)
    if not text:
        return ""
    text = re.sub(
        r"采纳红队与市场部门的综合裁决：当前市场属于[“\"]结构性分化[”\"]而非[“\"]系统性破位深调[”\"]",
        "综合现有证据，当前更支持结构性分化；是否属于系统性压力仍需市场宽度与流动性确认",
        text,
    )
    text = re.sub(
        r"采纳红队关于[“\"]A股系统性走弱[”\"]及[“\"]防御属性过度乐观偏见[”\"]的警示",
        "当前裁决更重视A股主要指数普遍承压，以及防御板块补跌的竞争风险",
        text,
    )
    text = re.sub(
        r"腾讯控股（HK00700）持续进行股份回购，基本面与资本运作事实支持当前[“\"]持有[”\"]的保守评级，但",
        "腾讯控股（HK00700）的持续回购已由公告确认；结构化财务数据仍有缺口，暂不据此作估值判断。",
        text,
    )
    replacements = {
        "采纳基准情景。": "",
        "当前海外信用利差（2.71%）极低，全球流动性危机证据不足": "美国高收益债利差本轮为2.71%；单一指标不足以确认全球流动性状态",
        "A股虽深调但属于结构性分化，未见跨市场信用踩踏": "A股主要指数普遍下跌；本轮尚缺美港主要指数与市场宽度，不能据单股样本判断跨市场传导",
        "红队提出的“末端抱团补跌”作为最强警示情景，需通过后续引入的市场宽度数据进行证伪": "竞争情景是港美观察样本随后转弱；需用美港主要指数与市场宽度验证",
        "抱团末端效应。美港股整体市场宽度实际已在恶化，AAPL和HK00700的强势仅为资金避险的末端抱团，后续将面临跨市场共振补跌，A股普跌将向权重蓝筹全面传导": "若后续美港主要指数与市场宽度同步转弱，AAPL 和 HK00700 的相对强势可能只是个股效应，届时需警惕跨市场风险扩散",
        "公司回购行动对股价形成机制性抗跌支撑": "公司已披露回购；是否形成价格支撑仍需验证",
        "公司回购行动对股价形成较强的机制性抗跌支撑": "公司已披露回购；是否形成价格支撑仍需验证",
        "受持续回购支撑表现出较强的抗跌韧性": "同期有持续回购披露，股价相对抗跌；二者因果仍待验证",
        "在持续回购支撑下偏强震荡": "同期有持续回购披露，最新价格表现偏强；二者因果仍待验证",
        "持续进行股份回购及申报进行资本管理，对股价形成机制性支撑": "持续披露股份回购；是否形成价格支撑仍需验证",
        "资金向白酒与银行等大盘蓝筹板块靠拢以寻求防御": "白酒与银行观察标的相对抗跌；主动资金流向仍待验证",
        "显示市场资金向传媒与科技应用板块集中": "显示传媒与科技应用板块价格表现较强；主动资金流向仍待验证",
        "个股抱团特征": "个股相对强势特征",
        "对冲A股大盘价值的下行压力": "形成与A股大盘价值不同的风格暴露；是否具有对冲效果需用组合相关性验证",
        "系统性主要指数深度调整": "系统性压力",
        "premarket": "开盘前快照",
        "后市交易": "最新行情快照",
        "A股白酒与银行板块盘前微幅震荡": "A股白酒与银行观察标的上一完整交易日涨跌分化",
        "收益率曲线维持倒挂后的正常化进程": "当前10年期与2年期、3个月期限利差均为正",
        "显示海外衰退预期降温但高利率压制仍在": "是否代表衰退预期变化仍需结合历史序列与利率期货验证",
        "债市已开始对未来降息预期进行修正": "当前期限利率结构已发生变化；对降息预期的解释仍需利率期货与历史变化验证",
        "对全球成长资产的估值扩张仍构成实质性约束": "可能约束全球成长资产估值扩张",
        "全球流动性危机并非当前基准情景": "单一美国信用指标未显示明显压力，但不足以代表全球流动性",
        "今日市场呈现结构性分化与局部获利回吐特征，并非风险偏好收缩": "A股主要指数普遍下跌；港美仅有单股观察样本，暂不能据此判断跨市场风险偏好",
        "不构成对美股市场的系统性信用或流动性冲击": "本轮采集未见其对美股市场形成系统性信用或流动性冲击",
        "对全球及中国主流权益资产（腾讯、贵州茅台、平安银行、苹果）无直接系统性传导": "本轮采集未发现其向观察标的（腾讯、贵州茅台、平安银行、苹果）直接传导的证据",
        "技术结构极强": "本轮价格结构偏强",
        "处于历史区间上沿": "位于本轮可见区间上沿",
        "短期支撑位上移至MA5": "当前MA5为",
        "断崖式下跌": "明显转弱",
        "重挫": "显著下跌",
        "遭遇集中抛售": "跌幅明显扩大",
        "采纳红队关于": "当前判断提高对",
        "采纳风险部门关于": "当前判断提高对",
        "无量破位补跌": "进一步下行",
        "无量破位下行": "进一步下行",
        "无量补跌": "进一步下行",
        "剧烈补跌": "明显补跌",
        "一旦因回购资金消耗完毕": "若回购披露减少且价格结构同步转弱",
        "确立A股权重股补跌趋势": "提高该标的转弱判断；是否扩散至权重板块需另行验证",
        "出现恐慌盘涌出及随后的量能衰竭": "成交量是否放大、跌势是否延续",
        "出现恐慌盘涌出": "成交量是否显著放大",
        "单兵突进": "单股走强",
        "单兵强势": "单股走强",
        "开盘前快照 仅为开盘前快照": "开盘前快照仅表示采集时段",
        "盘前窄幅波动": "上一完整交易日涨跌分化",
        "整体系统性信用与流动性危机尚未触发": "本轮美国信用与波动指标未显示显著压力；能否代表全球仍需更多宏观与市场数据",
        "当前海外信用环境与风险偏好并未出现系统性收缩": "本轮美国信用与波动指标未显示显著压力",
        "显示其股价表现有持续的公司回购行动支撑": "同期有持续回购披露；是否构成价格支撑仍需验证",
        "对股价形成机制性支撑": "是否形成价格支撑仍需验证",
        "本轮观察标的基本面呈现分化：美股科技龙头与A股金融/白酒龙头基本面增长稳健，支持当前“观察”的候选评级": "本轮结构化指标显示 AAPL、平安银行与贵州茅台的营收和净利同比为正；数据期次与估值仍需分别核对",
        "原系统分析中关于贵州茅台“2025年业绩下滑”的假设与当前最新披露的2026年中报增长数据存在背离，需以最新法披事实进行修正": "原系统旧分析与本轮结构化指标口径存在差异；在核对匹配期次的官方财报前，不据此判断趋势反转",
        "基本面增长强劲": "本轮营收与净利同比为正",
        "不构成系统性流动性或信用风险传导": "本轮未见直接的系统性流动性或信用风险传导证据",
        "发现线索 线索": "发现线索",
        "若美股和港股整体市场宽度实际已在恶化": "若后续美股和港股主要指数与市场宽度同步转弱",
        "资金抱团龙头的末端效应": "个股强势的末端效应",
        "跨市场安全岛": "跨市场安全信号",
        "未接入真实持仓，无法评估对真实组合的实际暴露影响，仅能对观察池（Watchlist）进行假设性风格暴露分析": "未接入真实持仓，无法评估组合的实际暴露；以下仅为观察池风格分析",
        "在无持仓数据及未确认A股企稳前，不要盲目对A股大盘蓝筹进行左侧抄底，亦不要将个股强势外推为美港股全市场安全信号": "未接入持仓且A股企稳信号未确认前，不新增A股大盘蓝筹风险暴露；不把单股强势外推为美港股市场结论",
        "不要在A股主要指数（科创50、创业板指）未见企稳信号前盲目对科技成长股进行左侧抄底；不要将腾讯控股（HK00700）的单股走强外推为港股整体风险偏好回升而盲目加仓港股": "A股主要指数企稳前，不新增科技成长风险暴露；不以腾讯控股单股走强作为增加港股风险暴露的依据",
        "不要在A股主要指数（科创50、创业板指）未见企稳信号前盲目对科技成长股进行左侧抄底；不要将腾讯控股（HK00700）的单兵强势外推为港股整体风险偏好回升而盲目加仓港股。": "A股主要指数企稳前，不新增科技成长风险暴露；不以腾讯控股单股走强作为增加港股风险暴露的依据。",
        "是否成交量是否": "成交量是否",
        "以验证是否存在龙头抱团瓦解的补跌风险": "以判断观察样本转弱是否与市场宽度恶化共振",
        "系统性弱势调整阶段": "主要指数普遍承压的调整阶段",
        "系统性走弱": "主要指数普遍承压",
        "A股风险偏好明显收缩": "A股主要指数显示风险偏好收缩",
        "基本面失速": "盈利增速放缓",
        "业绩失速": "盈利增速放缓",
        "业绩下修": "盈利增速放缓",
        "实质性压制": "潜在估值约束",
        "补跌概率更高": "补跌风险更值得关注",
        "主要受持续股份回购支撑": "同期存在持续股份回购",
        "独立基本面驱动": "个股自身走势",
        "整体宏观信用环境依然平稳": "现有宏观证据暂未显示信用压力显著扩张",
        "宏观信用环境依然平稳": "现有宏观信用指标暂未显示压力显著扩张",
        "单日盘前微涨无法对冲": "单日价格表现不足以抵消",
        "长期下行趋势尚未扭转": "中长期趋势尚未完全转强",
        "坚决执行止损": "将观察结论下调为防守并复核风险暴露",
        "则确立短期见顶": "则短线转弱风险上升",
        "对全球系统性宏观流动性未构成即时冲击": "现有宏观与市场证据暂未显示对全球信用和流动性形成即时传导",
        "已纳入主要指数与市场宽度 empty": "已纳入主要指数；市场宽度本轮未返回有效结果",
        "呈现量价齐升的主动流入特征": "呈现量价齐升；是否由主动资金推动仍待资金流验证",
        "红队的解释覆盖了": "当前风险解释覆盖了",
        "A股全市场指数大跌": "A股主要指数下跌",
        "在全市场普跌背景下": "在主要指数普遍承压的背景下",
        "高收益债信用利差维持在2.71%的低位": "高收益债信用利差为2.71%",
        "风险偏好整体平稳": "现有信用指标暂未显示压力显著扩张",
        "观察池标的基本面整体稳健": "观察池标的基本面表现分化",
        "展现出较强的营收与利润增长韧性": "本轮营收与利润同比均为正增长",
        "市场风格向大盘价值及防御性板块抱团": "大盘价值及防御样本相对抗跌；是否存在资金抱团仍待资金流验证",
        "凭借持续回购支撑表现出较强的抗跌韧性": "短期相对走强，同期存在持续回购；二者因果仍待验证",
        "A股大盘呈现普跌深调": "A股主要指数普遍承压",
        "A股大盘深调": "A股主要指数承压",
        "局部去杠杆特征": "局部风险释放特征",
        "大盘整体处于震荡偏弱格局": "当日主要指数整体偏弱",
        "强势创历史新高": "创本轮20日新高",
        "创历史新高": "处于本轮可见区间高位",
        "1200日收益率": "120日收益率",
        "市场宽度略微偏向空头": "市场宽度尚未返回有效数据",
        "市场宽度仍待有效数据确认": "市场宽度尚未返回有效数据",
        "长期下行趋势未改": "中长期趋势尚未完全转强",
        "高位题材补跌": "部分高位题材承压",
        "日线结构极强": "日线结构偏强",
        "趋势可持续": "趋势延续仍待验证",
        "极易形成": "可能形成",
        "防御表现难以持续": "防御表现能否持续仍待验证",
        "长期下行趋势并未扭转": "中长期趋势是否扭转仍待验证",
        "历史区间偏下沿": "本轮观察区间偏下沿",
        "市场整体呈现结构性分化": "本轮行业排行样本呈现结构性分化",
        "全球信用环境与现有信用指标暂未显示压力显著扩张": "美国信用与波动指标暂未显示压力显著扩张",
        "宏观层面暂未见系统性流动性收缩": "现有美国宏观指标暂未显示系统性流动性收缩",
        "对主流权益市场（如 AAPL、HK00700、600519）无直接基本面传导": "现有证据未显示对观察标的（AAPL、HK00700、600519）的直接基本面传导",
        "修复资金流数据接口": "补充资金流数据",
        "概念主题排行 和 热门标的列表 本轮未返回有效结果": "概念主题与热门标的本轮未返回有效结果",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = re.sub(
        r"(?:回购|分红|权益分派)[^。；]{0,36}(?:形成|提供)(?:较强的?)?机制性(?:抗跌)?支撑",
        "相关公司行动已披露；是否形成价格支撑仍需验证",
        text,
    )
    text = re.sub(
        r"(?:20日)?区间位置百分比[（(]range_position_pct[）)](?:仅)?为?\s*(-?\d+(?:\.\d+)?)%?",
        lambda match: f"位于本轮20日价格区间约{match.group(1)}%位置",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"range_position_pct\s*(?:达|为|=)\s*(-?\d+(?:\.\d+)?)%?",
        lambda match: f"位于本轮价格区间约{match.group(1)}%位置",
        text,
        flags=re.I,
    )
    text = text.replace("若后续证据支持这一情景：若", "若")
    text = text.replace("及市场宽度尚未返回有效数据", "，并补充市场宽度数据")
    text = re.sub(
        r"跨市场表现中，美股观察标的显著强于港股及A股",
        "本轮观察标的中，AAPL 当日表现相对较强",
        text,
    )
    text = re.sub(r"美港股(?:观察标的)?(?:强势|走强|占优|韧性|强)", "港美股观察样本相对较强", text)
    text = re.sub(
        r"并未污染A股与港股的整体弱势震荡结论",
        "该单股表现不用于代表美股或港股整体",
        text,
    )
    text = re.sub(r"range_position_pct\s*(?:达|为|=)\s*100%?", "位于本轮价格区间上沿", text, flags=re.I)
    text = re.sub(
        r"range_position_pct\s*(?:达|为|=)\s*(-?\d+(?:\.\d+)?)%?",
        lambda match: f"位于本轮价格区间约{match.group(1)}%位置",
        text,
        flags=re.I,
    )
    text = text.replace("20日成交量比（volume_vs_avg20）", "20日成交量比")
    text = text.replace("（volume_vs_avg20）", "")
    text = re.sub(r"volume_vs_avg20\s*=\s*(-?\d+(?:\.\d+)?)", r"20日量比 \1", text, flags=re.I)
    text = re.sub(r"high20\s*=\s*(-?\d+(?:\.\d+)?)", r"20日高点 \1", text, flags=re.I)
    text = re.sub(r"，盘后继续微涨\s*-?\d+(?:\.\d+)?%[^，。；]*", "", text)
    text = text.replace("及市场宽度仍待有效数据确认", "，并补充市场宽度数据")
    text = re.sub(
        r"-?\d+\.\d{3,}(?=%)",
        lambda match: f"{float(match.group(0)):.2f}",
        text,
    )
    return text


def _dedupe_reader_sentences(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    sentences = [item.strip() for item in re.split(r"(?<=[。！？!?])", text) if item.strip()]
    out: List[str] = []
    for sentence in sentences:
        if any(_reader_texts_overlap(sentence, existing) for existing in out):
            continue
        out.append(sentence)
    return "".join(out)


def _strip_reader_raw_fields(text: str) -> str:
    value = str(text or "")
    claim_match = re.search(r"(?:^|[；;]\s*)(?:claim|point|主张|观点)[:：]\s*(.*?)(?=[；;]\s*(?:basis|依据|evidence_ids|证据|$)|$)", value, flags=re.I)
    basis_match = re.search(r"(?:^|[；;]\s*)(?:basis|依据)[:：]\s*(.*?)(?=[；;]\s*(?:evidence_ids|证据|$)|$)", value, flags=re.I)
    if claim_match:
        claim = claim_match.group(1).strip(" ；;")
        basis = basis_match.group(1).strip(" ；;") if basis_match else ""
        value = f"{claim}。依据：{basis}" if basis else claim
    value = re.sub(r"(?:^|[；;]\s*)(?:evidence_ids|证据\s*id|证据ID|source_refs)[:：]\s*[^。]*", "", value, flags=re.I)
    value = re.sub(r"\b(?:memo|subject|tavily|fred|sec|cninfo|official|cio):[^\s，。；;、]+", "", value, flags=re.I)
    value = re.sub(r"\bproviderSummary\b|\boriginalAnalysisSummary\b", "", value)
    value = re.sub(r"\s*\[\s*(?:kind|source|provider)\s*:[^\]]*\]", "", value, flags=re.I)
    value = re.sub(r"\s*\[\s*$", "", value)
    value = re.sub(r"\s*；\s*；+", "；", value)
    value = re.sub(r"([\u4e00-\u9fffA-Za-z]+)[(（]\1[)）]", r"\1", value)
    value = value.replace("。。依据", "。依据")
    value = value.replace("。。", "。")
    value = value.replace("。；", "；")
    value = re.sub(r"\s+", " ", value)
    return value.strip(" ；;。")


def _reader_v2_department_card(row: Dict[str, Any], department_inputs: List[Dict[str, Any]], evidence_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    agent = str(row.get("agent") or "")
    profile = next((item for item in department_inputs if item.get("agent") == agent), {})
    claim_evidence_ids = _collect_evidence_refs(row.get("claimEvidence"))
    if not claim_evidence_ids:
        claim_evidence_ids = _collect_evidence_refs(row.get("semanticValidation"))
    evidence_ids = list(dict.fromkeys([
        *claim_evidence_ids,
        *[str(item) for item in row.get("evidenceIds") or [] if str(item)],
    ]))
    samples = _evidence_samples(evidence_items, evidence_ids, limit=3)
    support_signals = [
        signal
        for ref in profile.get("originalAnalysisRefs") or []
        if isinstance(ref, dict)
        for signal in [_reader_support_signal(ref)]
        if signal
    ][:4]
    return {
        "agent": agent,
        "label": _safe_reader_text(row.get("label") or agent),
        "conclusion": _safe_reader_text(row.get("summaryForReader") or "本部门未给出可读结论。"),
        "keyClaims": [_safe_reader_text(item) for item in (row.get("keyClaims") or [])[:5]],
        "counterpoints": [_safe_reader_text(item) for item in (row.get("counterpoints") or [])[:4]],
        "dataGaps": [_reader_gap_text(item) for item in (row.get("dataGaps") or [])[:4] if _reader_gap_text(item)],
        "nextAction": _safe_reader_text(row.get("nextAction") or ""),
        "confidence": row.get("confidence") or "medium",
        "supportSignals": support_signals,
        "evidenceIds": evidence_ids[:8],
        "evidenceSamples": samples,
    }


def _reader_support_signal(ref: Dict[str, Any]) -> str:
    kind = str(ref.get("kind") or "")
    summary = str(ref.get("summary") or "")
    symbols = [str(item) for item in ref.get("symbols") or [] if str(item)]
    symbol_text = "、".join(symbols[:4])
    if kind == "market_review":
        return "已纳入主要指数与市场统计，用于判断大盘结构。"
    if kind == "screening":
        if "concept_rankings empty" in summary:
            return "已纳入行业排行和热股候选；概念主题本轮无结果，只作限制。"
        return "已纳入行业排行、概念排行和热股候选。"
    if kind == "technical_context":
        return f"{symbol_text or '重点标的'} 已纳入行情与 K 线结构。"
    if kind == "fundamental_context":
        match = re.search(r"公告/法披\s*(\d+)\s*条", summary)
        count = match.group(1) if match else ""
        if count and count != "0":
            return f"{symbol_text or '重点标的'} 已纳入 {count} 条公告/法披证据。"
        return f"{symbol_text or '重点标的'} 结构化基本面已纳入；公告/法披仍需补强。"
    if kind == "stock_analysis_context":
        return f"{symbol_text or '重点标的'} 已纳入原系统个股行情、K 线和基本面上下文。"
    if kind == "portfolio_snapshot":
        return "已纳入持仓/自选股快照；真实持仓为空时只判断观察池。"
    if kind == "watchlist_snapshot":
        return f"已纳入自选观察池：{symbol_text}。"
    if kind == "geo_policy_seed":
        return "已纳入利率、能源、信用风险和新闻线索，用于地缘政策传导判断。"
    if kind == "decision_signals":
        return "原系统结构化决策信号本轮为空；不作为默认结论来源。"
    if kind == "history_summary":
        return "已纳入本轮标的范围内的历史报告约束。"
    return _safe_reader_text(summary or kind)


def _reader_gap_text(value: Any) -> str:
    text = _product_copy(value)
    if not text:
        return ""
    if _is_no_gap_text(text):
        return ""
    replacements = {
        "capital_flow": "资金流",
        "concept_rankings": "概念主题排行",
        "fundamental_context": "结构化基本面上下文",
        "subject_fundamental_depth_incomplete": "部分标的基本面深度不足",
        "provider_run": "数据源记录",
        "record_count": "记录数",
        "not_supported": "暂未适配",
        "rate_limited": "限流",
        "auth_missing": "缺授权",
        "关键数据缺口": "关键待确认项",
        "数据缺口": "待确认项",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"\b(success|failed|empty)\s*\(\d+\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" ；;。")
    return text


def _is_no_gap_text(value: str) -> bool:
    normalized = re.sub(r"[\s。.!！；;，,、]+", "", str(value or "")).lower()
    return normalized in {
        "无",
        "暂无",
        "没有",
        "无缺口",
        "无数据缺口",
        "无关键缺口",
        "无关键数据缺口",
        "无待确认项",
        "none",
        "n/a",
        "na",
    }


def _reader_v2_support_drawers(cards: List[Dict[str, Any]], original_refs: List[Dict[str, Any]], evidence_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for card in cards:
        evidence_ids = [str(item) for item in card.get("evidenceIds") or [] if str(item)]
        agent = str(card.get("agent") or "")
        used_refs = [
            _safe_reader_text(str(ref.get("summary") or ref.get("kind") or ""))
            for ref in original_refs
            if isinstance(ref, dict) and agent in [str(item) for item in ref.get("agentTargets") or []]
        ][:6]
        out.append({
            "agent": agent,
            "title": f"{card.get('label') or agent}支撑",
            "originalAnalysis": used_refs,
            "evidence": _evidence_samples(evidence_items, evidence_ids, limit=6),
        })
    return out


def _evidence_samples(evidence_items: List[Dict[str, Any]], evidence_ids: List[str], *, limit: int) -> List[Dict[str, Any]]:
    by_id = {str(item.get("id") or ""): item for item in evidence_items if isinstance(item, dict)}
    out: List[Dict[str, Any]] = []
    for evidence_id in evidence_ids:
        item = by_id.get(evidence_id)
        if not item:
            continue
        out.append({
            "id": item.get("id"),
            "label": _safe_reader_text(item.get("value") or item.get("id") or ""),
            "provider": item.get("provider") or "",
            "factType": item.get("factType") or "",
            "metric": item.get("metric") or "",
            "measurements": item.get("measurements") if isinstance(item.get("measurements"), dict) else {},
            "sourceUrl": item.get("sourceUrl") or "",
            "asOf": item.get("asOf") or item.get("publishedAt") or item.get("eventTime") or "",
        })
        if len(out) >= limit:
            break
    return out


def _clean_reader_v2_sections(sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cleaned: List[Dict[str, Any]] = []
    for section in sections:
        row = dict(section)
        row["body"] = _safe_reader_text(row.get("body") or "")
        row["bullets"] = [_safe_reader_text(item) for item in row.get("bullets") or [] if str(item).strip()]
        cleaned.append(row)
    return cleaned


_DEPARTMENT_LABELS = {
    "MacroAgent": "宏观部门",
    "MacroGeopoliticsAgent": "宏观部门",
    "GeoPolicyAgent": "地缘政策部门",
    "MarketAgent": "市场部门",
    "MarketStrategyAgent": "市场策略部门",
    "SectorAgent": "行业/风格部门",
    "CandidateReviewAgent": "候选池部门",
    "TechnicalAgent": "技术面部门",
    "IntelAgent": "新闻情报部门",
    "IntelCatalystAgent": "新闻情报部门",
    "SourceReviewAgent": "数据源复核",
    "FundamentalAgent": "基本面部门",
    "FundamentalReportsAgent": "基本面部门",
    "PortfolioReviewAgent": "持仓复核部门",
    "PortfolioAgent": "持仓复核部门",
    "RiskPositionAgent": "风险部门",
    "RiskAgent": "风险部门",
    "RedBlueAgent": "红队反证",
    "RedTeamAgent": "红队反证",
    "EvidenceGate": "证据门控",
    "ScoringAgent": "评分部门",
    "TradeDecisionGate": "CIO 门控",
    "DecisionReportAgent": "CIO 报告",
    "CIOAgent": "CIO 报告",
}

_READER_VISIBLE_AGENTS = {
    "MacroAgent",
    "MacroGeopoliticsAgent",
    "GeoPolicyAgent",
    "MarketAgent",
    "MarketStrategyAgent",
    "SectorAgent",
    "CandidateReviewAgent",
    "FundamentalAgent",
    "FundamentalReportsAgent",
    "TechnicalAgent",
    "IntelAgent",
    "IntelCatalystAgent",
    "PortfolioAgent",
    "PortfolioReviewAgent",
    "RiskAgent",
    "RiskPositionAgent",
    "RedBlueAgent",
    "RedTeamAgent",
    "DecisionReportAgent",
    "CIOAgent",
}

_DEPARTMENT_ORDER = {
    "DecisionReportAgent": 0,
    "CIOAgent": 0,
    "RedBlueAgent": 10,
    "RiskAgent": 20,
    "RiskPositionAgent": 20,
    "TechnicalAgent": 30,
    "IntelAgent": 40,
    "IntelCatalystAgent": 40,
    "FundamentalAgent": 50,
    "FundamentalReportsAgent": 50,
    "MacroAgent": 60,
    "MacroGeopoliticsAgent": 60,
    "GeoPolicyAgent": 65,
    "MarketStrategyAgent": 70,
    "MarketAgent": 70,
    "SectorAgent": 75,
    "CandidateReviewAgent": 80,
    "PortfolioAgent": 90,
    "PortfolioReviewAgent": 90,
}


def _department_reports(docs_dir: Path, run_date: str) -> List[Dict[str, Any]]:
    base = docs_dir / "agent_memos" / run_date
    if not base.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for path in sorted(base.rglob("*.json")):
        memo = _read_json(path)
        if not isinstance(memo, dict) or memo.get("schema") != "agent_memo_v1":
            continue
        agent = str(memo.get("agent") or "Agent")
        summary = _localized_department_summary(
            agent,
            _first_text(memo.get("summary_for_reader"), memo.get("readable_summary"), memo.get("conclusion"), default="本部门未给出可读结论。"),
        )
        claims = [str(item) for item in (memo.get("key_claims") or memo.get("facts") or []) if str(item)]
        evidence_ids = [str(item) for item in (memo.get("evidence_ids") or memo.get("source_refs") or []) if str(item)]
        counterpoints = [str(item) for item in (memo.get("counterpoints") or memo.get("missing_data") or []) if str(item)]
        data_gaps = memo.get("data_gaps") if "data_gaps" in memo else memo.get("missing_data") or []
        rows.append({
            "agent": agent,
            "label": _DEPARTMENT_LABELS.get(agent, agent.replace("Agent", "")),
            "subject": memo.get("subject") or memo.get("symbol") or memo.get("scope") or "",
            "origin": memo.get("origin") or "DERIVED_FROM_ARTIFACT",
            "agentRuntime": memo.get("agentRuntime") or memo.get("agent_runtime") or "unknown",
            "runtimeKind": memo.get("runtime_kind") or memo.get("runtimeKind") or "",
            "llmStatus": memo.get("llm_status") or "",
            "readerVisible": agent in _READER_VISIBLE_AGENTS,
            "summaryForReader": _safe_reader_text(summary),
            "keyClaims": [_safe_reader_text(item) for item in claims[:5]],
            "evidenceIds": evidence_ids[:8],
            "counterpoints": [_safe_reader_text(item) for item in counterpoints[:5]],
            "dataGaps": [str(item) for item in data_gaps if str(item)][:5],
            "confidence": memo.get("confidence") or "medium",
            "nextAction": _safe_reader_text(memo.get("next_action") or memo.get("next_step") or ""),
            "claimEvidence": [dict(item) for item in memo.get("claim_evidence") or [] if isinstance(item, dict)],
            "semanticValidation": dict(memo.get("semantic_validation") or {}) if isinstance(memo.get("semantic_validation"), dict) else {},
            "semanticWarnings": [str(item) for item in memo.get("semantic_warnings") or [] if str(item)][:8],
            "challenges": [dict(item) for item in memo.get("challenges") or [] if isinstance(item, dict)][:5],
            "adjudication": dict(memo.get("adjudication") or {}) if isinstance(memo.get("adjudication"), dict) else {},
        })
    return sorted(rows, key=lambda row: (_DEPARTMENT_ORDER.get(str(row.get("agent")), 999), str(row.get("agent") or "")))


def _reader_department_reports(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [row for row in rows if row.get("readerVisible") is not False]


def _apply_daily_reader_scope(rows: List[Dict[str, Any]], universe: Dict[str, Any]) -> None:
    if not isinstance(universe, dict):
        return
    subject_count = len(universe.get("subjectSymbols") or [])
    mode = str(universe.get("mode") or "")
    if mode != "market_and_candidates" and subject_count <= 1:
        return
    for row in rows:
        if not _is_daily_scope_department(row):
            row["readerVisible"] = False
            row["readerScope"] = "stock_drilldown"


def _daily_scope_department_reports(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [row for row in rows if _is_daily_scope_department(row)]


def _is_daily_scope_department(row: Dict[str, Any]) -> bool:
    subject = str(row.get("subject") or "").strip().lower()
    return subject in {"", "daily", "market", "portfolio"}


def _daily_final_text(rows: List[Dict[str, Any]], fallback: str) -> str:
    parts: List[str] = []
    for agents in [
        {"CIOAgent", "DecisionReportAgent"},
        {"MarketAgent", "MarketStrategyAgent"},
        {"SectorAgent"},
        {"MacroAgent", "MacroGeopoliticsAgent"},
        {"GeoPolicyAgent"},
        {"RiskAgent", "RiskPositionAgent"},
        {"RedTeamAgent", "RedBlueAgent"},
        {"PortfolioAgent", "PortfolioReviewAgent"},
    ]:
        row = _first_department(rows, agents)
        if row and row.get("summaryForReader"):
            parts.append(str(row.get("summaryForReader")))
    return "；".join(parts[:3]) if parts else fallback


def _legacy_daily_final_text(rows: List[Dict[str, Any]], fallback: str) -> str:
    parts: List[str] = []
    for agents in [
        {"MarketStrategyAgent"},
        {"CandidateReviewAgent"},
        {"MacroGeopoliticsAgent"},
        {"PortfolioReviewAgent"},
    ]:
        row = _first_department(rows, agents)
        if row and row.get("summaryForReader"):
            parts.append(str(row.get("summaryForReader")))
    return "；".join(parts[:3]) if parts else fallback


def _localized_department_summary(agent: str, summary: str) -> str:
    text = str(summary or "")
    if agent == "TechnicalAgent" and "bearish MA alignment" in text:
        return "技术面偏弱：均线空头排列，MACD 指向下行；今日虽反弹但量能不足，暂不追涨。"
    return text


def _build_reader_brief(
    *,
    run_date: str,
    mode: str,
    headline: str,
    governed_lines: List[str],
    candidate_lines: List[str],
    source_health_v2: Dict[str, Any],
    evidence_stats: Dict[str, Any],
    decision: Dict[str, Any],
    department_reports: List[Dict[str, Any]],
    universe: Dict[str, Any],
) -> Dict[str, Any]:
    action = str(decision.get("action") or "watch")
    blocked = decision.get("gateStatus") == "blocked" or action == "no_action"
    subject_count = len(universe.get("subjectSymbols") or []) if isinstance(universe, dict) else 0
    universe_mode = str(universe.get("mode") or "") if isinstance(universe, dict) else ""
    if universe_mode == "market_and_candidates":
        one_line = "今日结论：自选股为空，先做市场观察和候选跟踪。"
    elif subject_count > 1:
        one_line = f"今日结论：覆盖 {subject_count} 个观察标的，先看市场/行业，再看重点个股。"
    elif blocked:
        one_line = "今日结论：暂不行动，等待证据补齐和风险复核。"
    elif mode == "FULL_REVIEW":
        one_line = "今日结论：证据链可读，可进入人工交易前复核。"
    else:
        one_line = "今日结论：有限复盘，以观察和候选跟踪为主。"

    is_multi_scope_daily = universe_mode == "market_and_candidates" or subject_count > 1
    visible_departments = _reader_department_reports(department_reports)
    daily_departments = _daily_scope_department_reports(visible_departments) if is_multi_scope_daily else visible_departments
    cio_report = _first_department(daily_departments, {"DecisionReportAgent", "CIOAgent"})
    final_text = (
        str(cio_report.get("summaryForReader") or "")
        if cio_report
        else _daily_final_text(daily_departments, one_line)
        if is_multi_scope_daily
        else ("；".join(line.lstrip("- ") for line in governed_lines) if governed_lines else one_line)
    )

    why: List[str] = []
    universe_summary = _universe_summary_line(universe)
    if universe_summary:
        why.append(universe_summary)
    for agents in [
        {"CIOAgent", "DecisionReportAgent"},
        {"MacroAgent", "MacroGeopoliticsAgent"},
        {"GeoPolicyAgent"},
        {"MarketAgent", "MarketStrategyAgent"},
        {"SectorAgent"},
        {"FundamentalAgent", "FundamentalReportsAgent"},
        {"TechnicalAgent"},
        {"IntelAgent", "IntelCatalystAgent"},
        {"RiskAgent", "RiskPositionAgent"},
        {"RedTeamAgent", "RedBlueAgent"},
    ]:
        row = _first_department(daily_departments, agents)
        if row and row.get("summaryForReader"):
            why.append(str(row.get("summaryForReader")))
    if not why and headline:
        why.append(str(headline))
    if not why:
        why.append("本轮缺少足够分部门结论，只能保留观察。")

    risks: List[str] = []
    risk_report = _first_department(daily_departments, {"RiskAgent", "RiskPositionAgent", "RedTeamAgent", "RedBlueAgent"})
    if risk_report and risk_report.get("summaryForReader"):
        risks.append(str(risk_report.get("summaryForReader")))
    for reason in source_health_v2.get("blockingReasons") or []:
        risks.append(_human_blocking_reason(str(reason)))
    if evidence_stats.get("missingCriticalFacts"):
        risks.append(f"关键证据缺口：{evidence_stats.get('missingCriticalFacts')}")
    for row in daily_departments:
        risks.extend(_human_blocking_reason(str(item)) for item in row.get("counterpoints") or [] if str(item))
        if len(risks) >= 5:
            break

    watchlist = [_safe_reader_text(str(item).lstrip("- ")) for item in candidate_lines[:5]]
    data_confidence = _reader_data_confidence(source_health_v2, evidence_stats)
    next_steps = [
        "先看 CIO 结论和分部门摘要，不直接按单一信号行动。",
        "候选清单只做观察，等待证据和价格条件共振。",
        "日报先判断市场和行业，再下钻重点个股；不要让单一股票覆盖全局结论。",
        "只把搜索/新闻当线索，关键事实回跳公告、SEC、交易所或公司 IR。",
    ]
    if cio_report and cio_report.get("nextAction"):
        next_steps.insert(0, str(cio_report.get("nextAction")))

    universe_payload = {
        "mode": universe_mode,
        "subjectCount": subject_count,
        "subjects": [str(item) for item in (universe.get("subjectSymbols") or [])[:12]] if isinstance(universe, dict) else [],
    }

    return {
        "schema": "reader_brief_v1",
        "runDate": run_date,
        "mode": mode,
        "oneLine": _safe_reader_text(one_line),
        "analysis": _safe_reader_text(final_text),
        "finalConclusion": _safe_reader_text(final_text),
        "why": [_safe_reader_text(item) for item in list(dict.fromkeys(why))[:6]],
        "risks": [_safe_reader_text(item) for item in list(dict.fromkeys(risks))[:6]],
        "watchlist": watchlist,
        "universe": universe_payload,
        "dataConfidence": data_confidence,
        "nextSteps": [_safe_reader_text(item) for item in list(dict.fromkeys(next_steps))[:6]],
    }


def _universe_summary_line(universe: Dict[str, Any]) -> str:
    if not isinstance(universe, dict):
        return ""
    groups = universe.get("groups") if isinstance(universe.get("groups"), list) else []
    parts: List[str] = []
    for name in ("watchlist", "portfolio", "candidates", "market", "macro"):
        row = next((item for item in groups if isinstance(item, dict) and item.get("name") == name), None)
        if not row:
            continue
        if name == "market":
            parts.append("市场已纳入")
            continue
        if name == "macro":
            parts.append("宏观已纳入")
            continue
        symbols = row.get("symbols") if isinstance(row.get("symbols"), list) else []
        parts.append(f"{_universe_group_label(name)} {len(symbols)}")
    return "日报范围：" + "；".join(parts) if parts else ""


def _universe_group_label(name: str) -> str:
    return {
        "watchlist": "自选股",
        "portfolio": "持仓",
        "candidates": "候选",
        "market": "市场",
        "macro": "宏观",
    }.get(name, name)


def _first_department(rows: List[Dict[str, Any]], agents: set[str]) -> Dict[str, Any] | None:
    for row in rows:
        if str(row.get("agent") or "") in agents:
            return row
    return None


def _human_blocking_reason(reason: str) -> str:
    text = str(reason or "")
    if text.endswith(":agent_reported_data_gap"):
        domain = text.split(":", 1)[0]
        labels = {
            "price": "行情、资金流或市场宽度仍有缺口。",
            "fundamentals": "基本面证据仍有缺口。",
            "filings_events": "公告/事件证据仍有缺口。",
            "macro": "宏观证据仍有缺口。",
            "news_sentiment": "新闻/舆情线索仍需补强。",
            "portfolio": "持仓/组合数据仍有缺口。",
        }
        return labels.get(domain, "部门复核指出关键数据仍有缺口。")
    if text == "governance:no_completed_governed_report":
        return "本轮没有完成可行动个股深评。"
    mapping = {
        "fundamentals:subject_coverage_incomplete": "部分观察标的仍缺少结构化基本面，相关个股结论需谨慎。",
        "fundamentals:subject_fundamental_depth_incomplete": "部分观察标的只有浅层估值，缺少财务质量和增长数据；相关个股结论需谨慎。",
        "price:subject_coverage_incomplete": "部分观察标的仍缺少行情/K线，相关个股结论需谨慎。",
        "publish_bundle:not_observed": "报告发布包尚未完成最终校验。",
        "fundamentals:failed": "基本面证据不足：当前标的没有拿到可追源财务事实。",
        "fundamentals:missing": "基本面证据不足：当前标的缺少财务事实。",
        "price:missing": "行情证据不足：当前标的价格/K线未形成可用快照。",
        "macro:degraded": "宏观数据降级：宏观只能作为背景参考。",
        "news_sentiment:search_only_discovery": "新闻只属于发现线索，不能直接当事实。",
        "search_provider": "搜索源结果只作线索，需要回跳权威来源。",
        "official_announcements": "公告/交易所原文仍需补强。",
        "a_share_quote": "A 股行情快照需继续核对。",
        "a_share_quote_fallback": "A 股行情走了备用源，需要人工复核。",
        "no_auto_governed_candidates": "没有自动进入深评的候选，先观察。",
        "financial_statement_refs": "财报原文引用不足。",
        "valuation_peer_refs": "同业估值引用不足。",
    }
    return _safe_reader_text(mapping.get(text, text))


def _reader_data_confidence(source_health_v2: Dict[str, Any], evidence_stats: Dict[str, Any]) -> str:
    mode = str(source_health_v2.get("overallMode") or "OBSERVE_ONLY")
    score = source_health_v2.get("overallScore")
    try:
        score_value = float(score)
    except Exception:
        score_value = 0.0
    missing = evidence_stats.get("missingCriticalFacts") or 0
    if mode == "FULL_REVIEW" and score_value >= 0.85 and not missing:
        return "核心证据链完整；数据可信度高，结论仍需人工复核。"
    if score_value >= 0.55:
        return "数据可信度中等；可读结论，但必须看限制。"
    return "数据可信度低；本轮主要用于诊断和观察。"


def _align_legacy_source_health(
    source_health: Dict[str, Any],
    source_health_v2: Dict[str, Any],
) -> Dict[str, Any]:
    """Keep legacy flags consistent with the canonical v2 claim policy."""

    policy = source_health_v2.get("claimPolicy") if isinstance(source_health_v2.get("claimPolicy"), dict) else {}
    mode = str(source_health_v2.get("overallMode") or "OBSERVE_ONLY").upper()
    out = dict(source_health)
    out["canScore"] = bool(policy.get("canScore"))
    out["canTradeReview"] = bool(policy.get("canActionableAdvice"))
    if mode == "FULL_REVIEW":
        out["decisionImpact"] = "核心研究维度可用；仍需人工决策，不自动交易。"
    elif mode == "LIMITED_REVIEW":
        out["decisionImpact"] = "可形成有限复盘；细分结论需结合待确认项。"
    elif mode == "SCREEN_ONLY":
        out["decisionImpact"] = "仅用于候选筛选和异动观察。"
    elif mode == "OBSERVE_ONLY":
        out["decisionImpact"] = "仅用于市场观察，不支持完整评分。"
    else:
        out["decisionImpact"] = "数据不足，本轮只输出诊断。"
    return out


def _daily_source_health(health: Dict[str, Any]) -> Dict[str, Any]:
    status = _first_text(health.get("usability_verdict"), health.get("macro_status"), default="unknown")
    trade = _first_text(health.get("trade_review_usability"), default="unknown")
    normalized = f"{status} {trade}".lower()
    limited = any(token in normalized for token in ("degraded", "partial", "limited", "unknown"))
    failed = any(token in normalized for token in ("failed", "unavailable", "blocked"))
    rows = health.get("rows") if isinstance(health.get("rows"), list) else []
    available_rows = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_status = str(row.get("status") or "").upper()
        if row_status in {"AVAILABLE", "OK", "REFRESHED"}:
            available_rows += 1
    coverage = round(available_rows / len(rows), 4) if rows else None
    return {
        "status": status,
        "verdict": trade,
        "canScore": not failed,
        "canTradeReview": not limited and not failed,
        "coverageScore": coverage,
        "freshnessStatus": _first_text(health.get("freshness_status"), default="未提供"),
        "fallbackUsed": _first_text(health.get("fallback_used"), default="未提供"),
        "failureReason": _first_text(health.get("failure_reason"), default="未提供"),
        "decisionImpact": "数据源降级，可观察，不可作为满血交易依据" if limited or failed else "数据源可用于常规审查",
        "rows": rows,
    }


def _daily_completeness(missing_files: List[str], source_health: Dict[str, Any], source_health_v2: Dict[str, Any]) -> str:
    mode = str(source_health_v2.get("overallMode") or "").upper()
    if missing_files:
        return "partial"
    if mode != "FULL_REVIEW":
        return "partial"
    return "complete"


def _load_daily_source_health_v2_snapshot(docs_dir: Path, run_date: str) -> Dict[str, Any]:
    payload = _read_json(docs_dir / "run_status" / run_date / "source_health_v2.json")
    return dict(payload) if isinstance(payload, dict) and payload.get("schema") == "source_health_v2" else {}


def _load_daily_provider_runs(docs_dir: Path, run_date: str) -> List[Dict[str, Any]]:
    candidates = [
        docs_dir / "run_status" / run_date / "provider_runs.jsonl",
        docs_dir / "run_status" / "provider_runs.jsonl",
        docs_dir / "reports" / run_date / "provider_runs.jsonl",
        docs_dir / "reports" / "provider_runs.jsonl",
        docs_dir / "provider_runs.jsonl",
    ]
    rows: List[Dict[str, Any]] = []
    for path in candidates:
        rows.extend(load_provider_ledger(path))
    return rows


def _load_daily_evidence_facts(docs_dir: Path, run_date: str, health: Dict[str, Any], source_health: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates = [
        docs_dir / "run_status" / run_date / "evidence_ledger.jsonl",
        docs_dir / "run_status" / "evidence_ledger.jsonl",
        docs_dir / "reports" / run_date / "evidence_ledger.jsonl",
        docs_dir / "reports" / "evidence_ledger.jsonl",
        docs_dir / "evidence_ledger.jsonl",
    ]
    facts: List[Dict[str, Any]] = []
    for path in candidates:
        facts.extend(load_evidence_ledger(path))
    facts.extend(_daily_evidence_facts(health, source_health))
    return facts


def _daily_evidence_facts(health: Dict[str, Any], source_health: Dict[str, Any]) -> List[Dict[str, Any]]:
    facts: List[Dict[str, Any]] = []
    rows = health.get("rows") if isinstance(health.get("rows"), list) else []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        domain = _source_health_row_domain(row)
        status = str(row.get("status") or row.get("usability") or "").lower()
        evidence_refs = row.get("evidence_refs") if isinstance(row.get("evidence_refs"), list) else []
        if evidence_refs:
            facts.append({
                "id": f"derived:source_health:{idx}",
                "domain": domain,
                "fact_type": "derived_fact",
                "provider": row.get("source") or "source_health_v1",
                "confidence": "medium",
            })
        elif any(token in status for token in ("unavailable", "failed", "missing")):
            facts.append({
                "id": f"missing:source_health:{idx}",
                "domain": domain,
                "fact_type": "missing",
                "provider": row.get("source") or "source_health_v1",
                "confidence": "low",
            })
    text = f"{source_health.get('status', '')} {source_health.get('verdict', '')}".lower()
    if any(token in text for token in ("degraded", "limited", "unknown")) and not facts:
        facts.append({
            "id": "missing:source_health:limited",
            "domain": "macro",
            "fact_type": "missing",
            "provider": "source_health_v1",
            "confidence": "low",
        })
    return facts


def _evidence_items(
    facts: List[Dict[str, Any]],
    *,
    preferred_ids: Optional[List[str]] = None,
    limit: int = 80,
) -> List[Dict[str, Any]]:
    priority = {"verified_fact": 0, "discovery": 1, "derived_fact": 2, "missing": 3}
    preferred_rank = {
        evidence_id: index
        for index, evidence_id in enumerate(dict.fromkeys(preferred_ids or []))
    }
    normalized = [normalize_evidence_fact(fact) for fact in facts]
    normalized.sort(
        key=lambda item: (
            0 if str(item.get("id") or "") in preferred_rank else 1,
            preferred_rank.get(str(item.get("id") or ""), 9999),
            priority.get(str(item.get("fact_type")), 9),
            str(item.get("domain") or ""),
            str(item.get("id") or ""),
        )
    )
    out: List[Dict[str, Any]] = []
    effective_limit = max(limit, len(preferred_rank))
    for fact in normalized[:effective_limit]:
        out.append({
            "id": fact.get("id"),
            "domain": fact.get("domain"),
            "factType": fact.get("fact_type"),
            "provider": fact.get("provider"),
            "symbol": fact.get("symbol") or "",
            "metric": fact.get("metric") or "",
            "value": fact.get("value") or "",
            "measurements": dict(fact.get("measurements") or {}),
            "unit": fact.get("unit") or "",
            "asOf": fact.get("as_of") or fact.get("asOf") or "",
            "eventTime": fact.get("event_time") or fact.get("eventTime") or "",
            "publishedAt": fact.get("published_at") or fact.get("publishedAt") or "",
            "fetchedAt": fact.get("fetched_at") or fact.get("fetchedAt") or "",
            "sourceUrl": fact.get("source_url") or fact.get("sourceUrl") or "",
            "rawPath": fact.get("raw_path") or fact.get("rawPath") or "",
            "confidence": fact.get("confidence"),
            "evidenceScope": fact.get("evidence_scope") or "subject_evidence",
        })
    return out


def _source_health_row_domain(row: Dict[str, Any]) -> str:
    component = str(row.get("component") or row.get("source") or "").lower()
    if "macro" in component:
        return "macro"
    if "portfolio" in component:
        return "portfolio"
    if "governed" in component or "report" in component:
        return "publish_bundle"
    if "prediction" in component or "news" in component:
        return "news_sentiment"
    return "price"


def _is_limited_source_health(source_health: Dict[str, Any]) -> bool:
    text = f"{source_health.get('status', '')} {source_health.get('verdict', '')} {source_health.get('decisionImpact', '')}".lower()
    return any(token in text for token in ("degraded", "partial", "limited", "unknown", "不可作为满血"))


def _source_health_lines(health: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    rows = health.get("rows") if isinstance(health.get("rows"), list) else []
    if rows:
        for row in rows[:12]:
            if not isinstance(row, dict):
                continue
            name = _first_text(row.get("component"), row.get("source"), default="未命名来源")
            status = _first_text(row.get("status"), default="未提供")
            warning = _join_text(row.get("warnings") or row.get("warning") or [])
            suffix = f"；提示：{warning}" if warning else ""
            lines.append(f"- {name}：{status}{suffix}")
    else:
        status = _first_text(health.get("usability_verdict"), health.get("macro_status"), default="未提供")
        lines.append(f"- 源健康：{status}")
    return [_safe_reader_text(line) for line in lines]


def _candidate_lines(queue: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    candidates = queue.get("candidates") if isinstance(queue, dict) else []
    for row in (candidates or [])[:6]:
        if not isinstance(row, dict):
            continue
        symbol = _first_text(row.get("symbol"), default="")
        name = _first_text(row.get("name"), default=symbol or "未命名")
        verdict = _first_text(row.get("verdict"), default="待复核")
        risk = _first_text(row.get("price_risk"), default="未提供")
        lines.append(f"- {name}({symbol})：{verdict}；价格风险：{risk}")
    return [_safe_reader_text(line) for line in lines]


def _governed_summary_lines(rows: List[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    for row in rows:
        code = _first_text(row.get("code"), row.get("symbol"), default="")
        name = _first_text(row.get("name"), default=code or "未命名")
        trade_plan = row.get("trade_plan") if isinstance(row.get("trade_plan"), dict) else {}
        blocked = _is_blocked_governed_row(row)
        action = "暂不行动" if blocked else _human_action(trade_plan.get("action"))
        headline = _first_text(row.get("headline"), default="未提供")
        lines.append(f"- {name}({code})：{action}。原因：{headline}")
    return [_safe_reader_text(line) for line in lines]


def _daily_decision(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {
            "action": "watch",
            "gateStatus": "watch",
            "score": None,
            "targetPct": 0,
            "blockedReasons": [],
            "advisoryCaveats": ["no_completed_governed_report"],
        }
    scores = [_safe_float(row.get("score")) for row in rows]
    scores = [score for score in scores if score is not None]
    blocked_rows = [row for row in rows if _is_blocked_governed_row(row)]
    all_blocked = len(blocked_rows) == len(rows)
    return {
        "action": "no_action" if all_blocked else "watch",
        "gateStatus": "blocked" if all_blocked else "watch",
        "score": min(scores) if scores else None,
        "targetPct": 0,
        "blockedReasons": _blocked_reasons(blocked_rows) if all_blocked else [],
    }


def _blocked_reasons(rows: List[Dict[str, Any]]) -> List[str]:
    reasons: List[str] = []
    for row in rows:
        code = _first_text(row.get("code"), row.get("symbol"), default="unknown")
        status = _first_text(row.get("cio_status"), row.get("gate"), default="blocked")
        reasons.append(f"{code}:{status}")
    return reasons[:12]


def _is_blocked_governed_row(row: Dict[str, Any]) -> bool:
    return is_blocked_governed_row(row)


def _human_action(action: Any) -> str:
    value = str(action or "").strip().lower()
    if value == "no_action":
        return "不操作"
    if value == "buy":
        return "买入候选"
    if value == "sell":
        return "卖出候选"
    if value == "hold":
        return "持有/复核"
    if value == "watch":
        return "观察"
    if value == "wait":
        return "等待观察"
    return "未生成动作"


def _join_text(value: Any) -> str:
    if isinstance(value, list):
        return "；".join(str(item) for item in value if str(item))
    return str(value or "").strip()


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is _MISSING:
            continue
        if value is None:
            continue
        if isinstance(value, str) and value == "":
            continue
        return value
    return None


def _first_text(*values: Any, default: str = "未知") -> str:
    value = _first_present(*values)
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _safe_reader_text(text: Any) -> str:
    value = str(text or "")
    replacements = {
        "FULL_REVIEW": "完整复盘",
        "LIMITED_REVIEW": "有限复盘",
        "SCREEN_ONLY": "仅筛选观察",
        "OBSERVE_ONLY": "仅市场观察",
        "BLOCKED_BY_FATAL": "暂不行动",
        "BLOCKED": "暂不行动",
        "RAW_AGENT": "真实 Agent",
        "DERIVED_FROM_ARTIFACT": "历史材料整理",
        "回填审计：": "",
        "有限信息结论：": "",
        "source health": "数据健康",
        "source_health": "数据健康",
        "price / fundamentals / filings / macro": "行情、基本面、公告、宏观",
        "price": "行情",
        "fundamentals": "基本面",
        "filings": "公告",
        "macro": "宏观",
        "DEEP_REVIEW_WAIT_ENTRY": "等待深评入场条件",
        "OVERHEATED_WAIT_ENTRY": "短线过热，等待承接",
        "gate=暂不行动": "未通过",
        "ScoringAgent": "评分复核",
        "TradeDecisionGate": "交易前复核",
        "EvidenceGate": "证据复核",
        "FundamentalAgent": "基本面部门",
        "sector_rankings": "行业强弱排行",
        "hot_stocks": "热门标的列表",
        "originalAnalysisRefs": "上游分析材料",
        "portfolio_snapshot": "持仓快照",
        "quantity": "持仓数量",
        "market_value": "持仓市值",
        "cost_basis": "成本价",
        "评分复核未通过（总分4.0/10）": "综合判断偏弱，暂不支持行动",
        "评分门控未通过（总分4.0/10）": "综合判断偏弱，暂不支持行动",
        "MISSING agent": "未运行 Agent",
        "no_action": "不操作",
        "N/A": "未提供",
        "关键数据缺口": "关键待确认项",
        "数据缺口": "待确认项",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    return value


def _safe_float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _latest_evidence_time(facts: List[Dict[str, Any]], *, fallback: str) -> str:
    values: List[str] = []
    for fact in facts:
        value = iso_timestamp(
            fact.get("event_time")
            or fact.get("eventTime")
            or fact.get("published_at")
            or fact.get("publishedAt")
            or fact.get("as_of")
            or fact.get("asOf")
        )
        if value:
            values.append(value)
    if not values:
        return fallback
    latest_date = max(value[:10] for value in values)
    same_day = [value for value in values if value[:10] == latest_date]
    exact = [
        value
        for value in same_day
        if "T" in value and not re.search(r"T00:00(?::00)?(?:Z|[+-]00:00)?$", value)
    ]
    return max(exact) if exact else latest_date


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
