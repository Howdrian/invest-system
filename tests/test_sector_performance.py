from datetime import date, timedelta

from data_provider.sector_performance import collect_sector_performance


def series(end='2026-09-04', factor=1.0):
    end_date = date.fromisoformat(end)
    dates = [end_date - timedelta(days=n) for n in range(130)]
    dates = list(reversed([d for d in dates if d.weekday() < 5]))[-70:]
    return [{'date': str(d), 'close': 100 + i * factor} for i, d in enumerate(dates)]


def test_sector_history_matches_benchmark_dates_and_preserves_scope():
    data = collect_sector_performance('us', '2026-09-06', loader=lambda s: series(factor=2 if s == 'XLK' else 1))
    assert len(data['records']) == 11
    assert data['expected_count'] == 11
    row = next(r for r in data['records'] if r['code'] == 'XLK')
    assert row['as_of'] == '2026-09-04'
    assert row['relative_20d_pp'] > 0
    assert row['comparison_start_20d'] < row['as_of']
    assert row['return_60d_pct'] > row['return_20d_pct']
    assert data['benchmark'] == 'SPY'
    assert '标普500' in data['scope']
    assert {r['status'] for r in data['provider_runs']} == {'success'}


def test_hk_scope_is_not_falsely_entire_market_and_failure_remains_visible():
    def loader(s):
        if s == 'HSMBI':
            raise TimeoutError('fixture')
        return series()
    data = collect_sector_performance('hk', '2026-09-06', loader=loader)
    assert data['expected_count'] == 6 and len(data['records']) == 5
    assert data['benchmark'] == 'HSI'
    assert '全行业' in data['scope']
    assert any(r['symbol'] == 'HSMBI' and r['status'] == 'failed' for r in data['provider_runs'])


def test_missing_benchmark_date_cannot_create_misaligned_relative_return():
    def loader(s):
        values = series()
        return values[:-1] if s == 'SPY' else values
    data = collect_sector_performance('us', '2026-09-06', loader=loader)
    assert data['records'][0]['return_20d_pct'] > 0
    assert 'relative_20d_pp' not in data['records'][0]


def test_future_bars_removed_and_duplicate_dates_do_not_inflate_returns():
    data = collect_sector_performance('us', '2026-08-20', loader=lambda s: series() + series())
    assert len(data['records']) == 11
    assert all(r['as_of'] <= '2026-08-20' for r in data['records'])
    assert all(r['sample_count'] <= 70 for r in data['records'])


def test_unsupported_market_does_not_fetch():
    data = collect_sector_performance('jp', '2026-09-06', loader=lambda s: 1 / 0)
    assert not data['records']
    assert data['status'] == 'not_supported'


def test_six_month_comparison_uses_120_sessions_not_calendar_days():
    import pytest
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(230)]
    dates = [str(d) for d in dates if d.weekday() < 5]
    def loader(symbol):
        return [{'date': d, 'close': 100 + i * (2 if symbol == 'XLK' else 1)} for i, d in enumerate(dates)]
    data = collect_sector_performance('us', dates[-1], loader=loader)
    row = next(r for r in data['records'] if r['code'] == 'XLK')
    assert row['comparison_start_120d'] == dates[-121]
    prices = loader('XLK')
    expected = (prices[-1]['close'] / prices[-121]['close'] - 1) * 100
    assert row['return_120d_pct'] == pytest.approx(expected, abs=.001)
    assert 'relative_120d_pp' in row
    shorter = collect_sector_performance('us', '2026-09-06', loader=lambda _: series())
    assert all('return_120d_pct' not in r for r in shorter['records'])
