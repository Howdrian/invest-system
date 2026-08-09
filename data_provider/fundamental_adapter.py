# -*- coding: utf-8 -*-
"""
AkShare fundamental adapter (fail-open).

This adapter intentionally uses capability probing against multiple AkShare
endpoint candidates. It should never raise to caller; partial data is allowed.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

_DIVIDEND_KEYWORD_MAP: Dict[str, List[str]] = {
    "per_share": [
        "每股派息",
        "每股现金红利",
        "每股分红",
        "每股派现",
        "派现(元/股)",
        "派息(元/股)",
        "税前派息(元/股)",
        "现金分红(税前)",
    ],
    "plan_text": [
        "分配方案",
        "分红方案",
        "实施方案",
        "派息方案",
        "方案",
        "预案",
        "方案说明",
    ],
    "ex_dividend_date": ["除权除息日", "除息日", "除权日", "除权除息", "除息日期"],
    "record_date": ["股权登记日", "登记日"],
    "announce_date": ["公告日期", "公告日", "实施公告日", "预案公告日"],
    "report_date": ["报告期", "报告日期", "截止日期", "统计截止日期"],
}


def _safe_float(value: Any) -> Optional[float]:
    """Best-effort float conversion."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    s = str(value).strip().replace(",", "").replace("%", "")
    if not s:
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    try:
        parsed = pd.to_datetime(value)
    except Exception:
        return None
    if pd.isna(parsed):
        return None
    try:
        return parsed.to_pydatetime()
    except Exception:
        return None


def _normalize_code(raw: Any) -> str:
    s = _safe_str(raw).upper()
    if "." in s:
        s = s.split(".", 1)[0]
    s = re.sub(r"^(SH|SZ|BJ)", "", s)
    return s


def _pick_by_keywords(row: pd.Series, keywords: List[str]) -> Optional[Any]:
    """
    Return first non-empty row value whose column name contains any keyword.
    """
    for col in row.index:
        col_s = str(col)
        if any(k in col_s for k in keywords):
            val = row.get(col)
            if val is not None and str(val).strip() not in ("", "-", "nan", "None"):
                return val
    return None


def _parse_dividend_plan_to_per_share(plan_text: str) -> Optional[float]:
    """Parse per-share cash dividend from Chinese plan text."""
    text = _safe_str(plan_text)
    if not text:
        return None

    for pattern in (
        r"(?:每)?\s*10\s*股?\s*派(?:发)?\s*([0-9]+(?:\.[0-9]+)?)\s*元",
        r"10\s*派\s*([0-9]+(?:\.[0-9]+)?)\s*元",
    ):
        match = re.search(pattern, text)
        if match:
            parsed = _safe_float(match.group(1))
            if parsed is not None and parsed > 0:
                return parsed / 10.0

    match_per_share = re.search(r"每\s*股\s*派(?:发)?\s*([0-9]+(?:\.[0-9]+)?)\s*元", text)
    if match_per_share:
        parsed = _safe_float(match_per_share.group(1))
        if parsed is not None and parsed > 0:
            return parsed
    return None


def _extract_cash_dividend_per_share(row: pd.Series) -> Optional[float]:
    """Extract pre-tax cash dividend per share from a row."""
    plan_text = _safe_str(_pick_by_keywords(row, _DIVIDEND_KEYWORD_MAP["plan_text"]))
    # Keep pre-tax semantics; skip explicit after-tax plans unless pre-tax marker exists.
    if "税后" in plan_text and "税前" not in plan_text and "含税" not in plan_text:
        return None

    direct = _safe_float(_pick_by_keywords(row, _DIVIDEND_KEYWORD_MAP["per_share"]))
    if direct is not None and direct > 0:
        return direct
    return _parse_dividend_plan_to_per_share(plan_text)


