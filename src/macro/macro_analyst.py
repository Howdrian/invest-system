# -*- coding: utf-8 -*-
"""Compatibility entrypoint for the governed Macro Analyst.

The actual Agent implementation lives under ``src.agent.agents`` so it can be
instantiated by the multi-agent orchestrator. This module keeps the plan-facing
``src/macro/macro_analyst.py`` path valid for imports and documentation.
"""

from src.agent.agents.macro_agent import MacroAgent

__all__ = ["MacroAgent"]
