"""Daily universe builder for product-facing reports.

This layer decides *what the daily report is about*.  It intentionally does
not call network providers; provider collection is handled by
``subject_evidence`` so universe construction stays deterministic.
"""

from __future__ import annotations

import json
import logging
import os
import re
from calendar import monthrange
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from src.utils.market_review_region import normalize_market_review_region_lenient


DEFAULT_MACRO_SERIES = ["DGS10", "DGS2", "FEDFUNDS", "CPIAUCSL", "UNRATE", "M2SL"]


def research_window(run_date: str, *, recent_change_months: int = 1, outlook_months: int = 2) -> Dict[str, Any]:
    """Separate recent changes, historical context and the default decision horizon.

    Dates describe research emphasis, never a data-retention or holding rule.
    The legacy date fields remain aliases for existing artifact consumers.
    """
    anchor = date.fromisoformat(run_date)
    def shift(months: int) -> str:
        year, month0 = divmod(anchor.year * 12 + anchor.month - 1 + months, 12)
        month = month0 + 1
        return date(year, month, min(anchor.day, monthrange(year, month)[1])).isoformat()
    recent_start, outlook_end = shift(-recent_change_months), shift(outlook_months)
    horizon = '1–2' if outlook_months == 2 else str(outlook_months)
    return {
        "schema": "research_window_v2", "asOf": run_date,
        "lookbackStart": recent_start, "outlookEnd": outlook_end,
        "recentChanges": {"start": recent_start, "end": run_date, "months": recent_change_months},
        "decisionHorizon": {"start": run_date, "end": outlook_end, "months": outlook_months, "flexible": True},
        "label": f"聚焦未来{horizon}个月的机会与风险；结合近期变化及必要的中长期背景。",
        "basis": "近期变化窗口不截断历史资料，也不是数据过期标准；建议期限是默认重点，不是持有指令。具体观点可采用不同期限，说明当前影响及改变判断的条件。",
        "displayLines": [
            f"近期变化：{recent_start} 至 {run_date}（重点，不是历史资料截止线）",
            f"建议适用期：{run_date} 至 {outlook_end}（默认重点，具体观点可另列期限）",
            "历史参照：按部门使用相关历史与最新财报；实际覆盖范围以证据为准。",
        ],
    }


def _research_months(name: str, values: Mapping[str, str], default: int) -> int:
    raw = _env_get(name, values).strip()
    if not raw:
        return default
    try:
        months = int(raw)
        if 1 <= months <= 60:
            return months
    except ValueError:
        pass
    # Do not echo arbitrary env contents (including accidentally pasted keys).
    logging.getLogger(__name__).warning("%s must be 1..60 months; using default %s", name, default)
    return default


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
    raw_region = market if market is not None else _env_get("MARKET_REVIEW_REGION", env_values)
    region = normalize_market_review_region_lenient(raw_region) or "cn"

    groups = [
        {
            "name": "watchlist",
            "source": "cli_symbols" if explicit_symbols else "STOCK_LIST" if stock_list_symbols else "empty",
            "symbols": stock_list_symbols,
            "whyIncluded": (
                "用户手动指定的自选跟踪标的；不限制行业研究范围"
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
            "whyIncluded": "系统发现的研究候选，独立于用户自选；热度不是推荐，须经过公司研究与CIO取舍",
            "evidenceRequirements": ["price", "fundamentals", "filings_events", "news_sentiment"],
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
        "researchWindow": research_window(
            run_date,
            recent_change_months=_research_months("RESEARCH_RECENT_CHANGE_MONTHS", env_values, 1),
            outlook_months=_research_months("RESEARCH_OUTLOOK_MONTHS", env_values, 2),
        ),
        "market": region,
        "subjectSymbols": subject_symbols,
        "groups": groups,
        "notes": [
            "Daily universe is not allowed to silently fall back to single 600519.",
            "Source smoke proves provider availability; subject evidence proves current report coverage.",
        ],
    }


def integrate_discovered_candidates(
    universe: Mapping[str, Any], facts: Sequence[Mapping[str, Any]], *, per_market: int = 3,
) -> Dict[str, Any]:
    """Discover research subjects from provider rows, not an LLM ticker guess.

    A popularity result is a research lead, not an investment recommendation.
    The full list remains evidence; bounded enrichment prevents unbounded scans.
    """
    result = {**universe, "groups": [dict(group) for group in universe.get("groups") or []]}
    discoveries = []
    seen = set()
    as_of = date.fromisoformat(str(universe["runDate"]))
    # Candidate leads retain a recent-data rule independent of the chosen
    # research horizon. A six-month outlook does not revive stale hot lists.
    freshness_start = research_window(as_of.isoformat(), recent_change_months=1)["lookbackStart"]
    counts: Dict[str, int] = {}
    for fact in facts:
        if fact.get("metric") not in {"hot_stocks", "screening_candidates", "sector_constituents"}:
            continue
        if fact.get("evidence_scope", "subject_evidence") != "subject_evidence":
            continue
        observed = str(fact.get("as_of") or "")[:10]
        if not observed or not freshness_start <= observed <= as_of.isoformat():
            continue
        for row in fact.get("records") or []:
            if not isinstance(row, Mapping):
                continue
            symbol = str(row.get("symbol") or row.get("code") or row.get("stock_code") or "").upper()
            symbol = re.sub(r"^(?:SH|SZ|BJ)(?=\d{6}$)", "", symbol)
            if not re.fullmatch(r"(?:\d{6}|HK\d{4,5}|[A-Z]{1,5}(?:\.[A-Z])?)", symbol):
                continue
            market = "cn" if symbol.isdigit() else "hk" if symbol.startswith("HK") and symbol[2:].isdigit() else "us"
            if symbol in seen or counts.get(market, 0) >= per_market:
                continue
            seen.add(symbol)
            counts[market] = counts.get(market, 0) + 1
            discoveries.append({"symbol": symbol, "name": row.get("name") or symbol,
                                "market": market, "sourceEvidenceId": fact.get("id"),
                                "asOf": fact.get("as_of"),
                                "whyIncluded": "来自本期筛选/热度/行业成分资料；进入公司研究，不等于买入推荐"})
    for group in result["groups"]:
        if group.get("name") == "candidates":
            group["symbols"] = _dedupe([*group.get("symbols", []), *(row["symbol"] for row in discoveries)])
            group["discoveries"] = discoveries
            group["source"] = "provider_discovery_and_existing_screening"
    result["subjectSymbols"] = _dedupe([*result.get("subjectSymbols", []), *(row["symbol"] for row in discoveries)])
    return result


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
    raw = _env_get("STOCK_LIST", env_values) or _env_get("STOCK_LIST_CONFIG", env_values)
    symbols = _clean_symbols(raw.replace("，", ",").split(","))
    # STOCK_LIST is explicit user input, including a single chosen stock.
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
