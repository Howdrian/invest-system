"""Fixed local smoke profiles for source-health verification."""

from __future__ import annotations

from typing import Dict, List


FULL_REVIEW_SMOKE_SYMBOLS: Dict[str, List[str]] = {
    "a_share": ["600519", "000001"],
    "us": ["AAPL"],
    "hk": ["HK00700"],
}


def full_review_smoke_symbols() -> List[str]:
    """Return deterministic A/HK/US symbols for local source smoke checks."""

    return [
        *FULL_REVIEW_SMOKE_SYMBOLS["a_share"],
        *FULL_REVIEW_SMOKE_SYMBOLS["us"],
        *FULL_REVIEW_SMOKE_SYMBOLS["hk"],
    ]
