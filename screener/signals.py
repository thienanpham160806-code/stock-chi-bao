"""screener/signals.py

Sinh tín hiệu BUY / SELL / HOLD bằng thuật toán định lượng thuần túy
(không dùng nhận định chủ quan) — Task 3 của đề bài.

Chiến lược: Multi-factor Technical Strategy, kết hợp 3 khía cạnh phân
tích kỹ thuật độc lập, mỗi khía cạnh phản ánh một chiều thông tin khác
nhau của thị trường:

- Trend (SMA20 vs SMA50)   : SMA ngắn hạn cắt SMA dài hạn (golden/death
  cross) cho biết xu hướng giá trung hạn đang đảo chiều tăng hay giảm.
- Momentum (RSI14)         : RSI đo tốc độ & độ lớn biến động giá gần
  đây — BUY đòi RSI chưa quá mua (< 70), SELL đòi RSI đã cắt xuống dưới
  mốc trung tính 50 (momentum đang yếu đi, ủng hộ chiều giảm).
- Volume (Volume vs VolumeMA20): Khối lượng giao dịch lớn hơn trung
  bình 20 phiên xác nhận dòng tiền thực sự tham gia vào điểm đảo chiều
  (Market Strength) — loại bỏ tín hiệu chéo SMA "yếu" do thanh khoản thấp.
  Áp dụng đối xứng cho cả BUY và SELL.

Quy tắc định lượng (BUY và SELL đối xứng nhau — cùng 3 điều kiện AND,
chỉ khác chiều):

    BUY  :  SMA20_t > SMA50_t  và  SMA20_(t-1) <= SMA50_(t-1)      (golden cross)
        và  RSI14_t < 70                                          (chưa quá mua)
        và  Volume_t > VolumeMA20_t                                (dòng tiền xác nhận)

    SELL :  SMA20_t < SMA50_t  và  SMA20_(t-1) >= SMA50_(t-1)      (death cross)
        và  RSI14_t > 50                                          (momentum đang yếu đi)
        và  Volume_t > VolumeMA20_t                                (dòng tiền xác nhận)

    HOLD :  các trường hợp còn lại (bao gồm chưa đủ dữ liệu để tính chỉ báo).

Tất cả điều kiện trên đều là bất đẳng thức số học tính trực tiếp từ dữ
liệu OHLCV — không có bước diễn giải chủ quan nào.
"""
from __future__ import annotations

import pandas as pd

from screener.indicators import (
    DEFAULT_RSI_WINDOW,
    DEFAULT_SMA_WINDOWS,
    DEFAULT_VOLUME_MA_WINDOW,
    add_all_indicators,
)

RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
RSI_NEUTRAL = 50  # mốc trung tính dùng cho điều kiện SELL (momentum đang yếu đi)

# Cột đầu ra chuẩn cho bảng screener toàn universe (đúng theo yêu cầu đề bài:
# Ticker | Exchange | Close | Signal | Indicator | Signal Date).
SCREENER_OUTPUT_COLUMNS = ["Ticker", "Exchange", "Close", "Signal", "Indicator", "Signal Date"]


