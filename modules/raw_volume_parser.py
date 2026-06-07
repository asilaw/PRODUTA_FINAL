"""
raw_volume_parser.py
Membaca file Volume_F24-F26_RAW_VOLUME_.csv (format PT FBMI) menjadi long format.

Format input:
  - Row 0: header level 1 (BV, Q1, Q1, Q2, ...)
  - Row 1: bulan (Aug, Sep, Oct, Nov, Dec, Jan, Feb, Mar, Apr, May, Jun, Jul)
  - Row 2: kosong
  - Row 3+: data SKU (col 0=SKU, col 1=kode1, col 2=kode2, col 3=deskripsi, col 4+=volume)
  - Setiap 12 kolom = 1 fiscal year (F24=Aug2023-Jul2024, F25=Aug2024-Jul2025, F26=Aug2025-Jul2026)
  - Beberapa row col 0 = nama kategori (bukan SKU) → dilewati

Format output (long):
  ds | sku | description | y
"""

import pandas as pd
import numpy as np
import io
from pathlib import Path

# Kategori-kategori yang bukan SKU (baris pemisah)
_CATEGORY_NAMES = {
    'ANLENE ACTIFIT', 'ANLENE GOLD', 'ANLENE COMPLETE 10',
    'BONEETO REGULER', 'BONEETO JUNIOR', 'NPD',
    'ANMUM MATERNA', 'ANMUM LITE', 'ANMUM LACTA', 'ANMUM ESSETIAL',
    'ANCHOR FOOD PROFESSIONAL',
}

_MONTHS = ['Aug','Sep','Oct','Nov','Dec','Jan','Feb','Mar','Apr','May','Jun','Jul']
_MONTH_NUM = {'Aug':8,'Sep':9,'Oct':10,'Nov':11,'Dec':12,
              'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,'Jul':7}

# Fiscal year → start year (Aug)
_FY_START = {'F24': 2023, 'F25': 2024, 'F26': 2025}
_FY_LABELS = ['F24','F25','F26']


def _build_date_index() -> list:
    """36 tanggal: 3 FY × 12 bulan, mulai dari col 4."""
    dates = []
    for fy in _FY_LABELS:
        start_year = _FY_START[fy]
        for mo in _MONTHS:
            m_num = _MONTH_NUM[mo]
            year  = start_year if m_num >= 8 else start_year + 1
            dates.append(pd.Timestamp(year=year, month=m_num, day=1))
    return dates  # 36 tanggal


def parse_raw_volume(source) -> pd.DataFrame:
    """
    Parameters
    ----------
    source : str (path), Path, or bytes-like (uploaded file buffer)

    Returns
    -------
    pd.DataFrame dengan kolom: ds, sku, description, y
    """
    # Baca dengan berbagai encoding fallback
    encodings = ['latin-1', 'cp1252', 'iso-8859-1', 'utf-8-sig', 'utf-8']
    raw_df = None
    for enc in encodings:
        try:
            if hasattr(source, 'read'):
                source.seek(0)
                raw_df = pd.read_csv(source, encoding=enc, header=None,
                                     on_bad_lines='skip')
            else:
                raw_df = pd.read_csv(source, encoding=enc, header=None,
                                     on_bad_lines='skip')
            break
        except (UnicodeDecodeError, Exception):
            continue

    if raw_df is None:
        raise ValueError(
            "Tidak dapat membaca file. Coba simpan ulang sebagai CSV (UTF-8) dari Excel."
        )

    dates = _build_date_index()  # 36 dates
    data_col_start = 4

    records = []
    for _, row in raw_df.iterrows():
        sku = str(row[0]).strip() if pd.notna(row[0]) else ''
        if not sku or sku == 'nan' or sku in _CATEGORY_NAMES:
            continue
        # Skip header rows (nilai col 0 berisi kata-kata non-SKU)
        if any(k in sku for k in ['BV','Q1','Q2','Q3','Q4','Aug','Sep','Oct',
                                    'Nov','Dec','Jan','Feb','Mar','Apr','May',
                                    'Jun','Jul','Unnamed']):
            continue

        desc = str(row[3]).strip() if len(row) > 3 and pd.notna(row[3]) else sku

        for j, date in enumerate(dates):
            col_idx = data_col_start + j
            if col_idx >= len(row):
                continue
            try:
                vol = float(str(row[col_idx]).replace(',','.').strip() or 0)
            except (ValueError, TypeError):
                vol = 0.0
            records.append({'ds': date, 'sku': sku, 'description': desc, 'y': vol})

    if not records:
        raise ValueError(
            "Tidak ada data SKU yang berhasil dibaca. "
            "Pastikan format file sesuai: SKU di kolom pertama, "
            "bulan di baris ketiga (Aug, Sep, ...)."
        )

    result = pd.DataFrame(records)
    result['ds'] = pd.to_datetime(result['ds'])
    result['y']  = pd.to_numeric(result['y'], errors='coerce').fillna(0)
    return result
