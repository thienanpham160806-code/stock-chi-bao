"""Test cho data_pipeline/lock.py — file lock chống nhiều tiến trình cùng
download/extract song song (bug thực tế gặp trên Streamlit Cloud khi
nhiều session cùng tự trigger auto-refresh)."""
from __future__ import annotations

import os
import time
from pathlib import Path

from data_pipeline.lock import try_lock


def test_first_caller_acquires_lock_second_concurrent_caller_does_not(tmp_path: Path):
    lock_path = tmp_path / "test.lock"

    with try_lock(lock_path) as first:
        assert first is True
        assert lock_path.exists()

        # Mô phỏng 1 tiến trình khác cố giành lock trong lúc tiến trình
        # đầu vẫn đang giữ -> phải thất bại (không được cùng chạy song song).
        with try_lock(lock_path) as second:
            assert second is False

    # Sau khi tiến trình đầu thoát khỏi context -> lock phải được giải phóng.
    assert not lock_path.exists()


def test_lock_released_after_context_exits_can_reacquire(tmp_path: Path):
    lock_path = tmp_path / "test.lock"

    with try_lock(lock_path) as acquired:
        assert acquired is True

    with try_lock(lock_path) as acquired_again:
        assert acquired_again is True


def test_stale_lock_is_reclaimed(tmp_path: Path):
    lock_path = tmp_path / "test.lock"
    lock_path.write_text(str(os.getpid()))
    # Giả lập lock cũ (vd tiến trình giữ lock đã bị kill, không kịp giải phóng).
    old_time = time.time() - 3600
    os.utime(lock_path, (old_time, old_time))

    with try_lock(lock_path, stale_after_seconds=60) as acquired:
        assert acquired is True, "lock quá cũ phải được coi là stale và tự dọn"
