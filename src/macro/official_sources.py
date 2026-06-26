# -*- coding: utf-8 -*-
"""Macro official/free-source context for governed analysis.

The runtime path is fail-open: analysis can proceed with DEGRADED macro context
when network, FMP key, or official data are unavailable. A scheduled refresh can
populate the cache before market runs.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.macro.source_cache import JsonSourceCache

CACHE_KEY = "macro_context_latest"
DEFAULT_TTL_SECONDS = 12 * 60 * 60
REQUIRED_MACRO_FACTORS = (
    "growth",
    "inflation",
    "liquidity_rates",
    "credit",
    "risk_appetite",
    "energy_geo",
)


class MacroContextService:
    """Build/read a compact macro context for Agent prompts."""

    def __init__(
        self,
        cache: Optional[JsonSourceCache] = None,
        timeout_s: float = 4.0,
        fmp_api_key: Optional[str] = None,
    ):
        self.cache = cache or JsonSourceCache()
        self.timeout_s = timeout_s
        self.fmp_api_key = fmp_api_key

    def get_context(
        self,
        *,
        allow_network: bool = False,
        force_refresh: bool = False,
        max_age_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> Dict[str, Any]:
        if not force_refresh:
            cached = self.cache.read(CACHE_KEY, max_age_seconds=max_age_seconds)
            if cached:
                return cached
        if not allow_network:
            return self._degraded(reason="macro_cache_missing_or_stale")
        payload = self.refresh()
        return self.cache.write(CACHE_KEY, payload)

    def refresh(self) -> Dict[str, Any]:
        components: Dict[str, Any] = {}
        warnings: list[str] = []

        fmp_key = (
            self.fmp_api_key
            or os.getenv("FMP_API_KEY")
            or os.getenv("FINANCIAL_MODELING_PREP_API_KEY")
        )
        if fmp_key:
            fmp = self._fetch_fmp_market_context(fmp_key)
            components["fmp"] = fmp
            if fmp.get("status") != "available":
                warnings.append("fmp_unavailable")
        else:
            components["fmp"] = {"status": "missing_key", "source": "FMP", "needs_key": True}
            warnings.append("fmp_key_missing")

        # Free official/public hints. These are intentionally lightweight and
        # can be expanded without changing the Agent-facing contract.
        components["official_calendar"] = {
            "status": "available",
            "source": "system_clock",
            "as_of": datetime.now(timezone.utc).date().isoformat(),
            "note": "官方宏观源刷新入口已接入；无 key 时只提供降级上下文。",
        }

        regime = self._infer_regime(components)
        coverage = self._factor_coverage(components)
        if coverage["available_factors"] < coverage["required_factors"]:
            warnings.append("macro_factor_coverage_incomplete")
        return {
            "schema": "macro_context_v1",
            "status": "REFRESHED" if not warnings and coverage["coverage_score"] >= 1.0 else "PARTIAL" if coverage["available_factors"] > 0 else "DEGRADED",
            "as_of": datetime.now(timezone.utc).isoformat(),
            "regime": regime,
            "coverage": coverage,
            "components": components,
            "warnings": warnings,
            "source_policy": "official/free first; FMP optional enhancement",
        }

    def _fetch_fmp_market_context(self, api_key: str) -> Dict[str, Any]:
        base = "https://financialmodelingprep.com/stable/quote"
        symbols = ["^GSPC", "^IXIC", "^VIX", "HYG", "LQD", "IWM", "SPY", "TLT", "XLY", "XLP"]
        rows: list[Dict[str, Any]] = []
        errors: Dict[str, str] = {}
        for symbol in symbols:
            query = urllib.parse.urlencode({"symbol": symbol, "apikey": api_key})
            url = f"{base}?{query}"
            try:
                with urllib.request.urlopen(url, timeout=self.timeout_s) as response:  # nosec - configured public HTTPS endpoint
                    raw = response.read(512_000)
                parsed = json.loads(raw.decode("utf-8"))
                if isinstance(parsed, list):
                    rows.extend(item for item in parsed if isinstance(item, dict))
                elif isinstance(parsed, dict):
                    rows.append(parsed)
            except Exception as exc:
                errors[symbol] = str(exc)
        if rows:
            return {
                "status": "available" if not errors else "degraded",
                "source": "FMP Stable quote",
                "data": rows,
                "errors": errors,
            }
        if errors:
            return {"status": "unavailable", "source": "FMP Stable quote", "errors": errors}
        return {"status": "unavailable", "source": "FMP Stable quote", "error": "empty_response"}

    @staticmethod
    def _infer_regime(components: Dict[str, Any]) -> Dict[str, Any]:
        fmp = components.get("fmp") if isinstance(components.get("fmp"), dict) else {}
        data = fmp.get("data")
        vix_value = None
        if isinstance(data, list):
            for item in data:
                symbol = str(item.get("symbol") or item.get("name") or "").upper()
                if "VIX" in symbol:
                    vix_value = _to_float(item.get("price") or item.get("lastSalePrice"))
                    break
        if vix_value is None:
            return {"risk_state": "unknown", "confidence": "low", "reason": "macro data degraded"}
        if vix_value >= 30:
            return {"risk_state": "risk_off", "confidence": "medium", "reason": f"VIX elevated: {vix_value}"}
        if vix_value <= 16:
            return {"risk_state": "risk_on", "confidence": "medium", "reason": f"VIX low: {vix_value}"}
        return {"risk_state": "neutral", "confidence": "medium", "reason": f"VIX neutral: {vix_value}"}

    @staticmethod
    def _factor_coverage(components: Dict[str, Any]) -> Dict[str, Any]:
        fmp = components.get("fmp") if isinstance(components.get("fmp"), dict) else {}
        data = fmp.get("data") if isinstance(fmp.get("data"), list) else []
        symbols = {str(row.get("symbol") or row.get("name") or "").upper() for row in data if isinstance(row, dict)}
        available: list[str] = []
        if {"^GSPC", "^IXIC", "SPY"} & symbols:
            available.append("risk_appetite")
        if {"HYG", "LQD"} <= symbols:
            available.append("credit")
        if {"TLT"} & symbols:
            available.append("liquidity_rates")
        if {"^VIX"} & symbols:
            available.append("risk_appetite")
        available = list(dict.fromkeys(available))
        missing = [factor for factor in REQUIRED_MACRO_FACTORS if factor not in available]
        required = len(REQUIRED_MACRO_FACTORS)
        score = round(len(available) / required, 4) if required else 0.0
        return {
            "required_factors": required,
            "available_factors": len(available),
            "coverage_score": score,
            "available": available,
            "missing": missing,
            "boundary": "coverage_score < 1 means PARTIAL/DEGRADED; do not present as full macro regime.",
        }

    @staticmethod
    def _degraded(*, reason: str) -> Dict[str, Any]:
        return {
            "schema": "macro_context_v1",
            "status": "DEGRADED",
            "as_of": datetime.now(timezone.utc).isoformat(),
            "regime": {"risk_state": "unknown", "confidence": "low", "reason": reason},
            "coverage": {
                "required_factors": len(REQUIRED_MACRO_FACTORS),
                "available_factors": 0,
                "coverage_score": 0.0,
                "available": [],
                "missing": list(REQUIRED_MACRO_FACTORS),
            },
            "components": {},
            "warnings": [reason],
            "source_policy": "official/free first; FMP optional enhancement",
        }


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh governed macro context cache")
    parser.add_argument("--refresh", action="store_true", help="Fetch network sources and update cache")
    parser.add_argument("--json", action="store_true", help="Print JSON payload")
    args = parser.parse_args(argv)

    service = MacroContextService()
    payload = service.get_context(allow_network=args.refresh, force_refresh=args.refresh)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"macro_context status={payload.get('status')} regime={payload.get('regime', {}).get('risk_state')}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
