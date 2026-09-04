"""data_pipeline/lock.py

File lock đơn giản, an toàn giữa nhiều tiến trình (multi-process), dùng
để tránh nhiều session/tiến trình cùng chạy download+extract song song
— tình huống thực tế gặp trên Streamlit Cloud khi nhiều session cùng
tự trigger auto-refresh-if-stale cùng lúc, gây race condition khi ghi
file (vd 2 tiến trình cùng giải nén vào chung 1 thư mục tạm).

Dùng os.O_CREAT | O_EXCL để tạo file lock — thao tác này atomic ở cấp hệ
điều hành (không có khoảng hở giữa "kiểm tra" và "tạo"), nên đáng tin cậy
hơn kiểu `if not path.exists(): path.touch()`.
"""
from __future__ import annotations

import contextlib
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Lock quá thời gian này (giây) coi như bị bỏ quên do tiến trình cũ chết
# đột ngột (crash/kill) mà không kịp giải phóng -> tự dọn và chạy tiếp,
# tránh app bị kẹt vĩnh viễn vì 1 lock rác.
DEFAULT_STALE_AFTER_SECONDS = 900  # 15 phút — đủ dư so với thời gian tải+giải nén thực tế


def _try_acquire(lock_path: Path, stale_after_seconds: int) -> bool:
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    if lock_path.exists():
        age = time.time() - lock_path.stat().st_mtime
        if age > stale_after_seconds:
            logger.warning("Lock %s đã cũ %.0fs -> coi như stale, xóa và tiếp tục.", lock_path, age)
            lock_path.unlink(missing_ok=True)
        else:
            return False

    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False


@contextlib.contextmanager
def try_lock(lock_path: str | Path, stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS):
    """Context manager: yield True nếu giành được lock, False nếu không.

    Không raise khi không giành được lock — để caller tự quyết định bỏ
    qua bước cần lock (vd "tiến trình khác đang tải rồi, dùng tạm dữ
    liệu hiện có") thay vì chờ/crash.
    """
    lock_path = Path(lock_path)
    acquired = _try_acquire(lock_path, stale_after_seconds)
    try:
        yield acquired
    finally:
        if acquired:
            lock_path.unlink(missing_ok=True)
