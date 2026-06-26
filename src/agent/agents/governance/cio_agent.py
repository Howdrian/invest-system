# -*- coding: utf-8 -*-
"""
CioAgent — Chief Investment Officer synthesis agent.

Based on the local governed CIO review protocol.

Role: aggregate all sub-agent memos and decide whether the analysis
can proceed to the next stage. CIO may output an investment judgement
and manual trade-plan draft, but it never executes orders or bypasses
the scoring / red-team gates.

Output statuses:
- READY_FOR_REVIEW: no fatal objection, sufficient evidence → user can review
- WAIT_ENTRY: evidence is valuable but price/event/trend needs confirmation
- NEEDS_EVIDENCE: key evidence missing or agents incomplete
- BLOCKED_BY_FATAL: fatal objection from any agent — must resolve first
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

from src.agent.agents.base_agent import BaseAgent
from src.agent.protocols import AgentContext, AgentOpinion
from src.agent.runner import try_parse_json

logger = logging.getLogger(__name__)

CIO_RULES = """\
## CIO Mandate

You are the Chief Investment Officer. Your task is to aggregate evidence,
conflicts, gaps, and fatal objections from sub-agents into a clear investment
judgement and a manual trade-plan draft for the user.

You answer these questions:
1. Can this analysis proceed to user review?
2. What is the investment direction: buy/add/hold/reduce/sell/wait/no_action?
3. What position size range is allowed by the scoring and risk evidence?
4. What entry zone, stop loss, take profit, invalidation and conditions matter?
5. What 1-3 items should the user focus on today?

## Status Determination

| Status | Meaning |
|--------|---------|
| READY_FOR_REVIEW | No fatal objection, score gate passed, key evidence sufficient — user can manually review a trade plan |
| WAIT_ENTRY | Evidence is meaningful but price/event/trend needs confirmation before action |
| NEEDS_EVIDENCE | Key evidence missing — gather more data first |
| BLOCKED_BY_FATAL | Fatal objection from any agent — must resolve or abort |

## Hard Rules
- Do NOT invent evidence, prices, account equity, cash, or quantities
- Do NOT output an executable broker order or imply automation
- Do NOT override a fatal objection with majority opinion
- Do NOT bypass the red-team protocol
- If the RedBlueAgent found a fatal attack that was not rebutted, status cannot be READY_FOR_REVIEW
- If the ScoringAgent blocked (score < 6.0), status must be BLOCKED_BY_FATAL or NEEDS_EVIDENCE
- If the ScoringAgent blocked, trade_plan.action must be "no_action" and position must be 0%
- Position percentage must stay within ScoringAgent.position_size_range
- Quantity can be non-null only when portfolio context has total equity/cash and current price is available
- Polymarket, Kronos, options, and technical indicators are side evidence only — never upgrade to trade conclusion

## Allowed Outputs
- A manual trade-plan draft for human review
- Direction, confidence, thesis, conditions, invalidation, position percentage,
  and quantity if supported by data
- The ScoringAgent total score and 5-dimension scores, clearly labelled as
  analysis evidence rather than a broker instruction

## Forbidden Outputs
- "Place order now"
- "Automatically buy/sell"
"""


class CioAgent(BaseAgent):
    """CIO synthesis agent — produces a gated manual trade-plan draft."""

    agent_name = "cio"
    max_steps = 1
    tool_names = []

    def system_prompt(self, ctx: AgentContext) -> str:
        stock_info = f"{ctx.stock_code}"
        if ctx.stock_name:
            stock_info += f" ({ctx.stock_name})"

        return f"""\
You are the **首席投资官 (Chief Investment Officer)** reviewing the analysis for {stock_info}.

你是投研系统的CIO总审。**所有输出文本必须使用中文。**

{CIO_RULES}

