"""Free-first official/event evidence fetchers.

These adapters are read-only. They do not score stocks and do not turn search
hits into verified facts.  Official filing/disclosure portals can create
``verified_fact`` evidence; broad event/news APIs stay ``discovery``.
"""

from __future__ import annotations

import json
import os
import re
import ssl
import urllib.parse
import urllib.request
from functools import lru_cache
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence
from urllib.error import HTTPError

from src.safe_diagnostics import sanitize_diagnostic_text
from src.source_health.temporal import iso_timestamp, utc_now_iso


SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
RELIEFWEB_REPORTS_URL = "https://api.reliefweb.int/v2/reports"
OFAC_SDN_ADVANCED_URL = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN_ADVANCED.XML"
CNINFO_QUERY_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_STATIC_BASE = "http://static.cninfo.com.cn/"
SSE_QUERY_URL = "https://query.sse.com.cn/security/stock/queryCompanyBulletin.do"
SSE_STATIC_BASE = "https://www.sse.com.cn"
SZSE_ANN_LIST_URL = "https://www.szse.cn/api/disc/announcement/annList"
SZSE_STATIC_BASE = "https://www.szse.cn"
HKEX_TITLE_SEARCH_URL = "https://www1.hkexnews.hk/search/titlesearch.xhtml"
HKEX_STOCK_PREFIX_URL = "https://www1.hkexnews.hk/search/prefix.do"
HKEX_STATIC_BASE = "https://www1.hkexnews.hk"
SEC_COMPANYFACT_CONCEPTS = (
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "NetIncomeLoss",
    "OperatingIncomeLoss",
    "Assets",
    "CommonStockSharesOutstanding",
)
SEC_COMPANYFACT_MAX_AGE_DAYS = 730
DEFAULT_GEO_QUERY_TERMS = (
    "global sanctions export controls",
    "armed conflict escalation",
    "trade restrictions tariffs",
    "energy supply disruption",
    "Red Sea shipping disruption",
    "Taiwan Strait tensions",
    "Middle East conflict",
    "Ukraine conflict",
)


@dataclass(frozen=True)
class OfficialEventSourceResult:
    provider_runs: List[Dict[str, Any]]
    evidence_facts: List[Dict[str, Any]]
    raw: Dict[str, Any]


