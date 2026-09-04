"""Test cho screener/signals.py.

Thay vì hard-code 1 kịch bản giá rồi đoán tín hiệu kỳ vọng, các test này
tạo dữ liệu giá ngẫu nhiên (random walk, có seed cố định để tái lập được)
rồi kiểm chứng NGƯỢC LẠI rằng mọi dòng được gán BUY/SELL đều thỏa đúng
công thức định lượng nêu trong screener/signals.py — tức là xác nhận
thuật toán triển khai đúng quy tắc đã định nghĩa, không có ca đặc biệt
nào bị bỏ sót hoặc lẫn logic chủ quan.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from screener.indicators import DEFAULT_RSI_WINDOW, DEFAULT_SMA_WINDOWS, DEFAULT_VOLUME_MA_WINDOW
from screener.signals import SCREENER_OUTPUT_COLUMNS, generate_signals, screen_universe

SHORT_WIN, LONG_WIN = sorted(DEFAULT_SMA_WINDOWS)[:2]


def _make_random_walk_prices(ticker: str, exchange: str, n: int = 150, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-02", periods=n)
    returns = rng.normal(0, 0.02, n)
    close = 10 * np.exp(np.cumsum(returns))
    open_ = close * (1 + rng.normal(0, 0.005, n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.005, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.005, n)))
    volume = rng.integers(1_000, 100_000, n)
    return pd.DataFrame(
        {
            "Ticker": ticker,
            "Exchange": exchange,
            "Date": dates,
            "Open": open_,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": volume,
        }
    )


def test_buy_rows_satisfy_golden_cross_rsi_volume_rule():
    df = _make_random_walk_prices("AAA", "HOSE", seed=2)
    out = generate_signals(df)
    prev_short = out[f"SMA_{SHORT_WIN}"].shift(1)
    prev_long = out[f"SMA_{LONG_WIN}"].shift(1)

    buy_rows = out[out["Signal"] == "BUY"]
    assert len(buy_rows) > 0, "seed cần tạo ít nhất 1 tín hiệu BUY để test có ý nghĩa"
    for idx, row in buy_rows.iterrows():
        assert row[f"SMA_{SHORT_WIN}"] > row[f"SMA_{LONG_WIN}"]
        assert prev_short[idx] <= prev_long[idx]
        assert row[f"RSI_{DEFAULT_RSI_WINDOW}"] < 70
        assert row["Volume"] > row[f"VolumeMA_{DEFAULT_VOLUME_MA_WINDOW}"]


def test_sell_rows_satisfy_death_cross_and_rsi_and_volume_rule():
    # SELL đối xứng với BUY: death cross AND RSI>50 (momentum yếu đi) AND
    # volume xác nhận — cùng cấu trúc AND 3 điều kiện như BUY, không còn OR.
    df = _make_random_walk_prices("BBB", "HNX", seed=28)
    out = generate_signals(df)
    prev_short = out[f"SMA_{SHORT_WIN}"].shift(1)
    prev_long = out[f"SMA_{LONG_WIN}"].shift(1)

    sell_rows = out[out["Signal"] == "SELL"]
    assert len(sell_rows) > 0, "seed cần tạo ít nhất 1 tín hiệu SELL để test có ý nghĩa"
    for idx, row in sell_rows.iterrows():
        assert row[f"SMA_{SHORT_WIN}"] < row[f"SMA_{LONG_WIN}"]
        assert prev_short[idx] >= prev_long[idx]
        assert row[f"RSI_{DEFAULT_RSI_WINDOW}"] > 50
        assert row["Volume"] > row[f"VolumeMA_{DEFAULT_VOLUME_MA_WINDOW}"]


def test_screen_universe_output_shape_and_columns():
    df = pd.concat(
        [
            _make_random_walk_prices("AAA", "HOSE", seed=1),
            _make_random_walk_prices("BBB", "HNX", seed=2),
            _make_random_walk_prices("CCC", "UPCOM", seed=3),
        ],
        ignore_index=True,
    )
    result = screen_universe(df)

    assert list(result.columns) == SCREENER_OUTPUT_COLUMNS
    # Đúng 1 dòng (tín hiệu mới nhất) cho mỗi ticker trong universe.
    assert sorted(result["Ticker"]) == ["AAA", "BBB", "CCC"]
    assert set(result["Signal"]) <= {"BUY", "SELL", "HOLD"}

    # Signal Date phải là ngày giao dịch gần nhất có trong dữ liệu của mỗi mã.
    for ticker, sub in df.groupby("Ticker"):
        expected_last_date = sub["Date"].max()
        actual = result.loc[result["Ticker"] == ticker, "Signal Date"].iloc[0]
        assert pd.Timestamp(actual) == expected_last_date
