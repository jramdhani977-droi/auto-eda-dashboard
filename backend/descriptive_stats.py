"""
descriptive_stats.py — Module statistik deskriptif untuk variabel numerik
"""
import math
import pandas as pd
import numpy as np


_DATE_PATS = [
    r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}',
    r'^\d{1,2}[-/]\d{1,2}[-/]\d{4}',
    r'^\d{1,2}[-/]\d{1,2}[-/]\d{2}$',
    r'^\d{4}\d{2}\d{2}$',
    r'^\d{1,2}\s+\w+\s+\d{4}',
    r'^\w+\s+\d{1,2},?\s+\d{4}',
    r'^\d{4}[-/]\d{1,2}$',
    r'^\d{1,2}[-/]\d{4}$',
]

def _check_date(series, threshold=0.6):
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    sample = series.dropna().head(50).astype(str).str.strip()
    if len(sample) == 0:
        return False
    for pat in _DATE_PATS:
        if sample.str.match(pat, case=False).mean() >= threshold:
            return True
    try:
        parsed = pd.to_datetime(sample, errors='coerce', infer_datetime_format=True)
        if parsed.notna().mean() >= threshold:
            return True
    except Exception:
        pass
    return False


def detect_types(df: pd.DataFrame) -> dict:
    """Deteksi tipe data tiap kolom: numeric, categorical, datetime, boolean."""
    types = {}
    for col in df.columns:
        series = df[col].dropna()
        if len(series) == 0:
            types[col] = 'categorical'
            continue
        # 1) Datetime — prioritas pertama
        if pd.api.types.is_datetime64_any_dtype(df[col]) or _check_date(series):
            types[col] = 'datetime'
            continue
        # 2) Boolean
        ul = series.astype(str).str.lower().unique()
        bv = ['true', 'false', 'yes', 'no', '1', '0', 'y', 'n']
        if len(ul) <= 2 and all(v in bv for v in ul):
            types[col] = 'boolean'
            continue
        # 3) Numeric
        if pd.api.types.is_numeric_dtype(df[col]):
            types[col] = 'numeric'
            continue

        def try_num(v):
            try:
                float(str(v).replace(',', '').replace('$', '').replace('€', '').replace('Rp', '').replace(' ', ''))
                return True
            except Exception:
                return False

        if series.apply(try_num).mean() >= 0.85:
            types[col] = 'numeric'
            continue
        types[col] = 'categorical'
    return types


def _safe_round(val, d=4):
    try:
        v = float(val)
        return None if (math.isnan(v) or math.isinf(v)) else round(v, d)
    except Exception:
        return None


def numeric_stats(series: pd.Series, total_rows: int) -> dict | None:
    """
    Hitung statistik deskriptif lengkap untuk satu kolom numerik.
    Mencakup: count, mean, median, min, max, std, variance, mode,
              skewness, kurtosis, missing, missing_pct, outliers, normality.
    """
    clean = pd.to_numeric(
        series.astype(str).str.replace(r'[,$€£Rp\s]', '', regex=True),
        errors='coerce'
    ).dropna()

    if len(clean) == 0:
        return None

    missing = int(series.isna().sum())
    missing_pct = round((missing / total_rows) * 100, 2) if total_rows > 0 else 0

    q1 = float(clean.quantile(0.25))
    q3 = float(clean.quantile(0.75))
    iqr = q3 - q1
    outliers = int(((clean < q1 - 1.5 * iqr) | (clean > q3 + 1.5 * iqr)).sum())

    try:
        sv = float(clean.skew()) if len(clean) >= 3 else 0.0
        kv = float(clean.kurtosis()) if len(clean) >= 4 else 0.0
        if math.isnan(sv): sv = 0.0
        if math.isnan(kv): kv = 0.0
        normality = "Normal" if abs(sv) < 0.5 and abs(kv) < 1 else "Not Normal"
    except Exception:
        sv = kv = 0.0
        normality = "N/A"

    return {
        "count":       int(len(clean)),
        "mean":        _safe_round(clean.mean()),
        "median":      _safe_round(clean.median()),
        "min":         _safe_round(clean.min()),
        "max":         _safe_round(clean.max()),
        "std":         _safe_round(clean.std()),
        "variance":    _safe_round(clean.var()),
        "mode":        _safe_round(clean.mode().iloc[0]) if len(clean.mode()) > 0 else None,
        "skewness":    _safe_round(sv),
        "kurtosis":    _safe_round(kv),
        "missing":     missing,
        "missing_pct": missing_pct,
        "outliers":    outliers,
        "normality":   normality,
    }


def compute_all_numeric_stats(df: pd.DataFrame, col_types: dict) -> dict:
    """Hitung stats untuk semua kolom numerik di DataFrame."""
    total_rows = len(df)
    result = {}
    for col, ctype in col_types.items():
        if ctype == 'numeric':
            r = numeric_stats(df[col], total_rows)
            if r:
                result[col] = r
    return result