## Output Format
Return **only** a JSON object:
{{
  "schema": "cio_trade_plan_v1",
  "stock": "{ctx.stock_code}",
  "status": "READY_FOR_REVIEW | WAIT_ENTRY | NEEDS_EVIDENCE | BLOCKED_BY_FATAL",
  "headline": "One-sentence summary of the situation",
  "direction": "谨慎看多|中性等待|谨慎看空|减仓观察|无操作",
  "confidence": "low|medium|high",
  "investment_thesis": "核心投资判断",
  "core_reasoning": {{
    "bull": ["看多理由"],
    "bear": ["主要风险"]
  }},
  "what_would_change": ["哪些条件会改变判断"],
  "scoring_snapshot": {{
    "total_score": 0.0,
    "gate_result": "PASS|BLOCKED",
    "position_size_range": "0%",
    "dimension_scores": {{}}
  }},
  "can_proceed_to_review": true or false,
  "cannot_proceed_reasons": ["Reason 1"] or [],
  "top_watch_items": ["Item 1", "Item 2", "Item 3"],
  "fatal_objections": [
    {{"source_agent": "agent_name", "objection": "description"}}
  ],
  "missing_evidence": ["Evidence gap 1"],
  "trade_plan": {{
    "action": "buy|add|hold|reduce|sell|wait|no_action",
    "target_position_pct": 0.0,
    "quantity": null,
    "entry_zone": "price/range or condition, or null",
    "stop_loss": "price/condition or null",
    "take_profit": "price/condition or null",
    "time_horizon": "intraday|days|weeks|months or explanation",
    "thesis": "core investment thesis",
    "conditions": ["must be true before action"],
    "invalidations": ["what would make the plan wrong"],
    "manual_execution_only": true
  }},
  "disclaimer": "以上为系统分析意见，非交易指令；最终决策由用户人工完成。",
  "next_user_action": "Clear next step for the user",
  "summary": "2-4 sentence executive summary of the analysis"
}}