class OfficialEventSourceClient:
    def __init__(self, timeout_s: float = 5.0, sec_user_agent: str | None = None):
        self.timeout_s = timeout_s
        self.sec_user_agent = sec_user_agent or os.getenv("SEC_USER_AGENT") or "invest-system/0.1 contact@example.com"
        self._sec_tickers_cache: Dict[str, str] | None = None

    def fetch(self, *, symbols: Sequence[str], run_date: str, query_terms: Sequence[str] | None = None) -> OfficialEventSourceResult:
        provider_runs: List[Dict[str, Any]] = []
        evidence_facts: List[Dict[str, Any]] = []
        raw: Dict[str, Any] = {"schema": "official_event_sources_v1", "runDate": run_date, "symbols": list(symbols)}

        sec = self.fetch_sec_filings(symbols=symbols, run_date=run_date)
        provider_runs.extend(sec.provider_runs)
        evidence_facts.extend(sec.evidence_facts)
        raw["sec"] = sec.raw

        sec_facts = self.fetch_sec_companyfacts(symbols=symbols, run_date=run_date)
        provider_runs.extend(sec_facts.provider_runs)
        evidence_facts.extend(sec_facts.evidence_facts)
        raw["secCompanyfacts"] = sec_facts.raw

        cninfo = self.fetch_cninfo_announcements(symbols=symbols, run_date=run_date)
        provider_runs.extend(cninfo.provider_runs)
        evidence_facts.extend(cninfo.evidence_facts)
        raw["cninfo"] = cninfo.raw

        exchange = self.fetch_exchange_disclosures(symbols=symbols, run_date=run_date)
        provider_runs.extend(exchange.provider_runs)
        evidence_facts.extend(exchange.evidence_facts)
        raw["exchangeDisclosures"] = exchange.raw

        hkex = self.fetch_hkex_disclosures(symbols=symbols, run_date=run_date)
        provider_runs.extend(hkex.provider_runs)
        evidence_facts.extend(hkex.evidence_facts)
        raw["hkex"] = hkex.raw

        subject_terms = [str(item).strip() for item in (query_terms or symbols) if str(item).strip()]
        geo_terms = _geo_query_terms(subject_terms)
        mixed_search_terms = [*subject_terms[:4], *geo_terms[:4]]
        raw["queryScopes"] = {"subject": subject_terms, "geopolitical": geo_terms}

        gdelt = self.fetch_gdelt_events(query_terms=geo_terms, run_date=run_date)
        provider_runs.extend(gdelt.provider_runs)
        evidence_facts.extend(gdelt.evidence_facts)
        raw["gdelt"] = gdelt.raw

        tavily = self.fetch_tavily_search(query_terms=mixed_search_terms, run_date=run_date)
        provider_runs.extend(tavily.provider_runs)
        evidence_facts.extend(tavily.evidence_facts)
        raw["tavily"] = tavily.raw

        reliefweb = self.fetch_reliefweb_reports(query_terms=geo_terms, run_date=run_date)
        provider_runs.extend(reliefweb.provider_runs)
        evidence_facts.extend(reliefweb.evidence_facts)
        raw["reliefweb"] = reliefweb.raw

        ofac = self.fetch_ofac_sanctions_signals(query_terms=subject_terms, run_date=run_date)
        provider_runs.extend(ofac.provider_runs)
        evidence_facts.extend(ofac.evidence_facts)
        raw["ofac"] = ofac.raw

        return OfficialEventSourceResult(provider_runs=provider_runs, evidence_facts=evidence_facts, raw=raw)

    def fetch_sec_filings(self, *, symbols: Sequence[str], run_date: str, max_filings_per_symbol: int = 3) -> OfficialEventSourceResult:
        us_symbols = [symbol.upper() for symbol in symbols if _is_us_ticker(symbol)]
        if not us_symbols:
            return _single_provider_result("SEC_EDGAR", "filings_events", "sec_submissions", False, "not_supported", "no_us_symbols")

        try:
            ticker_map = self._sec_ticker_map()
        except Exception as exc:
            return _single_provider_result("SEC_EDGAR", "filings_events", "sec_ticker_map", False, "failed", _sanitize_error(exc))

        evidence: List[Dict[str, Any]] = []
        raw_symbols: Dict[str, Any] = {}
        for symbol in us_symbols:
            cik = ticker_map.get(symbol)
            if not cik:
                raw_symbols[symbol] = {"status": "not_found"}
                continue
            url = SEC_SUBMISSIONS_URL.format(cik=cik)
            try:
                payload = self._get_json(url, headers=self._sec_headers())
            except Exception as exc:
                raw_symbols[symbol] = {"status": "failed", "error": _sanitize_error(exc)}
                continue
            filings = _sec_recent_filings(payload, symbol=symbol, cik=cik, run_date=run_date, limit=max_filings_per_symbol)
            raw_symbols[symbol] = {"status": "available" if filings else "empty", "cik": cik, "filings": filings}
            for idx, filing in enumerate(filings):
                evidence.append({
                    "id": f"sec:{symbol}:{filing.get('accessionNumber') or idx}",
                    "domain": "filings_events",
                    "symbol": symbol,
                    "value": f"{filing.get('form')} {filing.get('filingDate')} {filing.get('primaryDocument')}",
                    "as_of": filing.get("filingDate") or run_date,
                    "provider": "SEC_EDGAR",
                    "source_url": filing.get("sourceUrl") or url,
                    "confidence": "high",
                    "fact_type": "verified_fact",
                    "filing_form": filing.get("form"),
                })
        success = bool(evidence)
        run = _provider_run(
            "SEC_EDGAR",
            "filings_events",
            "sec_submissions",
            success,
            len(evidence),
            None if success else "empty",
            None if success else "no_recent_filings_or_cik_match",
        )
        return OfficialEventSourceResult([run], evidence, {"symbols": raw_symbols})

    def fetch_sec_companyfacts(self, *, symbols: Sequence[str], run_date: str, max_facts_per_symbol: int = 4) -> OfficialEventSourceResult:
        us_symbols = [symbol.upper() for symbol in symbols if _is_us_ticker(symbol)]
        if not us_symbols:
            return _single_provider_result("SEC_EDGAR", "fundamentals", "sec_companyfacts", False, "not_supported", "no_us_symbols")

        try:
            ticker_map = self._sec_ticker_map()
        except Exception as exc:
            return _single_provider_result("SEC_EDGAR", "fundamentals", "sec_ticker_map", False, "failed", _sanitize_error(exc))

        evidence: List[Dict[str, Any]] = []
        raw_symbols: Dict[str, Any] = {}
        for symbol in us_symbols:
            cik = ticker_map.get(symbol)
            if not cik:
                raw_symbols[symbol] = {"status": "not_found"}
                continue
            url = SEC_COMPANYFACTS_URL.format(cik=cik)
            try:
                payload = self._get_json(url, headers=self._sec_headers())
            except Exception as exc:
                raw_symbols[symbol] = {"status": "failed", "error": _sanitize_error(exc)}
                continue
            rows = _sec_companyfacts(payload, symbol=symbol, run_date=run_date, limit=max_facts_per_symbol)
            raw_symbols[symbol] = {"status": "available" if rows else "empty", "cik": cik, "facts": rows}
            for idx, row in enumerate(rows):
                evidence.append({
                    "id": f"sec_companyfacts:{symbol}:{row.get('concept')}:{row.get('unit')}:{row.get('end') or idx}",
                    "domain": "fundamentals",
                    "symbol": symbol,
                    "value": f"{row.get('concept')}={row.get('value')} {row.get('unit')} @ {row.get('end')} filed {row.get('filed')}",
                    "as_of": row.get("filed") or row.get("end") or run_date,
                    "provider": "SEC_EDGAR",
                    "source_url": url,
                    "confidence": "high",
                    "fact_type": "verified_fact",
                    "metric": row.get("concept"),
                    "period_start": row.get("start"),
                    "period_end": row.get("end"),
                    "filing_form": row.get("form"),
                    "fiscal_period": row.get("fp"),
                    "fiscal_year": row.get("fy"),
                    "frame": row.get("frame"),
                })
        success = bool(evidence)
        run = _provider_run(
            "SEC_EDGAR",
            "fundamentals",
            "sec_companyfacts",
            success,
            len(evidence),
            None if success else "empty",
            None if success else "no_companyfacts_or_cik_match",
        )
        return OfficialEventSourceResult([run], evidence, {"symbols": raw_symbols})

    def fetch_gdelt_events(self, *, query_terms: Sequence[str], run_date: str, max_records: int = 10) -> OfficialEventSourceResult:
        terms = [str(item).strip() for item in query_terms if str(item).strip()]
        if not terms:
            return _single_provider_result("GDELT", "news_sentiment", "gdelt_doc", False, "not_supported", "no_query_terms")
        query = _or_query(_gdelt_term(term) for term in terms[:8])
        start, end = _datetime_window(run_date, days=14)
        params = {
            "query": query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": str(max_records),
            "sort": "datedesc",
            "startdatetime": start,
            "enddatetime": end,
        }
        url = f"{GDELT_DOC_URL}?{urllib.parse.urlencode(params)}"
        try:
            payload = self._get_json(url)
        except Exception as exc:
            return _single_provider_result("GDELT", "news_sentiment", "gdelt_doc", False, _error_type(exc), _sanitize_error(exc))
        articles = payload.get("articles") if isinstance(payload, Mapping) else []
        rows = [item for item in articles if isinstance(item, Mapping)]
        evidence = [
            {
                "id": f"gdelt:{idx}:{str(row.get('url') or '')[:80]}",
                "domain": "news_sentiment",
                "symbol": "",
                "value": str(row.get("title") or row.get("url") or "GDELT article"),
                "as_of": _yyyymmdd_to_iso(row.get("seendate")) or run_date,
                "provider": "GDELT",
                "source_url": str(row.get("url") or url),
                "confidence": "low",
                "fact_type": "discovery",
            }
            for idx, row in enumerate(rows)
        ]
        run = _provider_run(
            "GDELT",
            "news_sentiment",
            "gdelt_doc",
            bool(rows),
            len(rows),
            None if rows else "empty",
            None if rows else "empty_response",
        )
        return OfficialEventSourceResult([run], evidence, {"query": query, "dateWindow": f"{start}~{end}", "url": url, "articles": rows[:max_records]})

    def fetch_tavily_search(self, *, query_terms: Sequence[str], run_date: str, max_records: int = 6) -> OfficialEventSourceResult:
        """Fetch Tavily search results as discovery evidence.

        Tavily is an AI/search discovery source. Its results never become
        verified facts; they only help the geo/news/intel departments discover
        source documents that can be checked elsewhere.
        """

        keys = _env_csv("TAVILY_API_KEYS", "TAVILY_API_KEY")
        if not keys:
            return _single_provider_result("Tavily", "news_sentiment", "tavily_search", False, "auth_missing", "TAVILY_API_KEYS_missing")
        terms = [str(item).strip() for item in query_terms if str(item).strip()]
        if not terms:
            return _single_provider_result("Tavily", "news_sentiment", "tavily_search", False, "not_supported", "no_query_terms")
        query = _or_query(_search_term(term) for term in terms[:8])
        body = json.dumps(
            {
                "query": query,
                "topic": "news",
                "search_depth": "basic",
                "max_results": max_records,
                "include_answer": False,
                "include_raw_content": False,
            }
        ).encode("utf-8")
        errors: List[str] = []
        for key in keys:
            try:
                payload = self._post_json_body(
                    "https://api.tavily.com/search",
                    data=body,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "Authorization": f"Bearer {key}",
                    },
                )
            except Exception as exc:
                errors.append(_sanitize_error(exc))
                if _error_type(exc) in {"auth_missing", "rate_limited"}:
                    continue
                continue
            rows = payload.get("results") if isinstance(payload, Mapping) else []
            results = [row for row in rows if isinstance(row, Mapping)]
            evidence = [
                {
                    "id": f"tavily:{idx}:{_safe_id(row.get('url') or row.get('title') or idx)}",
                    "domain": "news_sentiment",
                    "symbol": "",
                    "value": str(row.get("title") or row.get("content") or row.get("url") or "Tavily result"),
                    "as_of": _iso_date(row.get("published_date")) or run_date,
                    "provider": "Tavily",
                    "source_url": str(row.get("url") or "https://api.tavily.com/search"),
                    "confidence": "low",
                    "fact_type": "discovery",
                }
                for idx, row in enumerate(results[:max_records])
            ]
            run = _provider_run(
                "Tavily",
                "news_sentiment",
                "tavily_search",
                bool(evidence),
                len(evidence),
                None if evidence else "empty",
                None if evidence else "empty_response",
            )
            return OfficialEventSourceResult([run], evidence, {"query": query, "results": results[:max_records]})

        error_type = "failed"
        if errors and all("429" in error or "rate" in error.lower() for error in errors):
            error_type = "rate_limited"
        elif errors and all("401" in error or "403" in error or "unauthorized" in error.lower() for error in errors):
            error_type = "auth_missing"
        return _single_provider_result("Tavily", "news_sentiment", "tavily_search", False, error_type, "; ".join(errors[:2]) or "tavily_failed")

    def fetch_reliefweb_reports(self, *, query_terms: Sequence[str], run_date: str, max_records: int = 6) -> OfficialEventSourceResult:
        """Fetch humanitarian/conflict context as geopolitical discovery.

        ReliefWeb requires an appname.  If no approved appname is configured we
        do not fake success; diagnostics gets an explicit ``auth_missing`` row.
        """

        appname = _env_value("RELIEFWEB_APPNAME")
        if not appname:
            return _single_provider_result("RELIEFWEB", "news_sentiment", "reliefweb_reports", False, "auth_missing", "RELIEFWEB_APPNAME_missing")
        terms = [str(item).strip() for item in query_terms if str(item).strip()]
        if not terms:
            return _single_provider_result("RELIEFWEB", "news_sentiment", "reliefweb_reports", False, "not_supported", "no_query_terms")
        query = _or_query(_reliefweb_term(term) for term in terms[:8])
        start, end = _date_window(run_date, days=30)
        params = {
            "appname": appname,
            "profile": "list",
            "limit": str(max_records),
            "query[value]": query,
            "sort[]": "date:desc",
            "filter[field]": "date.created",
            "filter[value][from]": f"{start}T00:00:00+00:00",
            "filter[value][to]": f"{end}T23:59:59+00:00",
        }
        url = f"{RELIEFWEB_REPORTS_URL}?{urllib.parse.urlencode(params)}"
        try:
            payload = self._get_json(url)
        except Exception as exc:
            return _single_provider_result("RELIEFWEB", "news_sentiment", "reliefweb_reports", False, _error_type(exc), _sanitize_error(exc))
        rows = payload.get("data") if isinstance(payload, Mapping) else []
        reports = [row for row in rows if isinstance(row, Mapping)]
        evidence = []
        for idx, row in enumerate(reports[:max_records]):
            fields = row.get("fields") if isinstance(row.get("fields"), Mapping) else {}
            evidence.append(
                {
                    "id": f"reliefweb:{idx}:{row.get('id') or ''}",
                    "domain": "news_sentiment",
                    "symbol": "",
                    "value": str(fields.get("title") or row.get("href") or "ReliefWeb report"),
                    "as_of": _iso_date(fields.get("date", {}).get("created")) if isinstance(fields.get("date"), Mapping) else run_date,
                    "provider": "RELIEFWEB",
                    "source_url": str(fields.get("url") or row.get("href") or url),
                    "confidence": "medium",
                    "fact_type": "discovery",
                }
            )
        run = _provider_run(
            "RELIEFWEB",
            "news_sentiment",
            "reliefweb_reports",
            bool(evidence),
            len(evidence),
            None if evidence else "empty",
            None if evidence else "empty_response",
        )
        return OfficialEventSourceResult([run], evidence, {"query": query, "dateWindow": f"{start}~{end}", "url": url, "reports": reports[:max_records]})

    def fetch_ofac_sanctions_signals(self, *, query_terms: Sequence[str], run_date: str, max_matches: int = 8) -> OfficialEventSourceResult:
        """Fetch OFAC SDN data and surface high-level sanctions matches.

        This is a conservative geopolitical signal: it only records whether
        query terms appear in the public sanctions data.  It is not a compliance
        screening engine and does not replace official due diligence.
        """

        if _env_value("ENABLE_OFAC_SDN") not in {"1", "true", "TRUE", "yes"}:
            return _single_provider_result("OFAC_SDN", "filings_events", "ofac_sdn_search", False, "not_supported", "ENABLE_OFAC_SDN_not_enabled")
        terms = [str(item).strip() for item in query_terms if len(str(item).strip()) >= 3][:12]
        if not terms:
            return _single_provider_result("OFAC_SDN", "filings_events", "ofac_sdn_search", False, "not_supported", "no_query_terms")
        try:
            xml_text = self._get_text(OFAC_SDN_ADVANCED_URL, headers={"User-Agent": "invest-system/0.1"})
        except Exception as exc:
            return _single_provider_result("OFAC_SDN", "filings_events", "ofac_sdn_search", False, "failed", _sanitize_error(exc))
        lower = xml_text.lower()
        matches: List[str] = []
        for term in terms:
            if term.lower() in lower:
                matches.append(term)
            if len(matches) >= max_matches:
                break
        evidence = [
            {
                "id": f"ofac_sdn:{_safe_id(term)}:{run_date}",
                "domain": "filings_events",
                "symbol": "",
                "value": f"OFAC SDN public list contains query term: {term}",
                "as_of": run_date,
                "provider": "OFAC_SDN",
                "source_url": OFAC_SDN_ADVANCED_URL,
                "confidence": "high",
                "fact_type": "verified_fact",
            }
            for term in matches
        ]
        run = _provider_run(
            "OFAC_SDN",
            "filings_events",
            "ofac_sdn_search",
            True,
            len(matches),
            None if matches else None,
            "no_query_matches" if not matches else None,
        )
        return OfficialEventSourceResult([run], evidence, {"queryTerms": terms, "matchCount": len(matches)})

    def fetch_cninfo_announcements(self, *, symbols: Sequence[str], run_date: str, max_records_per_symbol: int = 5) -> OfficialEventSourceResult:
        cn_symbols = [_normalize_cn_symbol(symbol) for symbol in symbols if _normalize_cn_symbol(symbol)]
        if not cn_symbols:
            return _single_provider_result("CNINFO", "filings_events", "cninfo_announcements", False, "not_supported", "no_cn_symbols")

        evidence: List[Dict[str, Any]] = []
        raw_symbols: Dict[str, Any] = {}
        start, end = _date_window(run_date, days=45)
        for symbol in cn_symbols:
            stock_param = _cninfo_stock_param(symbol)
            form = urllib.parse.urlencode({
                "pageNum": "1",
                "pageSize": str(max_records_per_symbol),
                "column": "szse",
                "tabName": "fulltext",
                "plate": _cninfo_plate(symbol),
                "stock": stock_param,
                "searchkey": "" if stock_param else symbol,
                "secid": "",
                "category": "",
                "trade": "",
                "seDate": f"{start}~{end}",
                "sortName": "",
                "sortType": "",
                "isHLtitle": "true",
            }).encode("utf-8")
            try:
                payload = self._post_json(CNINFO_QUERY_URL, data=form, headers=_cninfo_headers())
            except Exception as exc:
                raw_symbols[symbol] = {"status": "failed", "error": _sanitize_error(exc)}
                continue
            announcements = payload.get("announcements") if isinstance(payload, Mapping) else []
            if not isinstance(announcements, list):
                announcements = []
            rows = [item for item in announcements if isinstance(item, Mapping)]
            accepted_rows = [
                row
                for row in rows
                if _normalize_cn_symbol(_strip_html(str(row.get("secCode") or ""))) == symbol
            ]
            raw_symbols[symbol] = {
                "status": "available" if accepted_rows else "empty",
                "announcements": accepted_rows,
                "filteredOut": max(0, len(rows) - len(accepted_rows)),
            }
            for idx, row in enumerate(accepted_rows[:max_records_per_symbol]):
                adjunct = str(row.get("adjunctUrl") or "")
                source_url = urllib.parse.urljoin(CNINFO_STATIC_BASE, adjunct) if adjunct else CNINFO_QUERY_URL
                evidence.append({
                    "id": f"cninfo:{symbol}:{row.get('announcementId') or idx}",
                    "domain": "filings_events",
                    "symbol": symbol,
                    "value": _strip_html(str(row.get("announcementTitle") or "CNINFO announcement")),
                    "as_of": _cninfo_time_to_date(row.get("announcementTime")) or run_date,
                    "provider": "CNINFO",
                    "source_url": source_url,
                    "confidence": "high",
                    "fact_type": "verified_fact",
                })
        success = bool(evidence)
        run = _provider_run(
            "CNINFO",
            "filings_events",
            "cninfo_announcements",
            success,
            len(evidence),
            None if success else "empty",
            None if success else "no_recent_announcements",
        )
        return OfficialEventSourceResult([run], evidence, {"dateWindow": f"{start}~{end}", "symbols": raw_symbols})

    def fetch_exchange_disclosures(self, *, symbols: Sequence[str], run_date: str, max_records_per_symbol: int = 5) -> OfficialEventSourceResult:
        cn_symbols = [_normalize_cn_symbol(symbol) for symbol in symbols if _normalize_cn_symbol(symbol)]
        if not cn_symbols:
            return _single_provider_result("SSE_DISCLOSURE", "filings_events", "exchange_announcements", False, "not_supported", "no_cn_symbols")
        start, end = _date_window(run_date, days=45)
        evidence: List[Dict[str, Any]] = []
        raw: Dict[str, Any] = {"dateWindow": f"{start}~{end}", "symbols": {}}
        provider_counts = {"SSE_DISCLOSURE": 0, "SZSE_DISCLOSURE": 0}
        provider_errors: Dict[str, List[str]] = {"SSE_DISCLOSURE": [], "SZSE_DISCLOSURE": []}

        for symbol in cn_symbols:
            provider = "SSE_DISCLOSURE" if _cninfo_plate(symbol) == "sh" else "SZSE_DISCLOSURE"
            try:
                rows = self._fetch_sse_announcements(symbol, start, end, max_records_per_symbol) if provider == "SSE_DISCLOSURE" else self._fetch_szse_announcements(symbol, start, end, max_records_per_symbol)
            except Exception as exc:
                raw["symbols"][symbol] = {"status": "failed", "provider": provider, "error": _sanitize_error(exc)}
                provider_errors[provider].append(_sanitize_error(exc))
                continue
            raw["symbols"][symbol] = {"status": "available" if rows else "empty", "provider": provider, "announcements": rows}
            provider_counts[provider] += len(rows)
            for idx, row in enumerate(rows[:max_records_per_symbol]):
                source_url = str(row.get("sourceUrl") or "")
                evidence.append({
                    "id": f"{provider.lower()}:{symbol}:{row.get('id') or idx}",
                    "domain": "filings_events",
                    "symbol": symbol,
                    "value": _strip_html(str(row.get("title") or "exchange announcement")),
                    "as_of": row.get("date") or run_date,
                    "provider": provider,
                    "source_url": source_url,
                    "confidence": "high",
                    "fact_type": "verified_fact",
                })

        provider_runs = [
            _provider_run(
                provider,
                "filings_events",
                "exchange_announcements",
                count > 0,
                count,
                None if count > 0 else "failed" if provider_errors[provider] else "empty",
                None if count > 0 else "; ".join(provider_errors[provider][:2]) if provider_errors[provider] else "no_recent_exchange_announcements",
            )
            for provider, count in provider_counts.items()
            if count > 0 or provider_errors[provider] or any((raw["symbols"].get(symbol) or {}).get("provider") == provider for symbol in cn_symbols)
        ]
        return OfficialEventSourceResult(provider_runs, evidence, raw)

    def fetch_hkex_disclosures(self, *, symbols: Sequence[str], run_date: str, max_records_per_symbol: int = 5) -> OfficialEventSourceResult:
        hk_symbols = [_normalize_hk_symbol(symbol) for symbol in symbols if _normalize_hk_symbol(symbol)]
        if not hk_symbols:
            return _single_provider_result("HKEXNEWS", "filings_events", "hkex_announcements", False, "not_supported", "no_hk_symbols")
        evidence: List[Dict[str, Any]] = []
        raw_symbols: Dict[str, Any] = {}
        start, end = _date_window(run_date, days=45)
        for symbol in hk_symbols:
            lookup_params = urllib.parse.urlencode({
                "lang": "EN",
                "type": "A",
                "name": symbol,
                "market": "SEHK",
                "callback": "callback",
            })
            lookup_url = f"{HKEX_STOCK_PREFIX_URL}?{lookup_params}"
            try:
                lookup_text = self._get_text(lookup_url, headers=_hkex_headers())
            except Exception as exc:
                raw_symbols[symbol] = {"status": "failed", "error": _sanitize_error(exc)}
                continue
            stock = _parse_hkex_stock_match(lookup_text, symbol=symbol)
            if not stock:
                raw_symbols[symbol] = {
                    "status": "partial",
                    "lookupUrl": lookup_url,
                    "reason": "hkex_stock_id_not_resolved",
                }
                continue
            params = urllib.parse.urlencode({
                "category": "0",
                "lang": "EN",
                "market": "SEHK",
                "stockId": stock["stockId"],
                "from": start.replace("-", ""),
                "to": end.replace("-", ""),
            })
            url = f"{HKEX_TITLE_SEARCH_URL}?{params}"
            try:
                html = self._get_text(url, headers=_hkex_headers())
            except Exception as exc:
                raw_symbols[symbol] = {"status": "failed", "error": _sanitize_error(exc)}
                continue
            rows = _parse_hkex_links(html, symbol=symbol, limit=max_records_per_symbol)
            raw_symbols[symbol] = {
                "status": "available" if rows else "empty",
                "stockId": stock["stockId"],
                "stockName": stock.get("name") or "",
                "url": url,
                "announcements": rows,
            }
            for idx, row in enumerate(rows):
                evidence.append({
                    "id": f"hkex:{symbol}:{idx}:{str(row.get('sourceUrl') or '')[-24:]}",
                    "domain": "filings_events",
                    "symbol": symbol,
                    "value": _strip_html(str(row.get("title") or "HKEX announcement")),
                    "as_of": row.get("date") or run_date,
                    "provider": "HKEXNEWS",
                    "source_url": row.get("sourceUrl") or url,
                    "confidence": "high",
                    "fact_type": "verified_fact",
                })
        success = bool(evidence)
        run = _provider_run(
            "HKEXNEWS",
            "filings_events",
            "hkex_announcements",
            success,
            len(evidence),
            None if success else "empty",
            None if success else "no_recent_hkex_announcements",
        )
        return OfficialEventSourceResult([run], evidence, {"dateWindow": f"{start}~{end}", "symbols": raw_symbols})

    def _sec_ticker_map(self) -> Dict[str, str]:
        if self._sec_tickers_cache is not None:
            return dict(self._sec_tickers_cache)
        payload = self._get_json(SEC_TICKERS_URL, headers=self._sec_headers())
        out: Dict[str, str] = {}
        if isinstance(payload, Mapping):
            for item in payload.values():
                if not isinstance(item, Mapping):
                    continue
                ticker = str(item.get("ticker") or "").upper()
                cik = str(item.get("cik_str") or "")
                if ticker and cik:
                    out[ticker] = cik.zfill(10)
        self._sec_tickers_cache = dict(out)
        return out

    def _sec_headers(self) -> Dict[str, str]:
        return {"User-Agent": self.sec_user_agent}

    def _get_json(self, url: str, *, headers: Mapping[str, str] | None = None) -> Any:
        request = urllib.request.Request(url, headers=dict(headers or {"User-Agent": "invest-system/0.1"}))
        with _urlopen(request, timeout_s=self.timeout_s) as response:  # nosec - read-only public sources
            return json.loads(response.read().decode("utf-8", errors="replace"))

    def _post_json(self, url: str, *, data: bytes, headers: Mapping[str, str] | None = None) -> Any:
        request = urllib.request.Request(url, data=data, headers=dict(headers or {}), method="POST")
        with _urlopen(request, timeout_s=self.timeout_s) as response:  # nosec - read-only public sources
            return json.loads(response.read(2_000_000).decode("utf-8", errors="replace"))

    def _post_json_body(self, url: str, *, data: bytes, headers: Mapping[str, str] | None = None) -> Any:
        request = urllib.request.Request(url, data=data, headers=dict(headers or {}), method="POST")
        with _urlopen(request, timeout_s=self.timeout_s) as response:  # nosec - read-only public sources
            return json.loads(response.read(2_000_000).decode("utf-8", errors="replace"))

    def _get_text(self, url: str, *, headers: Mapping[str, str] | None = None) -> str:
        request = urllib.request.Request(url, headers=dict(headers or {"User-Agent": "invest-system/0.1"}))
        with _urlopen(request, timeout_s=self.timeout_s) as response:  # nosec - read-only public sources
            return response.read(2_000_000).decode("utf-8", errors="replace")

    def _fetch_sse_announcements(self, symbol: str, start: str, end: str, limit: int) -> List[Dict[str, Any]]:
        params = urllib.parse.urlencode({
            "isPagination": "true",
            "productId": symbol,
            "securityType": "0101",
            "reportType2": "",
            "reportType": "ALL",
            "beginDate": start,
            "endDate": end,
            "pageHelp.pageSize": str(limit),
            "pageHelp.pageNo": "1",
            "pageHelp.beginPage": "1",
            "pageHelp.cacheSize": "1",
            "pageHelp.endPage": "1",
        })
        payload = self._get_json(f"{SSE_QUERY_URL}?{params}", headers=_sse_headers())
        rows = payload.get("result") if isinstance(payload, Mapping) else []
        out: List[Dict[str, Any]] = []
        for item in rows if isinstance(rows, list) else []:
            if not isinstance(item, Mapping):
                continue
            code = _normalize_cn_symbol(item.get("SECURITY_CODE") or item.get("securityCode") or symbol)
            if code and code != symbol:
                continue
            href = str(item.get("URL") or item.get("url") or "")
            out.append({
                "id": item.get("BULLETIN_ID") or item.get("bulletinId") or href,
                "title": item.get("TITLE") or item.get("title") or "SSE announcement",
                "date": item.get("SSEDATE") or item.get("date") or item.get("publishTime"),
                "sourceUrl": urllib.parse.urljoin(SSE_STATIC_BASE, href) if href else SSE_QUERY_URL,
            })
        return out

    def _fetch_szse_announcements(self, symbol: str, start: str, end: str, limit: int) -> List[Dict[str, Any]]:
        params = urllib.parse.urlencode({
            "random": "0.1",
            "pageSize": str(limit),
            "pageNum": "1",
            "plateCode": _szse_plate(symbol),
            "stock": symbol,
            "seDate": f"{start}~{end}",
        })
        payload = self._get_json(f"{SZSE_ANN_LIST_URL}?{params}", headers=_szse_headers())
        rows = (payload.get("data") or payload.get("announcements")) if isinstance(payload, Mapping) else []
        out: List[Dict[str, Any]] = []
        for item in rows if isinstance(rows, list) else []:
            if not isinstance(item, Mapping):
                continue
            code = _normalize_cn_symbol(item.get("secCode") or item.get("stockCode") or symbol)
            if code and code != symbol:
                continue
            href = str(item.get("attachPath") or item.get("url") or item.get("href") or "")
            out.append({
                "id": item.get("id") or item.get("announcementId") or href,
                "title": item.get("title") or item.get("announcementTitle") or "SZSE announcement",
                "date": item.get("publishTime") or item.get("date"),
                "sourceUrl": urllib.parse.urljoin(SZSE_STATIC_BASE, href) if href else SZSE_ANN_LIST_URL,
            })
        return out


