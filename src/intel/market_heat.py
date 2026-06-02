# -*- coding: utf-8 -*-
"""Daily market-heat snapshot for governed intelligence prompts."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


DEFAULT_OUTPUT_DIR = "reports/market_heat"


def build_market_heat_snapshot(
    symbols: Optional[Iterable[str]] = None,
    *,
    live: bool = False,
    fetcher_manager: Any = None,
) -> Dict[str, Any]:
    symbol_list = [s.strip() for s in (symbols or []) if str(s).strip()]
    if not symbol_list:
        symbol_list = [s.strip() for s in os.getenv("STOCK_LIST", "").split(",") if s.strip()]
    live_payload = _fetch_live_market_heat(fetcher_manager=fetcher_manager) if live else {}
    warnings = list(live_payload.get("warnings") or [])
    hot_stocks = list(live_payload.get("hot_stocks") or [])
    sector_top = list(live_payload.get("sector_top") or [])
    concept_top = list(live_payload.get("concept_top") or [])
    has_live_data = bool(hot_stocks or sector_top or concept_top)
    return {
        "schema": "market_heat_v1",
        "status": "available" if (symbol_list or has_live_data) else "empty_watchlist",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "watchlist": symbol_list,
        "hot_stocks": hot_stocks,
        "sector_top": sector_top,
        "sector_bottom": list(live_payload.get("sector_bottom") or []),
        "concept_top": concept_top,
        "concept_bottom": list(live_payload.get("concept_bottom") or []),
        "focus_items": [
            {
                "symbol": symbol,
                "reason": "watchlist_member",
                "heat_bucket": "watch",
            }
            for symbol in symbol_list[:50]
        ],
        "notes": [
            "market heat 是情报发现入口，只用于提示关注，不直接触发交易。"
        ],
        "warnings": warnings,
    }


def _fetch_live_market_heat(fetcher_manager: Any = None) -> Dict[str, Any]:
    """Best-effort live hot stock / sector / concept rankings."""
    warnings: list[str] = []
    try:
        manager = fetcher_manager
        if manager is None:
            from data_provider import DataFetcherManager

            manager = DataFetcherManager()
        hot_stocks = _safe_call(lambda: manager.get_hot_stocks(20), warnings, "hot_stocks") or []
        sector_top, sector_bottom = _safe_pair(
            _safe_call(lambda: manager.get_sector_rankings(10), warnings, "sector_rankings")
        )
        concept_top, concept_bottom = _safe_pair(
            _safe_call(lambda: manager.get_concept_rankings(10), warnings, "concept_rankings")
        )
        return {
            "hot_stocks": hot_stocks,
            "sector_top": sector_top,
            "sector_bottom": sector_bottom,
            "concept_top": concept_top,
            "concept_bottom": concept_bottom,
            "warnings": warnings,
        }
    except Exception as exc:
        return {"warnings": [f"market_heat_live_unavailable: {exc}"]}


def _safe_call(fn, warnings: list[str], label: str) -> Any:
    try:
        return fn()
    except Exception as exc:
        warnings.append(f"{label}_failed: {exc}")
        return None


def _safe_pair(value: Any) -> tuple[list[Any], list[Any]]:
    if isinstance(value, tuple) and len(value) >= 2:
        return list(value[0] or []), list(value[1] or [])
    return [], []


def write_market_heat_snapshot(payload: Dict[str, Any], output_dir: str = DEFAULT_OUTPUT_DIR) -> Dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "latest_market_heat.json"
    md_path = out / "latest_market_heat.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    lines = ["# 今日关注摘要", "", f"- 状态：{payload.get('status')}", f"- 时间：{payload.get('as_of')}", "", "## Watchlist"]
    for item in payload.get("focus_items") or []:
        lines.append(f"- {item.get('symbol')}: {item.get('reason')} / {item.get('heat_bucket')}")
    if payload.get("hot_stocks"):
        lines.extend(["", "## 人气股"])
        for item in payload.get("hot_stocks") or []:
            code = item.get("code") or item.get("symbol") or item.get("股票代码") or ""
            name = item.get("name") or item.get("股票简称") or item.get("名称") or ""
            lines.append(f"- {code} {name}".strip())
    if payload.get("sector_top"):
        lines.extend(["", "## 板块热度 Top"])
        for item in payload.get("sector_top") or []:
            lines.append(f"- {item}")
    if payload.get("concept_top"):
        lines.extend(["", "## 概念热度 Top"])
        for item in payload.get("concept_top") or []:
            lines.append(f"- {item}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def load_latest_market_heat(output_dir: str = DEFAULT_OUTPUT_DIR) -> Optional[Dict[str, Any]]:
    path = Path(output_dir) / "latest_market_heat.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build daily market heat snapshot")
    parser.add_argument("--symbols", default="", help="Comma-separated symbols; defaults to STOCK_LIST")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--live", action="store_true", help="Fetch live hot-stock/sector/concept rankings")
    args = parser.parse_args(argv)
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()] if args.symbols else None
    payload = build_market_heat_snapshot(symbols, live=args.live)
    paths = write_market_heat_snapshot(payload, args.output_dir)
    print(json.dumps({"status": payload.get("status"), "paths": paths}, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
