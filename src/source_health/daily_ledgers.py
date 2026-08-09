"""Build daily source health ledgers from existing runtime artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from .daily_common import iter_agent_memos, official_events_payload, read_json
from .daily_evidence import (
    dedupe_evidence_facts,
    evidence_from_daily_universe,
    evidence_from_macro_context,
    evidence_from_market_cycle,
    evidence_from_official_events,
    evidence_from_successful_provider_runs,
)
from .daily_providers import (
    provider_runs_from_agent_memos,
    provider_runs_from_macro_context,
    provider_runs_from_official_events,
    provider_runs_from_pages_validation,
)
from .daily_universe import load_daily_universe, write_daily_universe
from .evidence_ledger import load_evidence_ledger, write_evidence_ledger
from .intelligence_evidence import load_intelligence_evidence_facts, load_intelligence_provider_runs
from .policy import build_source_health_v2
from .provider_ledger import load_provider_ledger, write_provider_ledger
from .run_matrix import load_run_matrix, sha256_file, upsert_run_matrix_stage, write_run_matrix
from .subject_evidence import load_subject_evidence_facts, load_subject_provider_runs

_OFFICIAL_EVENT_PROVIDERS = {
    "SEC_EDGAR",
    "CNINFO",
    "SSE_DISCLOSURE",
    "SZSE_DISCLOSURE",
    "HKEXNEWS",
    "GDELT",
    "Tavily",
    "RELIEFWEB",
    "OFAC_SDN",
}


def write_daily_source_health_ledgers(
    docs_dir: str | Path,
    run_date: str,
    *,
    preserve_runtime_enrichment: bool = False,
    include_pages_validation: bool = False,
) -> Dict[str, Any]:
    """Write provider/evidence ledgers under ``docs/run_status/{run_date}``.

    This is deterministic and offline. It converts existing official-event,
    Agent memo and market-cycle artifacts into product-facing ledgers.
    """

    docs = Path(docs_dir)
    out_dir = docs / "run_status" / run_date
    universe = load_daily_universe(docs, run_date) or write_daily_universe(docs, run_date)
    subject_provider_rows = load_subject_provider_runs(docs, run_date)
    subject_evidence_rows = load_subject_evidence_facts(docs, run_date)
    intelligence_provider_rows = load_intelligence_provider_runs(docs, run_date)
    intelligence_evidence_rows = load_intelligence_evidence_facts(docs, run_date)
    agent_provider_fingerprints = {
        _provider_origin_fingerprint(row)
        for row in provider_runs_from_agent_memos(docs, run_date)
    }
    loaded_provider_rows = load_provider_ledger(out_dir / "provider_runs.jsonl")
    loaded_evidence_rows = load_evidence_ledger(out_dir / "evidence_ledger.jsonl")
    provider_rows = _dedupe_daily_provider_rows([
        *_non_stale_loaded_provider_rows(
            loaded_provider_rows,
            agent_provider_fingerprints=agent_provider_fingerprints,
        ),
        *(_current_cio_provider_rows(loaded_provider_rows) if preserve_runtime_enrichment else []),
        *provider_runs_from_macro_context(docs, run_date),
        *subject_provider_rows,
        *intelligence_provider_rows,
        *provider_runs_from_official_events(docs, run_date),
        *(provider_runs_from_pages_validation(docs, run_date) if include_pages_validation else []),
    ])
    evidence_rows = dedupe_evidence_facts([
        *evidence_from_daily_universe(universe, run_date),
        *evidence_from_macro_context(docs, run_date),
        *subject_evidence_rows,
        *intelligence_evidence_rows,
        *evidence_from_official_events(docs, run_date),
        *evidence_from_market_cycle(docs, run_date),
        *evidence_from_successful_provider_runs(
            provider_rows,
            run_date=run_date,
            docs_relative_provider_ledger=f"run_status/{run_date}/provider_runs.jsonl",
        ),
        *(_current_cio_evidence_rows(loaded_evidence_rows, run_date) if preserve_runtime_enrichment else []),
    ])

    provider_path = out_dir / "provider_runs.jsonl"
    evidence_path = out_dir / "evidence_ledger.jsonl"
    source_health_path = out_dir / "source_health_v2.json"
    write_provider_ledger(provider_path, provider_rows)
    write_evidence_ledger(evidence_path, evidence_rows)

    legacy_health = read_json(docs / "market_cycle" / run_date / "13_source_health.json")
    if not isinstance(legacy_health, Mapping):
        legacy_health = {}
    source_health_v2 = build_source_health_v2(
        legacy_health,
        provider_runs=provider_rows,
        evidence_facts=evidence_rows,
        agent_origin_counts=_agent_origin_counts(docs, run_date),
        subject_symbols=_symbols_from_universe(universe),
    )
    source_health_path.write_text(json.dumps(source_health_v2, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    official_stage_status = "success" if (docs / "official_events" / f"{run_date}.json").exists() else "skipped"
    run_stages = [
        {
            "name": "daily_universe",
            "status": "success",
            "blocking": True,
            "outputs": [f"run_status/{run_date}/daily_universe.json"],
            "sha256": sha256_file(docs / "run_status" / run_date / "daily_universe.json"),
        },
        {
            "name": "official_event_sources",
            "status": official_stage_status,
            "blocking": False,
            "outputs": [f"official_events/{run_date}.json"] if official_stage_status == "success" else [],
            "sha256": sha256_file(docs / "official_events" / f"{run_date}.json"),
        },
        {
            "name": "subject_evidence_collection",
            "status": "success" if subject_provider_rows or subject_evidence_rows else "skipped",
            "blocking": False,
            "inputs": [f"run_status/{run_date}/daily_universe.json"],
            "outputs": [
                f"run_status/{run_date}/subject_provider_runs.jsonl",
                f"run_status/{run_date}/subject_evidence.jsonl",
            ],
            "sha256": sha256_file(docs / "run_status" / run_date / "subject_provider_runs.jsonl"),
        },
        {
            "name": "intelligence_evidence_collection",
            "status": "success" if intelligence_provider_rows or intelligence_evidence_rows else "skipped",
            "blocking": False,
            "outputs": [
                f"run_status/{run_date}/intelligence_provider_runs.jsonl",
                f"run_status/{run_date}/intelligence_evidence.jsonl",
            ] if intelligence_provider_rows or intelligence_evidence_rows else [],
            "sha256": sha256_file(docs / "run_status" / run_date / "intelligence_provider_runs.jsonl"),
        },
        {
            "name": "data_source_pre_smoke",
            "status": "success" if provider_rows or evidence_rows else "partial",
            "blocking": True,
            "outputs": [
                f"run_status/{run_date}/provider_runs.jsonl",
                f"run_status/{run_date}/evidence_ledger.jsonl",
            ],
            "sha256": sha256_file(provider_path),
        },
        {
            "name": "source_health_snapshot",
            "status": "success",
            "blocking": True,
            "inputs": [
                f"run_status/{run_date}/provider_runs.jsonl",
                f"run_status/{run_date}/evidence_ledger.jsonl",
            ],
            "outputs": [f"run_status/{run_date}/source_health_v2.json"],
            "sha256": sha256_file(source_health_path),
        },
    ]
    symbols = _symbols_from_universe(universe) or _symbols_from_official_events(docs, run_date)
    current_matrix = load_run_matrix(docs, run_date)
    if current_matrix.get("stages"):
        for stage in run_stages:
            upsert_run_matrix_stage(docs, run_date, stage, symbols=symbols)
    else:
        write_run_matrix(docs, run_date, symbols=symbols, stages=run_stages)

    return {
        "schema": "daily_source_health_ledgers_v1",
        "runDate": run_date,
        "providerRuns": len(provider_rows),
        "evidenceFacts": len(evidence_rows),
        "providerLedger": f"run_status/{run_date}/provider_runs.jsonl",
        "evidenceLedger": f"run_status/{run_date}/evidence_ledger.jsonl",
        "sourceHealthV2": f"run_status/{run_date}/source_health_v2.json",
        "runMatrix": f"run_status/{run_date}/run_matrix.json",
        "dailyUniverse": f"run_status/{run_date}/daily_universe.json",
        "universeSubjects": len(_symbols_from_universe(universe)),
    }


def _non_stale_loaded_provider_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    agent_provider_fingerprints: set[str] | None = None,
) -> List[Dict[str, Any]]:
    """Keep runtime provider rows, drop stale official-source rows.

    ``official_events/{date}.json`` is the source of truth for SEC/CNINFO/SSE/
    SZSE/HKEX/GDELT/Tavily/RELIEFWEB/OFAC in the current run. Older ledgers may
    contain previous attempts with the same ``source_scope``; keeping them can
    make diagnostics show stale failures after a successful refresh.
    """

    out: List[Dict[str, Any]] = []
    agent_fingerprints = agent_provider_fingerprints or set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        provider = str(row.get("provider") or "")
        scope = str(row.get("source_scope") or row.get("sourceScope") or "")
        operation = str(row.get("operation") or "")
        if scope in {"cio_enrichment", "agent_memo"} or operation == "cio_enrichment":
            continue
        if not scope and _provider_origin_fingerprint(row) in agent_fingerprints:
            continue
        if provider in _OFFICIAL_EVENT_PROVIDERS and scope != "source_smoke":
            continue
        out.append(dict(row))
    return out


def _current_cio_provider_rows(rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    return [
        dict(row)
        for row in rows
        if isinstance(row, Mapping)
        and (
            str(row.get("source_scope") or row.get("sourceScope") or "") == "cio_enrichment"
            or str(row.get("operation") or "") == "cio_enrichment"
        )
    ]


def _current_cio_evidence_rows(
    rows: Iterable[Mapping[str, Any]],
    run_date: str,
) -> List[Dict[str, Any]]:
    return [
        dict(row)
        for row in rows
        if isinstance(row, Mapping)
        and str(row.get("origin") or "") == "CIO_REQUESTED"
        and str(row.get("as_of") or row.get("asOf") or "") == run_date
    ]


def _provider_origin_fingerprint(row: Mapping[str, Any]) -> str:
    return json.dumps(
        {
            "provider": row.get("provider"),
            "operation": row.get("operation"),
            "data_type": row.get("data_type") or row.get("domain"),
            "domain": row.get("domain") or row.get("data_type"),
            "success": row.get("success"),
            "error_type": row.get("error_type") or row.get("errorType"),
            "record_count": row.get("record_count")
            if row.get("record_count") is not None
            else row.get("recordCount"),
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def _dedupe_daily_provider_rows(rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Dedupe attempts without collapsing distinct subject symbols."""

    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        payload = dict(row)
        key_payload = {
            key: payload.get(key)
            for key in (
                "trace_id",
                "provider",
                "operation",
                "data_type",
                "domain",
                "symbol",
                "subject",
                "symbols",
                "success",
                "status",
                "error_type",
                "record_count",
                "request_id",
            )
        }
        key_payload["source_scope"] = payload.get("source_scope") or payload.get("sourceScope")
        key = json.dumps(key_payload, ensure_ascii=False, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        out.append(payload)
    return out


def _agent_origin_counts(docs: Path, run_date: str) -> Dict[str, int]:
    counts = {"RAW_AGENT": 0, "DERIVED_FROM_ARTIFACT": 0, "MISSING": 0}
    for _path, memo in iter_agent_memos(docs, run_date):
        origin = str(memo.get("origin") or "DERIVED_FROM_ARTIFACT")
        counts[origin] = counts.get(origin, 0) + 1
    return counts


def _symbols_from_official_events(docs: Path, run_date: str) -> List[str]:
    payload = official_events_payload(docs, run_date)
    out: List[str] = []
    for symbol in payload.get("symbols") or []:
        text = str(symbol).strip()
        if text and text.upper() not in {item.upper() for item in out}:
            out.append(text)
    return out


def _symbols_from_universe(universe: Mapping[str, Any]) -> List[str]:
    out: List[str] = []
    for symbol in universe.get("subjectSymbols") or []:
        text = str(symbol).strip()
        if text and text.upper() not in {item.upper() for item in out}:
            out.append(text)
    return out
