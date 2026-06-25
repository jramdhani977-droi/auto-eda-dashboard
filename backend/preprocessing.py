"""
preprocessing.py — Pipeline Cleaning Data
SD-1306 Data Science Programming | Meeting 15
"""
import pandas as pd
import numpy as np
import re

NULL_PATTERNS = {
    'na', 'n/a', 'null', 'none', '-', '--', 'nan', '', 'n.a', 'n.a.',
    '#n/a', '#null!', 'missing', 'unknown', '?', 'none', 'tidak ada',
    'kosong', 'tidak diketahui', '#value!', '#ref!', '#div/0!'
}

DATE_PATTERNS = [
    r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}',
    r'^\d{1,2}[-/]\d{1,2}[-/]\d{4}',
    r'^\d{1,2}[-/]\d{1,2}[-/]\d{2}$',
    r'^\d{4}\d{2}\d{2}$',
    r'^\d{1,2}\s+\w+\s+\d{4}',
    r'^\w+\s+\d{1,2},?\s+\d{4}',
    r'^\d{4}[-/]\d{1,2}$',
    r'^\d{1,2}[-/]\d{4}$',
]

# Normalisasi gender (case-insensitive)
GENDER_MAP = {
    'male': 'Male', 'm': 'Male', 'laki': 'Male', 'laki-laki': 'Male', 'pria': 'Male', 'l': 'Male',
    'female': 'Female', 'f': 'Female', 'perempuan': 'Female', 'wanita': 'Female', 'p': 'Female',
}


def _try_fix_excel_header(df: pd.DataFrame) -> pd.DataFrame:
    """
    Deteksi dan perbaiki Excel dengan multi-level header atau header
    tersembunyi di row 0 (pola: banyak kolom 'Unnamed: X').
    """
    unnamed_count = sum(1 for c in df.columns if str(c).startswith('Unnamed:'))
    total_cols = len(df.columns)

    if unnamed_count < total_cols * 0.3:
        return df  # Header sudah oke

    # Coba baca ulang sebagai multi-level header [0, 1]
    return df  # Penanganan dilakukan di data_loader.py


def _is_date_column(series: pd.Series, threshold: float = 0.6) -> bool:
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    sample = series.dropna().head(100).astype(str).str.strip()
    if len(sample) == 0:
        return False
    # Gabungkan semua pattern: jika TOTAL yang cocok dengan SALAH SATU pattern >= threshold
    any_match = pd.Series([False] * len(sample), index=sample.index)
    for pat in DATE_PATTERNS:
        any_match = any_match | sample.str.match(pat, case=False)
    if any_match.mean() >= threshold:
        return True
    # Fallback: coba parse langsung
    try:
        parsed = pd.to_datetime(sample, errors="coerce")
        if parsed.notna().mean() >= threshold:
            return True
    except Exception:
        pass
    return False


def _is_gender_column(series: pd.Series) -> bool:
    sample = series.dropna().astype(str).str.strip().str.lower()
    known = set(GENDER_MAP.keys()) | {'unknown', 'other', 'lainnya'}
    matched = sample.isin(known).mean()
    return matched >= 0.5


def _normalize_gender(series: pd.Series) -> pd.Series:
    def _map(v):
        if pd.isna(v):
            return np.nan
        key = str(v).strip().lower()
        if key in NULL_PATTERNS or key in ('unknown', 'other', 'tidak diketahui'):
            return np.nan
        return GENDER_MAP.get(key, str(v).strip().title())
    return series.map(_map)


def _normalize_flag_column(series: pd.Series) -> pd.Series:
    flag_map = {
        'y': 'Y', 'yes': 'Y', 'priority': 'Y', '1': 'Y', 'true': 'Y',
        'n': 'N', 'no': 'N', 'normal': 'N', '0': 'N', 'false': 'N',
    }
    def _map(v):
        if pd.isna(v):
            return np.nan
        return flag_map.get(str(v).strip().lower(), str(v).strip())
    return series.map(_map)


