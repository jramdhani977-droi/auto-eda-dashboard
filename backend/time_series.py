"""
time_series.py — Module Time Series analytics (Meeting 15)
Dipakai oleh app.py di route /timeseries dan /ts-cols.
"""

import pandas as pd
import numpy as np
import math


# ── Deteksi kolom tanggal ─────────────────────────────────────
def detect_date_columns(df):
    """
    Mendeteksi kolom yang berisi data tanggal/waktu.
    Dipakai oleh app.py untuk endpoint /ts-cols.
    Return: list of dict {col, reason}
    """
    date_cols = []
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            date_cols.append({'col': col, 'reason': 'datetime type'})
            continue

        if df[col].dtype == object:
            sample = df[col].dropna().head(20).astype(str)
            patterns = [
                r'^\d{4}[-/]\d{2}[-/]\d{2}',
                r'^\d{2}[-/]\d{2}[-/]\d{4}',
                r'^\d{4}[-/]\d{2}[-/]\d{2}\s\d{2}:\d{2}',
            ]
            for pat in patterns:
                if sample.str.match(pat).mean() > 0.5:
                    date_cols.append({'col': col, 'reason': 'date-like strings'})
                    break

    return date_cols


# ── Parse kolom ke datetime ───────────────────────────────────
def parse_date_column(df, date_col):
    """Konversi kolom ke datetime Series."""
    series = df[date_col].copy()
    if not pd.api.types.is_datetime64_any_dtype(series):
        series = pd.to_datetime(series, errors='coerce')
    return series


# ── Statistik ringkas time series ─────────────────────────────
def time_series_stats(df, date_col, val_col):
    """
    Hitung statistik dasar: trend, volatilitas, outlier, MA.
    Return: dict stats — bisa dipakai untuk insight panel di frontend.
    """
    df = df.copy()
    df[date_col] = parse_date_column(df, date_col)
    df = df.dropna(subset=[date_col]).sort_values(date_col)
    y = pd.to_numeric(df[val_col], errors='coerce').dropna()

    if len(y) == 0:
        return {}

    idx = np.arange(len(y))
    try:
        from scipy import stats as scipy_stats
        slope, _, r_value, _, _ = scipy_stats.linregress(idx, y.values)
        trend_direction = 'naik' if slope > 0 else 'turun' if slope < 0 else 'stabil'
        r_squared = round(r_value ** 2, 4)
    except Exception:
        slope, r_squared, trend_direction = 0, 0, 'tidak diketahui'

    q1, q3 = y.quantile(0.25), y.quantile(0.75)
    iqr = q3 - q1
    outliers = int(((y < q1 - 1.5 * iqr) | (y > q3 + 1.5 * iqr)).sum())

    mean_val = float(y.mean())
    volatility = round(float(y.std()) / mean_val * 100, 2) if mean_val != 0 else 0

    ma7  = y.rolling(window=7,  min_periods=1).mean()
    ma30 = y.rolling(window=30, min_periods=1).mean()

    return {
        'n_points':        int(len(y)),
        'date_start':      str(df[date_col].min().date()),
        'date_end':        str(df[date_col].max().date()),
        'mean':            round(mean_val, 4),
        'std':             round(float(y.std()), 4),
        'min':             round(float(y.min()), 4),
        'max':             round(float(y.max()), 4),
        'trend_slope':     round(float(slope), 6),
        'trend_direction': trend_direction,
        'r_squared':       r_squared,
        'outliers':        outliers,
        'volatility_pct':  volatility,
        'ma7_last':        round(float(ma7.iloc[-1]), 4) if len(ma7) > 0 else None,
        'ma30_last':       round(float(ma30.iloc[-1]), 4) if len(ma30) > 0 else None,
    }


# ── Helper: bersihkan nilai float ─────────────────────────────
def _safe(v):
    """Return None jika NaN/Inf, supaya JSON serializable."""
    if v is None:
        return None
    try:
        if math.isnan(v) or math.isinf(v):
            return None
    except TypeError:
        pass
    return round(float(v), 4)


def _safe_list(series):
    return [_safe(v) for v in series.tolist()]


# ── Entry point utama — dipanggil dari app.py ─────────────────
def compute_time_series(df, date_col, val_col, ma_window=7, roll_window=30):
    """
    Dipakai oleh route /timeseries di app.py.
    Build semua data series yang dibutuhkan untuk 4 chart Plotly:
      - line_chart  : raw values
      - ma_chart    : raw + moving average (ma_window)
      - trend_chart : raw + linear trend
      - roll30_chart: raw + rolling mean (roll_window)

    Return: dict dengan key 'dates', 'values', 'ma', 'roll',
            'trend_line', 'stats', dan metadata.
    """
    df = df.copy()
    df[date_col] = parse_date_column(df, date_col)
    df = df.dropna(subset=[date_col]).sort_values(date_col)

    y = pd.to_numeric(df[val_col], errors='coerce').ffill().bfill()

    # Dates sebagai string ISO
    dates = df[date_col].dt.strftime('%Y-%m-%d %H:%M:%S').tolist()

    # Moving average (window custom dari request)
    ma = y.rolling(window=ma_window, center=True, min_periods=1).mean()

    # Rolling mean (window custom dari request)
    roll = y.rolling(window=roll_window, center=True, min_periods=1).mean()

    # Trend linear (polyfit)
    idx = np.arange(len(y))
    try:
        z = np.polyfit(idx, y.values, 1)
        trend_line = np.poly1d(z)(idx).tolist()
        trend_line = [round(v, 4) for v in trend_line]
    except Exception:
        trend_line = _safe_list(y)

    stats = time_series_stats(df, date_col, val_col)

    return {
        'dates':       dates,
        'values':      _safe_list(y),
        'ma':          _safe_list(ma),
        'roll':        _safe_list(roll),
        'trend_line':  trend_line,
        'stats':       stats,
        'date_col':    date_col,
        'val_col':     val_col,
        'ma_window':   ma_window,
        'roll_window': roll_window,
    }