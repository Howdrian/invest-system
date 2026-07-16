# -*- coding: utf-8 -*-
"""Helpers for provider error messages.

Provider exceptions can include the prepared request URL.  If the provider puts
credentials in query params, ``str(exc)`` may expose secrets to logs, ledgers, or
diagnostics.  Keep this module tiny and dependency-free so fetchers can use it
without changing their data flow.
"""

from __future__ import annotations

from typing import Any

from src.safe_diagnostics import sanitize_diagnostic_text


def redact_provider_error(error: Any) -> str:
    """Return a provider error string safe for logs and artifacts."""

    return sanitize_diagnostic_text(error)
