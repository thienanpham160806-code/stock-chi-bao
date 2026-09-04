"""dashboard/app.py

App Streamlit — Market Visualization Platform (Task 2) + Stock Screener
view (Task 3). Đọc trực tiếp từ SQLite do run_pipeline.py cập nhật, nên
sau mỗi lần chạy pipeline, dashboard tự phản ánh dữ liệu mới nhất mà
không cần chỉnh sửa gì thêm ("Update Dashboard" trong Task 4).

Chạy: streamlit run dashboard/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

# Cho phép chạy `streamlit run dashboard/app.py` trực tiếp mà vẫn import
# được các package ở thư mục gốc project.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data_pipeline.config import SQLITE_DB_PATH
from data_pipeline.db import load_prices, load_screener_results, save_screener_results
from data_pipeline.pipeline import run_ingest
from screener.indicators import DEFAULT_RSI_WINDOW, DEFAULT_SMA_WINDOWS
from screener.signals import generate_signals, screen_universe

st.set_page_config(page_title="Automated Stock Analytics Platform", layout="wide")


@st.cache_data(show_spinner=False)
def _load_all_prices() -> pd.DataFrame:
    return load_prices(SQLITE_DB_PATH)


@st.cache_data(show_spinner=False)
def _load_screener() -> pd.DataFrame:
    return load_screener_results(SQLITE_DB_PATH)


def render_market_watch(df: pd.DataFrame) -> None:
    """Tab theo dõi giá 1 mã: Stock Selection + Price Visualization + Market Information."""
    st.sidebar.header("Bộ lọc")

    exchanges = sorted(df["Exchange"].unique())
    exchange = st.sidebar.selectbox("Sàn giao dịch", exchanges)

    tickers = sorted(df.loc[df["Exchange"] == exchange, "Ticker"].unique())
    ticker = st.sidebar.selectbox("Mã cổ phiếu", tickers)

    ticker_df = df[(df["Exchange"] == exchange) & (df["Ticker"] == ticker)].sort_values("Date")

    min_date, max_date = ticker_df["Date"].min().date(), ticker_df["Date"].max().date()
    date_range = st.sidebar.date_input(
        "Khoảng thời gian",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date, end_date = min_date, max_date

    mask = (ticker_df["Date"].dt.date >= start_date) & (ticker_df["Date"].dt.date <= end_date)
    view_df = ticker_df.loc[mask]

    if view_df.empty:
        st.info("Không có dữ liệu trong khoảng thời gian đã chọn.")
        return

    # Tính chỉ báo + tín hiệu trên toàn bộ lịch sử của ticker rồi mới cắt
    # theo range, để SMA/RSI ở đầu khoảng thời gian không bị thiếu do cắt
    # dữ liệu quá sớm.
    signaled = generate_signals(ticker_df)
    signaled = signaled.loc[(signaled["Date"].dt.date >= start_date) & (signaled["Date"].dt.date <= end_date)]

    short_win, long_win = sorted(DEFAULT_SMA_WINDOWS)[:2]

    # --- C. Market Information ---
    latest = view_df.iloc[-1]
    prev_close = view_df.iloc[-2]["Close"] if len(view_df) >= 2 else latest["Open"]
    pct_change = (latest["Close"] - prev_close) / prev_close * 100 if prev_close else 0.0
    period_max = view_df["High"].max()
    period_min = view_df["Low"].min()
    latest_rsi = signaled[f"RSI_{DEFAULT_RSI_WINDOW}"].iloc[-1] if not signaled.empty else None
    latest_signal = signaled["Signal"].iloc[-1] if not signaled.empty else "HOLD"

    st.subheader(f"{ticker} ({exchange})")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Giá gần nhất", f"{latest['Close']:.2f}", f"{pct_change:+.2f}%")
    c2.metric("Khối lượng", f"{int(latest['Volume']):,}")
    c3.metric(f"Max ({start_date}→{end_date})", f"{period_max:.2f}")
    c4.metric(f"Min ({start_date}→{end_date})", f"{period_min:.2f}")
    c5.metric(f"RSI{DEFAULT_RSI_WINDOW}", f"{latest_rsi:.1f}" if pd.notna(latest_rsi) else "N/A")
    c6.metric("Tín hiệu mới nhất", latest_signal)

    # --- B. Price Visualization: candlestick + volume + SMA + RSI ---
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.55, 0.2, 0.25],
        vertical_spacing=0.03,
        subplot_titles=(f"{ticker} ({exchange})", "Khối lượng", f"RSI ({DEFAULT_RSI_WINDOW})"),
    )

    fig.add_trace(
        go.Candlestick(
            x=signaled["Date"], open=signaled["Open"], high=signaled["High"],
            low=signaled["Low"], close=signaled["Close"], name="Giá",
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(x=signaled["Date"], y=signaled[f"SMA_{short_win}"], name=f"SMA{short_win}", line=dict(width=1.2)),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(x=signaled["Date"], y=signaled[f"SMA_{long_win}"], name=f"SMA{long_win}", line=dict(width=1.2)),
        row=1, col=1,
    )

    buys = signaled[signaled["Signal"] == "BUY"]
    sells = signaled[signaled["Signal"] == "SELL"]
    fig.add_trace(
        go.Scatter(
            x=buys["Date"], y=buys["Low"] * 0.98, mode="markers", name="BUY",
            marker=dict(symbol="triangle-up", size=10, color="green"),
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=sells["Date"], y=sells["High"] * 1.02, mode="markers", name="SELL",
            marker=dict(symbol="triangle-down", size=10, color="red"),
        ),
        row=1, col=1,
    )

    fig.add_trace(go.Bar(x=signaled["Date"], y=signaled["Volume"], name="Volume"), row=2, col=1)

    fig.add_trace(
        go.Scatter(x=signaled["Date"], y=signaled[f"RSI_{DEFAULT_RSI_WINDOW}"], name="RSI", line=dict(width=1.2)),
        row=3, col=1,
    )
    fig.add_hline(y=70, line_dash="dot", line_color="red", row=3, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="green", row=3, col=1)

    fig.update_layout(height=800, xaxis_rangeslider_visible=False, legend=dict(orientation="h"))
    st.plotly_chart(fig, width="stretch")


def render_screener(screener_df: pd.DataFrame) -> None:
    """Tab Stock Screener — bảng tín hiệu BUY/SELL/HOLD toàn universe (Task 3)."""
    st.subheader("📋 Technical Analysis Stock Screener")
    st.caption(
        "Chiến lược Multi-factor: SMA20/50 crossover (Trend) + RSI14 (Momentum) "
        "+ Volume vs VolumeMA20 (Market Strength). Xem chi tiết trong screener/signals.py."
    )

    if screener_df.empty:
        st.warning("Chưa có kết quả screener. Hãy chạy `python run_pipeline.py`.")
        return

    col1, col2, col3 = st.columns(3)
    exchange_filter = col1.multiselect("Sàn", sorted(screener_df["Exchange"].unique()))
    signal_filter = col2.multiselect("Tín hiệu", ["BUY", "SELL", "HOLD"], default=["BUY", "SELL"])
    ticker_search = col3.text_input("Tìm mã (vd: FPT)").strip().upper()

    view = screener_df.copy()
    if exchange_filter:
        view = view[view["Exchange"].isin(exchange_filter)]
    if signal_filter:
        view = view[view["Signal"].isin(signal_filter)]
    if ticker_search:
        view = view[view["Ticker"].str.contains(ticker_search)]

    counts = screener_df["Signal"].value_counts()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Tổng số mã", len(screener_df))
    m2.metric("BUY", int(counts.get("BUY", 0)))
    m3.metric("SELL", int(counts.get("SELL", 0)))
    m4.metric("HOLD", int(counts.get("HOLD", 0)))

    st.dataframe(view.sort_values(["Signal", "Ticker"]), width="stretch", height=500)


def render_refresh_control() -> None:
    """Nút cập nhật dữ liệu ngay trong dashboard — bấm 1 nút là tự động
    Download -> Extract -> Clean -> Store -> Analyze -> Signal -> Screener,
    không cần rời trình duyệt / mở terminal (Task 4: hạn chế thao tác thủ công)."""
    with st.sidebar:
        st.subheader("⚙️ Dữ liệu")
        if st.button("🔄 Cập nhật dữ liệu mới nhất từ CafeF", width="stretch"):
            with st.spinner("Đang dò + tải + xử lý dữ liệu mới nhất từ CafeF (có thể mất vài phút)..."):
                try:
                    rows = run_ingest()
                    if rows:
                        prices = load_prices(SQLITE_DB_PATH)
                        screener_df = screen_universe(prices)
                        save_screener_results(screener_df, SQLITE_DB_PATH)
                    _load_all_prices.clear()
                    _load_screener.clear()
                except Exception as exc:  # noqa: BLE001 - hiển thị lỗi cho người dùng thay vì crash app
                    st.error(f"Cập nhật thất bại: {exc}")
                else:
                    if rows:
                        st.success(f"Đã cập nhật {rows:,} dòng dữ liệu.")
                    else:
                        st.warning("Không tải được dữ liệu mới (kiểm tra kết nối mạng).")
        st.divider()


def main() -> None:
    st.title("📈 Automated Stock Analytics Platform")

    render_refresh_control()

    df = _load_all_prices()
    if df.empty:
        st.warning(
            "Chưa có dữ liệu trong SQLite. Bấm nút '🔄 Cập nhật dữ liệu mới nhất từ CafeF' "
            "ở sidebar (hoặc chạy `python run_pipeline.py`) để tự động tải + xử lý dữ liệu."
        )
        return

    st.caption(f"📅 Dữ liệu giá tính đến: **{df['Date'].max().date()}**")

    tab_watch, tab_screener = st.tabs(["🕯️ Market Watch", "📋 Stock Screener"])
    with tab_watch:
        render_market_watch(df)
    with tab_screener:
        render_screener(_load_screener())


if __name__ == "__main__":
    main()