def write_official_event_sources_payload(
    path: str | Path,
    result: OfficialEventSourceResult,
    *,
    source_scope: str = "subject_evidence",
) -> Dict[str, Any]:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    scope = source_scope if source_scope in {"subject_evidence", "source_smoke"} else "subject_evidence"
    fetched_at = utc_now_iso()
    provider_runs = [
        {**row, "source_scope": scope, "observed_at": row.get("observed_at") or fetched_at}
        for row in result.provider_runs
    ]
    evidence_facts = []
    filing_providers = {"SEC_EDGAR", "CNINFO", "SSE_DISCLOSURE", "SZSE_DISCLOSURE", "HKEXNEWS"}
    for row in result.evidence_facts:
        fact = {**row, "evidence_scope": scope, "fetched_at": row.get("fetched_at") or fetched_at}
        as_of = iso_timestamp(fact.get("as_of") or fact.get("asOf"))
        provider = str(fact.get("provider") or "")
        if as_of and (provider in filing_providers or as_of[:10] != fetched_at[:10]):
            fact.setdefault("event_time", as_of)
            fact.setdefault("published_at", as_of)
        evidence_facts.append(fact)
    payload = {
        **result.raw,
        "sourceScope": scope,
        "providerRuns": provider_runs,
        "evidenceFacts": evidence_facts,
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def _sec_recent_filings(payload: Any, *, symbol: str, cik: str, run_date: str, limit: int) -> List[Dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return []
    recent = payload.get("filings", {}).get("recent") if isinstance(payload.get("filings"), Mapping) else {}
    if not isinstance(recent, Mapping):
        return []
    forms = list(recent.get("form") or [])
    dates = list(recent.get("filingDate") or [])
    accessions = list(recent.get("accessionNumber") or [])
    primary_docs = list(recent.get("primaryDocument") or [])
    rows: List[Dict[str, Any]] = []
    cik_no_zeros = str(int(cik)) if str(cik).isdigit() else cik.lstrip("0")
    for idx, form in enumerate(forms[: max(limit * 4, limit)]):
        filing_date = _list_get(dates, idx)
        if filing_date and not _is_on_or_before(filing_date, run_date):
            continue
        accession = _list_get(accessions, idx)
        primary_doc = _list_get(primary_docs, idx)
        source_url = ""
        if accession and primary_doc:
            accession_clean = str(accession).replace("-", "")
            source_url = f"https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/{accession_clean}/{primary_doc}"
        rows.append({
            "symbol": symbol,
            "cik": cik,
            "form": form,
            "filingDate": filing_date,
            "accessionNumber": accession,
            "primaryDocument": primary_doc,
            "sourceUrl": source_url,
        })
        if len(rows) >= limit:
            break
    return rows


def _sec_companyfacts(payload: Any, *, symbol: str, run_date: str, limit: int) -> List[Dict[str, Any]]:
    facts = payload.get("facts", {}) if isinstance(payload, Mapping) else {}
    us_gaap = facts.get("us-gaap", {}) if isinstance(facts, Mapping) else {}
    if not isinstance(us_gaap, Mapping):
        return []
    rows: List[Dict[str, Any]] = []
    for concept in SEC_COMPANYFACT_CONCEPTS:
        concept_payload = us_gaap.get(concept)
        if not isinstance(concept_payload, Mapping):
            continue
        units = concept_payload.get("units")
        if not isinstance(units, Mapping):
            continue
        candidate = _latest_companyfact_unit(units, run_date=run_date)
        if candidate is None:
            continue
        rows.append({"symbol": symbol, "concept": concept, **candidate})
        if len(rows) >= limit:
            break
    return rows


def _latest_companyfact_unit(units: Mapping[str, Any], *, run_date: str) -> Dict[str, Any] | None:
    candidates: List[Dict[str, Any]] = []
    for unit, unit_rows in units.items():
        if not isinstance(unit_rows, list):
            continue
        for row in unit_rows:
            if not isinstance(row, Mapping):
                continue
            filed = str(row.get("filed") or row.get("fy") or "")
            end = str(row.get("end") or "")
            if filed and not _is_on_or_before(filed, run_date):
                continue
            if end and not _is_on_or_before(end, run_date):
                continue
            if row.get("val") is None:
                continue
            if _days_between(row.get("filed") or row.get("end"), run_date) > SEC_COMPANYFACT_MAX_AGE_DAYS:
                continue
            candidates.append({
                "unit": str(unit),
                "value": row.get("val"),
                "start": str(row.get("start") or ""),
                "end": end,
                "filed": filed or end,
                "form": str(row.get("form") or ""),
                "fp": str(row.get("fp") or ""),
                "fy": str(row.get("fy") or ""),
                "frame": str(row.get("frame") or ""),
            })
    candidates.sort(key=lambda item: (str(item.get("filed") or ""), str(item.get("end") or "")), reverse=True)
    return candidates[0] if candidates else None


def _single_provider_result(provider: str, domain: str, operation: str, success: bool, error_type: str, message: str) -> OfficialEventSourceResult:
    return OfficialEventSourceResult(
        provider_runs=[_provider_run(provider, domain, operation, success, 0, error_type, message)],
        evidence_facts=[],
        raw={provider.lower(): {"status": error_type, "message": message}},
    )


def _provider_run(provider: str, domain: str, operation: str, success: bool, record_count: int, error_type: str | None = None, message: str | None = None) -> Dict[str, Any]:
    row = {
        "provider": provider,
        "domain": domain,
        "data_type": domain,
        "operation": operation,
        "success": success,
        "record_count": record_count,
        "observed_at": utc_now_iso(),
        "error_type": error_type,
        "error_message_sanitized": message,
    }
    return {key: value for key, value in row.items() if value not in (None, "", [])}


def _is_us_ticker(symbol: Any) -> bool:
    text = str(symbol or "").strip().upper()
    return bool(re.fullmatch(r"[A-Z][A-Z0-9.-]{0,7}", text)) and not text.startswith("HK")


def _normalize_cn_symbol(symbol: Any) -> str:
    text = str(symbol or "").strip().lower()
    text = re.sub(r"^(sh|sz|bj)", "", text)
    text = re.sub(r"\.(sh|sz|bj)$", "", text)
    return text if re.fullmatch(r"\d{6}", text) else ""


def _normalize_hk_symbol(symbol: Any) -> str:
    text = str(symbol or "").strip().upper()
    text = re.sub(r"^HK", "", text)
    text = re.sub(r"\.HK$", "", text)
    text = re.sub(r"\D", "", text)
    return text.zfill(5) if 1 <= len(text) <= 5 else ""


def _gdelt_term(term: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff ._-]+", " ", term).strip()
    if not safe:
        return "market"
    return f'"{safe}"' if " " in safe else safe


def _geo_query_terms(query_terms: Sequence[str]) -> List[str]:
    geo_tokens = ("sanction", "conflict", "war", "tariff", "trade", "export", "energy", "shipping", "strait", "制裁", "冲突", "关税", "出口")
    selected = [
        str(term).strip()
        for term in query_terms
        if str(term).strip() and any(token in str(term).lower() for token in geo_tokens)
    ]
    return list(dict.fromkeys([*selected, *DEFAULT_GEO_QUERY_TERMS]))[:8]


def _search_term(term: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff ._-]+", " ", str(term or "")).strip()
    return f'"{safe}"' if " " in safe else (safe or "market")


def _or_query(terms: Iterable[str]) -> str:
    cleaned = [term for term in terms if str(term or "").strip()]
    if not cleaned:
        return "market"
    if len(cleaned) == 1:
        return cleaned[0]
    return "(" + " OR ".join(cleaned) + ")"


def _reliefweb_term(term: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff ._-]+", " ", str(term or "")).strip()
    return f'"{safe}"' if " " in safe else (safe or "market")


def _iso_date(value: Any) -> str:
    text = str(value or "")
    match = re.match(r"(\d{4}-\d{2}-\d{2})", text)
    return match.group(1) if match else ""


def _safe_id(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())[:80] or "term"


def _env_value(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    return _project_env_values().get(name, "").strip()


def _env_csv(*names: str) -> List[str]:
    values: List[str] = []
    seen: set[str] = set()
    for name in names:
        raw = _env_value(name)
        for item in raw.split(","):
            key = item.strip()
            if not key or key in seen:
                continue
            seen.add(key)
            values.append(key)
    return values


def _urlopen(request: urllib.request.Request, *, timeout_s: float):
    return urllib.request.urlopen(request, timeout=timeout_s, context=_ssl_context())


@lru_cache(maxsize=1)
def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi  # type: ignore  # noqa: WPS433 - optional CA bundle
    except Exception:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


@lru_cache(maxsize=1)
def _project_env_values() -> Dict[str, str]:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return {}
    try:
        from dotenv import dotenv_values  # noqa: WPS433 - optional lightweight parser
    except Exception:
        return _parse_env_file(env_path)
    return {str(k): "" if v is None else str(v) for k, v in dotenv_values(env_path, interpolate=False).items() if k}


def _parse_env_file(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        out[key.strip()] = value.strip().strip('"\'')
    return out


def _error_type(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        if exc.code == 429:
            return "rate_limited"
        if exc.code in {401, 403}:
            return "auth_missing"
    text = str(exc).lower()
    if "429" in text or "rate" in text or "too many" in text:
        return "rate_limited"
    if "401" in text or "403" in text or "unauthorized" in text or "forbidden" in text:
        return "auth_missing"
    return "failed"


def _date_window(run_date: str, *, days: int) -> tuple[str, str]:
    try:
        end = date.fromisoformat(run_date)
    except ValueError:
        end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)
    return start.isoformat(), end.isoformat()


def _datetime_window(run_date: str, *, days: int) -> tuple[str, str]:
    start, end = _date_window(run_date, days=days)
    return start.replace("-", "") + "000000", end.replace("-", "") + "235959"


def _is_on_or_before(value: Any, run_date: str) -> bool:
    try:
        return date.fromisoformat(str(value)) <= date.fromisoformat(str(run_date))
    except ValueError:
        return False


def _days_between(value: Any, run_date: str) -> int:
    try:
        return (date.fromisoformat(str(run_date)) - date.fromisoformat(str(value))).days
    except Exception:
        return 10_000


def _cninfo_headers() -> Dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 invest-system/0.1",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": "http://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
        "Origin": "http://www.cninfo.com.cn",
        "X-Requested-With": "XMLHttpRequest",
    }


def _cninfo_plate(symbol: str) -> str:
    if symbol.startswith(("60", "68", "90")):
        return "sh"
    if symbol.startswith(("00", "30", "20")):
        return "sz"
    if symbol.startswith(("43", "83", "87", "92")):
        return "bj"
    return ""


def _cninfo_stock_param(symbol: str) -> str:
    """Return CNINFO's precise stock selector when the pattern is stable."""

    if symbol.startswith(("00", "20")):
        return f"{symbol},gssz0{symbol}"
    if symbol.startswith("30"):
        return f"{symbol},gscy0{symbol}"
    return ""


def _szse_plate(symbol: str) -> str:
    if symbol.startswith("30"):
        return "cyb"
    if symbol.startswith(("00", "20")):
        return "szse"
    if symbol.startswith(("43", "83", "87", "92")):
        return "bj"
    return ""


def _sse_headers() -> Dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 invest-system/0.1",
        "Referer": "https://www.sse.com.cn/disclosure/listedinfo/announcement/",
    }


def _szse_headers() -> Dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 invest-system/0.1",
        "Referer": "https://www.szse.cn/disclosure/listed/notice/index.html",
    }


def _hkex_headers() -> Dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 invest-system/0.1",
        "Referer": "https://www.hkexnews.hk/",
    }


