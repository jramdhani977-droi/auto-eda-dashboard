"""
data_loader.py — Load file Excel/CSV/TXT dengan handle multi-level header & Unnamed columns
"""
import pandas as pd
import io
import re

SUPPORTED_EXTENSIONS = ['csv', 'txt', 'xlsx', 'xls']


def _build_multilevel_cols(row0: list, row1: list) -> list:
    """
    Buat nama kolom dari 2 baris header:
    row0 = nama grup (merged cell → NaN di kolom setelahnya)
    row1 = sub-header (tahun / nama kolom spesifik)
    Hasilnya: 'Grup_SubHeader' atau hanya 'SubHeader' jika tidak ada grup.
    """
    cols = []
    current_group = None
    for i, (g, s) in enumerate(zip(row0, row1)):
        g = str(g).strip() if str(g) not in ('nan', 'None', '') else None
        s = str(s).strip() if str(s) not in ('nan', 'None', '') else f'Col_{i+1}'
        if g:
            current_group = g
        if current_group and current_group not in (s,):
            col_name = f'{current_group}_{s}'
        else:
            col_name = s
            if g:
                current_group = g  # reset grup baru
        cols.append(col_name)

    # Pastikan unik
    seen = {}
    final = []
    for c in cols:
        if c in seen:
            seen[c] += 1
            final.append(f'{c}_{seen[c]}')
        else:
            seen[c] = 0
            final.append(c)
    return final


def _clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename kolom Unnamed, drop kolom/baris kosong."""
    new_cols = []
    for i, col in enumerate(df.columns):
        c = str(col).strip()
        if c.startswith('Unnamed:') or c in ('', 'nan', 'None'):
            c = f'Col_{i+1}'
        new_cols.append(c)

    # Pastikan unik
    seen = {}
    final = []
    for c in new_cols:
        if c in seen:
            seen[c] += 1
            final.append(f'{c}_{seen[c]}')
        else:
            seen[c] = 0
            final.append(c)
    df.columns = final

    df = df.dropna(axis=1, how='all')
    df = df.dropna(axis=0, how='all')
    df = df.reset_index(drop=True)
    return df


def _ffill_merged_cols(df: pd.DataFrame) -> pd.DataFrame:
    """
    Forward-fill kolom yang punya banyak NaN karena merged cells di Excel.
    Contoh: kolom Provinsi yang hanya terisi di baris pertama per grup.
    """
    for col in df.columns:
        series = df[col]
        null_pct = series.isna().mean()
        
        # Skip jika hampir tidak ada NaN
        if null_pct < 0.10:
            continue
        
        # Skip jika kolom ini adalah kolom numerik murni
        non_null = series.dropna()
        if len(non_null) == 0:
            continue
        try:
            pd.to_numeric(non_null.head(10), errors='raise')
            continue  # kolom numerik, skip
        except (ValueError, TypeError):
            pass
        
        # Kondisi ffill: NaN banyak (>10%), nilai pertama ada, dan bukan kolom ID unik per baris
        # Kolom ID unik: setiap nilai non-NaN muncul tepat sekali (seperti UUID/kode unik)
        # Kolom Provinsi: 34 unique dari 34 non-null → ini normal utk merged cell, TETAP ffill
        first_val = series.dropna().iloc[0] if len(series.dropna()) > 0 else None
        if first_val is not None and null_pct > 0.10:
            df[col] = series.ffill()
    
    return df
    return df


def _read_excel_smart(content: bytes, filename: str) -> pd.DataFrame:
    """
    Baca Excel dengan deteksi otomatis multi-level header.
    Logika:
    1. Baca tanpa header (header=None) untuk inspect baris 0 dan 1
    2. Jika baris 0 punya banyak NaN dan baris 1 seperti header → multi-level header
    3. Jika tidak → pakai header=0 biasa
    """
    df_raw = pd.read_excel(io.BytesIO(content), dtype=str, header=None)

    if len(df_raw) < 2:
        df = pd.read_excel(io.BytesIO(content), dtype=str, header=0)
        return _clean_columns(df)

    row0 = df_raw.iloc[0].tolist()
    row1 = df_raw.iloc[1].tolist()

    # Hitung berapa banyak cell non-NaN di row0
    row0_filled = [x for x in row0 if str(x).strip() not in ('nan', 'None', '')]
    row1_filled = [x for x in row1 if str(x).strip() not in ('nan', 'None', '')]

    # Deteksi multi-level: row0 punya isian tapi banyak NaN (merged cells), row1 lebih padat
    is_multilevel = (
        len(row0_filled) > 0
        and len(row0_filled) < len(row0) * 0.8   # row0 banyak NaN (merged)
        and len(row1_filled) >= len(row1) * 0.5   # row1 cukup padat
    )

    if is_multilevel:
        cols = _build_multilevel_cols(row0, row1)
        df = df_raw.iloc[2:].copy()
        df.columns = cols
        df = df.dropna(axis=1, how='all')
        df = df.dropna(axis=0, how='all')
        df = df.reset_index(drop=True)
        # Forward-fill kolom kategorik yang punya merged cells (e.g. Provinsi)
        df = _ffill_merged_cols(df)
        return df
    else:
        # Header normal di baris 0
        df = pd.read_excel(io.BytesIO(content), dtype=str, header=0)
        df = _clean_columns(df)
        # Forward-fill merged cells juga untuk file Excel non-multilevel
        df = _ffill_merged_cols(df)
        return df


def load_file(file_obj, filename: str) -> pd.DataFrame:
    """
    Load file ke DataFrame. Mendukung xlsx, xls, csv, txt.
    Otomatis handle multi-level header dan Unnamed columns.
    """
    ext = filename.rsplit('.', 1)[-1].lower()

    if ext == 'csv':
        content = file_obj.read()
        df = None
        for enc in ['utf-8', 'latin-1', 'cp1252']:
            try:
                df = pd.read_csv(io.BytesIO(content), dtype=str, encoding=enc)
                break
            except Exception:
                continue
        if df is None:
            df = pd.read_csv(io.BytesIO(content), dtype=str, encoding='utf-8', errors='replace')
        df = _clean_columns(df)

    elif ext == 'txt':
        content = file_obj.read()
        df = None
        for sep in ['\t', ',', ';', '|']:
            try:
                tmp = pd.read_csv(io.BytesIO(content), sep=sep, dtype=str)
                if len(tmp.columns) > 1:
                    df = tmp
                    break
            except Exception:
                continue
        if df is None:
            df = pd.read_csv(io.BytesIO(content), dtype=str)
        df = _clean_columns(df)

    elif ext in ['xlsx', 'xls']:
        content = file_obj.read()
        df = _read_excel_smart(content, filename)

    else:
        raise ValueError(
            f"Format .{ext} tidak didukung. Gunakan: {', '.join(SUPPORTED_EXTENSIONS)}"
        )

    return df


def get_file_info(df: pd.DataFrame, filename: str) -> dict:
    return {
        'filename': filename,
        'rows': len(df),
        'columns': len(df.columns),
        'column_names': list(df.columns),
        'memory_kb': round(df.memory_usage(deep=True).sum() / 1024, 1),
    }
