# -*- coding: utf-8 -*-
"""EvidenceGateAgent — deterministic evidence gate before red-blue review.

This stage does not call tools or an LLM. It records whether the governed
pipeline has enough evidence to proceed into red-blue/scoring, and makes data
gaps explicit for later agents and Pages.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from src.agent.protocols import AgentContext, AgentOpinion, StageResult, StageStatus


class EvidenceGateAgent:
    """Pre-red-blue evidence gate for governed stock analysis."""

    agent_name = "evidence_gate"
    max_steps = 1

    def __init__(
        self,
        tool_registry=None,
        llm_adapter=None,
        skill_instructions: str = "",
        technical_skill_policy: str = "",
    ):
        self.tool_registry = tool_registry
        self.llm_adapter = llm_adapter
        self.skill_instructions = skill_instructions
        self.technical_skill_policy = technical_skill_policy

    def run(
        self,
        ctx: AgentContext,
        progress_callback=None,
        timeout_seconds: Optional[float] = None,
    ) -> StageResult:
        """Evaluate evidence sufficiency and append an AgentOpinion."""
        t0 = time.time()
        payload = self._evaluate(ctx)
        ctx.set_data("evidence_gate_result", payload)

        status = str(payload.get("status") or "NEEDS_EVIDENCE")
        fatal = bool(payload.get("fatal_objection"))
        if fatal:
            ctx.add_risk_flag(
                category="evidence_gate",
                description="EvidenceGate found a fatal objection before red-blue review",
                severity="high",
            )

        opinion = AgentOpinion(
            agent_name=self.agent_name,
            signal="sell" if fatal else "hold",
            confidence=0.35 if status != "PASS" else 0.7,
            reasoning=payload.get("conclusion") or "证据门已完成。",
            raw_data=payload,
        )
        ctx.add_opinion(opinion)

        return StageResult(
            stage_name=self.agent_name,
            status=StageStatus.COMPLETED,
            opinion=opinion,
            duration_s=round(time.time() - t0, 2),
            tokens_used=0,
            tool_calls_count=0,
            meta={
                "raw_text": json.dumps(payload, ensure_ascii=False, indent=2),
                "models_used": ["deterministic/evidence_gate"],
                "tool_calls_log": [],
            },
        )

    def _evaluate(self, ctx: AgentContext) -> Dict[str, Any]:
        missing: List[str] = []
        warnings: List[str] = []

        if not _truthy(ctx.get_data("realtime_quote")):
            missing.append("realtime_quote")
        if not _truthy(ctx.get_data("daily_history")) and not _truthy(ctx.get_data("trend_result")):
            missing.append("daily_history_or_trend_result")
        if not _has_opinion(ctx, "technical"):
            missing.append("technical_opinion")
        if not _has_opinion(ctx, "intel"):
            warnings.append("intel_opinion_missing_or_degraded")
        if not _has_opinion(ctx, "risk"):
            warnings.append("risk_opinion_missing_or_degraded")

        macro_review = ctx.get_data("macro_review") or {}
        macro_status = str(macro_review.get("status") or "").upper()
        if macro_review and macro_status and macro_status != "REFRESHED":
            warnings.append(f"macro_review_{macro_status.lower()}")
        elif not macro_review:
            warnings.append("macro_review_missing")

        high_risks = [
            flag for flag in ctx.risk_flags
            if isinstance(flag, dict) and str(flag.get("severity") or "").lower() == "high"
        ]
        fatal = bool(high_risks)
        status = "BLOCKED" if fatal else ("NEEDS_EVIDENCE" if missing else "PASS")

        facts = [
            f"opinions={','.join(op.agent_name for op in ctx.opinions) or 'none'}",
            f"missing_evidence_count={len(missing)}",
            f"risk_flags={len(ctx.risk_flags)}",
            f"macro_status={macro_status or 'UNKNOWN'}",
        ]
        reasoning = [
            "EvidenceGate 只判断证据是否足够进入红蓝对抗，不产生交易动作。",
            "缺少技术/行情核心证据会标记 NEEDS_EVIDENCE；高严重度风险会升级为 BLOCKED。",
        ]
        if warnings:
            reasoning.append("降级项：" + "；".join(warnings))
        conclusion = (
            "存在高严重度风险，进入阻断状态。"
            if fatal
            else "核心证据不足，后续治理层应保守处理。"
            if missing
            else "核心证据可进入红蓝对抗，仍需评分和 TradeDecisionGate 门控。"
        )

        return {
            "schema": "evidence_gate_v1",
            "stock": ctx.stock_code,
            "status": status,
            "facts": facts,
            "reasoning": reasoning,
            "conclusion": conclusion,
            "missing_evidence": missing,
            "warnings": warnings,
            "fatal_objection": fatal,
            "high_risk_flags": high_risks,
            "no_trade_execution": True,
        }


def _has_opinion(ctx: AgentContext, agent_name: str) -> bool:
    return any(op.agent_name == agent_name for op in ctx.opinions)


def _truthy(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, dict, str)):
        return bool(value)
    return True