def _clean_numeric_string(series: pd.Series) -> pd.Series:
    cleaned = (series.astype(str)
               .str.replace(r'[Rp$€£\s%]', '', regex=True)
               .str.replace(r'\.(?=\d{3}(?:[^\d]|$))', '', regex=True)
               .str.replace(',', '.', regex=False))
    return pd.to_numeric(cleaned, errors='coerce')


def standardize_nulls(df: pd.DataFrame):
    log = []
    df.columns = [str(c).strip() for c in df.columns]
    nulls_fixed = 0
    for col in df.columns:
        mask = df[col].astype(str).str.strip().str.lower().isin(NULL_PATTERNS)
        nulls_fixed += int(mask.sum())
        df.loc[mask, col] = np.nan
    for col in df.select_dtypes(include='object').columns:
        df[col] = df[col].where(df[col].astype(str).str.strip() != 'nan', other=np.nan)
        df[col] = df[col].where(df[col].astype(str).str.strip() != 'None', other=np.nan)
    if nulls_fixed > 0:
        log.append(f"Standardized {nulls_fixed} null/empty string(s) to NaN")
    else:
        log.append("No null string patterns found")
    df.dropna(how='all', inplace=True)
    return df, log


def remove_duplicates(df: pd.DataFrame):
    before = len(df)
    df.drop_duplicates(inplace=True)
    removed = before - len(df)
    df.reset_index(drop=True, inplace=True)
    log = [f"Removed {removed} duplicate row(s)" if removed > 0 else "No duplicate rows found"]
    return df, log


def fix_dtypes(df: pd.DataFrame):
    log = []
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            continue
        series = df[col].dropna()
        if len(series) == 0:
            continue

        # === 1. DETEKSI TANGGAL — selalu cek duluan, terlepas dari dtype ===
        if _is_date_column(series):
            try:
                converted = pd.to_datetime(df[col], errors="coerce")
                if converted.notna().mean() >= 0.85:
                    df[col] = converted
                    log.append(f"'{col}': converted to datetime")
                    continue
                # Fallback: parse per-element dengan dateutil (robust untuk mixed format)
                import dateutil.parser as dparser
                def _safe_parse(v):
                    if pd.isna(v) or str(v).strip() in ('nan', 'None', ''):
                        return pd.NaT
                    try:
                        return dparser.parse(str(v), dayfirst=False)
                    except Exception:
                        return pd.NaT
                converted2 = pd.to_datetime(df[col].apply(_safe_parse), errors='coerce')
                if converted2.notna().mean() >= 0.6:
                    df[col] = converted2
                    log.append(f"'{col}': converted to datetime (mixed format)")
                    continue
            except Exception:
                pass

        # Skip kolom yang sudah numeric murni
        if pd.api.types.is_numeric_dtype(df[col]):
            continue

        # === 2. NORMALISASI GENDER ===
        if _is_gender_column(series):
            df[col] = _normalize_gender(df[col])
            log.append(f"'{col}': gender normalized (Male/Female)")
            continue

        # === 3. NORMALISASI FLAG (Y/N) ===
        unique_lower = set(str(v).strip().lower() for v in series.unique())
        flag_vals = {'y', 'n', 'yes', 'no', 'priority', 'normal', '0', '1', 'true', 'false'}
        if unique_lower.issubset(flag_vals) and len(unique_lower) >= 2:
            df[col] = _normalize_flag_column(df[col])
            log.append(f"'{col}': flag values normalized → Y/N")
            continue

        # === 4. KONVERSI NUMERIK ===
        converted = _clean_numeric_string(df[col])
        if converted.notna().mean() >= 0.85:
            df[col] = converted
            log.append(f"'{col}': converted to numeric (cleaned currency/format)")
            continue

    if not log:
        log.append("All column types are already correct")
    return df, log


