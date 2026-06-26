# -*- coding: utf-8 -*-
"""MacroAgent — governed-mode macro/regime analyst."""

from __future__ import annotations

import json
import logging
from typing import Optional

from src.agent.agents.base_agent import BaseAgent
from src.agent.protocols import AgentContext, AgentOpinion
from src.agent.runner import try_parse_json

logger = logging.getLogger(__name__)


class MacroAgent(BaseAgent):
    """Summarise macro context once before per-stock governed analysis."""

    agent_name = "macro"
    max_steps = 1
    tool_names = []

    def system_prompt(self, ctx: AgentContext) -> str:
        return """\
You are the Macro Analyst for the governed stock-analysis pipeline.
你的任务是把完整宏观报告（macro_review）和轻量宏观上下文（macro_context）压缩成结构化 macro opinion，供后续 Technical/Intel/Risk/CIO 使用。
所有人类可读文本必须使用中文。不要编造数据；宏观上下文缺失时必须标记 degraded。
Polymarket 只能作为外部概率校准和 Red Team 触发，不能作为事实源、交易源或评分越过 6.0 的理由。

Return only JSON:
{
  "schema": "macro_opinion_v1",
  "status": "available|degraded|missing",
  "risk_state": "risk_on|risk_off|neutral|unknown",
  "market_regime": "short label",
  "confidence": 0.0,
  "key_macro_drivers": ["driver 1"],
  "impact_on_stock": "对本标的的影响",
  "positioning_bias": "risk_on/risk_off/neutral 对仓位的约束",
  "data_gaps": ["gap 1"]
}
"""

    def build_user_message(self, ctx: AgentContext) -> str:
        macro_context = ctx.get_data("macro_context") or {}
        macro_review = ctx.get_data("macro_review") or {}
        return "\n".join([
            f"Summarise macro context for {ctx.stock_code} {ctx.stock_name or ''}.",
            "## Macro Review",
            json.dumps(macro_review, ensure_ascii=False, default=str),
            "## Macro Context",
            json.dumps(macro_context, ensure_ascii=False, default=str),
        ])

    def post_process(self, ctx: AgentContext, raw_text: str) -> Optional[AgentOpinion]:
        parsed = try_parse_json(raw_text)
        if parsed is None:
            logger.warning("[MacroAgent] failed to parse macro JSON")
            parsed = {
                "schema": "macro_opinion_v1",
                "status": "degraded",
                "risk_state": "unknown",
                "market_regime": "unknown",
                "confidence": 0.2,
                "key_macro_drivers": [],
                "impact_on_stock": "宏观分析未能结构化解析，按降级处理。",
                "positioning_bias": "neutral",
                "data_gaps": ["macro_agent_parse_failed"],
            }

        ctx.set_data("macro_opinion", parsed)
        confidence = _float(parsed.get("confidence"), default=0.4)
        return AgentOpinion(
            agent_name=self.agent_name,
            signal=_risk_state_to_signal(parsed.get("risk_state")),
            confidence=confidence,
            reasoning=parsed.get("impact_on_stock") or parsed.get("market_regime") or "宏观上下文降级。",
            raw_data=parsed,
        )


def _risk_state_to_signal(value) -> str:
    # Macro is a context/budget layer, not a stock-level trade signal.
    # risk_on/risk_off may adjust risk budget and Red Team questions, but must
    # not emit buy/sell that later agents could mistake for a stock action.
    return "hold"


def _float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
