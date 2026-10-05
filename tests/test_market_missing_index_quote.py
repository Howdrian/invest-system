"""Incomplete provider index rows must not abort a multi-market report."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.market_analyzer import MarketAnalyzer, MarketIndex, MarketOverview


@pytest.mark.parametrize('change', [None, float('nan')])
@pytest.mark.parametrize('region', ['cn', 'hk', 'us'])
def test_missing_index_change_is_unknown_not_flat(change, region):
    with patch('src.market_analyzer.get_config', return_value=SimpleNamespace(report_language='zh')):
        analyzer = MarketAnalyzer(region=region)
    overview = MarketOverview(date='2026-09-05', indices=[
        MarketIndex(code=analyzer.profile.mood_index_code, name='ExampleIndex', current=None, change_pct=change),
    ])
    for text in [analyzer._build_review_prompt(overview, []),
                 analyzer._build_indices_block(overview),
                 analyzer._generate_template_review(overview, [])]:
        assert 'ExampleIndex' in text
        assert 'N/A' in text
        assert 'nan%' not in text
        assert '+0.00%' not in text
