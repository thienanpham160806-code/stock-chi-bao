"""data_pipeline/downloader.py

Tự động xác định và tải bộ dữ liệu "Upto 3 sàn" mới nhất từ CafeF
(https://cafef.vn/du-lieu/du-lieu-download.chn), không cần người dùng
vào web bấm tải thủ công.

CafeF publish file theo URL có quy luật:
    https://cafef1.mediacdn.vn/data/ami_data/<YYYYMMDD>/CafeF.SolieuGD.Upto<DDMMYYYY>.zip
trong đó <YYYYMMDD>/<DDMMYYYY> là ngày giao dịch gần nhất có dữ liệu.
Vì không phải ngày nào cũng có dữ liệu (cuối tuần, lễ, hoặc CafeF chưa
kịp cập nhật trong ngày), module này dò lùi từ ngày hôm nay tối đa
`MAX_LOOKBACK_DAYS` ngày để tìm ngày gần nhất thực sự có file.
"""
from __future__ import annotations

import logging
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from data_pipeline.config import DOWNLOAD_DIR

logger = logging.getLogger(__name__)

URL_TEMPLATE = "https://cafef1.mediacdn.vn/data/ami_data/{yyyymmdd}/CafeF.SolieuGD.Upto{ddmmyyyy}.zip"
MAX_LOOKBACK_DAYS = 10
_REQUEST_TIMEOUT = 15
_USER_AGENT = "Mozilla/5.0 (AutomatedStockAnalyticsPlatform/1.0)"


class DownloadError(RuntimeError):
    """Lỗi khi dò/tải dữ liệu từ CafeF."""


def build_url(d: date) -> str:
    return URL_TEMPLATE.format(yyyymmdd=d.strftime("%Y%m%d"), ddmmyyyy=d.strftime("%d%m%Y"))


def _url_exists(url: str) -> bool:
    """Kiểm tra file có tồn tại trên server hay không bằng HEAD request."""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            return resp.status == 200
    except urllib.error.HTTPError:
        return False
    except urllib.error.URLError as exc:
        logger.warning("Không thể kết nối tới CafeF khi kiểm tra %s: %s", url, exc)
        return False


def find_latest_available_date(start: date | None = None, lookback_days: int = MAX_LOOKBACK_DAYS) -> date:
    """Dò lùi từ `start` (mặc định hôm nay) để tìm ngày gần nhất CafeF đã publish dữ liệu."""
    start = start or date.today()
    for offset in range(lookback_days + 1):
        candidate = start - timedelta(days=offset)
        url = build_url(candidate)
        if _url_exists(url):
            logger.info("Tìm thấy dataset CafeF mới nhất: %s (%s)", candidate.isoformat(), url)
            return candidate
    raise DownloadError(
        f"Không tìm thấy dataset CafeF nào trong {lookback_days} ngày gần nhất "
        f"tính từ {start.isoformat()}."
    )


def download_dataset(
    target_date: date | None = None,
    dest_dir: str | Path = DOWNLOAD_DIR,
    force: bool = False,
) -> Path:
    """Tải file zip "Upto 3 sàn" của ngày gần nhất có dữ liệu.

    Idempotent: nếu file zip của ngày đó đã tồn tại ở dest_dir, không tải lại
    (trừ khi force=True) -> chạy lại pipeline nhiều lần trong ngày không tốn
    băng thông vô ích.
    """
    resolved_date = target_date or find_latest_available_date()
    url = build_url(resolved_date)

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dest_dir / f"CafeF.SolieuGD.Upto{resolved_date.strftime('%d%m%Y')}.zip"

    if zip_path.exists() and not force:
        logger.info("Đã có sẵn dataset %s, bỏ qua tải lại (%s).", resolved_date.isoformat(), zip_path)
        return zip_path

    logger.info("Đang tải dataset CafeF ngày %s từ %s ...", resolved_date.isoformat(), url)
    # Tải vào file .part rồi rename sang tên thật khi xong hẳn — tải dở
    # dang (mạng đứt giữa chừng, tiến trình bị kill...) sẽ không bao giờ
    # để lại 1 file trùng tên zip_path mà idempotency-check ở trên lầm
    # tưởng là "đã tải xong đủ".
    part_path = zip_path.with_suffix(zip_path.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp, open(part_path, "wb") as out_file:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                out_file.write(chunk)
        part_path.replace(zip_path)
    except urllib.error.URLError as exc:
        part_path.unlink(missing_ok=True)
        raise DownloadError(f"Tải dữ liệu CafeF thất bại ({url}): {exc}") from exc
    except BaseException:
        part_path.unlink(missing_ok=True)
        raise

    logger.info("Tải xong: %s (%.1f MB)", zip_path, zip_path.stat().st_size / 1_048_576)
    return zip_path
