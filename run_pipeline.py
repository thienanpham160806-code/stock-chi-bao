"""run_pipeline.py

Điểm vào duy nhất của toàn bộ hệ thống — nối 3 module (Data Acquisition,
Technical Screening, Dashboard) thành MỘT quy trình tự động (Task 4):

    Detect latest CafeF dataset -> Download -> Extract -> Clean & validate
        -> Update database -> Calculate Technical Indicators
        -> Generate BUY/SELL/HOLD signals -> Update Stock Screener
        -> (Update Dashboard: dashboard/app.py tự đọc lại SQLite mới nhất)

Sau khi chạy xong lệnh này, người dùng chỉ cần mở dashboard
(`streamlit run dashboard/app.py`) — không cần tải file, giải nén, tính
chỉ báo hay lập danh sách BUY/SELL thủ công.

Chạy: python run_pipeline.py
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from data_pipeline.config import DOWNLOAD_DIR, RAW_DATA_DIR, SQLITE_DB_PATH
from data_pipeline.db import load_prices, save_screener_results
from data_pipeline.pipeline import run_ingest
from screener.signals import screen_universe

logger = logging.getLogger(__name__)

# Console mặc định trên Windows (cp1252) không encode được tiếng Việt có
# dấu -> ép stdout/stderr sang UTF-8 để log/print không bị crash.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automated Stock Analytics Platform - pipeline runner")
    parser.add_argument("--raw-dir", default=str(RAW_DATA_DIR), help="Thư mục chứa CSV nguồn (mặc định data/raw)")
    parser.add_argument("--download-dir", default=str(DOWNLOAD_DIR), help="Thư mục lưu zip tải từ CafeF")
    parser.add_argument("--db-path", default=str(SQLITE_DB_PATH), help="Đường dẫn SQLite output")
    parser.add_argument(
        "--no-download", action="store_true",
        help="Bỏ qua bước tự động download/giải nén từ CafeF, chỉ dùng CSV có sẵn trong --raw-dir "
        "(dùng cho môi trường offline/CI).",
    )
    parser.add_argument(
        "--date", default=None,
        help="Chỉ định ngày dataset muốn tải, định dạng YYYY-MM-DD (mặc định: tự dò ngày mới nhất).",
    )
    parser.add_argument("--force-download", action="store_true", help="Tải lại dataset kể cả khi đã có sẵn.")
    parser.add_argument("--skip-screener", action="store_true", help="Chỉ chạy ingest, bỏ qua bước sinh tín hiệu")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    args = parse_args()
    target_date = date.fromisoformat(args.date) if args.date else None

    # ---- Detect -> Download -> Extract -> Clean & validate -> Update database ----
    rows_saved = run_ingest(
        raw_dir=args.raw_dir,
        db_path=args.db_path,
        download_dir=args.download_dir,
        auto_download=not args.no_download,
        target_date=target_date,
        force_download=args.force_download,
    )
    if rows_saved == 0:
        logger.warning("Không có dữ liệu để xử lý tiếp. Kiểm tra kết nối mạng hoặc %s.", args.raw_dir)
        return

    if args.skip_screener:
        return

    # ---- Calculate Technical Indicators -> Generate BUY/SELL/HOLD signals ----
    df = load_prices(args.db_path)
    screener_df = screen_universe(df)

    # ---- Update Stock Screener (lưu lại để dashboard/Task 3 đọc trực tiếp) ----
    save_screener_results(screener_df, args.db_path)

    counts = screener_df["Signal"].value_counts()
    logger.info(
        "Screener hoàn tất: BUY=%d, SELL=%d, HOLD=%d (tổng %d mã).",
        counts.get("BUY", 0), counts.get("SELL", 0), counts.get("HOLD", 0), len(screener_df),
    )

    actionable = screener_df[screener_df["Signal"] != "HOLD"]
    if not actionable.empty:
        print("\n=== Tín hiệu BUY/SELL mới nhất (toàn bộ universe) ===")
        print(actionable.drop(columns=["Indicator"]).to_string(index=False))
    else:
        print("\nKhông có tín hiệu BUY/SELL nào ở phiên gần nhất.")

    print(f"\nDashboard: streamlit run dashboard/app.py  (đọc dữ liệu trực tiếp từ {args.db_path})")


if __name__ == "__main__":
    main()
