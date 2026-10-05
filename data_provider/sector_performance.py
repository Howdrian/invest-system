"""Free regional sector proxies, exposed by DataFetcherManager.

These are price-performance observations, not fund-flow or whole-market
breadth. US ETFs are adjusted; HK thematic indexes are price indexes.
"""
from __future__ import annotations

import math
import time
from datetime import date, datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

US_SECTORS = {
    'XLC': '通信服务', 'XLY': '可选消费', 'XLP': '必需消费', 'XLE': '能源',
    'XLF': '金融', 'XLV': '医疗保健', 'XLI': '工业', 'XLB': '原材料',
    'XLRE': '房地产', 'XLK': '信息技术', 'XLU': '公用事业',
}
# Exact names/scopes supplied by the upstream AkShare/Sina HK index catalogue.
HK_SECTORS = {
    'HSTECH': '恒生科技', 'HSMBI': '恒生内地银行', 'HSMOGI': '恒生内地油气',
    'HSMPI': '恒生内地地产', 'CSHKLC': '香港上市内地消费', 'CESG10': '中华博彩',
}


def _load_us(symbol: str, as_of: str) -> list[dict]:
    import yfinance as yf

    end = date.fromisoformat(as_of) + timedelta(days=1)  # Yahoo end is exclusive.
    frame = yf.Ticker(symbol).history(start=str(end - timedelta(days=200)), end=str(end),
                                      interval='1d', auto_adjust=True, timeout=15, raise_errors=True)
    return [{'date': str(day.date()), 'close': row['Close']} for day, row in frame.iterrows()]


def _load_hk(symbol: str, _as_of: str) -> list[dict]:
    import requests
    # Reuse AkShare's existing Sina decoder, but bound the otherwise unbounded HTTP call.
    from akshare.index.index_stock_hk import hk_js_decode, py_mini_racer

    url = f'https://finance.sina.com.cn/stock/hkstock/{symbol}/klc2_kl.js'
    response = requests.get(url, timeout=(5, 15))
    response.raise_for_status()
    encoded = response.text.split('=', 1)[1].split(';', 1)[0].strip().strip('"')
    js = py_mini_racer.MiniRacer()
    try:
        js.eval(hk_js_decode)
        return js.call('d', encoded)
    finally:
        js.close()


def _prices(rows: list[dict], as_of: str) -> dict[str, float]:
    prices: dict[str, float] = {}
    for row in rows:
        raw_date = str(row.get('date') or '')[:10]
        try:
            day = date.fromisoformat(raw_date).isoformat()
            value = float(row['close'])
        except (ValueError, TypeError, KeyError):
            continue
        if day <= as_of and math.isfinite(value) and value > 0:
            prices[day] = value
    return dict(sorted(prices.items()))


def collect_sector_performance(
    market: str, as_of: str, *, loader: Callable[[str], list[dict]] | None = None,
) -> dict[str, Any]:
    """Collect bounded, free series once each and compare only identical dates."""
    date.fromisoformat(as_of)
    market = market.lower()
    if market not in {'us', 'hk'}:
        return {'market': market, 'status': 'not_supported', 'records': [], 'provider_runs': []}
    catalog = US_SECTORS if market == 'us' else HK_SECTORS
    benchmark = 'SPY' if market == 'us' else 'HSI'
    provider = 'YfinanceFetcher' if market == 'us' else 'AkshareSinaIndex'
    fetch = loader or (lambda s: (_load_us if market == 'us' else _load_hk)(s, as_of))
    runs, series = [], {}
    for symbol in [benchmark, *catalog]:
        started = time.monotonic()
        try:
            values = _prices(fetch(symbol), as_of)
            series[symbol] = values
            status = 'success' if len(values) >= 2 else 'empty'
            error = None if status == 'success' else 'empty'
        except Exception as exc:
            values = {}
            status = 'rate_limited' if '429' in str(exc) else 'failed'
            error = 'rate_limited' if status == 'rate_limited' else type(exc).__name__
        runs.append({'provider': provider, 'symbol': symbol, 'status': status, 'error_type': error,
                     'record_count': len(values), 'latency_ms': round((time.monotonic() - started) * 1000),
                     'observed_at': datetime.now(ZoneInfo('UTC')).isoformat()})
    base = series.get(benchmark, {})
    records = []
    now = datetime.now(ZoneInfo('America/New_York' if market == 'us' else 'Asia/Hong_Kong'))
    for symbol, name in catalog.items():
        prices = series.get(symbol, {})
        dates = list(prices)
        if len(dates) < 2:
            continue
        latest = dates[-1]
        row = {'code': symbol, 'name': name, 'market': market, 'as_of': latest,
               'sample_count': len(dates), 'benchmark': benchmark,
               'is_partial_bar': latest == str(now.date()) and now.hour < 17,
               'source_url': (f'https://finance.yahoo.com/quote/{symbol}/history/' if market == 'us'
                              else f'https://stock.finance.sina.com.cn/hkstock/quotes/{symbol}.html')}
        for window in (1, 5, 20, 60, 120):
            if len(dates) <= window:
                continue
            start = dates[-window - 1]
            change = (prices[latest] / prices[start] - 1) * 100
            row[f'return_{window}d_pct'] = round(change, 3)
            row[f'comparison_start_{window}d'] = start
            if start in base and latest in base:
                row[f'relative_{window}d_pp'] = round(change - (base[latest] / base[start] - 1) * 100, 3)
        records.append(row)
    return {
        'market': market, 'status': 'success' if len(records) == len(catalog) and len(base) >= 2 else 'partial',
        'records': records, 'provider_runs': runs, 'expected_count': len(catalog), 'benchmark': benchmark,
        'scope': ('标普500的11个行业ETF代理；复权收益，不代表全部美股或资金净流入。' if market == 'us'
                  else '港股6个行业/主题指数代理，部分仅覆盖内地企业；不代表港股全行业或资金净流入。'),
    }
