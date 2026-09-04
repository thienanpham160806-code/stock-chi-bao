"""data_pipeline/db.py

Lưu DataFrame giá đã chuẩn hóa vào SQLite, và đọc lại cho các module
downstream (screener, dashboard) dùng.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pandas as pd

from data_pipeline.config import PRICES_TABLE, SCREENER_TABLE, SQLITE_DB_PATH

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {PRICES_TABLE} (
    Ticker   TEXT    NOT NULL,
    Exchange TEXT    NOT NULL,
    Date     TEXT    NOT NULL,
    Open     REAL    NOT NULL,
    High     REAL    NOT NULL,
    Low      REAL    NOT NULL,
    Close    REAL    NOT NULL,
    Volume   INTEGER NOT NULL,
    PRIMARY KEY (Ticker, Date)
);
"""

_CREATE_INDEX_SQL = f"""
CREATE INDEX IF NOT EXISTS idx_{PRICES_TABLE}_exchange
ON {PRICES_TABLE} (Exchange);
"""


def get_connection(db_path: str | Path = SQLITE_DB_PATH) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)


def save_prices(df: pd.DataFrame, db_path: str | Path = SQLITE_DB_PATH) -> int:
    """Ghi (upsert theo Ticker+Date) DataFrame giá chuẩn hóa vào SQLite.

    Dùng INSERT OR REPLACE để chạy lại pipeline nhiều lần không bị lỗi
    trùng khóa chính, đồng thời tự cập nhật dữ liệu nếu file nguồn thay đổi.
    """
    if df.empty:
        logger.warning("DataFrame rỗng, không có gì để lưu vào SQLite.")
        return 0

    out = df.copy()
    out["Date"] = out["Date"].dt.strftime("%Y-%m-%d")

    conn = get_connection(db_path)
    try:
        conn.execute(_CREATE_TABLE_SQL)
        conn.execute(_CREATE_INDEX_SQL)
        rows = out[["Ticker", "Exchange", "Date", "Open", "High", "Low", "Close", "Volume"]].values.tolist()
        conn.executemany(
            f"""
            INSERT INTO {PRICES_TABLE}
                (Ticker, Exchange, Date, Open, High, Low, Close, Volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(Ticker, Date) DO UPDATE SET
                Exchange=excluded.Exchange,
                Open=excluded.Open,
                High=excluded.High,
                Low=excluded.Low,
                Close=excluded.Close,
                Volume=excluded.Volume;
            """,
            rows,
        )
        conn.commit()
        logger.info("Đã lưu %d dòng vào bảng %s (%s)", len(rows), PRICES_TABLE, db_path)
        return len(rows)
    finally:
        conn.close()


def save_screener_results(df: pd.DataFrame, db_path: str | Path = SQLITE_DB_PATH) -> int:
    """Ghi đè bảng kết quả screener (Ticker/Exchange/Close/Signal/Indicator/Signal Date).

    Bảng này luôn phản ánh lần chạy screener gần nhất -> dùng REPLACE toàn
    bộ (không upsert theo dòng) vì mỗi ticker chỉ có đúng 1 dòng "mới nhất".
    """
    if df.empty:
        logger.warning("Kết quả screener rỗng, không có gì để lưu.")
        return 0

    out = df.copy()
    out["Signal Date"] = pd.to_datetime(out["Signal Date"]).dt.strftime("%Y-%m-%d")

    conn = get_connection(db_path)
    try:
        out.to_sql(SCREENER_TABLE, conn, if_exists="replace", index=False)
        conn.commit()
        logger.info("Đã cập nhật bảng %s: %d mã.", SCREENER_TABLE, len(out))
        return len(out)
    finally:
        conn.close()


def load_screener_results(db_path: str | Path = SQLITE_DB_PATH) -> pd.DataFrame:
    """Đọc bảng kết quả screener mới nhất, dùng cho dashboard."""
    conn = get_connection(db_path)
    try:
        query = f"SELECT * FROM {SCREENER_TABLE}"
        try:
            return pd.read_sql_query(query, conn, parse_dates=["Signal Date"])
        except pd.errors.DatabaseError:
            logger.warning("Bảng %s chưa tồn tại, chạy run_pipeline.py trước.", SCREENER_TABLE)
            return pd.DataFrame(columns=["Ticker", "Exchange", "Close", "Signal", "Indicator", "Signal Date"])
    finally:
        conn.close()


def load_prices(
    db_path: str | Path = SQLITE_DB_PATH,
    exchange: str | None = None,
    ticker: str | None = None,
) -> pd.DataFrame:
    """Đọc dữ liệu giá từ SQLite, có thể lọc theo sàn/mã, dùng cho dashboard/screener.

    Trả về DataFrame rỗng (không raise) nếu bảng `prices` chưa tồn tại —
    trường hợp bình thường ở lần chạy đầu tiên (deploy mới/DB trống, chưa
    ingest lần nào) — để dashboard tự phát hiện và kích hoạt auto-refresh
    thay vì crash toàn bộ app.
    """
    conn = get_connection(db_path)
    try:
        query = f"SELECT * FROM {PRICES_TABLE} WHERE 1=1"
        params: list[str] = []
        if exchange:
            query += " AND Exchange = ?"
            params.append(exchange)
        if ticker:
            query += " AND Ticker = ?"
            params.append(ticker)
        query += " ORDER BY Ticker, Date"
        try:
            return pd.read_sql_query(query, conn, params=params, parse_dates=["Date"])
        except pd.errors.DatabaseError:
            logger.warning("Bảng %s chưa tồn tại (chưa ingest lần nào), trả về DataFrame rỗng.", PRICES_TABLE)
            return pd.DataFrame(columns=["Ticker", "Exchange", "Date", "Open", "High", "Low", "Close", "Volume"])
    finally:
        conn.close()
