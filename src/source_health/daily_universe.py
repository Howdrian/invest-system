"""Daily universe builder for product-facing reports.

This layer decides *what the daily report is about*.  It intentionally does
not call network providers; provider collection is handled by
``subject_evidence`` so universe construction stays deterministic.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence


DEFAULT_MACRO_SERIES = ["DGS10", "DGS2", "FEDFUNDS", "CPIAUCSL", "UNRATE", "M2SL"]


def build_daily_universe(
    docs_dir: str | Path,
    run_date: str,
    *,
    symbols: Sequence[str] | None = None,
    market: str | None = None,
) -> Dict[str, Any]:
    """Build a deterministic daily universe payload.

    ``symbols`` is an explicit test/local override.  If omitted, only an
    explicitly configured ``STOCK_LIST`` is used; the upstream default
    ``600519`` is not treated as a daily universe fallback.
    """

    docs = Path(docs_dir)
    env_values = _read_env_values()
    explicit_symbols = _clean_symbols(symbols or [])
    stock_list_symbols = explicit_symbols or _symbols_from_env(env_values)
    candidates = _candidate_symbols_from_docs(docs, run_date)
    region = (market or _env_get("MARKET_REVIEW_REGION", env_values) or "cn").strip() or "cn"

    groups = [
        {
            "name": "watchlist",
            "source": "cli_symbols" if explicit_symbols else "STOCK_LIST" if stock_list_symbols else "empty",
            "symbols": stock_list_symbols,
            "whyIncluded": (
                "本地验收显式指定标的"
                if explicit_symbols
                else "来自本地 STOCK_LIST 配置"
                if stock_list_symbols
                else "自选股为空；不回退到单只 600519 fixture"
            ),
            "evidenceRequirements": ["price", "fundamentals", "filings_events", "news_sentiment"],
        },
        {
            "name": "portfolio",
            "source": "not_connected",
            "symbols": [],
            "snapshotAvailable": False,
            "scope": "not_connected",
            "whyIncluded": "公开日报未接入私有持仓；不得从 PORTFOLIO_HOLDINGS 自动展开标的",
            "evidenceRequirements": ["portfolio", "price", "risk"],
        },
        {
            "name": "candidates",
            "source": "market_cycle_or_market_heat",
            "symbols": candidates,
            "whyIncluded": "来自候选池、市场热度或筛选产物；只做观察清单",
            "evidenceRequirements": ["price", "news_sentiment"],
        },
        {
            "name": "market",
            "source": "MARKET_REVIEW_REGION",
            "symbols": [],
            "market": region,
            "whyIncluded": "日报必须包含市场状态；指数不作为个股 subject",
            "evidenceRequirements": ["price", "macro", "news_sentiment"],
        },
        {
            "name": "macro",
            "source": "FRED/market_cycle",
            "symbols": [],
            "series": DEFAULT_MACRO_SERIES,
            "whyIncluded": "日报必须包含宏观背景；宏观序列不作为个股 subject",
            "evidenceRequirements": ["macro"],
        },
    ]
    subject_symbols = _dedupe([*stock_list_symbols, *candidates])
    mode = "market_and_candidates" if not stock_list_symbols else "multi_subject_daily"
    return {
        "schema": "daily_universe_v1",
        "runDate": run_date,
        "mode": mode,
        "market": region,
        "subjectSymbols": subject_symbols,
        "groups": groups,
        "notes": [
            "Daily universe is not allowed to silently fall back to single 600519.",
            "Source smoke proves provider availability; subject evidence proves current report coverage.",
        ],
    }


def write_daily_universe(
    docs_dir: str | Path,
    run_date: str,
    *,
    symbols: Sequence[str] | None = None,
    market: str | None = None,
) -> Dict[str, Any]:
    docs = Path(docs_dir)
    payload = build_daily_universe(docs, run_date, symbols=symbols, market=market)
    out = docs / "run_status" / run_date / "daily_universe.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def load_daily_universe(docs_dir: str | Path, run_date: str) -> Dict[str, Any]:
    path = Path(docs_dir) / "run_status" / run_date / "daily_universe.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _symbols_from_env(env_values: Mapping[str, str]) -> List[str]:
    raw = _env_get("STOCK_LIST", env_values)
    symbols = _clean_symbols(raw.replace("，", ",").split(","))
    # Guard against upstream's old minimum fallback being mistaken as a daily
    # universe. A user may still explicitly pass --symbols 600519.
    if symbols == ["600519"]:
        return []
    return symbols


def _env_get(name: str, env_values: Mapping[str, str]) -> str:
    current = os.getenv(name)
    if current is not None:
        return str(current)
    return str(env_values.get(name, "") or "")


def _read_env_values() -> Dict[str, str]:
    env_file = os.getenv("ENV_FILE")
    env_path = Path(env_file) if env_file else Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return {}
    try:
        from dotenv import dotenv_values  # noqa: WPS433 - optional parser

        return {str(k): "" if v is None else str(v) for k, v in dotenv_values(env_path, interpolate=False).items() if k}
    except Exception:
        values: Dict[str, str] = {}
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip().strip("'\"")
        return values


def _candidate_symbols_from_docs(docs: Path, run_date: str) -> List[str]:
    out: List[str] = []
    for path in [
        docs / "market_cycle" / run_date / "11_deep_review_queue.json",
        docs / "market_heat" / "latest_market_heat.json",
    ]:
        payload = _read_json(path)
        if isinstance(payload, Mapping):
            _collect_symbol_like(payload, out)
    return _dedupe(out)[:20]


def _collect_symbol_like(value: Any, out: List[str]) -> None:
    if isinstance(value, Mapping):
        for key in ("symbol", "code", "stock_code", "ts_code"):
            if key in value:
                out.extend(_clean_symbols([str(value.get(key) or "")]))
        for item in value.values():
            _collect_symbol_like(item, out)
    elif isinstance(value, list):
        for item in value:
            _collect_symbol_like(item, out)


def _clean_symbols(values: Iterable[str]) -> List[str]:
    return _dedupe([str(item).strip() for item in values if str(item or "").strip()])


def _dedupe(values: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.upper()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