def generate_signals(
    df: pd.DataFrame,
    sma_windows: tuple[int, ...] = DEFAULT_SMA_WINDOWS,
    rsi_window: int = DEFAULT_RSI_WINDOW,
    volume_ma_window: int = DEFAULT_VOLUME_MA_WINDOW,
) -> pd.DataFrame:
    """Trả về DataFrame gốc + các cột chỉ báo + cột Signal (BUY/SELL/HOLD) cho mọi phiên.

    Dùng cho chart (dashboard cần Signal ở từng điểm dữ liệu để vẽ marker),
    khác với screen_universe() chỉ lấy tín hiệu mới nhất của mỗi mã.
    """
    if len(sma_windows) < 2:
        raise ValueError("Cần ít nhất 2 SMA window (ngắn, dài) để so sánh golden/death cross.")

    short_win, long_win = sorted(sma_windows)[:2]
    out = add_all_indicators(df, sma_windows, rsi_window, volume_ma_window)

    sma_short = out[f"SMA_{short_win}"]
    sma_long = out[f"SMA_{long_win}"]
    rsi = out[f"RSI_{rsi_window}"]
    volume_ma = out[f"VolumeMA_{volume_ma_window}"]

    # So sánh với phiên trước đó (trong cùng 1 ticker) để phát hiện điểm cắt.
    prev_short = out.groupby("Ticker")[f"SMA_{short_win}"].shift(1)
    prev_long = out.groupby("Ticker")[f"SMA_{long_win}"].shift(1)

    golden_cross = (prev_short <= prev_long) & (sma_short > sma_long)
    death_cross = (prev_short >= prev_long) & (sma_short < sma_long)

    has_indicators = sma_short.notna() & sma_long.notna() & rsi.notna() & volume_ma.notna()

    # BUY và SELL đối xứng nhau: cùng 3 điều kiện AND (cross + RSI + volume),
    # chỉ khác chiều — tránh bất đối xứng logic (BUY chặt bằng AND 3 điều
    # kiện trong khi SELL trước đây chỉ cần OR 1 trong 2).
    buy = has_indicators & golden_cross & (rsi < RSI_OVERBOUGHT) & (out["Volume"] > volume_ma)
    sell = has_indicators & death_cross & (rsi > RSI_NEUTRAL) & (out["Volume"] > volume_ma)

    out["Signal"] = "HOLD"
    out.loc[buy, "Signal"] = "BUY"
    out.loc[sell, "Signal"] = "SELL"

    return out


def _indicator_summary(row: pd.Series, short_win: int, long_win: int, rsi_window: int, volume_ma_window: int) -> str:
    """Tạo chuỗi tóm tắt chỉ báo tại thời điểm sinh tín hiệu, dùng cho cột 'Indicator'."""
    sma_s = row.get(f"SMA_{short_win}")
    sma_l = row.get(f"SMA_{long_win}")
    rsi = row.get(f"RSI_{rsi_window}")
    vol_ma = row.get(f"VolumeMA_{volume_ma_window}")

    if pd.isna(sma_s) or pd.isna(sma_l) or pd.isna(rsi) or pd.isna(vol_ma) or vol_ma == 0:
        return "Chưa đủ dữ liệu (< window)"

    vol_ratio = row["Volume"] / vol_ma
    cross = ">" if sma_s > sma_l else ("<" if sma_s < sma_l else "=")
    return f"SMA{short_win}={sma_s:.2f}{cross}SMA{long_win}={sma_l:.2f}; RSI{rsi_window}={rsi:.1f}; Vol={vol_ratio:.2f}xMA{volume_ma_window}"


def screen_universe(
    df: pd.DataFrame,
    sma_windows: tuple[int, ...] = DEFAULT_SMA_WINDOWS,
    rsi_window: int = DEFAULT_RSI_WINDOW,
    volume_ma_window: int = DEFAULT_VOLUME_MA_WINDOW,
) -> pd.DataFrame:
    """Sinh tín hiệu BUY/SELL/HOLD mới nhất cho TOÀN BỘ universe cổ phiếu.

    Trả về bảng đúng định dạng yêu cầu Task 3:
        Ticker | Exchange | Close | Signal | Indicator | Signal Date
    """
    short_win, long_win = sorted(sma_windows)[:2]
    signaled = generate_signals(df, sma_windows, rsi_window, volume_ma_window)

    latest = signaled.sort_values("Date").groupby("Ticker", as_index=False).tail(1).copy()
    latest["Indicator"] = latest.apply(
        lambda r: _indicator_summary(r, short_win, long_win, rsi_window, volume_ma_window), axis=1
    )
    latest = latest.rename(columns={"Date": "Signal Date"})
    latest = latest[SCREENER_OUTPUT_COLUMNS].sort_values(["Signal", "Ticker"]).reset_index(drop=True)
    return latest


# Alias giữ tương thích ngược cho code/dashboard gọi tên cũ.
latest_signals = screen_universe
