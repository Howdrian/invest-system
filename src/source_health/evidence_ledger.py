"""Evidence ledger helpers for product-facing report confidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from .temporal import iso_timestamp


VALID_FACT_TYPES = {
    "verified_fact",
    "derived_fact",
    "discovery",
    "agent_opinion",
    "sellside_opinion",
    "final_claim",
    "missing",
}
SEARCH_DISCOVERY_PROVIDERS = {
    "tavily",
    "serpapi",
    "brave",
    "searxng",
    "kimi",
    "ai_search",
    "search",
    "gdelt",
}


def normalize_evidence_fact(row: Mapping[str, Any]) -> Dict[str, Any]:
    """Normalize one evidence fact without network calls.

    Search/AI search providers stay discovery. Verified facts need provider +
    source_url/raw_path.
    """

    fact = dict(row)
    provider = str(fact.get("provider") or "").strip()
    provider_key = provider.lower()
    fact_type = str(fact.get("fact_type") or fact.get("factType") or "missing").lower()
    if fact_type not in VALID_FACT_TYPES:
        fact_type = "missing"

    if fact_type == "verified_fact" and provider_key in SEARCH_DISCOVERY_PROVIDERS:
        fact_type = "discovery"
        fact["downgradeReason"] = "search_provider_not_verified_fact"

    if fact_type == "verified_fact" and not has_fact_source(fact):
        fact_type = "missing"
        fact["missingReason"] = "verified_fact_missing_source"

    fact["fact_type"] = fact_type
    fact.pop("factType", None)
    scope = str(fact.get("evidence_scope") or fact.get("evidenceScope") or fact.get("source_scope") or fact.get("sourceScope") or "subject_evidence")
    fact["evidence_scope"] = scope if scope in {"subject_evidence", "source_smoke"} else "subject_evidence"
    fact.pop("evidenceScope", None)
    if "subject" not in fact and fact.get("symbol"):
        fact["subject"] = str(fact.get("symbol") or "")
    fact.setdefault("confidence", _confidence_for_type(fact_type))
    fact.setdefault("provider", provider or "unknown")
    fact.setdefault("id", _fallback_fact_id(fact))
    for snake, camel in (
        ("event_time", "eventTime"),
        ("published_at", "publishedAt"),
        ("fetched_at", "fetchedAt"),
    ):
        normalized = iso_timestamp(fact.get(snake) or fact.get(camel))
        if normalized:
            fact[snake] = normalized
        else:
            fact.pop(snake, None)
        fact.pop(camel, None)
    return fact


def has_fact_source(fact: Mapping[str, Any]) -> bool:
    provider = str(fact.get("provider") or "").strip()
    source = str(fact.get("source_url") or fact.get("sourceUrl") or fact.get("raw_path") or fact.get("rawPath") or "").strip()
    return bool(provider and source)


def write_evidence_ledger(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            handle.write(json.dumps(normalize_evidence_fact(row), ensure_ascii=False, sort_keys=True) + "\n")


def load_evidence_ledger(path: str | Path) -> List[Dict[str, Any]]:
    source = Path(path)
    if not source.exists() or not source.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(raw, Mapping):
            rows.append(normalize_evidence_fact(raw))
    return rows


def _confidence_for_type(fact_type: str) -> str:
    if fact_type == "verified_fact":
        return "high"
    if fact_type == "derived_fact":
        return "medium"
    return "low"


def _fallback_fact_id(fact: Mapping[str, Any]) -> str:
    domain = str(fact.get("domain") or "unknown")
    fact_type = str(fact.get("fact_type") or "missing")
    provider = str(fact.get("provider") or "unknown")
    return f"{fact_type}:{domain}:{provider}"
