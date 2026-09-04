"""screener/indicators.py

Tính các chỉ báo kỹ thuật cơ bản: SMA, RSI, Volume MA.
Tất cả hàm nhận vào DataFrame giá đã chuẩn hóa (cột Ticker, Date, Close,
Volume, ... như trả về bởi data_pipeline.loader) và tính riêng cho từng
Ticker (groupby) để tránh rò rỉ dữ liệu giữa các mã.
"""
from __future__ import annotations

import pandas as pd

DEFAULT_SMA_WINDOWS = (20, 50)
DEFAULT_RSI_WINDOW = 14
DEFAULT_VOLUME_MA_WINDOW = 20


def add_sma(df: pd.DataFrame, windows: tuple[int, ...] = DEFAULT_SMA_WINDOWS) -> pd.DataFrame:
    """Thêm cột SMA_<n> = trung bình động Close, tính riêng theo từng Ticker.

    Yêu cầu df đã được sort theo (Ticker, Date) tăng dần.
    """
    out = df.copy()
    for window in windows:
        out[f"SMA_{window}"] = out.groupby("Ticker")["Close"].transform(
            lambda s: s.rolling(window=window, min_periods=window).mean()
        )
    return out


def add_rsi(df: pd.DataFrame, window: int = DEFAULT_RSI_WINDOW) -> pd.DataFrame:
    """Thêm cột RSI_<n> (Relative Strength Index, Wilder's smoothing), theo từng Ticker."""
    out = df.copy()

    def _rsi(close: pd.Series) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        # Wilder's smoothing == EMA với alpha = 1/window.
        avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, pd.NA)
        rsi = 100 - (100 / (1 + rs))
        rsi = rsi.where(avg_loss != 0, 100.0)  # loss = 0 toàn bộ -> RSI = 100
        return rsi

    out[f"RSI_{window}"] = out.groupby("Ticker")["Close"].transform(_rsi)
    return out


def add_volume_ma(df: pd.DataFrame, window: int = DEFAULT_VOLUME_MA_WINDOW) -> pd.DataFrame:
    """Thêm cột VolumeMA_<n> = trung bình động Volume, tính riêng theo từng Ticker."""
    out = df.copy()
    out[f"VolumeMA_{window}"] = out.groupby("Ticker")["Volume"].transform(
        lambda s: s.rolling(window=window, min_periods=window).mean()
    )
    return out


def add_all_indicators(
    df: pd.DataFrame,
    sma_windows: tuple[int, ...] = DEFAULT_SMA_WINDOWS,
    rsi_window: int = DEFAULT_RSI_WINDOW,
    volume_ma_window: int = DEFAULT_VOLUME_MA_WINDOW,
) -> pd.DataFrame:
    """Tính gộp SMA + RSI + Volume MA trên DataFrame giá."""
    out = df.sort_values(["Ticker", "Date"]).reset_index(drop=True)
    out = add_sma(out, sma_windows)
    out = add_rsi(out, rsi_window)
    out = add_volume_ma(out, volume_ma_window)
    return out