def _filter_rows_by_code(df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    code_cols = [c for c in df.columns if any(k in str(c) for k in ("代码", "股票代码", "证券代码", "symbol", "ts_code"))]
    if not code_cols:
        return df

    target = _normalize_code(stock_code)
    for col in code_cols:
        try:
            series = df[col].astype(str).map(_normalize_code)
            filtered = df[series == target]
            if not filtered.empty:
                return filtered
        except Exception:
            continue
    return pd.DataFrame()


def _normalize_report_date(value: Any) -> Optional[str]:
    parsed = _safe_datetime(value)
    return parsed.date().isoformat() if parsed else None


def _build_dividend_payload(
    dividend_df: pd.DataFrame,
    stock_code: str,
    max_events: int = 5,
) -> Dict[str, Any]:
    work_df = _filter_rows_by_code(dividend_df, stock_code)
    if work_df.empty:
        return {}

    now_date = datetime.now().date()
    ttm_start_date = now_date - timedelta(days=365)
    dedupe_keys = set()
    events: List[Dict[str, Any]] = []

    for _, row in work_df.iterrows():
        if not isinstance(row, pd.Series):
            continue
        ex_dt = _safe_datetime(_pick_by_keywords(row, _DIVIDEND_KEYWORD_MAP["ex_dividend_date"]))
        record_dt = _safe_datetime(_pick_by_keywords(row, _DIVIDEND_KEYWORD_MAP["record_date"]))
        announce_dt = _safe_datetime(_pick_by_keywords(row, _DIVIDEND_KEYWORD_MAP["announce_date"]))
        event_dt = ex_dt or record_dt or announce_dt
        if event_dt is None:
            continue
        event_date = event_dt.date()
        if event_date > now_date:
            continue

        per_share = _extract_cash_dividend_per_share(row)
        if per_share is None or per_share <= 0:
            continue

        dedupe_key = (event_date.isoformat(), round(per_share, 6))
        if dedupe_key in dedupe_keys:
            continue
        dedupe_keys.add(dedupe_key)

        events.append(
            {
                "event_date": event_date.isoformat(),
                "ex_dividend_date": ex_dt.date().isoformat() if ex_dt else None,
                "record_date": record_dt.date().isoformat() if record_dt else None,
                "announcement_date": announce_dt.date().isoformat() if announce_dt else None,
                "cash_dividend_per_share": round(per_share, 6),
                "is_pre_tax": True,
            }
        )

    if not events:
        return {}

    events.sort(key=lambda item: item.get("event_date") or "", reverse=True)
    ttm_events: List[Dict[str, Any]] = []
    for item in events:
        event_dt = _safe_datetime(item.get("event_date"))
        if event_dt is None:
            continue
        event_date = event_dt.date()
        if ttm_start_date <= event_date <= now_date:
            ttm_events.append(item)

    return {
        "events": events[:max(1, max_events)],
        "ttm_event_count": len(ttm_events),
        "ttm_cash_dividend_per_share": (
            round(sum(float(item.get("cash_dividend_per_share") or 0.0) for item in ttm_events), 6)
            if ttm_events else None
        ),
        "coverage": "cash_dividend_pre_tax",
        "as_of": now_date.isoformat(),
    }


def _extract_latest_row(df: pd.DataFrame, stock_code: str) -> Optional[pd.Series]:
    """
    Select the most relevant row for the given stock.
    """
    if df is None or df.empty:
        return None

    code_cols = [c for c in df.columns if any(k in str(c) for k in ("代码", "股票代码", "证券代码", "ts_code", "symbol"))]
    target = _normalize_code(stock_code)
    if code_cols:
        for col in code_cols:
            try:
                series = df[col].astype(str).map(_normalize_code)
                matched = df[series == target]
                if not matched.empty:
                    return matched.iloc[0]
            except Exception:
                continue
        return None

    # Fallback: use latest row
    return df.iloc[0]


def _date_column(value: Any) -> Optional[str]:
    """Return a normalized YYYYMMDD column label when one is present."""

    text = re.sub(r"\D", "", _safe_str(value))
    if len(text) != 8:
        return None
    try:
        datetime.strptime(text, "%Y%m%d")
    except ValueError:
        return None
    return text


def _valuation_series_summary(df: Optional[pd.DataFrame]) -> Dict[str, Any]:
    """Normalize a generic dated valuation series into a compact snapshot.

    AkShare endpoints have changed their Chinese/English column names across
    versions.  This parser deliberately relies on data shape as a final
    fallback and never assumes that a single latest value is a percentile.
    """

    if df is None or df.empty:
        return {}
    date_col = next(
        (col for col in df.columns if any(key in str(col).lower() for key in ("date", "日期", "时间"))),
        None,
    )
    value_col = next(
        (
            col
            for col in df.columns
            if col != date_col
            and any(key in str(col).lower() for key in ("value", "值", "市盈", "市净", "估值"))
        ),
        None,
    )
    if value_col is None:
        value_col = next((col for col in df.columns if col != date_col), None)
    if value_col is None:
        return {}

    work = pd.DataFrame({"value": pd.to_numeric(df[value_col], errors="coerce")})
    if date_col is not None:
        work["date"] = pd.to_datetime(df[date_col], errors="coerce")
        work = work.dropna(subset=["value", "date"]).sort_values("date")
    else:
        work = work.dropna(subset=["value"])
    if work.empty:
        return {}

    # Negative PE values are not comparable as valuation multiples.  PB and
    # other positive series are unaffected by this filter.
    comparable = work[work["value"] > 0]
    latest_row = work.iloc[-1]
    latest = _safe_float(latest_row.get("value"))
    result: Dict[str, Any] = {
        "latest": latest,
        "sample_count": int(len(comparable)),
    }
    if date_col is not None and not pd.isna(latest_row.get("date")):
        result["as_of"] = latest_row["date"].date().isoformat()
    if latest is not None and latest > 0 and len(comparable) >= 20:
        result["percentile"] = round(
            float((comparable["value"] <= latest).sum()) / float(len(comparable)) * 100.0,
            2,
        )
    return result


def _metric_value_from_wide_frame(
    df: pd.DataFrame,
    labels: List[str],
    period: str,
) -> Optional[float]:
    """Read a metric from AkShare's metric-as-row financial abstract."""

    if "指标" not in df.columns or period not in df.columns:
        return None
    names = df["指标"].astype(str).str.strip()
    for label in labels:
        exact = df[names == label]
        if not exact.empty:
            return _safe_float(exact.iloc[0].get(period))
    for label in labels:
        matched = df[names.str.contains(re.escape(label), na=False)]
        if not matched.empty:
            return _safe_float(matched.iloc[0].get(period))
    return None


def _growth_percent(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    if current is None or previous in (None, 0):
        return None
    return round((current / previous - 1.0) * 100.0, 4)


def _parse_financial_abstract_wide(df: pd.DataFrame) -> Dict[str, Any]:
    """Parse the current AkShare ``stock_financial_abstract`` wide layout.

    Current AkShare responses store metrics in rows and report dates in
    columns.  Treating the first row as a company record silently produced
    empty or incorrect growth fields, so this layout needs an explicit parser.
    """

    if df is None or df.empty or "指标" not in df.columns:
        return {}
    periods = [period for column in df.columns if (period := _date_column(column))]
    if not periods:
        return {}
    periods = sorted(set(periods), reverse=True)
    latest = periods[0]
    prior_year = str(int(latest[:4]) - 1) + latest[4:]

    revenue_labels = ["营业总收入", "营业收入"]
    net_profit_labels = ["归母净利润", "归属于母公司股东的净利润"]
    cash_flow_labels = ["经营活动产生的现金流量净额", "经营现金流量净额"]
    roe_labels = ["净资产收益率", "ROE"]
    gross_margin_labels = ["毛利率"]

    revenue = _metric_value_from_wide_frame(df, revenue_labels, latest)
    previous_revenue = _metric_value_from_wide_frame(df, revenue_labels, prior_year)
    net_profit = _metric_value_from_wide_frame(df, net_profit_labels, latest)
    previous_net_profit = _metric_value_from_wide_frame(
        df,
        net_profit_labels,
        prior_year,
    )
    operating_cash_flow = _metric_value_from_wide_frame(
        df,
        cash_flow_labels,
        latest,
    )
    roe = _metric_value_from_wide_frame(df, roe_labels, latest)
    gross_margin = _metric_value_from_wide_frame(df, gross_margin_labels, latest)

    growth = {
        "revenue_yoy": _growth_percent(revenue, previous_revenue),
        "net_profit_yoy": _growth_percent(net_profit, previous_net_profit),
        "roe": roe,
        "gross_margin": gross_margin,
    }
    report = {
        "report_date": datetime.strptime(latest, "%Y%m%d").date().isoformat(),
        "comparison_period": (
            datetime.strptime(prior_year, "%Y%m%d").date().isoformat()
            if prior_year in periods
            else None
        ),
        "revenue": revenue,
        "net_profit_parent": net_profit,
        "operating_cash_flow": operating_cash_flow,
        "roe": roe,
    }
    growth = {key: value for key, value in growth.items() if value is not None}
    report = {key: value for key, value in report.items() if value is not None}
    history: List[Dict[str, Any]] = []
    for period in periods[:12]:
        row = {
            "report_date": datetime.strptime(period, "%Y%m%d").date().isoformat(),
            "revenue": _metric_value_from_wide_frame(df, revenue_labels, period),
            "net_profit_parent": _metric_value_from_wide_frame(df, net_profit_labels, period),
            "operating_cash_flow": _metric_value_from_wide_frame(df, cash_flow_labels, period),
            "roe": _metric_value_from_wide_frame(df, roe_labels, period),
            "gross_margin": _metric_value_from_wide_frame(df, gross_margin_labels, period),
        }
        normalized = {key: value for key, value in row.items() if value is not None}
        if len(normalized) > 1:
            history.append(normalized)
    result = {"growth": growth, "financial_report": report}
    if history:
        result["financial_history"] = history
    return result if growth or report or history else {}


def _parse_financial_frame(df: pd.DataFrame, stock_code: str) -> Dict[str, Any]:
    wide = _parse_financial_abstract_wide(df)
    if wide:
        return wide
    row = _extract_latest_row(df, stock_code)
    if row is None:
        return {}
    revenue_yoy = _safe_float(_pick_by_keywords(row, ["营业收入同比", "营收同比", "收入同比", "同比增长"]))
    profit_yoy = _safe_float(_pick_by_keywords(row, ["净利润同比", "净利同比", "归母净利润同比"]))
    roe = _safe_float(_pick_by_keywords(row, ["净资产收益率", "ROE", "净资产收益"]))
    gross_margin = _safe_float(_pick_by_keywords(row, ["毛利率"]))
    report = {
        "report_date": _normalize_report_date(_pick_by_keywords(row, _DIVIDEND_KEYWORD_MAP["report_date"])),
        "revenue": _safe_float(_pick_by_keywords(row, ["营业总收入", "营业收入", "营收"])),
        "net_profit_parent": _safe_float(_pick_by_keywords(row, ["归母净利润", "母公司股东净利润", "净利润"])),
        "operating_cash_flow": _safe_float(
            _pick_by_keywords(row, ["经营活动产生的现金流量净额", "经营现金流", "经营活动现金流"])
        ),
        "roe": roe,
    }
    growth = {
        "revenue_yoy": revenue_yoy,
        "net_profit_yoy": profit_yoy,
        "roe": roe,
        "gross_margin": gross_margin,
    }
    return {
        "growth": {key: value for key, value in growth.items() if value is not None},
        "financial_report": {key: value for key, value in report.items() if value is not None},
    }


class AkshareFundamentalAdapter:
    """AkShare adapter for fundamentals, capital flow and dragon-tiger signals."""

    def _call_df_candidates(
        self,
        candidates: List[Tuple[str, Dict[str, Any]]],
    ) -> Tuple[Optional[pd.DataFrame], Optional[str], List[str]]:
        errors: List[str] = []
        try:
            import akshare as ak
        except Exception as exc:
            return None, None, [f"import_akshare:{type(exc).__name__}"]

        for func_name, kwargs in candidates:
            fn = getattr(ak, func_name, None)
            if fn is None:
                continue
            try:
                df = fn(**kwargs)
                if isinstance(df, pd.Series):
                    df = df.to_frame().T
                if isinstance(df, pd.DataFrame) and not df.empty:
                    return df, func_name, errors
            except Exception as exc:
                errors.append(f"{func_name}:{type(exc).__name__}")
                continue
        return None, None, errors

    def get_fundamental_bundle(self, stock_code: str) -> Dict[str, Any]:
        """
        Return normalized fundamental blocks from AkShare with partial tolerance.
        """
        result: Dict[str, Any] = {
            "status": "not_supported",
            "growth": {},
            "earnings": {},
            "institution": {},
            "source_chain": [],
            "errors": [],
        }

        # Financial indicators
        fin_df, fin_source, fin_errors = self._call_df_candidates([
            ("stock_financial_abstract", {"symbol": stock_code}),
            ("stock_financial_analysis_indicator", {"symbol": stock_code}),
            ("stock_financial_analysis_indicator", {}),
        ])
        result["errors"].extend(fin_errors)
        if fin_df is not None:
            parsed = _parse_financial_frame(fin_df, stock_code)
            if parsed:
                result["growth"] = parsed.get("growth") or {}
                financial_report_payload = parsed.get("financial_report") or {}
                if financial_report_payload:
                    result["earnings"]["financial_report"] = financial_report_payload
                financial_history_payload = parsed.get("financial_history") or []
                if financial_history_payload:
                    result["earnings"]["financial_history"] = financial_history_payload
                result["source_chain"].append(f"growth:{fin_source}")

        # Earnings forecast
        forecast_df, forecast_source, forecast_errors = self._call_df_candidates([
            ("stock_yjyg_em", {"symbol": stock_code}),
            ("stock_yjyg_em", {}),
            ("stock_yjbb_em", {"symbol": stock_code}),
            ("stock_yjbb_em", {}),
        ])
        result["errors"].extend(forecast_errors)
        if forecast_df is not None:
            row = _extract_latest_row(forecast_df, stock_code)
            if row is not None:
                result["earnings"]["forecast_summary"] = _safe_str(
                    _pick_by_keywords(row, ["预告", "业绩变动", "内容", "摘要", "公告"])
                )[:200]
                result["source_chain"].append(f"earnings_forecast:{forecast_source}")

        # Earnings quick report
        quick_df, quick_source, quick_errors = self._call_df_candidates([
            ("stock_yjkb_em", {"symbol": stock_code}),
            ("stock_yjkb_em", {}),
        ])
        result["errors"].extend(quick_errors)
        if quick_df is not None:
            row = _extract_latest_row(quick_df, stock_code)
            if row is not None:
                result["earnings"]["quick_report_summary"] = _safe_str(
                    _pick_by_keywords(row, ["快报", "摘要", "公告", "说明"])
                )[:200]
                result["source_chain"].append(f"earnings_quick:{quick_source}")

        # Dividend details (cash dividend, pre-tax)
        dividend_df, dividend_source, dividend_errors = self._call_df_candidates([
            ("stock_fhps_detail_em", {"symbol": stock_code}),
            ("stock_history_dividend_detail", {"symbol": stock_code, "indicator": "分红", "date": ""}),
            ("stock_dividend_cninfo", {"symbol": stock_code}),
        ])
        result["errors"].extend(dividend_errors)
        if dividend_df is not None:
            dividend_payload = _build_dividend_payload(dividend_df, stock_code, max_events=5)
            if dividend_payload:
                result["earnings"]["dividend"] = dividend_payload
                result["source_chain"].append(f"dividend:{dividend_source}")

        # Institution / top shareholders
        inst_df, inst_source, inst_errors = self._call_df_candidates([
            ("stock_institute_hold", {}),
            ("stock_institute_recommend", {}),
        ])
        result["errors"].extend(inst_errors)
        if inst_df is not None:
            row = _extract_latest_row(inst_df, stock_code)
            if row is not None:
                inst_change = _safe_float(_pick_by_keywords(row, ["增减", "变化", "变动", "持股变化"]))
                result["institution"]["institution_holding_change"] = inst_change
                result["source_chain"].append(f"institution:{inst_source}")

        top10_df, top10_source, top10_errors = self._call_df_candidates([
            ("stock_gdfx_top_10_em", {"symbol": stock_code}),
            ("stock_gdfx_top_10_em", {}),
            ("stock_zh_a_gdhs_detail_em", {"symbol": stock_code}),
            ("stock_zh_a_gdhs_detail_em", {}),
        ])
        result["errors"].extend(top10_errors)
        if top10_df is not None:
            row = _extract_latest_row(top10_df, stock_code)
            if row is not None:
                holder_change = _safe_float(_pick_by_keywords(row, ["增减", "变化", "持股变化", "变动"]))
                result["institution"]["top10_holder_change"] = holder_change
                result["source_chain"].append(f"top10:{top10_source}")

        has_content = bool(result["growth"] or result["earnings"] or result["institution"])
        result["status"] = "partial" if has_content else "not_supported"
        return result

    def get_core_financials(self, stock_code: str) -> Dict[str, Any]:
        """Fetch only the lightweight A-share financial abstract.

        Daily research uses this when the broader fundamental context exceeds
        its latency budget.  It deliberately avoids unrelated optional calls
        and never routes a mainland symbol through Yahoo fundamentals.
        """

        result: Dict[str, Any] = {
            "status": "not_supported",
            "valuation": {},
            "growth": {},
            "earnings": {},
            "institution": {},
            "source_chain": [],
            "errors": [],
        }
        valuation = self.get_core_valuation(stock_code)
        result["errors"].extend(valuation.get("errors") or [])
        if valuation.get("valuation"):
            result["valuation"] = dict(valuation["valuation"])
            result["source_chain"].extend(valuation.get("source_chain") or [])

        fin_df, fin_source, errors = self._call_df_candidates([
            ("stock_financial_abstract", {"symbol": stock_code}),
            ("stock_financial_analysis_indicator", {"symbol": stock_code}),
        ])
        result["errors"].extend(errors)
        if fin_df is not None:
            parsed = _parse_financial_frame(fin_df, stock_code)
            if parsed:
                result["growth"] = parsed.get("growth") or {}
                report = parsed.get("financial_report") or {}
                if report:
                    result["earnings"]["financial_report"] = report
                history = parsed.get("financial_history") or []
                if history:
                    result["earnings"]["financial_history"] = history
                result["source_chain"].append(f"growth:{fin_source}")
        if result["valuation"] or result["growth"] or result["earnings"]:
            result["status"] = "partial"
        return result

    def get_core_valuation(self, stock_code: str) -> Dict[str, Any]:
        """Fetch generic A-share PE/PB history and derive the current snapshot.

        This is a market-wide fallback through AkShare's public Baidu adapter,
        not a ticker-specific rule.  It fails open when the upstream endpoint
        is unavailable.
        """

        result: Dict[str, Any] = {
            "status": "not_supported",
            "valuation": {},
            "source_chain": [],
            "errors": [],
        }
        latest_as_of = ""
        eligible = False
        for indicator, prefix, target_key in (
            ("市盈率(TTM)", "pe", "trailing_pe"),
            ("市净率", "pb", "price_to_book"),
        ):
            frame, source, errors = self._call_df_candidates([
                (
                    "stock_zh_valuation_baidu",
                    {"symbol": stock_code, "indicator": indicator, "period": "近三年"},
                ),
            ])
            result["errors"].extend(errors)
            summary = _valuation_series_summary(frame)
            latest = _safe_float(summary.get("latest"))
            if latest is None:
                continue
            result["valuation"][target_key] = latest
            result["valuation"][f"{prefix}_history_sample_count"] = int(summary.get("sample_count") or 0)
            if summary.get("percentile") is not None:
                result["valuation"][f"{prefix}_history_percentile"] = float(summary["percentile"])
                eligible = True
            latest_as_of = max(latest_as_of, str(summary.get("as_of") or ""))
            if source:
                result["source_chain"].append(f"valuation:{source}:{indicator}")
        if result["valuation"]:
            result["valuation"]["valuation_percentile_eligible"] = 1.0 if eligible else 0.0
            if latest_as_of:
                result["valuation"]["as_of"] = latest_as_of
            result["status"] = "partial"
        return result

    def get_capital_flow(self, stock_code: str, top_n: int = 5) -> Dict[str, Any]:
        """
        Return stock + sector capital flow.
        """
        result: Dict[str, Any] = {
            "status": "not_supported",
            "stock_flow": {},
            "sector_rankings": {"top": [], "bottom": []},
            "source_chain": [],
            "errors": [],
        }

        stock_df, stock_source, stock_errors = self._call_df_candidates([
            ("stock_individual_fund_flow", {"stock": stock_code}),
            ("stock_individual_fund_flow", {"symbol": stock_code}),
            ("stock_individual_fund_flow", {}),
            ("stock_main_fund_flow", {"symbol": stock_code}),
            ("stock_main_fund_flow", {}),
        ])
        result["errors"].extend(stock_errors)
        if stock_df is not None:
            row = _extract_latest_row(stock_df, stock_code)
            if row is not None:
                net_inflow = _safe_float(_pick_by_keywords(row, ["主力净流入", "净流入", "净额"]))
                inflow_5d = _safe_float(_pick_by_keywords(row, ["5日", "五日"]))
                inflow_10d = _safe_float(_pick_by_keywords(row, ["10日", "十日"]))
                result["stock_flow"] = {
                    "main_net_inflow": net_inflow,
                    "inflow_5d": inflow_5d,
                    "inflow_10d": inflow_10d,
                }
                result["source_chain"].append(f"capital_stock:{stock_source}")

        sector_df, sector_source, sector_errors = self._call_df_candidates([
            ("stock_sector_fund_flow_rank", {}),
            ("stock_sector_fund_flow_summary", {}),
        ])
        result["errors"].extend(sector_errors)
        if sector_df is not None:
            name_col = next((c for c in sector_df.columns if any(k in str(c) for k in ("板块", "行业", "名称", "name"))), None)
            flow_col = next((c for c in sector_df.columns if any(k in str(c) for k in ("净流入", "主力", "flow", "净额"))), None)
            if name_col and flow_col:
                work_df = sector_df[[name_col, flow_col]].copy()
                work_df[flow_col] = pd.to_numeric(work_df[flow_col], errors="coerce")
                work_df = work_df.dropna(subset=[flow_col])
                top_df = work_df.nlargest(top_n, flow_col)
                bottom_df = work_df.nsmallest(top_n, flow_col)
                result["sector_rankings"] = {
                    "top": [{"name": _safe_str(r[name_col]), "net_inflow": float(r[flow_col])} for _, r in top_df.iterrows()],
                    "bottom": [{"name": _safe_str(r[name_col]), "net_inflow": float(r[flow_col])} for _, r in bottom_df.iterrows()],
                }
                result["source_chain"].append(f"capital_sector:{sector_source}")

        has_content = bool(result["stock_flow"] or result["sector_rankings"]["top"] or result["sector_rankings"]["bottom"])
        result["status"] = "partial" if has_content else "not_supported"
        return result

    def get_dragon_tiger_flag(self, stock_code: str, lookback_days: int = 20) -> Dict[str, Any]:
        """
        Return dragon-tiger signal in lookback window.
        """
        result: Dict[str, Any] = {
            "status": "not_supported",
            "is_on_list": False,
            "recent_count": 0,
            "latest_date": None,
            "source_chain": [],
            "errors": [],
        }

        df, source, errors = self._call_df_candidates([
            ("stock_lhb_stock_statistic_em", {}),
            ("stock_lhb_detail_em", {}),
            ("stock_lhb_jgmmtj_em", {}),
        ])
        result["errors"].extend(errors)
        if df is None:
            return result

        # Try code filter
        code_cols = [c for c in df.columns if any(k in str(c) for k in ("代码", "股票代码", "证券代码"))]
        target = _normalize_code(stock_code)
        matched = pd.DataFrame()
        for col in code_cols:
            try:
                series = df[col].astype(str).map(_normalize_code)
                cur = df[series == target]
                if not cur.empty:
                    matched = cur
                    break
            except Exception:
                continue
        if matched.empty:
            result["source_chain"].append(f"dragon_tiger:{source}")
            result["status"] = "ok" if code_cols else "partial"
            return result

        date_col = next((c for c in matched.columns if any(k in str(c) for k in ("日期", "上榜", "交易日", "time"))), None)
        parsed_dates: List[datetime] = []
        if date_col is not None:
            for val in matched[date_col].astype(str).tolist():
                try:
                    parsed_dates.append(pd.to_datetime(val).to_pydatetime())
                except Exception:
                    continue
        now = datetime.now()
        start = now - timedelta(days=max(1, lookback_days))
        recent_dates = [d for d in parsed_dates if start <= d <= now]

        result["is_on_list"] = bool(recent_dates)
        result["recent_count"] = len(recent_dates) if recent_dates else int(len(matched))
        result["latest_date"] = max(recent_dates).date().isoformat() if recent_dates else (
            max(parsed_dates).date().isoformat() if parsed_dates else None
        )
        result["status"] = "ok"
        result["source_chain"].append(f"dragon_tiger:{source}")
        return result
