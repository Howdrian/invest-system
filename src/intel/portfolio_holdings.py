# -*- coding: utf-8 -*-
"""Portfolio holding extraction for daily governed analysis selection."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

LIGHT_REVIEW_TYPE_TOKENS = (
    "基金",
    "ETF",
    "LOF",
    "QDII",
    "REIT",
    "FOF",
    "INDEX FUND",
    "MUTUAL FUND",
)
LIGHT_REVIEW_SYMBOL_PREFIXES = (
    "159",
    "160",
    "161",
    "162",
    "163",
    "164",
    "165",
    "166",
    "167",
    "168",
    "169",
    "510",
    "511",
    "512",
    "513",
    "515",
    "516",
    "517",
    "518",
    "588",
)


def normalize_symbol(symbol: str) -> str:
    value = str(symbol or "").strip().replace(" ", "")
    value = re.sub(r"^(SH|SZ|BJ|HK|US)(?=\d|[A-Z])", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\.(SH|SZ|BJ|HK|US)$", "", value, flags=re.IGNORECASE)
    return value.upper() if not value.isdigit() else value


def build_portfolio_holding_snapshot(
    *,
    max_symbols: Optional[int] = None,
    portfolio_service: Optional[Any] = None,
) -> Dict[str, Any]:
    """Return date-safe holding symbols from the invest-system portfolio DB.

    The function is fail-open: missing DB tables, no accounts, or pricing
    failures return a structured degraded/empty status rather than blocking the
    daily report.
    """
    try:
        if portfolio_service is None:
            from src.services.portfolio_service import PortfolioService

            portfolio_service = PortfolioService()
        snapshot = portfolio_service.get_portfolio_snapshot()
    except Exception as exc:
        return {
            "schema": "portfolio_holding_snapshot_v1",
            "status": "degraded",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "symbols": [],
            "positions": [],
            "warnings": [f"portfolio_snapshot_unavailable: {exc}"],
        }

    positions = _extract_positions(snapshot if isinstance(snapshot, dict) else {})
    source = "portfolio_service"
    if not positions:
        env_positions = _extract_env_positions(os.environ.get("PORTFOLIO_HOLDINGS") or os.environ.get("PORTFOLIO_STOCK_LIST"))
        if env_positions:
            positions = env_positions
            source = "env"
        else:
            explicit_path = os.environ.get("PORTFOLIO_HOLDINGS_FILE")
            if explicit_path:
                legacy_positions = _extract_legacy_markdown_positions(Path(explicit_path))
                if legacy_positions:
                    positions = legacy_positions
                    source = "explicit_portfolio_file"
    positions.sort(key=lambda item: _safe_float(item.get("market_value_base")), reverse=True)

    seen: set[str] = set()
    symbols: List[str] = []
    selected_positions: List[Dict[str, Any]] = []
    for item in positions:
        symbol = normalize_symbol(str(item.get("symbol") or ""))
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        symbols.append(symbol)
        copied = dict(item)
        copied["symbol"] = symbol
        tier, reason = _classify_analysis_tier(symbol, copied)
        copied["analysis_tier"] = tier
        copied["analysis_tier_reason"] = reason
        selected_positions.append(copied)

    limit = _coerce_limit(max_symbols)
    omitted: List[str] = []
    if limit is not None and len(symbols) > limit:
        omitted = symbols[limit:]
        symbols = symbols[:limit]
        selected_positions = selected_positions[:limit]

    governed_symbols = [item["symbol"] for item in selected_positions if item.get("analysis_tier") == "governed_deep_review"]
    light_review_symbols = [item["symbol"] for item in selected_positions if item.get("analysis_tier") == "light_review_only"]
    status = "available" if symbols else "empty"
    warnings = ["portfolio_holdings_truncated"] if omitted else []
    return {
        "schema": "portfolio_holding_snapshot_v1",
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": snapshot.get("as_of") if isinstance(snapshot, dict) else None,
        "source": source,
        "symbols": symbols,
        "governed_symbols": governed_symbols,
        "light_review_symbols": light_review_symbols,
        "omitted_symbols": omitted,
        "position_count": len(positions),
        "selected_count": len(symbols),
        "governed_count": len(governed_symbols),
        "light_review_count": len(light_review_symbols),
        "positions": selected_positions,
        "policy": (
            "portfolio holdings are daily light-review inputs; only stock-like holdings can enter "
            "governed deep review, and none bypass RedBlue/Scoring/CIO."
        ),
        "notes": ["fund_etf_lof_holdings_light_review_only"] if light_review_symbols else [],
        "warnings": warnings,
    }


def write_portfolio_holding_snapshot(payload: Dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _extract_positions(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for account in snapshot.get("accounts") or []:
        if not isinstance(account, dict):
            continue
        for pos in account.get("positions") or []:
            if not isinstance(pos, dict):
                continue
            quantity = _safe_float(pos.get("quantity"))
            if quantity <= 0:
                continue
            rows.append({
                "account_id": account.get("account_id"),
                "account_name": account.get("account_name"),
                "symbol": pos.get("symbol"),
                "market": pos.get("market"),
                "type": pos.get("type") or pos.get("asset_type") or pos.get("instrument_type") or pos.get("security_type"),
                "name": pos.get("name") or pos.get("stock_name") or pos.get("display_name"),
                "quantity": quantity,
                "avg_cost": pos.get("avg_cost"),
                "last_price": pos.get("last_price"),
                "market_value_base": _safe_float(pos.get("market_value_base")),
                "unrealized_pnl_pct": pos.get("unrealized_pnl_pct"),
            })
    return rows


def _extract_env_positions(value: Optional[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not value:
        return rows
    for raw in re.split(r"[,;\s]+", value):
        symbol = normalize_symbol(raw)
        if not symbol:
            continue
        rows.append({
            "account_id": None,
            "account_name": "env",
            "symbol": symbol,
            "market": None,
            "type": None,
            "name": None,
            "quantity": 1.0,
            "avg_cost": None,
            "last_price": None,
            "market_value_base": 0.0,
            "unrealized_pnl_pct": None,
        })
    return rows


def _extract_legacy_markdown_positions(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return rows

    in_holdings = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("## 持仓明细"):
            in_holdings = True
            continue
        if in_holdings and line.startswith("## "):
            break
        if not in_holdings or not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 10 or cells[0] in {"标的", "------"} or set(cells[0]) <= {"-"}:
            continue
        status = cells[9]
        if "持仓" not in status:
            continue
        symbol = normalize_symbol(cells[1])
        if not symbol:
            continue
        rows.append({
            "account_id": None,
            "account_name": "legacy_portfolio_md",
            "symbol": symbol,
            "market": cells[2],
            "type": cells[3],
            "quantity": _parse_quantity(cells[5]),
            "avg_cost": _parse_money(cells[6]),
            "last_price": None,
            "market_value_base": _parse_money(cells[7]),
            "unrealized_pnl_pct": None,
            "name": cells[0],
        })
    return rows


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _coerce_limit(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, parsed)


def _classify_analysis_tier(symbol: str, item: Dict[str, Any]) -> tuple[str, str]:
    if _is_light_review_only(symbol, item):
        return "light_review_only", "fund_etf_lof_or_index_like_holding"
    return "governed_deep_review", "stock_like_holding"


def _is_light_review_only(symbol: str, item: Dict[str, Any]) -> bool:
    text = " ".join(
        str(item.get(key) or "")
        for key in ("type", "name", "market", "asset_type", "instrument_type", "security_type")
    ).upper()
    if any(token.upper() in text for token in LIGHT_REVIEW_TYPE_TOKENS):
        return True
    digits = normalize_symbol(symbol)
    if digits.isdigit() and len(digits) == 6 and digits.startswith(LIGHT_REVIEW_SYMBOL_PREFIXES):
        return True
    return False


def _parse_money(value: Any) -> Optional[float]:
    if value is None:
        return None
    match = re.search(r"-?\d[\d,]*(?:\.\d+)?", str(value))
    if not match:
        return None
    return _safe_float(match.group(0).replace(",", ""))


def _parse_quantity(value: Any) -> float:
    if value is None:
        return 0.0
    text = str(value)
    approx = re.search(r"约\s*(\d[\d,]*(?:\.\d+)?)", text)
    if approx:
        return _safe_float(approx.group(1).replace(",", ""))
    match = re.search(r"\d[\d,]*(?:\.\d+)?", text)
    if not match:
        return 0.0
    return _safe_float(match.group(0).replace(",", ""))


def merge_symbols_by_priority(*groups: Iterable[str], limit: int) -> Dict[str, Any]:
    """Merge symbol groups preserving priority and de-duplicating."""
    selected: List[str] = []
    omitted: List[str] = []
    seen: set[str] = set()
    max_items = max(1, int(limit))
    for group in groups:
        for raw in group:
            symbol = normalize_symbol(str(raw))
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            if len(selected) < max_items:
                selected.append(symbol)
            else:
                omitted.append(symbol)
    return {"selected": selected, "omitted": omitted}
