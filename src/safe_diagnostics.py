# -*- coding: utf-8 -*-
"""Sanitize diagnostic text before it reaches logs, ledgers, or artifacts."""

from __future__ import annotations

import re
from typing import Any


_SENSITIVE_QUERY_RE = re.compile(
    r"([?&](?:token|api[_-]?key|apikey|access_token|key)=)([^&#\s]+)",
    re.IGNORECASE,
)
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)\b("
    r"FINNHUB_API_KEY|TAVILY_API_KEYS?|FRED_API_KEY|ALPHAVANTAGE_API_KEY|"
    r"FMP_API_KEY|FINANCIAL_MODELING_PREP_API_KEY|TUSHARE_TOKEN"
    r")\s*=\s*([^\s;,]+)"
)


def sanitize_diagnostic_text(value: Any, *, max_len: int = 240) -> str:
    """Return a short text safe for public diagnostics."""

    text = str(value).replace("\n", " ")
    text = _SENSITIVE_QUERY_RE.sub(r"\1<redacted>", text)
    text = _SENSITIVE_ASSIGNMENT_RE.sub(r"\1=<redacted>", text)
    return text[:max_len]
