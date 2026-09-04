"""data_pipeline/pipeline.py

Nối các bước "Automated Data Pipeline" (Task 1 + phần đầu Task 4):

    Detect latest CafeF dataset -> Download -> Extract
        -> Clean & validate (loader.py) -> Update database (db.py)

Toàn bộ chạy tự động, không cần người dùng tải/giải nén/copy file thủ công.
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from data_pipeline.config import DOWNLOAD_DIR, INGEST_LOCK_PATH, RAW_DATA_DIR, SQLITE_DB_PATH
from data_pipeline.db import save_prices
from data_pipeline.downloader import download_dataset, find_latest_available_date
from data_pipeline.extractor import extract_dataset
from data_pipeline.loader import load_all_csv
from data_pipeline.lock import try_lock

logger = logging.getLogger(__name__)


def run_ingest(
    raw_dir: str | Path = RAW_DATA_DIR,
    db_path: str | Path = SQLITE_DB_PATH,
    download_dir: str | Path = DOWNLOAD_DIR,
    auto_download: bool = True,
    target_date: date | None = None,
    force_download: bool = False,
) -> int:
    """Chạy toàn bộ bước ingest, trả về số dòng đã lưu vào SQLite.

    Args:
        auto_download: nếu True (mặc định), tự dò + tải dataset mới nhất
            từ CafeF trước khi đọc data/raw. Đặt False để chỉ dùng các
            file CSV đã có sẵn trong raw_dir (vd môi trường offline/CI).
        target_date: chỉ định ngày dataset muốn tải thay vì tự dò ngày
            mới nhất (hữu ích khi cần tải lại 1 ngày cụ thể).
        force_download: tải lại dataset kể cả khi đã có sẵn zip cho ngày đó.
    """
    if auto_download:
        # Khóa để chỉ 1 tiến trình/session được download+extract cùng lúc —
        # tránh race condition khi nhiều session (vd nhiều tab trên
        # Streamlit Cloud) cùng tự trigger auto-refresh song song. Nếu
        # không giành được lock, coi như tiến trình khác đang lo việc này,
        # bỏ qua bước download/extract và dùng tạm dữ liệu sẵn có (nếu có).
        with try_lock(INGEST_LOCK_PATH) as acquired:
            if not acquired:
                logger.info(
                    "Tiến trình khác đang download/giải nén (lock %s đang giữ) -> bỏ qua, "
                    "dùng dữ liệu sẵn có trong %s.",
                    INGEST_LOCK_PATH, raw_dir,
                )
            else:
                try:
                    resolved_date = target_date or find_latest_available_date()
                    zip_path = download_dataset(resolved_date, download_dir, force=force_download)
                    extract_dataset(zip_path, raw_dir)
                except Exception:
                    logger.exception(
                        "Tự động download/giải nén từ CafeF thất bại, sẽ dùng dữ liệu "
                        "sẵn có (nếu có) trong %s.",
                        raw_dir,
                    )

    logger.info("Bắt đầu ingest CSV từ %s", raw_dir)
    df = load_all_csv(raw_dir)
    if df.empty:
        logger.warning("Không có dữ liệu nào được ingest.")
        return 0
    rows_saved = save_prices(df, db_path)
    logger.info("Ingest hoàn tất: %d dòng, %d mã.", rows_saved, df["Ticker"].nunique())
    return rows_saved


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    run_ingest()
