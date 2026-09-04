"""Test cho data_pipeline/loader.py.

Fixture tests/fixtures/CafeF.HSX.Upto04092026.csv mô phỏng đúng đặc
điểm dữ liệu nguồn: có BOM, CRLF, nhóm theo ticker (không sort theo
ngày toàn cục), có 1 dòng trùng lặp y hệt, và không có cột Exchange.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from data_pipeline.loader import (
    STANDARD_COLUMNS,
    LoaderError,
    infer_exchange_from_filename,
    load_csv,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
SAMPLE_CSV = FIXTURES_DIR / "CafeF.HSX.Upto04092026.csv"


def test_infer_exchange_from_filename():
    assert infer_exchange_from_filename("CafeF.HSX.Upto04092026.csv") == "HOSE"
    assert infer_exchange_from_filename("CafeF.HOSE.Upto04092026.csv") == "HOSE"
    assert infer_exchange_from_filename("CafeF.HNX.Upto04092026.csv") == "HNX"
    assert infer_exchange_from_filename("CafeF.UPCOM.Upto04092026.csv") == "UPCOM"


def test_infer_exchange_unknown_raises():
    with pytest.raises(LoaderError):
        infer_exchange_from_filename("some_random_file.csv")


def test_load_csv_missing_file_raises():
    with pytest.raises(LoaderError):
        load_csv(FIXTURES_DIR / "does_not_exist.csv")


def test_load_csv_returns_standard_columns():
    df = load_csv(SAMPLE_CSV)
    assert list(df.columns) == STANDARD_COLUMNS


def test_load_csv_infers_exchange_from_filename():
    df = load_csv(SAMPLE_CSV)
    assert set(df["Exchange"].unique()) == {"HOSE"}


def test_load_csv_dedupes_exact_duplicate_rows():
    # File nguồn có 7 dòng dữ liệu: 1 dòng trùng y hệt (AAA, 2024-01-02)
    # và 1 dòng thiếu Ticker -> cả hai đều phải bị loại, còn lại 5 dòng.
    df = load_csv(SAMPLE_CSV)
    assert len(df) == 5
    # Không còn cặp (Ticker, Date) nào bị trùng.
    assert not df.duplicated(subset=["Ticker", "Date"]).any()


def test_load_csv_drops_rows_missing_ticker():
    # Dữ liệu CafeF thực tế có thể có dòng bị thiếu Ticker (trường rỗng
    # ở đầu dòng) -> phải bị loại bỏ thay vì để lọt vào DataFrame chuẩn hóa.
    df = load_csv(SAMPLE_CSV)
    assert not (df["Ticker"].isna() | (df["Ticker"] == "")).any()
    assert pd.Timestamp("2024-01-05") not in set(df["Date"])


def test_load_csv_parses_date_and_dtypes():
    df = load_csv(SAMPLE_CSV)
    assert pd.api.types.is_datetime64_any_dtype(df["Date"])
    assert df["Date"].min() == pd.Timestamp("2024-01-02")
    assert pd.api.types.is_integer_dtype(df["Volume"])
    for col in ["Open", "High", "Low", "Close"]:
        assert pd.api.types.is_float_dtype(df[col])


def test_load_csv_sorted_per_ticker_ascending_date():
    # File nguồn nhóm theo ticker và KHÔNG sort theo ngày (AAA: 3,2,2,4)
    # -> loader phải tự sort lại tăng dần theo (Ticker, Date).
    df = load_csv(SAMPLE_CSV)
    aaa = df[df["Ticker"] == "AAA"].reset_index(drop=True)
    assert list(aaa["Date"]) == sorted(aaa["Date"])
    assert list(aaa["Date"].dt.strftime("%Y%m%d")) == ["20240102", "20240103", "20240104"]

    bbb = df[df["Ticker"] == "BBB"].reset_index(drop=True)
    assert list(bbb["Date"].dt.strftime("%Y%m%d")) == ["20240102", "20240103"]


def test_load_csv_values_are_correct():
    df = load_csv(SAMPLE_CSV)
    row = df[(df["Ticker"] == "AAA") & (df["Date"] == pd.Timestamp("2024-01-04"))].iloc[0]
    assert row["Open"] == 10.2
    assert row["High"] == 10.6
    assert row["Low"] == 10.1
    assert row["Close"] == 10.5
    assert row["Volume"] == 110000
