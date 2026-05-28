#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from integrations.kronos.adapter import build_result, render_markdown
from integrations.kronos.schemas import KronosForecastRequest


def fake_fetcher(symbol: str, range_: str = "2y", interval: str = "1d"):
    dates = pd.date_range("2026-01-01", periods=40, freq="D")
    df = pd.DataFrame({
        "timestamps": dates,
        "open": [100 + i * 0.1 for i in range(40)],
        "high": [101 + i * 0.1 for i in range(40)],
        "low": [99 + i * 0.1 for i in range(40)],
        "close": [100 + i * 0.1 for i in range(40)],
        "volume": [1000 + i for i in range(40)],
    })
    df["amount"] = df["close"] * df["volume"]
    return df, {"source": "fixture", "missing_bars_count": 0, "amount_missing": True}


class KronosAdapterTests(unittest.TestCase):
    def test_default_smoke_is_sidecar_only(self):
        req = KronosForecastRequest(symbol="CCJ", analysis_date="2026-05-18", lookback=20, pred_len=5)
        result, _ = build_result(req, fetcher=fake_fetcher)
        self.assertIn(result.status, {"degraded", "ok"})
        self.assertEqual(result.scoring_impact, 0)
        self.assertFalse(result.protected_writeback)
        self.assertEqual(result.forecast_direction, "uncertain")
        self.assertTrue(result.amount_missing)

    def test_markdown_contains_boundaries(self):
        req = KronosForecastRequest(symbol="0700.HK", analysis_date="2026-05-18", lookback=20, pred_len=5)
        result, _ = build_result(req, fetcher=fake_fetcher)
        md = render_markdown(result)
        self.assertIn("scoring", md.lower())
        self.assertIn("Protected writeback", md)
        self.assertIn("12_preliminary_deep_review.md", md)


if __name__ == "__main__":
    unittest.main()
