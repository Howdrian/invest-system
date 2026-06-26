# -*- coding: utf-8 -*-
"""
RedBlueAgent — mandatory red-blue debate before any trading decision.

Based on the local governed red-team protocol.

Flow:
1. Blue team: construct 3 bull arguments (data + timeframe + catalyst)
2. Red team: attack each argument with 3 fatal counterpoints (evidence + probability)
3. Blue team: rebut each red attack with evidence or concede the weakness
4. Red team: final counter-rebuttal, separating fatal objections from residual risk
5. Arbitrator: assess which side is stronger, identify blind spots, output verdict

This agent does NOT use tools — it works purely from the context
accumulated by prior agents (Technical, Intel, Risk).
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from src.agent.agents.base_agent import BaseAgent
from src.agent.protocols import AgentContext, AgentOpinion
from src.agent.runner import try_parse_json

logger = logging.getLogger(__name__)

# Anti-flattery firewall — injected into system prompt
ANTI_FLATTERY_FIREWALL = """\
## Anti-Flattery Firewall (HARD RULE)
The following behaviours are FORBIDDEN:
1. Do NOT soften red-team attacks because the user appears excited or confident
2. Do NOT give vague arbitration ("both sides have merit" is banned)
3. Do NOT yield without reason if the user disputes a finding
4. Do NOT fabricate precise numbers to dress up guesses
5. Do NOT selectively present data — bad news and good news MUST both appear

If the user's message contains: "this will definitely go up", "all in",
"everyone is buying", "FOMO", "can't miss this boat" — red-team attacks
MUST be upgraded to maximum severity.
"""


class RedBlueAgent(BaseAgent):
    """Red-Blue debate agent — structured bull vs bear argumentation."""

    agent_name = "red_blue"
    max_steps = 2  # pure reasoning, no tools needed
    tool_names = []  # no tool access — synthesises from context

    def system_prompt(self, ctx: AgentContext) -> str:
        stock_info = f"{ctx.stock_code}"
        if ctx.stock_name:
            stock_info += f" ({ctx.stock_name})"

        return f"""\
You are the **红蓝对抗仲裁官 (Red-Blue Debate Arbitrator)** for stock {stock_info}.

你的任务不是给投资建议。你主持蓝队（多方）与红队（空方）之间的结构化辩论，
然后给出中立的仲裁结果。**所有输出必须使用中文。**

Your job is NOT to give investment advice. You run a structured debate
between a bull case (Blue Team) and a bear case (Red Team), then deliver
a neutral arbitration. **ALL output text MUST be in Chinese.**

## Step 1 — Blue Team (Bull Case)
Construct **3 core arguments** supporting a position in {stock_info}.
Each argument MUST include:
- Specific data/facts (not vague statements)
- Timeframe (when does this thesis play out?)
- Catalyst (what event would make this thesis pay off?)

## Step 2 — Red Team (Bear Case)
Attack EACH blue-team argument with **at least 1 fatal counterpoint**.
Find at least 3 total fatal risks. Each must include:
- Which blue argument it attacks
- Specific evidence (not "might go down")
- Estimated probability of this risk materialising

Red Team discipline:
- If you can't find 3 fatal risks, the bull arguments are too vague — criticise them harder
- Every attack must be verifiable
- You may challenge the reliability of the data sources themselves

## Step 3 — Blue Team Rebuttal
For EACH red attack:
- Either rebut it with specific evidence already present in context
- Or concede it as a real weakness
- Do not invent new facts

## Step 4 — Red Team Final Counter-Rebuttal
For EACH blue rebuttal:
- State whether the rebuttal fully resolves, partially resolves, or fails to
  resolve the attack
- Identify remaining fatal objections, if any
- Escalate weak-source or missing-data problems

## Step 5 — Arbitration (Neutral Judge)
1. Assess which side has stronger evidence
2. Identify blind spots BOTH sides missed
3. Output a 0-10 confidence score for the bull case
4. Give a clear verdict

{ANTI_FLATTERY_FIREWALL}

