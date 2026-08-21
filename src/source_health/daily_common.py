"""Shared helpers for daily source-health ledgers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    return []


def official_events_payload(docs: Path, run_date: str) -> Dict[str, Any]:
    payload = read_json(docs / "official_events" / f"{run_date}.json")
    return dict(payload) if isinstance(payload, Mapping) else {}


def official_events_payloads(docs: Path, run_date: str) -> List[Dict[str, Any]]:
    payloads: List[Dict[str, Any]] = []
    for path in [
        docs / "official_events" / f"{run_date}.json",
        docs / "official_events" / f"{run_date}.source_smoke.json",
    ]:
        payload = read_json(path)
        if isinstance(payload, Mapping):
            payloads.append(dict(payload))
    return payloads


def iter_agent_memos(docs: Path, run_date: str) -> Iterable[Tuple[Path, Dict[str, Any]]]:
    base = docs / "agent_memos" / run_date
    if not base.exists():
        return
    for path in sorted(base.rglob("*.json")):
        payload = read_json(path)
        if isinstance(payload, Mapping) and payload.get("schema") == "agent_memo_v1":
            yield path, dict(payload)


def iter_attempts(memo: Mapping[str, Any]) -> Iterable[Dict[str, Any]]:
    seen: set[str] = set()
    candidates: List[Any] = []
    candidates.extend(as_list(memo.get("source_attempts")))
    pack = memo.get("evidence_pack") if isinstance(memo.get("evidence_pack"), Mapping) else {}
    candidates.extend(as_list(pack.get("source_attempts")))
    for item in candidates:
        if not isinstance(item, Mapping):
            continue
        key = json.dumps(dict(item), ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        yield dict(item)


def domain_from_memo(memo: Mapping[str, Any]) -> str:
    return normalize_domain(memo.get("domain") or memo.get("scope") or memo.get("agent"))


def domain_from_path(name: str) -> str:
    lower = name.lower()
    if "macro" in lower:
        return "macro"
    if "source" in lower:
        return "news_sentiment"
    if "strategy" in lower or "screening" in lower or "queue" in lower:
        return "news_sentiment"
    if "portfolio" in lower:
        return "portfolio"
    return "publish_bundle"


def normalize_domain(value: Any) -> str:
    text = str(value or "").lower()
    if any(token in text for token in ("price", "quote", "daily", "realtime", "kline", "technical")):
        return "price"
    if any(token in text for token in ("fundamental", "financial", "valuation")):
        return "fundamentals"
    if any(token in text for token in ("filing", "announcement", "event", "notice")):
        return "filings_events"
    if any(token in text for token in ("macro", "geo")):
        return "macro"
    if any(token in text for token in ("news", "sentiment", "search", "intel", "candidate", "source")):
        return "news_sentiment"
    if "portfolio" in text or "holding" in text:
        return "portfolio"
    if "memo" in text or "agent" in text:
        return "agent_memos"
    if "report" in text or "publish" in text:
        return "publish_bundle"
    return "news_sentiment"


def dedupe(rows: Iterable[Dict[str, Any]], *, keys: Tuple[str, ...]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: set[Tuple[Any, ...]] = set()
    for row in rows:
        key = tuple(row.get(item) for item in keys)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None