CRITICAL: If any agent raised a fatal objection, status MUST be BLOCKED_BY_FATAL.
If the scoring gate returned BLOCKED, status MUST be BLOCKED_BY_FATAL.
Never imply automatic execution; this is a manual review draft only.
"""
    def build_user_message(self, ctx: AgentContext) -> str:
        parts = [
            f"Review the complete analysis pipeline results for **{ctx.stock_code}**",
        ]
        if ctx.stock_name:
            parts[0] += f" ({ctx.stock_name})"
        parts.append("and determine the CIO status.")

        # Feed all agent opinions
        if ctx.opinions:
            parts.append("\n## All Agent Opinions (in pipeline order)")
            for i, op in enumerate(ctx.opinions):
                parts.append(f"\n### Agent {i+1}: {op.agent_name}")
                parts.append(f"Signal: {op.signal}, Confidence: {op.confidence:.2f}")
                if op.reasoning:
                    parts.append(f"Reasoning: {op.reasoning}")
                if op.raw_data:
                    parts.append(f"Data: {json.dumps(op.raw_data, ensure_ascii=False, default=str)}")

        # Feed red-blue result
        rb = ctx.get_data("red_blue_result")
        if rb:
            parts.append("\n## Red-Blue Debate")
            parts.append(json.dumps(rb, ensure_ascii=False, default=str))

        # Feed scoring result
        scoring = ctx.get_data("scoring_result")
        if scoring:
            parts.append("\n## Scoring Card")
            parts.append(json.dumps(scoring, ensure_ascii=False, default=str))

        portfolio = ctx.get_data("portfolio_context")
        if portfolio:
            parts.append("\n## Portfolio Context (invest-system DB source of truth)")
            parts.append(json.dumps(portfolio, ensure_ascii=False, default=str))

        # Feed risk flags
        if ctx.risk_flags:
            parts.append("\n## All Risk Flags")
            parts.append(json.dumps(ctx.risk_flags, ensure_ascii=False, default=str))

        return "\n".join(parts)

    def post_process(self, ctx: AgentContext, raw_text: str) -> Optional[AgentOpinion]:
        parsed = try_parse_json(raw_text)
        if parsed is None:
            logger.warning("[CioAgent] failed to parse CIO JSON")
            # Fallback: create a conservative opinion
            return AgentOpinion(
                agent_name=self.agent_name,
                signal="hold",
                confidence=0.3,
                reasoning="CIO review failed to parse — treat as BLOCKED pending manual review",
                raw_data={"status": "BLOCKED_BY_FATAL", "headline": "CIO parsing failed"},
            )

        parsed = _normalize_cio_trade_plan(parsed, ctx)
        status = parsed.get("status", "BLOCKED_BY_FATAL")
        trade_plan = parsed.get("trade_plan") if isinstance(parsed.get("trade_plan"), dict) else {}

        # Store CIO result
        ctx.set_data("cio_result", parsed)

        # Build reasoning summary
        reasoning = (
            f"[{status}] {parsed.get('headline', 'No headline')}\n"
            f"Next: {parsed.get('next_user_action', 'Manual review required')}"
        )

        signal = _trade_action_to_signal(trade_plan.get("action"), status)

        return AgentOpinion(
            agent_name=self.agent_name,
            signal=signal,
            confidence=_cio_confidence_from_status(status),
            reasoning=reasoning,
            raw_data=parsed,
        )


def _normalize_cio_trade_plan(parsed: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Apply deterministic CIO guardrails after model output."""
    result = dict(parsed or {})
    result["schema"] = "cio_trade_plan_v1"
    result.setdefault("disclaimer", "以上为系统分析意见，非交易指令；最终决策由用户人工完成。")

    scoring = ctx.get_data("scoring_result") or {}
    gate = str(scoring.get("gate_result") or "").upper()
    total_score = _coerce_float(scoring.get("total_score"), default=0.0)
    position_range = str(scoring.get("position_size_range") or "0%")
    position_cap = _position_range_cap(position_range)
    fatal_objections = result.get("fatal_objections")
    redblue_unresolved_fatal = _redblue_has_unresolved_fatal(ctx.get_data("red_blue_result"))
    has_fatal = (isinstance(fatal_objections, list) and bool(fatal_objections)) or redblue_unresolved_fatal
    gate_blocked = gate == "BLOCKED" or total_score < 6.0

    trade_plan = result.get("trade_plan")
    if not isinstance(trade_plan, dict):
        trade_plan = {}
    trade_plan = dict(trade_plan)

    result["scoring_snapshot"] = _build_scoring_snapshot(scoring, total_score, gate, position_range)
    result.setdefault("direction", _direction_from_trade_action(trade_plan.get("action")))
    result.setdefault("confidence", "medium" if not gate_blocked else "low")
    result.setdefault("investment_thesis", trade_plan.get("thesis") or result.get("headline") or "")
    result.setdefault(
        "core_reasoning",
        {
            "bull": [],
            "bear": list(result.get("cannot_proceed_reasons") or []),
        },
    )
    result.setdefault("what_would_change", list(trade_plan.get("invalidations") or []))

    if gate_blocked or has_fatal:
        reasons = list(result.get("cannot_proceed_reasons") or [])
        if gate_blocked:
            reasons.append(f"评分门控未通过：score={total_score}/10, gate={gate or 'UNKNOWN'}")
        if has_fatal:
            reasons.append("存在未解决的 fatal objection")
            if redblue_unresolved_fatal:
                existing_fatals = result.get("fatal_objections")
                if not isinstance(existing_fatals, list):
                    existing_fatals = []
                existing_fatals.append({
                    "source_agent": "red_blue",
                    "objection": "红队终局反驳仍保留 fatal remaining_risk",
                })
                result["fatal_objections"] = existing_fatals
        result["status"] = "BLOCKED_BY_FATAL"
        result["direction"] = "无操作"
        result["confidence"] = "low"
        result["can_proceed_to_review"] = False
        result["cannot_proceed_reasons"] = list(dict.fromkeys(str(r) for r in reasons if r))
        result["trade_plan"] = _blocked_trade_plan(position_range)
        result["next_user_action"] = "不执行交易计划；先解决阻断原因后重新审查。"
        return result

    trade_plan.setdefault("action", "wait")
    trade_plan["action"] = _normalize_trade_action(trade_plan.get("action"))
    result["direction"] = _direction_from_trade_action(trade_plan.get("action"))
    target_pct = _coerce_float(trade_plan.get("target_position_pct"), default=None)
    if target_pct is not None:
        target_pct = max(0.0, min(float(target_pct), position_cap))
    trade_plan["target_position_pct"] = target_pct
    trade_plan["position_size_range"] = position_range
    trade_plan["manual_execution_only"] = True

    portfolio = ctx.get_data("portfolio_context")
    has_quantity_inputs = _portfolio_has_quantity_inputs(portfolio)
    if not has_quantity_inputs:
        trade_plan["quantity"] = None
        missing = list(result.get("missing_evidence") or [])
        missing.append("portfolio_context 缺少账户权益/现金或当前价，无法计算具体数量")
        result["missing_evidence"] = list(dict.fromkeys(str(item) for item in missing if item))
    elif trade_plan.get("quantity") is not None:
        quantity = _coerce_float(trade_plan.get("quantity"), default=None)
        trade_plan["quantity"] = quantity if quantity is not None and quantity >= 0 else None

    result["trade_plan"] = trade_plan
    if result.get("status") == "READY_FOR_REVIEW":
        result["can_proceed_to_review"] = True
    return result