## Output Format
Return **only** a JSON object:
{{
  "blue_team": {{
    "arguments": [
      {{
        "thesis": "Core argument",
        "data": "Supporting facts/numbers",
        "timeframe": "When this plays out",
        "catalyst": "What triggers the payoff"
      }}
    ],
    "rebuttals": [
      {{
        "targets_red_attack": 1,
        "response": "Blue rebuttal or concession",
        "evidence": "Context evidence used, or data gap",
        "resolved": "yes|partial|no"
      }}
    ],
    "overall_strength": 0-10
  }},
  "red_team": {{
    "attacks": [
      {{
        "targets_blue_arg": 1-3,
        "fatal_risk": "The specific risk",
        "evidence": "Verifiable evidence",
        "probability": "Estimated likelihood (low/medium/high/critical)"
      }}
    ],
    "final_attacks": [
      {{
        "targets_blue_rebuttal": 1,
        "counterpoint": "Final red response",
        "remaining_risk": "fatal|material|minor|resolved",
        "evidence_gap": "Missing evidence if any"
      }}
    ],
    "overall_strength": 0-10
  }},
  "arbitration": {{
    "blue_strength": 0-10,
    "red_strength": 0-10,
    "stronger_side": "blue|red|tie",
    "blind_spots": ["Blind spot 1", "Blind spot 2"],
    "confidence_in_bull_case": 0-10,
    "verdict": "One clear sentence on which side wins and why"
  }},
  "emotion_injection_detected": false,
  "emotion_signal": ""
}}
"""
    def build_user_message(self, ctx: AgentContext) -> str:
        parts = [
            f"Run a FULL red-blue debate for **{ctx.stock_code}**",
        ]
        if ctx.stock_name:
            parts[0] += f" ({ctx.stock_name})"

        # Feed prior agent opinions as context
        if ctx.opinions:
            parts.append("\n## Prior Agent Opinions (context only)")
            for op in ctx.opinions:
                parts.append(f"\n### {op.agent_name}")
                if op.reasoning:
                    parts.append(f"Reasoning: {op.reasoning}")
                if op.signal:
                    parts.append(f"Signal: {op.signal}")
                if op.key_levels:
                    parts.append(f"Key levels: {json.dumps(op.key_levels, ensure_ascii=False)}")
                if op.raw_data:
                    parts.append(f"Data: {json.dumps(op.raw_data, ensure_ascii=False, default=str)}")

        # Feed risk flags
        if ctx.risk_flags:
            parts.append("\n## Risk Flags (context only)")
            parts.append(json.dumps(ctx.risk_flags, ensure_ascii=False, default=str))

        # Feed pre-fetched data
        if ctx.data:
            parts.append("\n## Market Data (context only)")
            parts.append(json.dumps(ctx.data, ensure_ascii=False, default=str))

        # Emotion injection check
        user_query = ctx.query or ""
        parts.append(f"\n## User's Original Query")
        parts.append(user_query if user_query else "(No user query — system-triggered review)")
        parts.append("\nCheck the user query for emotional signals per the Anti-Flattery Firewall rules.")

        return "\n".join(parts)

    def post_process(self, ctx: AgentContext, raw_text: str) -> Optional[AgentOpinion]:
        parsed = try_parse_json(raw_text)
        if parsed is None:
            logger.warning("[RedBlueAgent] failed to parse debate JSON")
            return None

        arbitration = parsed.get("arbitration", {})
        confidence = float(arbitration.get("confidence_in_bull_case", 5)) / 10.0

        # Store debate result in context for downstream agents
        ctx.set_data("red_blue_result", parsed)

        # If emotion injection detected, flag context
        if parsed.get("emotion_injection_detected"):
            ctx.add_risk_flag(
                category="behavioral",
                description=f"Emotion injection detected: {parsed.get('emotion_signal', 'unknown')}",
                severity="high",
            )

        return AgentOpinion(
            agent_name=self.agent_name,
            signal=_debate_to_signal(arbitration.get("stronger_side", "tie")),
            confidence=confidence,
            reasoning=arbitration.get("verdict", ""),
            raw_data=parsed,
        )


def _debate_to_signal(stronger_side: str) -> str:
    mapping = {
        "blue": "buy",
        "red": "sell",
        "tie": "hold",
    }
    return mapping.get(stronger_side, "hold")
