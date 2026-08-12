# -*- coding: utf-8 -*-
"""Regression tests for YfinanceFetcher daily data normalization."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd

from data_provider.yfinance_fetcher import YfinanceFetcher


def test_normalize_daily_data_recovers_unnamed_datetime_index_date_column() -> None:
    fetcher = YfinanceFetcher()
    raw = pd.DataFrame(
        {
            "Open": [10.0, 10.5],
            "High": [11.0, 11.2],
            "Low": [9.8, 10.1],
            "Close": [10.8, 11.0],
            "Volume": [1000, 1200],
        },
        index=pd.DatetimeIndex(["2026-05-25", "2026-05-26"]),
    )

    normalized = fetcher._normalize_data(raw, "DRAM")
    cleaned = fetcher._clean_data(normalized)

    assert "date" in normalized.columns
    assert cleaned["date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-05-25", "2026-05-26"]


def test_us_realtime_quote_reuses_info_for_pe_pb_and_quality() -> None:
    """US quote fundamentals must not be discarded after Ticker.info is fetched."""
    ticker = MagicMock()
    ticker.fast_info = SimpleNamespace(
        lastPrice=200.0,
        previousClose=198.0,
        open=199.0,
        dayHigh=202.0,
        dayLow=197.0,
        lastVolume=1_000_000,
        marketCap=4_800_000_000_000,
    )
    ticker.info = {
        "shortName": "NVIDIA Corporation",
        "currency": "USD",
        "trailingPE": 48.25,
        "priceToBook": 41.5,
    }

    with patch("yfinance.Ticker", return_value=ticker):
        quote = YfinanceFetcher().get_realtime_quote("NVDA")

    assert quote is not None
    assert quote.pe_ratio == 48.25
    assert quote.pb_ratio == 41.5
    assert quote.currency == "USD"
    assert "pe_ratio" not in (quote.missing_fields or [])
    assert "pb_ratio" not in (quote.missing_fields or [])
