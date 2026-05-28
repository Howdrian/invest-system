# -*- coding: utf-8 -*-
"""
CioAgent — Chief Investment Officer synthesis agent.

Based on invest-brain ``agents/chief-investment-officer.md``.

Role: aggregate all sub-agent memos and decide whether the analysis
can proceed to the next stage. CIO does NOT score, vote, execute,
or output buy/sell recommendations.

Output statuses:
- READY_FOR_REVIEW: no fatal objection, sufficient evidence → user can review
- WAIT_ENTRY: evidence is valuable but price/event/trend needs confirmation
- NEEDS_EVIDENCE: key evidence missing or agents incomplete
- BLOCKED_BY_FATAL: fatal objection from any agent — must resolve first
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from src.agent.agents.base_agent import BaseAgent
from src.agent.protocols import AgentContext, AgentOpinion
from src.agent.runner import try_parse_json

logger = logging.getLogger(__name__)

CIO_RULES = """\
## CIO Mandate

You are the Chief Investment Officer. Your task is NOT to give trading
advice — it is to aggregate evidence, conflicts, gaps, and fatal objections
from sub-agents into a clear next step for the user.

You answer ONLY these 4 questions:
1. Can this analysis proceed to user review?
2. If not, what evidence is missing or what is the fatal objection?
3. What 1-3 items should the user focus on today?
4. What is the next step: gather evidence, wait for entry, proceed to review?

## Status Determination

| Status | Meaning |
|--------|---------|
| READY_FOR_REVIEW | No fatal objection, key evidence sufficient — user should review |
| WAIT_ENTRY | Evidence is meaningful but price/event/trend needs confirmation |
| NEEDS_EVIDENCE | Key evidence missing — gather more data first |
| BLOCKED_BY_FATAL | Fatal objection from any agent — must resolve or abort |

## Hard Rules
- Do NOT output a 0-10 score
- Do NOT output buy, sell, add, reduce, position size, or order quantity
- Do NOT override a fatal objection with majority opinion
- Do NOT bypass the red-team protocol
- If the RedBlueAgent found a fatal attack that was not rebutted, status cannot be READY_FOR_REVIEW
- If the ScoringAgent blocked (score < 6.0), status must be BLOCKED_BY_FATAL or NEEDS_EVIDENCE
- Polymarket, Kronos, options, and technical indicators are side evidence only — never upgrade to trade conclusion

## Allowed Outputs
- "Ready for user review"
- "Wait for entry confirmation"
- "Missing evidence — gather more data"
- "Blocked by fatal objection"

## Forbidden Outputs
- "Can buy / can sell"
- "Suggest building position / adding / small starter position"
- "Score X/10"
- "Position X%"
"""


class CioAgent(BaseAgent):
    """CIO synthesis agent — aggregates, does not decide."""

    agent_name = "cio"
    max_steps = 1
    tool_names = []

    def system_prompt(self, ctx: AgentContext) -> str:
        stock_info = f"{ctx.stock_code}"
        if ctx.stock_name:
            stock_info += f" ({ctx.stock_name})"

        return f"""\
You are the **Chief Investment Officer** reviewing the analysis for {stock_info}.

{CIO_RULES}

## Output Format
Return **only** a JSON object:
{{
  "schema": "cio_review_v1",
  "stock": "{ctx.stock_code}",
  "status": "READY_FOR_REVIEW | WAIT_ENTRY | NEEDS_EVIDENCE | BLOCKED_BY_FATAL",
  "headline": "One-sentence summary of the situation",
  "can_proceed_to_review": true or false,
  "cannot_proceed_reasons": ["Reason 1"] or [],
  "top_watch_items": ["Item 1", "Item 2", "Item 3"],
  "fatal_objections": [
    {{"source_agent": "agent_name", "objection": "description"}}
  ],
  "missing_evidence": ["Evidence gap 1"],
  "next_user_action": "Clear next step for the user",
  "summary": "2-4 sentence executive summary of the analysis"
}}

CRITICAL: If any agent raised a fatal objection, status MUST be BLOCKED_BY_FATAL.
If the scoring gate returned BLOCKED, status MUST be BLOCKED_BY_FATAL.
Never output buy/sell/sizing/score in any field.
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

        status = parsed.get("status", "BLOCKED_BY_FATAL")
        can_proceed = parsed.get("can_proceed_to_review", False)

        # Store CIO result
        ctx.set_data("cio_result", parsed)

        # Build reasoning summary
        reasoning = (
            f"[{status}] {parsed.get('headline', 'No headline')}\n"
            f"Next: {parsed.get('next_user_action', 'Manual review required')}"
        )

        # Signal mapping: CIO doesn't give buy/sell, only proceed/hold
        if can_proceed and status == "READY_FOR_REVIEW":
            signal = "hold"  # "hold" = proceed to user review, not "buy"
        else:
            signal = "hold"  # blocked or waiting = hold

        return AgentOpinion(
            agent_name=self.agent_name,
            signal=signal,
            confidence=0.5,  # CIO confidence is about process completeness, not price direction
            reasoning=reasoning,
            raw_data=parsed,
        )
