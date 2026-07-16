import sys
import types
from unittest.mock import patch

import pandas as pd

from data_provider.akshare_fetcher import AkshareFetcher


def test_akshare_main_indices_recomputes_zero_change_fields_from_previous_close():
    fetcher = AkshareFetcher()
    fake_df = pd.DataFrame(
        {
            "代码": ["sh000688"],
            "最新价": [1924.2736],
            "昨收": [2009.67],
            "涨跌额": [0.0],
            "涨跌幅": [0.0],
            "今开": [2000.0],
            "最高": [2021.58],
            "最低": [1908.18],
            "成交量": [100],
            "成交额": [200],
        }
    )
    fake_akshare = types.SimpleNamespace(stock_zh_index_spot_sina=lambda: fake_df)

    with patch.dict(sys.modules, {"akshare": fake_akshare}), patch.object(
        fetcher, "_set_random_user_agent", return_value=None
    ), patch.object(fetcher, "_enforce_rate_limit", return_value=None):
        rows = fetcher.get_main_indices("cn")

    assert rows and len(rows) == 1
    assert round(rows[0]["change"], 4) == round(1924.2736 - 2009.67, 4)
    assert round(rows[0]["change_pct"], 2) == -4.25