def impute_missing(df: pd.DataFrame):
    log = []
    for col in df.columns:
        # Skip datetime — NaN di datetime kolom setelah konversi adalah wajar (tidak bisa diimput dengan median/mode)
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            n_miss = int(df[col].isna().sum())
            if n_miss > 0:
                # Isi dengan forward fill lalu backward fill untuk time series
                df[col] = df[col].ffill().bfill()
                remaining = int(df[col].isna().sum())
                if remaining == 0:
                    log.append(f"'{col}': {n_miss} missing datetime → filled with forward/backward fill")
            continue
        n_miss = int(df[col].isna().sum())
        if n_miss == 0:
            continue
        pct = round(n_miss / len(df) * 100, 1)
        if pd.api.types.is_numeric_dtype(df[col]):
            fv = df[col].median()
            df[col] = df[col].fillna(fv)
            log.append(f"'{col}': {n_miss} missing ({pct}%) → filled with median ({round(float(fv), 2):,})")
        else:
            mv = df[col].mode()
            if len(mv) > 0:
                df[col] = df[col].fillna(mv[0])
                log.append(f"'{col}': {n_miss} missing ({pct}%) → filled with mode ('{mv[0]}')")
    if not log:
        log.append("No missing values to impute")
    return df, log


def cap_outliers(df: pd.DataFrame):
    """
    Cap outlier dengan IQR, plus validasi logis per kolom:
    - Kolom 'age'/'umur': nilai di bawah 15 atau di atas 100 dikap
    - Kolom 'salary'/'gaji'/'income': nilai negatif diubah ke median
    - Kolom persentase (pct/%/rate): dikap ke [0, 100]
    """
    log = []
    for col in df.select_dtypes(include=[np.number]).columns:
        col_lower = col.lower()

        # Validasi logis khusus
        if any(k in col_lower for k in ['age', 'umur', 'usia']):
            invalid = (df[col] < 15) | (df[col] > 100)
            n = int(invalid.sum())
            if n > 0:
                median_val = df.loc[~invalid, col].median()
                df.loc[invalid, col] = median_val
                log.append(f"'{col}': {n} nilai tidak valid (age <15 atau >100) → diganti median ({round(float(median_val),1)})")
            continue

        if any(k in col_lower for k in ['experience', 'pengalaman', 'lama_kerja', 'tenure']):
            neg = df[col] < 0
            n = int(neg.sum())
            if n > 0:
                median_val = df.loc[~neg, col].median()
                df.loc[neg, col] = median_val
                log.append(f"'{col}': {n} nilai negatif tidak valid → diganti median ({round(float(median_val),1)})")
            continue

        if any(k in col_lower for k in ['salary', 'gaji', 'income', 'pendapatan', 'upah', 'wage']):
            neg = df[col] < 0
            n = int(neg.sum())
            if n > 0:
                median_val = df.loc[~neg, col].median()
                df.loc[neg, col] = median_val
                log.append(f"'{col}': {n} nilai negatif tidak valid → diganti median ({round(float(median_val),2):,})")

        if any(k in col_lower for k in ['pct', 'percent', 'rate', 'persen', 'persentase']):
            out = (df[col] < 0) | (df[col] > 100)
            n = int(out.sum())
            if n > 0:
                df.loc[df[col] < 0, col] = 0
                df.loc[df[col] > 100, col] = 100
                log.append(f"'{col}': {n} nilai di luar [0,100] → dikap ke range valid")
            continue

        # IQR capping umum
        q1 = df[col].quantile(0.25)
        q3 = df[col].quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        lo = q1 - 1.5 * iqr
        hi = q3 + 1.5 * iqr
        # Untuk kolom revenue/sales/amount/harga: lower bound tidak boleh negatif
        revenue_keys = ['sales', 'revenue', 'amount', 'price', 'harga', 'nilai',
                        'cost', 'biaya', 'gross', 'net', 'total', 'income',
                        'pendapatan', 'omzet', 'penjualan', 'profit']
        if any(k in col_lower for k in revenue_keys) and lo < 0:
            lo = 0
        n = int(((df[col] < lo) | (df[col] > hi)).sum())
        if n > 0:
            df[col] = df[col].clip(lower=lo, upper=hi)
            log.append(f"'{col}': {n} outlier(s) capped → [{round(float(lo),2):,}, {round(float(hi),2):,}]")

    if not log:
        log.append("No outliers detected")
    return df, log


