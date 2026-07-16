"""JSONL persistence for provider attempts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .temporal import iso_timestamp, utc_now_iso


def normalize_provider_run(row: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(row)
    observed_at = iso_timestamp(payload.get("observed_at") or payload.get("observedAt"))
    payload["observed_at"] = observed_at or utc_now_iso()
    payload.pop("observedAt", None)
    return payload


def append_provider_ledger(path: str | Path, row: Dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(normalize_provider_run(row), ensure_ascii=False, sort_keys=True) + "\n")


def write_provider_ledger(path: str | Path, rows: Iterable[Dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(normalize_provider_run(row), ensure_ascii=False, sort_keys=True) for row in rows if isinstance(row, dict)]
    target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def load_provider_ledger(path: str | Path) -> List[Dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            # Reading an old ledger must not invent a new observation time.
            # Exact timestamps are attached when a provider run is written.
            observed_at = iso_timestamp(payload.get("observed_at") or payload.get("observedAt"))
            if observed_at:
                payload["observed_at"] = observed_at
            payload.pop("observedAt", None)
            rows.append(payload)
    return rows
