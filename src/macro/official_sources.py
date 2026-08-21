# -*- coding: utf-8 -*-
"""Macro official/free-source context for governed analysis.

The runtime path is fail-open: analysis can proceed with DEGRADED macro context
when network or official data are unavailable. FMP is optional only and never
required for the default free-first review path.
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
from src.safe_diagnostics import sanitize_diagnostic_text
from src.services.run_diagnostics import record_provider_run

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
REQUIRED_FRED_SERIES = {
    "GDP", "UNRATE", "SAHMREALTIME", "CPIAUCSL", "DFF", "DGS10",
    "DGS2", "T10Y2Y", "T10Y3M", "BAMLH0A0HYM2", "DCOILWTICO", "VIXCLS",
}


class MacroContextService:
    """Build/read a compact macro context for Agent prompts."""

    def __init__(
        self,
        cache: Optional[JsonSourceCache] = None,
        timeout_s: float = 4.0,
        fmp_api_key: Optional[str] = None,
        fred_api_key: Optional[str] = None,
        enable_fmp: Optional[bool] = None,
        enable_china_public: bool = False,
    ):
        self.cache = cache or JsonSourceCache()
        self.timeout_s = timeout_s
        self.fmp_api_key = fmp_api_key
        self.fred_api_key = fred_api_key
        self.enable_fmp = enable_fmp
        self.enable_china_public = enable_china_public

    def get_context(
        self,
        *,
        allow_network: bool = False,
        force_refresh: bool = False,
        max_age_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> Dict[str, Any]:
        if not force_refresh:
            cached = self.cache.read(CACHE_KEY, max_age_seconds=max_age_seconds)
            if cached and not self._cache_needs_refresh(cached):
                return cached
        if not allow_network:
            return self._degraded(reason="macro_cache_missing_or_stale")
        payload = self.refresh()
        return self.cache.write(CACHE_KEY, payload)

    def _cache_needs_refresh(self, cached: Dict[str, Any]) -> bool:
        fred_key = self.fred_api_key or os.getenv("FRED_API_KEY")
        if not fred_key:
            return False
        warnings = {str(item) for item in (cached.get("warnings") or [])}
        components = cached.get("components") if isinstance(cached.get("components"), dict) else {}
        fred = components.get("fred") if isinstance(components.get("fred"), dict) else {}
        series = fred.get("series") if isinstance(fred.get("series"), list) else []
        series_ids = {str(row.get("series_id") or "") for row in series if isinstance(row, dict)}
        return (
            "fred_key_missing" in warnings
            or fred.get("status") == "missing_key"
            or not REQUIRED_FRED_SERIES <= series_ids
        )

    def refresh(self) -> Dict[str, Any]:
        components: Dict[str, Any] = {}
        warnings: list[str] = []

        fmp_key = (
            self.fmp_api_key
            or os.getenv("FMP_API_KEY")
            or os.getenv("FINANCIAL_MODELING_PREP_API_KEY")
        )
        if fmp_key and self.enable_fmp is not False:
            fmp = self._fetch_fmp_market_context(fmp_key)
            components["fmp"] = fmp
            if fmp.get("status") != "available":
                fmp["optional"] = True
        else:
            components["fmp"] = {
                "status": "optional_disabled" if self.enable_fmp is False else "optional_not_configured",
                "source": "FMP",
                "optional": True,
                "note": "FMP is an optional paid enhancement and is not required for FULL_REVIEW.",
            }

        fred_key = self.fred_api_key or os.getenv("FRED_API_KEY")
        if fred_key:
            fred = self._fetch_fred_context(fred_key)
            components["fred"] = fred
            if fred.get("status") != "available":
                warnings.append("fred_unavailable")
        else:
            components["fred"] = {"status": "missing_key", "source": "FRED", "needs_key": True}
            warnings.append("fred_key_missing")

        if self.enable_china_public:
            components["china_public"] = self._fetch_china_public_context()

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
            "source_policy": "official/free first; FMP optional non-blocking enhancement",
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
                errors[symbol] = sanitize_diagnostic_text(exc)
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

    def _fetch_fred_context(self, api_key: str) -> Dict[str, Any]:
        series_map = {
            "GDP": "growth",
            "UNRATE": "growth",
            "SAHMREALTIME": "growth",
            "CPIAUCSL": "inflation",
            "DFF": "liquidity_rates",
            "DGS10": "liquidity_rates",
            "DGS2": "liquidity_rates",
            "T10Y2Y": "liquidity_rates",
            "T10Y3M": "liquidity_rates",
            "BAMLH0A0HYM2": "credit",
            "DCOILWTICO": "energy_geo",
            "VIXCLS": "risk_appetite",
        }
        rows: list[Dict[str, Any]] = []
        errors: Dict[str, str] = {}
        for series_id, factor in series_map.items():
            query = urllib.parse.urlencode({
                "series_id": series_id,
                "api_key": api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 260,
            })
            url = f"https://api.stlouisfed.org/fred/series/observations?{query}"
            try:
                started = datetime.now(timezone.utc)
                payload = self._get_json(url, timeout_s=self.timeout_s)
                observations = payload.get("observations") if isinstance(payload, dict) else []
                latest = _latest_numeric_observation(observations)
                if latest:
                    history = [
                        {"date": item.get("date"), "value": _to_float(item.get("value"))}
                        for item in observations
                        if isinstance(item, dict) and _to_float(item.get("value")) is not None
                    ][:260]
                    row = {
                        "series_id": series_id,
                        "factor": factor,
                        "date": latest.get("date"),
                        "value": latest.get("value"),
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                        "history": history,
                    }
                    rows.append(row)
                    record_provider_run(
                        data_type="macro",
                        provider="FRED",
                        operation=f"series_observations:{series_id}",
                        success=True,
                        latency_ms=int((datetime.now(timezone.utc) - started).total_seconds() * 1000),
                        record_count=len(history),
                    )
                else:
                    errors[series_id] = "empty_observations"
                    record_provider_run(
                        data_type="macro",
                        provider="FRED",
                        operation=f"series_observations:{series_id}",
                        success=False,
                        error_type="empty",
                        error_message="empty_observations",
                        record_count=0,
                    )
            except Exception as exc:
                sanitized = sanitize_diagnostic_text(exc)
                errors[series_id] = sanitized
                record_provider_run(
                    data_type="macro",
                    provider="FRED",
                    operation=f"series_observations:{series_id}",
                    success=False,
                    error_type=type(exc).__name__,
                    error_message=sanitized,
                )
        if rows:
            return {
                "status": "available" if not errors else "degraded",
                "source": "FRED",
                "series": rows,
                "errors": errors,
            }
        return {"status": "unavailable", "source": "FRED", "errors": errors or {"FRED": "empty_response"}}

    def _fetch_china_public_context(self) -> Dict[str, Any]:
        """Fetch free, market-wide China macro series through AkShare.

        The upstream endpoints are public Eastmoney datasets.  They are useful
        secondary macro observations, but are not labelled official/verified
        facts because this runtime did not fetch them from NBS directly.
        """

        try:
            import akshare as ak
        except Exception as exc:
            return {
                "status": "unavailable",
                "source": "AkShare public China macro",
                "errors": {"import": sanitize_diagnostic_text(exc)},
            }

        specs = (
            (
                "CN_GDP_YOY",
                "growth",
                "macro_china_gdp",
                "季度",
                "国内生产总值-同比增长",
                "https://data.eastmoney.com/cjsj/gdp.html",
            ),
            (
                "CN_CPI_YOY",
                "inflation",
                "macro_china_cpi",
                "月份",
                "全国-同比增长",
                "https://data.eastmoney.com/cjsj/cpi.html",
            ),
            (
                "CN_PMI_MANUFACTURING",
                "growth",
                "macro_china_pmi",
                "月份",
                "制造业-指数",
                "https://data.eastmoney.com/cjsj/pmi.html",
            ),
        )
        rows: list[Dict[str, Any]] = []
        errors: Dict[str, str] = {}
        for series_id, factor, function_name, date_column, value_column, source_url in specs:
            started = datetime.now(timezone.utc)
            try:
                fn = getattr(ak, function_name)
                frame = fn()
                history = _china_macro_history(frame, date_column=date_column, value_column=value_column)
                if not history:
                    raise ValueError("empty_observations")
                latest = history[0]
                rows.append({
                    "series_id": series_id,
                    "factor": factor,
                    "date": latest["date"],
                    "value": latest["value"],
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "history": history[:120],
                    "source": "Eastmoney via AkShare",
                    "source_url": source_url,
                    "fact_policy": "public_secondary_derived",
                })
                record_provider_run(
                    data_type="macro",
                    provider="AkShareChinaMacro",
                    operation=function_name,
                    success=True,
                    latency_ms=int((datetime.now(timezone.utc) - started).total_seconds() * 1000),
                    record_count=len(history),
                )
            except Exception as exc:
                sanitized = sanitize_diagnostic_text(exc)
                errors[series_id] = sanitized
                record_provider_run(
                    data_type="macro",
                    provider="AkShareChinaMacro",
                    operation=function_name,
                    success=False,
                    error_type=type(exc).__name__,
                    error_message=sanitized,
                    record_count=0,
                )
        if rows:
            return {
                "status": "available" if not errors else "degraded",
                "source": "AkShare public China macro",
                "series": rows,
                "errors": errors,
                "fact_policy": "public_secondary_derived",
            }
        return {
            "status": "unavailable",
            "source": "AkShare public China macro",
            "series": [],
            "errors": errors or {"china_public": "empty_response"},
            "fact_policy": "public_secondary_derived",
        }

    def _get_json(self, url: str, *, timeout_s: float) -> Dict[str, Any]:
        with urllib.request.urlopen(url, timeout=timeout_s) as response:  # nosec - configured public HTTPS endpoint
            raw = response.read(512_000)
        parsed = json.loads(raw.decode("utf-8"))
        return parsed if isinstance(parsed, dict) else {"payload": parsed}

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
        fred = components.get("fred") if isinstance(components.get("fred"), dict) else {}
        fred_series = fred.get("series") if isinstance(fred.get("series"), list) else []
        symbols = {str(row.get("symbol") or row.get("name") or "").upper() for row in data if isinstance(row, dict)}
        fred_factors = {str(row.get("factor") or "") for row in fred_series if isinstance(row, dict)}
        available: list[str] = []
        if {"^GSPC", "^IXIC", "SPY"} & symbols:
            available.append("risk_appetite")
        if {"HYG", "LQD"} <= symbols:
            available.append("credit")
        if {"TLT"} & symbols:
            available.append("liquidity_rates")
        if {"^VIX"} & symbols:
            available.append("risk_appetite")
        for factor in ("growth", "inflation", "liquidity_rates", "credit", "energy_geo", "risk_appetite"):
            if factor in fred_factors:
                available.append(factor)
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
            "source_policy": "official/free first; FMP optional non-blocking enhancement",
        }


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _latest_numeric_observation(observations: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(observations, list):
        return None
    for row in observations:
        if not isinstance(row, dict):
            continue
        value = row.get("value")
        parsed = _to_float(value)
        if parsed is None:
            continue
        return {"date": row.get("date"), "value": parsed}
    return None


def _china_macro_history(frame: Any, *, date_column: str, value_column: str) -> list[Dict[str, Any]]:
    if frame is None or not hasattr(frame, "columns"):
        return []
    if date_column not in frame.columns or value_column not in frame.columns:
        return []
    history: list[Dict[str, Any]] = []
    seen: set[str] = set()
    for _, row in frame.iterrows():
        date = str(row.get(date_column) or "").strip()
        value = _to_float(row.get(value_column))
        if not date or value is None or date in seen:
            continue
        seen.add(date)
        history.append({"date": date, "value": value})
    return history


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh governed macro context cache")
    parser.add_argument("--refresh", action="store_true", help="Fetch network sources and update cache")
    parser.add_argument("--fred-only", action="store_true", help="Skip optional FMP requests")
    parser.add_argument("--json", action="store_true", help="Print JSON payload")
    args = parser.parse_args(argv)

    try:
        from dotenv import load_dotenv

        load_dotenv(os.getenv("ENV_FILE") or ".env", override=False)
    except Exception:
        pass
    service = MacroContextService(
        enable_fmp=False if args.fred_only else None,
        enable_china_public=args.refresh,
    )
    payload = service.get_context(allow_network=args.refresh, force_refresh=args.refresh)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"macro_context status={payload.get('status')} regime={payload.get('regime', {}).get('risk_state')}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