def _parse_hkex_links(html: str, *, symbol: str, limit: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    row_pattern = re.compile(r"<tr\b[^>]*>(?P<body>.*?)</tr>", re.I | re.S)
    code_pattern = re.compile(
        r"<td\b[^>]*class=[\"'][^\"']*\bstock-short-code\b[^\"']*[\"'][^>]*>(?P<value>.*?)</td>",
        re.I | re.S,
    )
    name_pattern = re.compile(
        r"<td\b[^>]*class=[\"'][^\"']*\bstock-short-name\b[^\"']*[\"'][^>]*>(?P<value>.*?)</td>",
        re.I | re.S,
    )
    link_pattern = re.compile(r"<a[^>]+href=[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<title>.*?)</a>", re.I | re.S)
    for row_match in row_pattern.finditer(html or ""):
        body = row_match.group("body")
        code_match = code_pattern.search(body)
        stock_codes = _hkex_stock_codes(code_match.group("value")) if code_match else []
        if symbol not in stock_codes:
            continue
        name_match = name_pattern.search(body)
        issuer = _hkex_cell_value(name_match.group("value")) if name_match else ""
        for link_match in link_pattern.finditer(body):
            href = link_match.group("href")
            title = _strip_html(link_match.group("title"))
            if "listedco/listconews" not in href.lower() and not href.lower().endswith(".pdf"):
                continue
            source_url = urllib.parse.urljoin(HKEX_STATIC_BASE, href)
            date_match = re.search(r"/(20\d{2})/(\d{4})/", source_url)
            as_of = f"{date_match.group(1)}-{date_match.group(2)[:2]}-{date_match.group(2)[2:]}" if date_match else ""
            rows.append({
                "symbol": symbol,
                "stockCode": symbol,
                "stockCodes": stock_codes,
                "issuer": issuer,
                "title": title or "HKEX announcement",
                "date": as_of,
                "sourceUrl": source_url,
            })
            if len(rows) >= limit:
                return rows
    return rows


def _parse_hkex_stock_match(text: str, *, symbol: str) -> Dict[str, Any] | None:
    start = str(text or "").find("{")
    end = str(text or "").rfind("}")
    if start < 0 or end < start:
        return None
    try:
        payload = json.loads(str(text)[start:end + 1])
    except (TypeError, ValueError):
        return None
    stock_info = payload.get("stockInfo") if isinstance(payload, Mapping) else []
    for item in stock_info if isinstance(stock_info, list) else []:
        if not isinstance(item, Mapping):
            continue
        code = _normalize_hk_symbol(item.get("code"))
        stock_id = str(item.get("stockId") or "").strip()
        if code == symbol and stock_id:
            return {"stockId": stock_id, "code": code, "name": str(item.get("name") or "")}
    return None


def _hkex_cell_value(value: str) -> str:
    text = _strip_html(value)
    return re.sub(r"^(?:Stock Code|Stock Short Name)\s*:\s*", "", text, flags=re.I).strip()


def _hkex_stock_codes(value: str) -> List[str]:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    codes: List[str] = []
    for raw_code in re.findall(r"(?<!\d)\d{1,5}(?!\d)", text):
        code = _normalize_hk_symbol(raw_code)
        if code and code not in codes:
            codes.append(code)
    return codes


def _cninfo_time_to_date(value: Any) -> str:
    try:
        number = int(value)
    except Exception:
        return ""
    if number > 10_000_000_000:
        number = number // 1000
    return datetime.fromtimestamp(number, tz=timezone.utc).date().isoformat()


def _yyyymmdd_to_iso(value: Any) -> str:
    text = str(value or "")
    if len(text) >= 8 and text[:8].isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return ""


def _strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value).strip()


def _list_get(values: Sequence[Any], idx: int) -> Any:
    return values[idx] if idx < len(values) else ""


def _sanitize_error(exc: Exception) -> str:
    return sanitize_diagnostic_text(exc, max_len=180)
