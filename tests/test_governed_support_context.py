# -*- coding: utf-8 -*-
"""Tests for governed macro and market-heat support context."""

import tempfile
import unittest

from src.intel.market_heat import build_market_heat_snapshot, load_latest_market_heat, write_market_heat_snapshot
from src.macro.official_sources import MacroContextService
from src.macro.source_cache import JsonSourceCache


class GovernedSupportContextTestCase(unittest.TestCase):
    def test_macro_context_fail_open_without_network(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = MacroContextService(cache=JsonSourceCache(tmpdir))

            payload = service.get_context(allow_network=False, force_refresh=False, max_age_seconds=60)

        self.assertEqual(payload["status"], "DEGRADED")
        self.assertIn("macro_cache_missing_or_stale", payload["warnings"])

    def test_market_heat_snapshot_roundtrip(self):
        payload = build_market_heat_snapshot(["600519", "AAPL"])
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = write_market_heat_snapshot(payload, tmpdir)
            loaded = load_latest_market_heat(tmpdir)

        self.assertIn("json", paths)
        self.assertEqual(loaded["status"], "available")
        self.assertEqual([item["symbol"] for item in loaded["focus_items"]], ["600519", "AAPL"])


if __name__ == "__main__":
    unittest.main()
