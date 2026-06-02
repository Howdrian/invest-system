# -*- coding: utf-8 -*-
"""Helpers for evaluating governed-mode analysis records in backtests."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional


def extract_governed_trade_plan(
    raw_result: Any = None,
    context_snapshot: Any = None,
) -> Optional[Dict[str, Any]]:
    """Extract a governed CIO trade plan from persisted analysis payloads.

    Supports both current and transitional shapes:
    - raw_result.governance.trade_plan
    - raw_result.governance.cio.trade_plan
    - raw_result.dashboard.governance.trade_plan
    - context_snapshot.governance.trade_plan
    """
    for payload in (_loads(raw_result), _loads(context_snapshot)):
        if not isinstance(payload, dict):
            continue
        governance = _find_governance(payload)
        if not isinstance(governance, dict):
            continue
        trade_plan = governance.get("trade_plan")
        if isinstance(trade_plan, dict):
            return trade_plan
        cio = governance.get("cio")
        if isinstance(cio, dict) and isinstance(cio.get("trade_plan"), dict):
            return cio["trade_plan"]
    return None


def resolve_governed_operation_advice(
    *,
    raw_result: Any = None,
    context_snapshot: Any = None,
    fallback: Optional[str] = None,
) -> Optional[str]:
    """Map governed CIO trade-plan action to legacy backtest advice text."""
    trade_plan = extract_governed_trade_plan(raw_result=raw_result, context_snapshot=context_snapshot)
    if not isinstance(trade_plan, dict):
        return fallback
    action = str(trade_plan.get("action") or "").strip().lower()
    mapping = {
        "buy": "买入",
        "add": "买入",
        "increase": "买入",
        "build": "买入",
        "sell": "卖出",
        "reduce": "减仓",
        "trim": "减仓",
        "hold": "持有",
        "wait": "观望",
        "no_action": "观望",
        "none": "观望",
    }
    return mapping.get(action, fallback)


def resolve_governed_price_levels(
    *,
    raw_result: Any = None,
    context_snapshot: Any = None,
    fallback_stop_loss: Optional[float] = None,
    fallback_take_profit: Optional[float] = None,
) -> tuple[Optional[float], Optional[float]]:
    """Resolve stop/take-profit hints from governed trade_plan when numeric."""
    trade_plan = extract_governed_trade_plan(raw_result=raw_result, context_snapshot=context_snapshot)
    if not isinstance(trade_plan, dict):
        return fallback_stop_loss, fallback_take_profit
    stop_loss = _first_number(trade_plan.get("stop_loss"))
    take_profit = _first_number(trade_plan.get("take_profit"))
    return (
        stop_loss if stop_loss is not None else fallback_stop_loss,
        take_profit if take_profit is not None else fallback_take_profit,
    )


def _find_governance(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    governance = payload.get("governance")
    if isinstance(governance, dict):
        return governance
    dashboard = payload.get("dashboard")
    if isinstance(dashboard, dict) and isinstance(dashboard.get("governance"), dict):
        return dashboard["governance"]
    return None


def _loads(value: Any) -> Any:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except Exception:
            return None
    return None


def _first_number(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    match = re.search(r"\d+(?:\.\d+)?", value.replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None
