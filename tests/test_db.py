"""Test cho data_pipeline/db.py.

Bug thực tế phát hiện trên Streamlit Cloud (deploy mới/DB trống, chưa
ingest lần nào): load_prices() query bảng `prices` chưa tồn tại ->
pandas.errors.DatabaseError -> crash toàn bộ app trước khi kịp kích
hoạt auto-refresh. Test này khóa lại hành vi đúng: trả DataFrame rỗng,
không raise.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from data_pipeline.db import load_prices, load_screener_results, save_prices, save_screener_results


def test_load_prices_on_missing_table_returns_empty_dataframe(tmp_path: Path):
    db_path = tmp_path / "fresh.db"  # chưa từng ingest -> chưa có bảng nào
    df = load_prices(db_path)
    assert df.empty
    assert list(df.columns) == ["Ticker", "Exchange", "Date", "Open", "High", "Low", "Close", "Volume"]


def test_load_screener_results_on_missing_table_returns_empty_dataframe(tmp_path: Path):
    db_path = tmp_path / "fresh.db"
    df = load_screener_results(db_path)
    assert df.empty
    assert list(df.columns) == ["Ticker", "Exchange", "Close", "Signal", "Indicator", "Signal Date"]


def test_save_then_load_prices_roundtrip(tmp_path: Path):
    db_path = tmp_path / "roundtrip.db"
    prices = pd.DataFrame(
        {
            "Ticker": ["AAA", "AAA"],
            "Exchange": ["HOSE", "HOSE"],
            "Date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "Open": [10.0, 10.2],
            "High": [10.5, 10.6],
            "Low": [9.8, 10.1],
            "Close": [10.2, 10.5],
            "Volume": [100000, 110000],
        }
    )
    saved = save_prices(prices, db_path)
    assert saved == 2

    loaded = load_prices(db_path)
    assert len(loaded) == 2
    assert set(loaded["Ticker"]) == {"AAA"}
