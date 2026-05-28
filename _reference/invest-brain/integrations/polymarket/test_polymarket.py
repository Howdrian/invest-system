from __future__ import annotations

from pathlib import Path
import unittest
import sys

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

def _drop_foreign_local_modules(names):
    for name in names:
        module = sys.modules.get(name)
        module_file = getattr(module, "__file__", None)
        if module_file and Path(module_file).resolve().parent != THIS_DIR:
            del sys.modules[name]

_drop_foreign_local_modules(('schemas', 'ab_test', 'normalize', 'fusion', 'report', 'cli', 'client'))

from fusion import linear_fusion, log_odds_fusion
from client import PolymarketAPIError, PolymarketClient
from normalize import market_has_yes_token, normalize_market, orderbook_snapshot, parse_array
from schemas import PolymarketIntegrationError, PROJECT_ROOT, assert_safe_output_path
from ab_test import SCENARIOS, build_samples, choose_signal, compare_snapshots, score_total


class TestPolymarketIntegration(unittest.TestCase):
    def test_parse_array_handles_json_strings(self):
        self.assertEqual(parse_array('["Yes", "No"]'), ["Yes", "No"])
        self.assertEqual(parse_array('bad'), [])

    def test_market_has_yes_token(self):
        market = {"outcomes": '["Yes", "No"]', "clobTokenIds": '["yes-token", "no-token"]'}
        self.assertEqual(market_has_yes_token(market), "yes-token")

    def test_orderbook_mid_and_spread(self):
        book = {"bids": [{"price": "0.20", "size": "10"}], "asks": [{"price": "0.22", "size": "15"}]}
        snap = orderbook_snapshot(book)
        self.assertEqual(snap.bid, 0.20)
        self.assertEqual(snap.ask, 0.22)
        self.assertAlmostEqual(snap.mid, 0.21)
        self.assertAlmostEqual(snap.spread, 0.02)

    def test_normalize_market_scores_quality(self):
        event = {"id": "1", "title": "Fed Decision", "slug": "fed-decision"}
        market = {
            "id": "m1",
            "conditionId": "c1",
            "question": "Will there be no change in Fed interest rates?",
            "outcomes": '["Yes", "No"]',
            "outcomePrices": '["0.70", "0.30"]',
            "volume": "1000000",
            "volume24hr": "200000",
            "liquidity": "300000",
            "endDate": "2099-01-01T00:00:00Z",
            "active": True,
            "closed": False,
            "acceptingOrders": True,
        }
        signal = normalize_market(event, market, book={"bids": [{"price":"0.69","size":"10"}], "asks":[{"price":"0.71","size":"10"}]})
        self.assertGreaterEqual(signal.quality_score, 8)
        self.assertEqual(signal.quality_bucket, "high")
        self.assertAlmostEqual(signal.yes_probability, 0.70)

    def test_fusion_keeps_market_weight_limited(self):
        self.assertAlmostEqual(linear_fusion(0.10, 0.50, 0.25), 0.20)
        self.assertGreater(log_odds_fusion(0.10, 0.50, 0.25), 0.10)
        self.assertLess(log_odds_fusion(0.10, 0.50, 0.25), 0.50)

    def test_safe_output_rejects_protected_files(self):
        with self.assertRaises(PolymarketIntegrationError):
            assert_safe_output_path(PROJECT_ROOT / "state" / "portfolio.md")

    def test_client_wraps_timeout_as_api_error(self):
        client = PolymarketClient(timeout=1)

        class TimeoutResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                raise TimeoutError("read timed out")

        original = __import__("urllib.request").request.urlopen
        try:
            __import__("urllib.request").request.urlopen = lambda *args, **kwargs: TimeoutResponse()
            with self.assertRaises(PolymarketAPIError):
                client._get_json("https://example.invalid/test")
        finally:
            __import__("urllib.request").request.urlopen = original


if __name__ == "__main__":
    unittest.main()


class TestPolymarketAB(unittest.TestCase):
    def test_ab_sample_with_signal_scores_higher(self):
        signal = {
            "question": "Will China invade Taiwan by end of 2026?",
            "event_title": "China Taiwan risk",
            "yes_probability": 0.06,
            "quality_score": 9.0,
            "volume_24h": 200000.0,
            "liquidity": 500000.0,
            "end_date": "2099-01-01T00:00:00Z",
            "orderbook": {"spread": 0.01},
        }
        samples = build_samples([signal])
        taiwan = [sample for sample in samples if sample.scenario_id == "taiwan"][0]
        self.assertGreater(score_total(taiwan.b_scores), score_total(taiwan.a_scores))
        self.assertFalse(taiwan.local_gate_bypassed)

    def test_protected_snapshot_compare_detects_change(self):
        audit = compare_snapshots({"a": "1"}, {"a": "2"})
        self.assertTrue(audit["writeback_violation"])
        self.assertEqual(audit["changed_files"], ["a"])

    def test_fed_rate_path_does_not_use_fed_chair_market(self):
        fed_scenario = [scenario for scenario in SCENARIOS if scenario["id"] == "fed"][0]
        chair_signal = {
            "question": "Will Judy Shelton be confirmed as Fed Chair?",
            "event_title": "Fed Chair confirmation",
            "yes_probability": 0.01,
            "quality_score": 10.0,
            "volume_24h": 500000.0,
        }
        rate_signal = {
            "question": "Will there be no change in Fed interest rates after the next FOMC meeting?",
            "event_title": "Fed interest rates",
            "yes_probability": 0.72,
            "quality_score": 8.0,
            "volume_24h": 10000.0,
        }
        self.assertEqual(choose_signal([chair_signal], fed_scenario), None)
        self.assertEqual(choose_signal([chair_signal, rate_signal], fed_scenario), rate_signal)
