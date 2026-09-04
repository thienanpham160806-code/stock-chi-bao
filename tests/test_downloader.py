"""Test cho data_pipeline/downloader.py (chỉ phần logic thuần, không gọi mạng thật)."""
from __future__ import annotations

from datetime import date

from data_pipeline.downloader import build_url


def test_build_url_matches_cafef_pattern():
    url = build_url(date(2026, 9, 3))
    assert url == "https://cafef1.mediacdn.vn/data/ami_data/20260903/CafeF.SolieuGD.Upto03092026.zip"


def test_build_url_zero_pads_day_and_month():
    url = build_url(date(2024, 1, 5))
    assert url == "https://cafef1.mediacdn.vn/data/ami_data/20240105/CafeF.SolieuGD.Upto05012024.zip"
