# -*- coding: utf-8 -*-
"""
ScoringAgent — 5-dimension scoring card with hard gate at < 6.0.

Based on the local governed scoring-card protocol.

Dimensions:
1. Fundamental Strength (0-2)
2. Catalyst Clarity (0-2)
3. Risk/Reward Ratio (0-2)
4. Timing (0-2)
5. Red Team Inverse Strength (0-2)

Gate: total < 6.0 = BLOCKED (non-negotiable)
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from src.agent.agents.base_agent import BaseAgent
from src.agent.protocols import AgentContext, AgentOpinion
from src.agent.runner import try_parse_json

logger = logging.getLogger(__name__)

SCORING_CARD_RULES = """\
## Scoring Dimensions (0-10 total)

### 1. Fundamental Strength (0-2)
For individual stocks:
- 0: Financial deterioration, widening losses, negative FCF
- 0.5: Profitable but slowing or below industry
- 1.0: Stable earnings, reasonable valuation (PE near industry avg)
- 1.5: High growth + improving earnings, PEG < 1
- 2.0: Explosive growth + strong FCF + moat + reasonable valuation

For commodities:
- 0: Supply/demand balanced or oversupply, no structural gap
- 0.5: Gap exists but covered by inventories
- 1.0: Structural supply deficit, inventories falling
- 1.5: Widening deficit, substitute supply needs 3+ years
- 2.0: Severe supply crisis, no short-term relief

### 2. Catalyst Clarity (0-2)
- 0: No identifiable catalyst, purely "it will go up eventually"
- 0.5: Vague catalyst with uncertain timing
- 1.0: Clear catalyst but wide window (3-6 months)
- 1.5: Clear catalyst, narrow window (1-3 months)
- 2.0: Multiple catalysts with specific trigger dates

### 3. Risk/Reward Ratio (0-2)
Calculate: upside = target - current, downside = current - stop_loss
Ratio = upside / downside
- 0: Ratio < 1:1
- 0.5: 1:1 to 1.5:1
- 1.0: 1.5:1 to 2:1
- 1.5: 2:1 to 3:1
- 2.0: > 3:1 (asymmetric opportunity)

### 4. Timing (0-2)
- 0: Chasing (up 20%+) or catching a falling knife
- 0.5: Consolidating at highs, direction unclear
- 1.0: Reasonable range, no obvious chase or knife-catch
- 1.5: Bouncing off key support / breakout with retest confirmation
- 2.0: Oversold rebound after panic / reversal after VIX extreme

