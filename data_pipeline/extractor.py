"""data_pipeline/extractor.py

Giải nén file .zip "Upto 3 sàn" tải từ CafeF và đưa các file CSV
(HOSE/HNX/UPCOM) ra thư mục data/raw để loader.py xử lý tiếp.

CafeF nén 3 file CSV vào 1 file .zip, có thể nằm ngay ở root của zip
hoặc trong 1 thư mục con — module này duyệt đệ quy nên không phụ thuộc
vào cấu trúc thư mục bên trong zip.
"""
from __future__ import annotations

import logging
import shutil
import tempfile
import zipfile
from pathlib import Path

from data_pipeline.config import RAW_DATA_DIR

logger = logging.getLogger(__name__)


class ExtractError(RuntimeError):
    """Lỗi khi giải nén file zip CafeF."""


def extract_dataset(zip_path: str | Path, raw_dir: str | Path = RAW_DATA_DIR) -> list[Path]:
    """Giải nén zip_path, copy toàn bộ *.csv tìm được (đệ quy) vào raw_dir.

    Trả về danh sách đường dẫn các file CSV đã được đưa vào raw_dir.
    File CSV trùng tên sẽ bị ghi đè (idempotent khi chạy lại pipeline).

    Dùng tempfile.TemporaryDirectory (thư mục tạm riêng biệt, tên ngẫu
    nhiên) thay vì 1 đường dẫn cố định — trên môi trường có thể chạy
    nhiều tiến trình song song (vd nhiều session Streamlit Cloud cùng
    tự trigger auto-refresh), 1 thư mục tạm dùng chung dễ bị tiến trình
    này xóa/ghi đè giữa lúc tiến trình khác đang đọc, gây
    FileNotFoundError giữa chừng.
    """
    zip_path = Path(zip_path)
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)

    if not zip_path.exists():
        raise ExtractError(f"File zip không tồn tại: {zip_path}")

    extracted: list[Path] = []
    with tempfile.TemporaryDirectory(prefix=f"cafef_extract_{zip_path.stem}_") as tmp:
        stage_dir = Path(tmp)
        try:
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(stage_dir)
        except zipfile.BadZipFile as exc:
            raise ExtractError(f"File zip lỗi/không đọc được: {zip_path} ({exc})") from exc

        csv_files = sorted(stage_dir.rglob("*.csv"))
        if not csv_files:
            raise ExtractError(f"Không tìm thấy file CSV nào bên trong zip: {zip_path}")

        for src in csv_files:
            dest = raw_dir / src.name
            shutil.copy2(src, dest)
            extracted.append(dest)
            logger.info("Đã giải nén %s -> %s", src.name, dest)

    return extracted
