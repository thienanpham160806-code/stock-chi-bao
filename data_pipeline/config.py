"""Cấu hình đường dẫn dùng chung cho data_pipeline."""
from __future__ import annotations

from pathlib import Path

# Thư mục gốc của project (chứa run_pipeline.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Nơi lưu file .zip tải thẳng từ CafeF (chưa giải nén).
DOWNLOAD_DIR = PROJECT_ROOT / "data" / "downloads"

# Nơi chứa các file CSV nguồn (đã giải nén từ zip CafeF, dạng "upto3").
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"

# Nơi lưu database SQLite sau khi ingest.
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"
SQLITE_DB_PATH = PROCESSED_DATA_DIR / "stock.db"

# Tên bảng chứa dữ liệu giá đã chuẩn hóa.
PRICES_TABLE = "prices"

# Tên bảng chứa kết quả screener (tín hiệu BUY/SELL/HOLD mới nhất, toàn universe).
SCREENER_TABLE = "screener_signals"