### 5. Red Team Inverse Strength (0-2) — INVERTED: stronger red = lower score
- 0: Red team found fatal, irrefutable risk (fraud evidence, confirmed investigation)
- 0.5: Red team found 2-3 severe risks, blue can only partially rebut
- 1.0: Red team found risks but blue has reasonable rebuttals, balanced
- 1.5: Red team attacks mostly rebutted, residual risk manageable
- 2.0: Red team found no substantive fatal risk (RARE — verify red wasn't lazy)

## Gate Rules (HARD — cannot be overridden)
| Score | Action | Position Size |
|-------|--------|---------------|
| < 6.0 | **NO ACTION** — explicitly state reasons | 0% |
| 6.0-7.0 | Small test position | 2-5% of capital |
| 7.0-7.5 | Normal position build | 5-10% |
| 7.5-8.5 | Above-average conviction | 10-15% |
| > 8.5 | High conviction (RARE) | 15-20% |

Absolute cap: single position ≤ 25% of total capital regardless of score.

## Anti-Manipulation Rules
1. Do NOT chase high scores — 8+ should be extremely rare
2. If you find yourself giving 8+ frequently, your standards are too loose
3. 6.0-7.5 is the normal range for good opportunities
4. Record key assumptions — if any break, re-score immediately
5. Selling decisions also go through scoring (reverse the dimension logic)
"""


class ScoringAgent(BaseAgent):
    """5-dimension scoring agent with hard <6.0 gate."""

    agent_name = "scoring"
    max_steps = 1
    tool_names = []

    def system_prompt(self, ctx: AgentContext) -> str:
        stock_info = f"{ctx.stock_code}"
        if ctx.stock_name:
            stock_info += f" ({ctx.stock_name})"

        return f"""\
You are the **评分卡审查员 (Scoring Agent)** for stock {stock_info}.

你的任务：按标准化评分卡对5个维度进行0-10分评分。
这不是主观意见——严格遵循评分标准。
**所有文本（rationale、reasoning、stop_loss_hint 等）必须用中文。**

Your job: assign a 0-10 score across 5 dimensions using the standardised
scoring card. This is NOT a subjective opinion — follow the rubric exactly.
**ALL text fields MUST be in Chinese.**

{SCORING_CARD_RULES}

## Output Format
Return **only** a JSON object:
{{
  "stock": "{ctx.stock_code}",
  "scores": {{
    "fundamental_strength": {{"score": 0.0, "rationale": "..."}},
    "catalyst_clarity": {{"score": 0.0, "rationale": "..."}},
    "risk_reward_ratio": {{"score": 0.0, "rationale": "...", "upside_pct": 0, "downside_pct": 0, "ratio": 0.0}},
    "timing": {{"score": 0.0, "rationale": "..."}},
    "red_team_inverse": {{"score": 0.0, "rationale": "...", "red_team_severity": "low|medium|high|critical"}}
  }},
  "total_score": 0.0,
  "gate_result": "PASS|BLOCKED",
  "position_size_range": "0%|2-5%|5-10%|10-15%|15-20%",
  "key_assumptions": ["Assumption 1", "Assumption 2"],
  "stop_loss_hint": "Suggested stop-loss rationale (NOT a specific price order)",
  "cannot_trade_reasons": ["Reason 1"] or []
}}

If total_score < 6.0, gate_result MUST be "BLOCKED" and position_size_range MUST be "0%".

IMPORTANT: Score what the evidence supports, not what sounds bullish.
If evidence is missing for a dimension, score it conservatively (0.5 or lower).
"""
    def build_user_message(self, ctx: AgentContext) -> str:
        parts = [
            f"Score **{ctx.stock_code}**",
        ]
        if ctx.stock_name:
            parts[0] += f" ({ctx.stock_name})"
        parts.append("using the 5-dimension scoring card rubric.")

        rb = ctx.get_data("red_blue_result")
        if rb:
            parts.append("\n## Red-Blue Debate Result")
            parts.append(json.dumps(rb, ensure_ascii=False, default=str))

        if ctx.opinions:
            parts.append("\n## Prior Agent Opinions")
            for op in ctx.opinions:
                parts.append(f"\n### {op.agent_name} (signal={op.signal}, confidence={op.confidence:.2f})")
                if op.reasoning:
                    parts.append(op.reasoning)

        if ctx.risk_flags:
            parts.append("\n## Risk Flags")
            parts.append(json.dumps(ctx.risk_flags, ensure_ascii=False, default=str))

        return "\n".join(parts)

    def post_process(self, ctx: AgentContext, raw_text: str) -> Optional[AgentOpinion]:
        parsed = try_parse_json(raw_text)
        if parsed is None:
            logger.warning("[ScoringAgent] failed to parse scoring JSON")
            return None

        total = float(parsed.get("total_score", 0))
        gate = parsed.get("gate_result", "BLOCKED")
        scores = parsed.get("scores", {})

        ctx.set_data("scoring_result", parsed)

        if gate == "BLOCKED" or total < 6.0:
            reasons = parsed.get("cannot_trade_reasons", ["Score below 6.0 gate"])
            ctx.add_risk_flag(
                category="scoring_gate",
                description=f"BLOCKED (score={total}/10): {'; '.join(reasons)}",
                severity="high",
            )

        dim_summary = []
        for dim_name, dim_data in scores.items():
            if isinstance(dim_data, dict):
                dim_summary.append(f"{dim_name}: {dim_data.get('score', '?')}/2")
        reasoning = f"Score {total}/10 [{', '.join(dim_summary)}]. Gate: {gate}. {parsed.get('position_size_range', '0%')}"

        return AgentOpinion(
            agent_name=self.agent_name,
            signal=_score_to_signal(total, gate),
            confidence=total / 10.0,
            reasoning=reasoning,
            raw_data=parsed,
            key_levels={
                "total_score": total,
                "gate_blocked": 1.0 if gate == "BLOCKED" else 0.0,
            },
        )


def _score_to_signal(score: float, gate: str) -> str:
    if gate == "BLOCKED" or score < 6.0:
        return "hold"
    if score >= 6.0:
        return "buy"
    return "hold"
