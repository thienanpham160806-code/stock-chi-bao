"""Test cho data_pipeline/extractor.py."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from data_pipeline.extractor import ExtractError, extract_dataset


def _make_zip_with_nested_csvs(zip_path: Path) -> None:
    """Zip mô phỏng cấu trúc CafeF thật: 1 thư mục con chứa 3 file CSV sàn."""
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("CafeF.SolieuGD.Upto03092026/CafeF.HNX.Upto03.09.2026.csv", "dummy hnx")
        zf.writestr("CafeF.SolieuGD.Upto03092026/CafeF.HSX.Upto03.09.2026.csv", "dummy hsx")
        zf.writestr("CafeF.SolieuGD.Upto03092026/CafeF.UPCOM.Upto03.09.2026.csv", "dummy upcom")


def test_extract_dataset_copies_nested_csvs_to_raw_dir(tmp_path: Path):
    zip_path = tmp_path / "CafeF.SolieuGD.Upto03092026.zip"
    raw_dir = tmp_path / "raw"
    _make_zip_with_nested_csvs(zip_path)

    extracted = extract_dataset(zip_path, raw_dir)

    names = {p.name for p in extracted}
    assert names == {
        "CafeF.HNX.Upto03.09.2026.csv",
        "CafeF.HSX.Upto03.09.2026.csv",
        "CafeF.UPCOM.Upto03.09.2026.csv",
    }
    for p in extracted:
        assert p.parent == raw_dir
        assert p.exists()


def test_extract_dataset_missing_zip_raises(tmp_path: Path):
    with pytest.raises(ExtractError):
        extract_dataset(tmp_path / "does_not_exist.zip", tmp_path / "raw")


def test_extract_dataset_bad_zip_raises(tmp_path: Path):
    bad_zip = tmp_path / "not_really_a_zip.zip"
    bad_zip.write_text("this is not a zip file")
    with pytest.raises(ExtractError):
        extract_dataset(bad_zip, tmp_path / "raw")


def test_extract_dataset_no_csv_inside_raises(tmp_path: Path):
    zip_path = tmp_path / "empty.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("readme.txt", "no csv here")
    with pytest.raises(ExtractError):
        extract_dataset(zip_path, tmp_path / "raw")


def test_extract_dataset_uses_isolated_temp_dir_not_shared_fixed_path(tmp_path: Path):
    """Regression test: trước đây dùng 1 thư mục tạm cố định
    (raw_dir.parent/_extract_tmp/<stem>) dùng chung giữa các lần gọi ->
    2 lần gọi liên tiếp (mô phỏng 2 session song song) có thể đụng nhau.
    Giờ mỗi lần gọi phải dùng thư mục tạm riêng và tự dọn sau khi xong."""
    zip_path = tmp_path / "CafeF.SolieuGD.Upto03092026.zip"
    raw_dir = tmp_path / "raw"
    _make_zip_with_nested_csvs(zip_path)

    extract_dataset(zip_path, raw_dir)
    extract_dataset(zip_path, raw_dir)  # gọi lại lần 2 không được lỗi do đụng thư mục tạm cũ

    # Không còn thư mục tạm cố định nào sót lại sau khi extract xong.
    assert not (raw_dir.parent / "_extract_tmp").exists()
