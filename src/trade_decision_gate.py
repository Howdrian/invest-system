# -*- coding: utf-8 -*-
"""Deterministic final trade-decision gate.

This module is intentionally small and side-effect free except for mutating the
``AnalysisResult`` object passed in. It sits after agent/model output and before
history/report publication so raw buy/sell wording cannot bypass governance.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


BLOCKING_CIO_STATUSES = {"BLOCKED_BY_FATAL", "NEEDS_EVIDENCE"}
BLOCKING_EVIDENCE_STATUSES = {"BLOCKED", "NEEDS_EVIDENCE"}
TRADE_ACTIONS = {"buy", "add", "sell", "reduce"}


def apply_trade_decision_gate(result: Any) -> Tuple[bool, List[str]]:
    """Clamp an ``AnalysisResult`` if governance disallows trade actions.

    Rules:
    - EvidenceGate BLOCKED / NEEDS_EVIDENCE -> no_action + 0%
    - score < 6.0 -> no_action + 0%
    - CIO BLOCKED_BY_FATAL / NEEDS_EVIDENCE -> no_action + 0%
    - WAIT_ENTRY can only wait/watch with 0%, never buy/sell/reduce/add
    """

    governance = _extract_governance(result)
    dashboard = getattr(result, "dashboard", None)
    if not isinstance(dashboard, dict):
        dashboard = {}
        setattr(result, "dashboard", dashboard)

    reasons: List[str] = []

    cio = governance.get("cio") if isinstance(governance.get("cio"), dict) else {}
    status = str(governance.get("cio_status") or cio.get("status") or "").upper()
    if status in BLOCKING_CIO_STATUSES:
        reasons.append(f"cio_status={status}")

    evidence_status = _extract_evidence_status(governance, dashboard)
    if evidence_status in BLOCKING_EVIDENCE_STATUSES:
        reasons.append(f"evidence_gate={evidence_status}")

    score = _governance_score(governance)
    if score is not None and score < 6.0:
        reasons.append(f"score={score}/10<6")

    gate = _extract_scoring_gate(governance)
    if gate == "BLOCKED":
        reasons.append("scoring_gate=BLOCKED")

    trade_plan = governance.get("trade_plan") if isinstance(governance.get("trade_plan"), dict) else {}
    action = _normalize_action(trade_plan.get("action") or dashboard.get("decision_type"))

    if reasons or action == "no_action":
        if action == "no_action" and not reasons:
            reasons.append("trade_plan_action=no_action")
        _apply_blocked_result(result, dashboard, governance, reasons, score)
        return True, reasons

    if status == "WAIT_ENTRY" and action in TRADE_ACTIONS:
        _apply_wait_entry_result(result, dashboard, governance)
        return True, ["cio_status=WAIT_ENTRY forbids trade action"]

    return False, []


def _extract_governance(result: Any) -> Dict[str, Any]:
    dashboard = getattr(result, "dashboard", None)
    if isinstance(dashboard, dict) and isinstance(dashboard.get("governance"), dict):
        governance = dashboard["governance"]
    elif isinstance(getattr(result, "_governance", None), dict):
        governance = getattr(result, "_governance")
    else:
        governance = {}
    if not isinstance(governance, dict):
        return {}
    return governance


def _extract_evidence_status(governance: Dict[str, Any], dashboard: Dict[str, Any]) -> str:
    candidates = [
        governance.get("evidence_gate"),
        governance.get("evidence_gate_result"),
        dashboard.get("evidence_gate"),
        dashboard.get("evidence_gate_result"),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            status = str(candidate.get("status") or candidate.get("gate") or "").upper()
            if status:
                return status
        elif isinstance(candidate, str) and candidate.strip():
            return candidate.strip().upper()
    return ""


def _extract_scoring_gate(governance: Dict[str, Any]) -> str:
    scoring = governance.get("scoring") if isinstance(governance.get("scoring"), dict) else {}
    return str(
        governance.get("gate")
        or governance.get("gate_result")
        or scoring.get("gate_result")
        or ""
    ).upper()


def _governance_score(governance: Dict[str, Any]) -> Optional[float]:
    scoring = governance.get("scoring") if isinstance(governance.get("scoring"), dict) else {}
    for key in ("score", "total_score"):
        value = governance.get(key)
        parsed = _safe_float(value)
        if parsed is not None:
            return parsed
    return _safe_float(scoring.get("total_score"))


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except (TypeError, ValueError, OverflowError):
            return None
    text = str(value).strip().replace(",", "")
    if text.endswith("%"):
        text = text[:-1].strip()
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError, OverflowError):
        return None


def _normalize_action(value: Any) -> str:
    action = str(value or "").strip().lower()
    aliases = {
        "buy": "buy",
        "add": "add",
        "increase": "add",
        "sell": "sell",
        "reduce": "reduce",
        "trim": "reduce",
        "hold": "hold",
        "wait": "wait",
        "watch": "watch",
        "blocked": "no_action",
        "no_action": "no_action",
        "none": "no_action",
    }
    return aliases.get(action, action)


def _normalise_trade_plan(governance: Dict[str, Any]) -> Dict[str, Any]:
    trade_plan = governance.get("trade_plan")
    if not isinstance(trade_plan, dict):
        trade_plan = {}
    else:
        trade_plan = dict(trade_plan)
    governance["trade_plan"] = trade_plan
    return trade_plan


def _apply_blocked_result(
    result: Any,
    dashboard: Dict[str, Any],
    governance: Dict[str, Any],
    reasons: List[str],
    score: Optional[float],
) -> None:
    trade_plan = _normalise_trade_plan(governance)
    trade_plan["action"] = "no_action"
    trade_plan["target_pct"] = 0
    trade_plan["target_position_pct"] = 0
    trade_plan["position"] = "0%"
    trade_plan["manual_execution_only"] = True

    governance["trade_plan"] = trade_plan
    governance.setdefault("cio_status", "BLOCKED_BY_FATAL")
    governance["blocked_reasons"] = list(dict.fromkeys(str(reason) for reason in reasons if reason))

    setattr(result, "_governance", governance)
    setattr(result, "decision_type", "blocked")
    setattr(result, "operation_advice", "阻断 / 不操作 / 0%")
    setattr(result, "confidence_level", "低")
    if score is not None:
        setattr(result, "sentiment_score", min(59, max(0, int(round(score * 10)))))
    else:
        current_score = _safe_float(getattr(result, "sentiment_score", None))
        if current_score is not None:
            setattr(result, "sentiment_score", min(59, int(current_score)))

    dashboard["governance"] = governance
    dashboard["decision_type"] = "blocked"
    dashboard["operation_advice"] = "阻断 / 不操作 / 0%"
    dashboard["trade_decision_gate"] = {
        "status": "blocked",
        "action": "no_action",
        "target_pct": 0,
        "reasons": governance["blocked_reasons"],
    }
    core = dashboard.setdefault("core_conclusion", {})
    if isinstance(core, dict):
        core["one_sentence"] = "治理层已阻断：最终动作为 no_action，目标仓位 0%。"
        core["position_advice"] = {
            "no_position": "不新增仓位；等待补证据或重新评估。",
            "has_position": "不新增仓位；如已持仓，仅做人工风险复核。",
        }


def _apply_wait_entry_result(
    result: Any,
    dashboard: Dict[str, Any],
    governance: Dict[str, Any],
) -> None:
    trade_plan = _normalise_trade_plan(governance)
    trade_plan["action"] = "wait"
    trade_plan["target_pct"] = 0
    trade_plan["target_position_pct"] = 0
    trade_plan["position"] = "0%"
    trade_plan["manual_execution_only"] = True

    governance["trade_plan"] = trade_plan
    setattr(result, "_governance", governance)
    setattr(result, "decision_type", "hold")
    setattr(result, "operation_advice", "等待观察 / 0%")

    dashboard["governance"] = governance
    dashboard["decision_type"] = "hold"
    dashboard["operation_advice"] = "等待观察 / 0%"
    dashboard["trade_decision_gate"] = {
        "status": "watch",
        "action": "wait",
        "target_pct": 0,
        "reasons": ["WAIT_ENTRY forbids buy/sell/reduce/add"],
    }
