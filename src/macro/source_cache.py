# -*- coding: utf-8 -*-
"""Small JSON cache for macro/governed support data."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JsonSourceCache:
    """Filesystem JSON cache with TTL and fail-open reads."""

    def __init__(self, cache_dir: Optional[str] = None):
        base = cache_dir or os.getenv("MACRO_CACHE_DIR") or "data/macro_cache"
        self.cache_dir = Path(base)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in key)
        return self.cache_dir / f"{safe}.json"

    def read(self, key: str, *, max_age_seconds: Optional[int] = None) -> Optional[Dict[str, Any]]:
        path = self.path_for(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        if max_age_seconds is not None:
            fetched_at = _parse_dt(payload.get("fetched_at"))
            if fetched_at is None or utc_now() - fetched_at > timedelta(seconds=max_age_seconds):
                return None
        return payload

    def write(self, key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(payload)
        data.setdefault("fetched_at", utc_now().isoformat())
        self.path_for(key).write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return data


def _parse_dt(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
