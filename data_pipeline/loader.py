"""
data_pipeline/loader.py

Đọc 1 file CSV lịch sử giá tải từ CafeF (dạng "upto3") và trả về một
DataFrame đã chuẩn hóa, sẵn sàng cho các bước tiếp theo của pipeline
(normalize/dedupe đã được xử lý ngay tại đây).

Đặc điểm dữ liệu nguồn cần xử lý:
- File có BOM (UTF-8 with BOM) ở đầu.
- Dòng kết thúc bằng CRLF ("\\r\\n").
- Cột ngày dạng YYYYMMDD liền không dấu (vd: 20240115), tên cột gốc
  CafeF là "<DTYYYYMMDD>".
- Tên cột gốc CafeF bọc trong dấu <...> (vd: "<Ticker>", "<Open>"...).
- File KHÔNG có cột Exchange -> phải suy ra sàn (HOSE/HNX/UPCOM) từ
  tên file khi ingest.
- Dữ liệu được nhóm theo từng ticker, KHÔNG sort toàn cục theo ngày.
- Có thể có vài dòng trùng lặp y hệt -> cần dedupe theo (Ticker, Date).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Cột chuẩn hóa đầu ra, đúng thứ tự trả về.
STANDARD_COLUMNS = ["Ticker", "Exchange", "Date", "Open", "High", "Low", "Close", "Volume"]

# Map tên cột CafeF gốc (đã bỏ dấu <>, upper-case) -> tên cột chuẩn.
_RAW_COLUMN_ALIASES = {
    "TICKER": "Ticker",
    "SYMBOL": "Ticker",
    "DTYYYYMMDD": "Date",
    "DATE": "Date",
    "OPEN": "Open",
    "HIGH": "High",
    "LOW": "Low",
    "CLOSE": "Close",
    "VOLUME": "Volume",
}

# Suy luận sàn giao dịch từ tên file, vd:
#   CafeF.HSX.Upto04092026.csv   -> HOSE
#   CafeF.HNX.Upto04092026.csv   -> HNX
#   CafeF.UPCOM.Upto04092026.csv -> UPCOM
_EXCHANGE_PATTERNS = {
    "HOSE": re.compile(r"HOSE|HSX", re.IGNORECASE),
    "HNX": re.compile(r"HNX", re.IGNORECASE),
    "UPCOM": re.compile(r"UPCOM", re.IGNORECASE),
}


class LoaderError(ValueError):
    """Lỗi khi đọc/parse file CSV nguồn."""


def infer_exchange_from_filename(file_path: str | Path) -> str:
    """Suy ra sàn giao dịch (HOSE/HNX/UPCOM) từ tên file CafeF.

    File CafeF "upto3" thường có dạng: CafeF.<SAN>.UptoDDMMYYYY.csv
    File không có cột Exchange nên đây là nguồn duy nhất để xác định sàn.
    """
    name = Path(file_path).name
    for exchange, pattern in _EXCHANGE_PATTERNS.items():
        if pattern.search(name):
            return exchange
    raise LoaderError(
        f"Không thể suy ra sàn giao dịch từ tên file: '{name}'. "
        "Tên file cần chứa HOSE/HSX, HNX hoặc UPCOM."
    )


def _normalize_columns(columns: list[str]) -> list[str]:
    """Bỏ dấu <...> quanh tên cột CafeF và map về tên cột chuẩn."""
    normalized = []
    for col in columns:
        key = col.strip().strip("<>").strip().upper()
        if key not in _RAW_COLUMN_ALIASES:
            raise LoaderError(f"Không nhận diện được cột '{col}' trong file CSV.")
        normalized.append(_RAW_COLUMN_ALIASES[key])
    return normalized


def load_csv(file_path: str | Path) -> pd.DataFrame:
    """Đọc 1 file CSV CafeF và trả về DataFrame đã chuẩn hóa + dedupe.

    Args:
        file_path: đường dẫn tới file CSV nguồn (vd trong data/raw/).

    Returns:
        DataFrame với cột: Ticker, Exchange, Date (datetime64[ns]),
        Open, High, Low, Close (float64), Volume (int64) — đã loại
        bỏ dòng trùng lặp theo (Ticker, Date) và được sort theo
        (Ticker, Date) tăng dần để tiện dùng ở bước screener.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise LoaderError(f"File không tồn tại: {file_path}")

    exchange = infer_exchange_from_filename(file_path)

    # encoding="utf-8-sig" tự loại bỏ BOM nếu có, không lỗi nếu không có.
    # pandas tự nhận diện line-ending CRLF nên không cần xử lý riêng.
    df = pd.read_csv(
        file_path,
        encoding="utf-8-sig",
        dtype=str,
        skipinitialspace=True,
    )

    if df.empty:
        logger.warning("File rỗng (không có dữ liệu): %s", file_path)
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    df.columns = _normalize_columns(list(df.columns))

    missing = (set(STANDARD_COLUMNS) - {"Exchange"}) - set(df.columns)
    if missing:
        raise LoaderError(f"Thiếu cột bắt buộc {missing} trong file {file_path}")

    df["Exchange"] = exchange

    # Ticker: chuẩn hóa khoảng trắng, upper-case.
    df["Ticker"] = df["Ticker"].str.strip().str.upper()

    # Dữ liệu CafeF thực tế có thể có dòng bị thiếu Ticker (trường rỗng ở
    # đầu dòng, vd: ",20250507,7.1,7.1,6.3,6.8,100500") -> không thể quy
    # về mã nào nên phải loại bỏ, không được để lọt xuống SQLite (cột
    # Ticker là NOT NULL / khóa chính).
    bad_ticker = df["Ticker"].isna() | (df["Ticker"] == "")
    if bad_ticker.any():
        logger.warning(
            "%d dòng bị thiếu Ticker, đã bị loại bỏ (%s)",
            int(bad_ticker.sum()), file_path,
        )
        df = df[~bad_ticker]

    # Date: YYYYMMDD liền không dấu -> datetime.
    df["Date"] = pd.to_datetime(df["Date"].str.strip(), format="%Y%m%d", errors="coerce")
    bad_dates = df["Date"].isna()
    if bad_dates.any():
        logger.warning(
            "%d dòng có Date không hợp lệ, đã bị loại bỏ (%s)",
            int(bad_dates.sum()), file_path,
        )
        df = df[~bad_dates]

    # Giá & khối lượng -> numeric.
    for col in ["Open", "High", "Low", "Close"]:
        df[col] = pd.to_numeric(df[col].str.strip(), errors="coerce")
    df["Volume"] = pd.to_numeric(df["Volume"].str.strip(), errors="coerce")

    bad_numeric = df[["Open", "High", "Low", "Close", "Volume"]].isna().any(axis=1)
    if bad_numeric.any():
        logger.warning(
            "%d dòng có giá trị số không hợp lệ, đã bị loại bỏ (%s)",
            int(bad_numeric.sum()), file_path,
        )
        df = df[~bad_numeric]

    df = df[STANDARD_COLUMNS]

    # Dedupe: dữ liệu nhóm theo ticker (không sort theo ngày toàn cục
    # trong file gốc), có thể có vài dòng trùng y hệt -> giữ dòng đầu
    # tiên theo khóa (Ticker, Date).
    before = len(df)
    df = df.drop_duplicates(subset=["Ticker", "Date"], keep="first")
    removed = before - len(df)
    if removed:
        logger.info("Đã loại bỏ %d dòng trùng lặp (Ticker, Date) trong %s", removed, file_path)

    # Sort lại theo (Ticker, Date) tăng dần cho tiện dùng downstream
    # (screener cần chuỗi thời gian liên tục theo từng ticker), dù
    # nguồn gốc không sort toàn cục theo ngày.
    df["Volume"] = df["Volume"].astype("int64")
    df = df.sort_values(["Ticker", "Date"]).reset_index(drop=True)

    return df


def load_all_csv(raw_dir: str | Path) -> pd.DataFrame:
    """Đọc toàn bộ file *.csv trong thư mục raw_dir và gộp lại thành 1 DataFrame.

    File lỗi (không suy ra được sàn, sai cấu trúc cột...) sẽ bị bỏ qua
    và log lỗi thay vì làm hỏng toàn bộ quá trình ingest.
    """
    raw_dir = Path(raw_dir)
    csv_files = sorted(raw_dir.glob("*.csv"))
    if not csv_files:
        logger.warning("Không tìm thấy file CSV nào trong %s", raw_dir)
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    frames = []
    for path in csv_files:
        try:
            frames.append(load_csv(path))
        except LoaderError as exc:
            logger.error("Bỏ qua file lỗi %s: %s", path, exc)

    if not frames:
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates(subset=["Ticker", "Date"], keep="first")
    combined = combined.sort_values(["Ticker", "Date"]).reset_index(drop=True)
    return combined
