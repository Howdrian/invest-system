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


def test_akshare_main_indices_supports_hk_indices_from_public_spot_source():
    fetcher = AkshareFetcher()
    fake_df = pd.DataFrame(
        {
            "代码": ["HSI", "HSTECH", "HSCEI", "VHSI"],
            "名称": ["恒生指数", "恒生科技指数", "国企指数", "恒指波幅指数"],
            "最新价": [24000.0, 5200.0, 8700.0, 20.0],
            "涨跌额": [100.0, 0.0, -20.0, 1.0],
            "涨跌幅": [0.42, 0.0, -0.23, 5.0],
            "今开": [23920.0, 5100.0, 8720.0, 19.0],
            "最高": [24100.0, 5250.0, 8750.0, 21.0],
            "最低": [23800.0, 5050.0, 8650.0, 18.0],
            "昨收": [23900.0, 5100.0, 8720.0, 19.0],
            "成交量": [1, 2, 3, 4],
            "成交额": [10, 20, 30, 40],
        }
    )
    fake_akshare = types.SimpleNamespace(stock_hk_index_spot_em=lambda: fake_df)

    with patch.dict(sys.modules, {"akshare": fake_akshare}), patch.object(
        fetcher, "_set_random_user_agent", return_value=None
    ), patch.object(fetcher, "_enforce_rate_limit", return_value=None):
        rows = fetcher.get_main_indices("hk")

    assert rows and {row["code"] for row in rows} == {"HSI", "HSTECH", "HSCEI"}
    hstech = next(row for row in rows if row["code"] == "HSTECH")
    assert round(hstech["change_pct"], 2) == 1.96
