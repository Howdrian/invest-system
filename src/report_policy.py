"""Shared report governance policy helpers."""

from __future__ import annotations

from typing import Any, Mapping, Optional


def is_blocked_governed_row(row: Mapping[str, Any]) -> bool:
    """Return whether a governed row should be treated as no-action blocked."""
    status = str(row.get("cio_status") or "").upper()
    gate = str(row.get("gate") or "").upper()
    trade_plan = row.get("trade_plan") if isinstance(row.get("trade_plan"), Mapping) else {}
    action = str(trade_plan.get("action") or "").lower()
    score = _safe_float(row.get("score"))
    return status == "BLOCKED_BY_FATAL" or gate == "BLOCKED" or action == "no_action" or (score is not None and score < 6)


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return None
