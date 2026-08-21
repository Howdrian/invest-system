"""Small timestamp helpers shared by research ledgers."""

from __future__ import annotations

from datetime import date, datetime, timezone, tzinfo
from typing import Any, Mapping


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def iso_timestamp(value: Any, *, naive_timezone: tzinfo | None = None) -> str:
    """Return an ISO timestamp/date without inventing a missing source time."""

    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        parsed = value
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=naive_timezone or timezone.utc)
        return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return ""
    # ``datetime.fromisoformat('YYYY-MM-DD')`` silently invents midnight.
    # Preserve source precision instead: a date-only observation must remain a
    # date so Reader copy never displays a fabricated 00:00/08:00 timestamp.
    if len(text) == 10:
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            return date.fromisoformat(text[:10]).isoformat()
        except ValueError:
            return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=naive_timezone or timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def first_timestamp(source: Any, *keys: str) -> str:
    for key in keys:
        if isinstance(source, Mapping):
            value = source.get(key)
        else:
            value = getattr(source, key, None)
        normalized = iso_timestamp(value)
        if normalized:
            return normalized
    return ""


def date_part(value: Any, fallback: str = "") -> str:
    normalized = iso_timestamp(value)
    return normalized[:10] if normalized else fallback