def auto_clean(df: pd.DataFrame):
    """Pipeline cleaning lengkap & robust untuk data apapun."""
    log_all = []
    df, log = standardize_nulls(df);  log_all += ['[1] STANDARDIZE NULLS'] + log
    df, log = remove_duplicates(df);  log_all += ['[2] REMOVE DUPLICATES'] + log
    df, log = fix_dtypes(df);         log_all += ['[3] FIX DATA TYPES'] + log
    df, log = impute_missing(df);     log_all += ['[4] IMPUTE MISSING VALUES'] + log
    df, log = cap_outliers(df);       log_all += ['[5] CAP OUTLIERS (IQR + VALIDASI LOGIS)'] + log
    return df, log_all

# ============================================================
# FITUR BARU: DIAGNOSIS + CUSTOM CLEANING + DROP EMPTY COLS
# ============================================================

def drop_empty_cols(df: pd.DataFrame, threshold: float = 0.8):
    """
    Hapus kolom yang >80% nilainya kosong (NaN).
    """
    log = []
    total = len(df)
    cols_to_drop = []
    for col in df.columns:
        miss_pct = df[col].isna().sum() / max(total, 1)
        if miss_pct > threshold:
            cols_to_drop.append(col)
    if cols_to_drop:
        df.drop(columns=cols_to_drop, inplace=True)
        log.append(f"Dropped {len(cols_to_drop)} kolom dengan >80% nilai kosong: {cols_to_drop}")
    else:
        log.append("Tidak ada kolom dengan >80% nilai kosong")
    return df, log