def _build_scoring_snapshot(
    scoring: Dict[str, Any],
    total_score: Optional[float],
    gate: str,
    position_range: str,
) -> Dict[str, Any]:
    scores = scoring.get("scores") if isinstance(scoring, dict) else {}
    dimension_scores: Dict[str, Any] = {}
    if isinstance(scores, dict):
        for key, value in scores.items():
            if isinstance(value, dict):
                dimension_scores[key] = {
                    "score": value.get("score"),
                    "rationale": value.get("rationale"),
                }
            else:
                dimension_scores[key] = value
    return {
        "total_score": total_score,
        "gate_result": gate or (scoring.get("gate_result") if isinstance(scoring, dict) else ""),
        "position_size_range": position_range,
        "dimension_scores": dimension_scores,
    }


def _direction_from_trade_action(action: Any) -> str:
    normalized = _normalize_trade_action(action)
    mapping = {
        "buy": "谨慎看多",
        "add": "谨慎看多",
        "hold": "中性持有",
        "wait": "中性等待",
        "reduce": "减仓观察",
        "sell": "谨慎看空",
        "no_action": "无操作",
    }
    return mapping.get(normalized, "中性等待")


def _redblue_has_unresolved_fatal(redblue_result: Any) -> bool:
    if not isinstance(redblue_result, dict):
        return False
    red_team = redblue_result.get("red_team")
    if not isinstance(red_team, dict):
        return False
    final_attacks = red_team.get("final_attacks")
    if not isinstance(final_attacks, list):
        return False
    for attack in final_attacks:
        if not isinstance(attack, dict):
            continue
        remaining_risk = str(attack.get("remaining_risk") or "").strip().lower()
        if remaining_risk in {"fatal", "critical"}:
            return True
    return False


def _blocked_trade_plan(position_range: str) -> Dict[str, Any]:
    return {
        "action": "no_action",
        "target_position_pct": 0.0,
        "quantity": None,
        "entry_zone": None,
        "stop_loss": None,
        "take_profit": None,
        "time_horizon": None,
        "thesis": "评分门控或 fatal objection 阻断，不能形成可执行交易计划。",
        "conditions": ["重新审查前先补齐或解决阻断证据"],
        "invalidations": ["当前计划已被治理层阻断"],
        "position_size_range": position_range or "0%",
        "manual_execution_only": True,
    }


def _normalize_trade_action(value: Any) -> str:
    action = str(value or "").strip().lower()
    aliases = {
        "buy": "buy",
        "add": "add",
        "increase": "add",
        "build": "buy",
        "hold": "hold",
        "wait": "wait",
        "reduce": "reduce",
        "trim": "reduce",
        "sell": "sell",
        "no_action": "no_action",
        "none": "no_action",
    }
    return aliases.get(action, "wait")


def _trade_action_to_signal(action: Any, status: Any) -> str:
    if str(status or "").upper() in {"BLOCKED_BY_FATAL", "NEEDS_EVIDENCE"}:
        return "hold"
    normalized = _normalize_trade_action(action)
    if normalized in {"buy", "add"}:
        return "buy"
    if normalized in {"sell", "reduce"}:
        return "sell"
    return "hold"


def _cio_confidence_from_status(status: Any) -> float:
    normalized = str(status or "").upper()
    if normalized == "READY_FOR_REVIEW":
        return 0.75
    if normalized == "WAIT_ENTRY":
        return 0.6
    if normalized == "NEEDS_EVIDENCE":
        return 0.4
    return 0.3


def _coerce_float(value: Any, default: Optional[float] = 0.0) -> Optional[float]:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("%", "")
    try:
        return float(text)
    except (TypeError, ValueError):
        return default


def _position_range_cap(position_range: str) -> float:
    numbers = [float(match.group(0)) for match in re.finditer(r"\d+(?:\.\d+)?", position_range or "")]
    if not numbers:
        return 0.0
    return max(numbers)


def _portfolio_has_quantity_inputs(portfolio: Any) -> bool:
    if not isinstance(portfolio, dict):
        return False
    total_equity = _coerce_float(portfolio.get("total_equity"), default=None)
    current_price = _coerce_float(portfolio.get("current_price"), default=None)
    cash = _coerce_float(portfolio.get("available_cash"), default=None)
    return (
        total_equity is not None
        and total_equity > 0
        and current_price is not None
        and current_price > 0
        and cash is not None
        and cash >= 0
    )
