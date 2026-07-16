# -*- coding: utf-8 -*-
"""Runtime date helpers for scheduled/local analysis runs.

`ANALYSIS_RUN_DATE` is the single source of truth when present.  It is expected
to be `YYYY-MM-DD` and falls back to Asia/Shanghai today when absent or invalid.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

ANALYSIS_RUN_DATE_ENV = "ANALYSIS_RUN_DATE"
DEFAULT_RUN_TZ = "Asia/Shanghai"


def resolve_analysis_run_date(value: str | None = None, *, env: dict[str, str] | None = None) -> str:
    """Return the analysis run date as `YYYY-MM-DD`.

    Precedence:
    1. explicit `value`
    2. `ANALYSIS_RUN_DATE`
    3. current date in Asia/Shanghai
    """

    source = value
    if source is None:
        source = (env or os.environ).get(ANALYSIS_RUN_DATE_ENV)
    source = str(source or "").strip()
    if source:
        try:
            return datetime.strptime(source, "%Y-%m-%d").date().isoformat()
        except ValueError:
            logger.warning(
                "Invalid %s=%r; falling back to %s today",
                ANALYSIS_RUN_DATE_ENV,
                source,
                DEFAULT_RUN_TZ,
            )
    return datetime.now(ZoneInfo(DEFAULT_RUN_TZ)).date().isoformat()


def compact_run_date(run_date: str | None = None) -> str:
    """Return `YYYYMMDD` for the resolved run date."""

    return resolve_analysis_run_date(run_date).replace("-", "")


def report_filename_for_date(run_date: str | None = None) -> str:
    """Return the canonical daily report markdown filename."""

    return f"report_{compact_run_date(run_date)}.md"
