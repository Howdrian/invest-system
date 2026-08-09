# -*- coding: utf-8 -*-
"""Sanitize diagnostic text before it reaches logs, ledgers, or artifacts."""

from __future__ import annotations

import re
from typing import Any


_SENSITIVE_QUERY_RE = re.compile(
    r"([?&](?:token|api[_-]?key|apikey|access[_-]?token|auth[_-]?token|"
    r"refresh[_-]?token|secret|password|key)=)([^&#\s]+)",
    re.IGNORECASE,
)
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:API[_-]?KEYS?|ACCESS[_-]?TOKEN|AUTH[_-]?TOKEN|"
    r"REFRESH[_-]?TOKEN|SESSION(?:[_-]?(?:ID|TOKEN))?|CSRF(?:[_-]?TOKEN)?|"
    r"TOKEN|SECRET|PASSWORD|PASSWD|"
    r"COOKIE|WEBHOOK[_-]?URL|SENDKEY))(\s*[:=]\s*)([^\s,;&]+)"
)
_QUOTED_AUTH_HEADER_RE = re.compile(
    r"(?i)([\"']?(?:authorization|proxy[_-]?authorization|cookie|set[_-]?cookie)"
    r"[\"']?\s*[:=]\s*)([\"'])(.*?)(\2)"
)
_AUTH_HEADER_RE = re.compile(
    r"(?i)\b(authorization|proxy[_-]?authorization|cookie|set[_-]?cookie)"
    r"(\s*[:=]\s*).*?"
    r"(?=(?:\s+(?:authorization|proxy[_-]?authorization|cookie|set[_-]?cookie|"
    r"[A-Z0-9_]*(?:API[_-]?KEYS?|WEBHOOK[_-]?URL|SENDKEY))\s*[:=])|[\r\n]|$)"
)
_BEARER_RE = re.compile(r"(?i)\b(Bearer\s+)[A-Za-z0-9._~+/=-]+")
_URL_USERINFO_RE = re.compile(r"(https?://)([^/\s:@]+):([^@\s/]+)@")
_WEBHOOK_URL_RE = re.compile(
    r"(?i)https?://[^\s,;]*(?:"
    r"hooks\.slack\.com/services/|discord(?:app)?\.com/api/webhooks/|"
    r"open\.feishu\.cn/open-apis/bot/.*/hook/|oapi\.dingtalk\.com/robot/send|"
    r"qyapi\.weixin\.qq\.com/cgi-bin/webhook/send|/webhooks?/"
    r")[^\s,;]*"
)
_TOKEN_LIKE_RE = re.compile(
    r"(?i)\b(?:sk-[a-z0-9_-]{16,}|xox[baprs]-[a-z0-9-]{16,}|"
    r"gh[pousr]_[a-z0-9_]{20,})\b"
)


def sanitize_diagnostic_text(value: Any, *, max_len: int = 240) -> str:
    """Return a short text safe for public diagnostics."""

    # Redact header values before whitespace folding.  Cookie values commonly
    # contain spaces and semicolon-delimited pairs, so token-by-token masking
    # can leave later session cookies visible.
    text = str(value)
    text = _QUOTED_AUTH_HEADER_RE.sub(r"\1\2<redacted>\4", text)
    text = _AUTH_HEADER_RE.sub(r"\1\2<redacted>", text)
    text = " ".join(text.split())
    text = _WEBHOOK_URL_RE.sub("<redacted-url>", text)
    text = _URL_USERINFO_RE.sub(r"\1<redacted>:<redacted>@", text)
    text = _SENSITIVE_QUERY_RE.sub(r"\1<redacted>", text)
    text = _BEARER_RE.sub(r"\1<redacted>", text)
    text = _SENSITIVE_ASSIGNMENT_RE.sub(r"\1\2<redacted>", text)
    text = _TOKEN_LIKE_RE.sub("<redacted>", text)
    return text[:max_len]