def diagnose_dataset(df: pd.DataFrame) -> dict:
    """
    Diagnosa masalah dataset dan kembalikan ringkasan untuk ditampilkan di UI.
    Return dict berisi:
    - issues: list of {type, severity, label, count, detail}
    - summary: jumlah masalah
    - cleaning_features: info per fitur (berapa row/col terpengaruh)
    """
    issues = []

    # 1. Duplikat
    dup_count = int(df.duplicated().sum())
    issues.append({
        'type': 'duplicates',
        'severity': 'error' if dup_count > 0 else 'ok',
        'label': 'Baris duplikat',
        'count': dup_count,
        'count_label': f'{dup_count} baris',
        'detail': f'Ditemukan {dup_count} baris yang identik persis di dataset.' if dup_count > 0
                  else 'Tidak ada baris duplikat.',
    })

    # 2. Missing value — per kolom
    miss_total = int(df.isna().sum().sum())
    miss_cols = {col: int(df[col].isna().sum()) for col in df.columns if df[col].isna().sum() > 0}
    miss_detail_str = ', '.join([f'{col} ({n} null)' for col, n in list(miss_cols.items())[:5]])
    issues.append({
        'type': 'missing',
        'severity': 'warning' if miss_total > 0 else 'ok',
        'label': 'Missing value',
        'count': miss_total,
        'count_label': f'{miss_total} sel kosong',
        'detail': f'Kolom: {miss_detail_str}' if miss_total > 0 else 'Tidak ada missing value.',
        'cols': miss_cols,
    })

    # 3. Tipe data tidak sesuai (deteksi date & bool)
    wrong_type_cols = []
    for col in df.select_dtypes(include='object').columns:
        series = df[col].dropna()
        if len(series) == 0:
            continue
        if _is_date_column(series):
            wrong_type_cols.append({'col': col, 'current': 'object', 'should': 'datetime'})
            continue
        unique_lower = set(str(v).strip().lower() for v in series.unique())
        bool_vals = {'true', 'false', '1', '0', 'yes', 'no', 'y', 'n'}
        if unique_lower.issubset(bool_vals) and len(unique_lower) >= 2:
            wrong_type_cols.append({'col': col, 'current': 'object', 'should': 'bool'})

    type_detail = '. '.join([
        f"Kolom {x['col']} terdeteksi sebagai {x['current']}, harusnya {x['should']}."
        for x in wrong_type_cols[:3]
    ])
    issues.append({
        'type': 'dtype',
        'severity': 'warning' if wrong_type_cols else 'ok',
        'label': 'Tipe data tidak sesuai',
        'count': len(wrong_type_cols),
        'count_label': f'{len(wrong_type_cols)} kolom',
        'detail': type_detail if wrong_type_cols else 'Semua tipe data sudah sesuai.',
        'cols': wrong_type_cols,
    })

    # 4. Outlier (IQR check)
    outlier_cols = {}
    for col in df.select_dtypes(include=[np.number]).columns:
        q1 = df[col].quantile(0.25)
        q3 = df[col].quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        lo = q1 - 1.5 * iqr
        hi = q3 + 1.5 * iqr
        n_out = int(((df[col] < lo) | (df[col] > hi)).sum())
        if n_out > 0:
            outlier_cols[col] = n_out
    total_outliers = sum(outlier_cols.values())
    issues.append({
        'type': 'outlier',
        'severity': 'ok' if total_outliers == 0 else 'warning',
        'label': 'Tidak ada outlier ekstrem' if total_outliers == 0 else 'Outlier terdeteksi',
        'count': total_outliers,
        'count_label': f'{total_outliers} nilai',
        'detail': 'Semua kolom numerik dalam batas wajar (IQR check passed).' if total_outliers == 0
                  else f'{len(outlier_cols)} kolom punya outlier: {", ".join(list(outlier_cols.keys())[:3])}',
    })

    # 5. Kolom kosong (>80% null)
    total_rows = len(df)
    empty_cols = [col for col in df.columns if df[col].isna().sum() / max(total_rows, 1) > 0.8]
    issues.append({
        'type': 'empty_cols',
        'severity': 'warning' if empty_cols else 'ok',
        'label': 'Kolom hampir kosong',
        'count': len(empty_cols),
        'count_label': f'{len(empty_cols)} kolom',
        'detail': f'Kolom dengan >80% nilai kosong: {empty_cols}' if empty_cols
                  else 'Tidak ada kolom dengan >80% nilai kosong.',
    })

    problem_count = sum(1 for i in issues if i['severity'] != 'ok')

    return {
        'issues': issues,
        'problem_count': problem_count,
        'cleaning_features': {
            'remove_duplicates': dup_count,
            'impute_missing': miss_total,
            'fix_dtypes': len(wrong_type_cols),
            'cap_outliers': total_outliers,
            'drop_empty_cols': len(empty_cols),
        }
    }


def custom_clean(df: pd.DataFrame, features: dict) -> tuple:
    """
    Cleaning selektif berdasarkan fitur yang dipilih user.
    features: dict of {feature_name: bool}
    """
    log_all = []
    df, log = standardize_nulls(df)
    log_all += ['[0] STANDARDIZE NULLS'] + log

    if features.get('remove_duplicates', False):
        df, log = remove_duplicates(df)
        log_all += ['[1] REMOVE DUPLICATES'] + log

    if features.get('fix_dtypes', False):
        df, log = fix_dtypes(df)
        log_all += ['[2] FIX DATA TYPES'] + log

    if features.get('impute_missing', False):
        df, log = impute_missing(df)
        log_all += ['[3] IMPUTE MISSING VALUES'] + log

    if features.get('cap_outliers', False):
        df, log = cap_outliers(df)
        log_all += ['[4] CAP OUTLIERS'] + log

    if features.get('drop_empty_cols', False):
        df, log = drop_empty_cols(df)
        log_all += ['[5] DROP EMPTY COLS'] + log

    return df, log_all