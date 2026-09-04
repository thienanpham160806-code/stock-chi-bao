# Automated Stock Analytics Platform

Hệ thống tự động: **Detect → Download → Extract → Clean & validate →
Update database → Calculate Technical Indicators → Generate BUY/SELL/HOLD
signals → Update Stock Screener → Update Dashboard**, thu thập dữ liệu
giá lịch sử 3 sàn (HOSE/HNX/UPCOM) từ CafeF, không cần thao tác thủ công.

## Mapping với đề bài

| Task | Yêu cầu | Thực hiện ở |
|---|---|---|
| Task 1 — Automated Data Pipeline | Tự dò/tải/giải nén/chuẩn hóa/dedupe/lưu | `data_pipeline/` |
| Task 2 — Market Visualization Platform | Chọn sàn/mã/thời gian, candlestick+volume+indicator, Market Information | `dashboard/app.py` (tab "Market Watch") |
| Task 3 — Technical Analysis Stock Screener | Chiến lược định lượng, bảng BUY/SELL/HOLD toàn universe | `screener/` + `dashboard/app.py` (tab "Stock Screener") |
| Task 4 — Full Automation | 1 lệnh chạy hết, không thao tác thủ công | `run_pipeline.py` |

## Cấu trúc project

```
data_pipeline/
  downloader.py   Tự dò ngày dataset mới nhất trên CafeF (dò lùi tối đa
                   10 ngày qua HEAD request) và tải file .zip "Upto 3 sàn".
                   URL pattern: cafef1.mediacdn.vn/data/ami_data/<YYYYMMDD>/
                   CafeF.SolieuGD.Upto<DDMMYYYY>.zip — idempotent (không
                   tải lại nếu đã có sẵn zip của ngày đó).
  extractor.py     Giải nén zip -> copy toàn bộ *.csv (đệ quy, không phụ
                   thuộc cấu trúc thư mục trong zip) vào data/raw/.
  loader.py        Đọc 1 file CSV CafeF -> DataFrame chuẩn (Ticker,
                   Exchange, Date, Open, High, Low, Close, Volume).
                   Xử lý BOM, CRLF, cột <...>, suy luận Exchange từ tên
                   file, dedupe theo (Ticker, Date), loại dòng thiếu
                   Ticker/Date/numeric không hợp lệ.
  db.py            Lưu/đọc SQLite: bảng `prices` (upsert theo Ticker+Date)
                   và bảng `screener_signals` (kết quả screener mới nhất).
  pipeline.py      Nối Detect -> Download -> Extract -> Clean -> Store.
  config.py        Đường dẫn dùng chung.

screener/
  indicators.py    SMA, RSI (Wilder smoothing), Volume MA — tính riêng
                   theo từng Ticker (groupby), không rò rỉ dữ liệu chéo mã.
  signals.py       Multi-factor Technical Strategy (thuần định lượng,
                   xem docstring trong file để biết công thức đầy đủ):
                     - Trend    : SMA20/SMA50 golden/death cross
                     - Momentum : RSI14 (tránh mua quá mua / bán quá bán)
                     - Volume   : Volume > VolumeMA20 (xác nhận dòng tiền)
                   screen_universe() trả về đúng bảng:
                     Ticker | Exchange | Close | Signal | Indicator | Signal Date

dashboard/
  app.py           Streamlit — tab "Market Watch" (Stock Selection +
                   candlestick/volume/SMA/RSI + Market Information: giá,
                   %change, volume, max/min, RSI, tín hiệu) và tab
                   "Stock Screener" (bảng toàn universe, lọc theo
                   sàn/tín hiệu/mã).

run_pipeline.py    Điểm vào duy nhất — chạy toàn bộ luồng Task 4.
requirements.txt
tests/             Unit test cho loader/downloader/signals (pytest).
```

## Nguồn dữ liệu

CafeF – "Dữ liệu lịch sử cho MetaStock/AmiBroker – Upto 3 sàn"
(https://cafef.vn/du-lieu/du-lieu-download.chn). Đặc điểm dữ liệu đã xử
lý trong `data_pipeline/loader.py`:

- File có BOM (UTF-8 with BOM), dòng CRLF.
- Cột `<DTYYYYMMDD>` dạng `YYYYMMDD` liền không dấu; tên cột gốc bọc
  trong `<...>`.
- **Không có cột Exchange** — suy ra từ tên file zip/csv
  (`CafeF.HSX...` → HOSE, `CafeF.HNX...` → HNX, `CafeF.UPCOM...` → UPCOM).
- Dữ liệu nhóm theo từng ticker, không sort toàn cục theo ngày trong
  file gốc — `loader.py` tự sort lại theo (Ticker, Date).
- Có dòng trùng lặp y hệt → dedupe theo (Ticker, Date).
- Trên dữ liệu thực tế còn gặp một số dòng **thiếu Ticker** (trường
  rỗng, ví dụ ~1200 dòng trong file UPCOM một kỳ tải thực tế) — các
  dòng này bị loại bỏ và log cảnh báo vì không thể quy về mã nào.

## Cài đặt

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

## Chạy hệ thống (Task 4 — Full Automation)

```bash
# Tự động: dò ngày mới nhất -> tải zip từ CafeF -> giải nén -> chuẩn hóa
# -> lưu SQLite -> tính chỉ báo -> sinh tín hiệu -> lưu bảng screener.
python run_pipeline.py

# Mở dashboard (đọc trực tiếp SQLite vừa cập nhật)
streamlit run dashboard/app.py
```

Chạy lại `python run_pipeline.py` bất cứ lúc nào để đồng bộ dữ liệu mới
nhất — không cần tải/giải nén/copy file hay tính lại chỉ báo thủ công.

Tuỳ chọn hữu ích:
```bash
python run_pipeline.py --no-download        # chỉ dùng CSV có sẵn trong data/raw (offline/CI)
python run_pipeline.py --date 2026-09-03    # tải đúng 1 ngày cụ thể
python run_pipeline.py --force-download     # tải lại dù đã có sẵn zip
```

> **Lưu ý môi trường:** file zip CafeF nặng ~40–70MB; nếu mạng chậm,
> bước download có thể mất vài phút. `downloader.py` idempotent — chạy
> lại sẽ không tải lại file đã có sẵn trong `data/downloads/`.

## Test

```bash
pytest tests/ -v
```

## Giới hạn hiện tại / hướng mở rộng

- Chiến lược screener hiện dùng SMA+RSI+Volume (Trend/Momentum/Volume);
  có thể bổ sung MACD/Bollinger Bands/ATR/ADX (Volatility/Market
  Strength) trong `screener/indicators.py` + `screener/signals.py` nếu
  cần đa dạng hơn cho báo cáo kỹ thuật.
- "Signal Date" trong bảng screener là ngày giao dịch **gần nhất có
  trong dữ liệu của từng mã** — với mã đã ngừng giao dịch lâu, ngày này
  có thể là một ngày trong quá khứ chứ không phải phiên gần nhất của
  thị trường.
- Technical Report (10–15 trang) theo yêu cầu đề bài là phần sinh viên
  tự trình bày phương pháp luận — code này cung cấp phần triển khai kỹ
  thuật kèm docstring giải thích rõ công thức, dùng làm tài liệu tham
  khảo khi viết báo cáo.
