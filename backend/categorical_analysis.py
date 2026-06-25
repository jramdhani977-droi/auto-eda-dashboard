"""
categorical_analysis.py — Module analisis statistik variabel kategorik
"""
import pandas as pd


def categorical_stats(series: pd.Series, total_rows: int) -> dict:
    """
    Hitung statistik deskriptif untuk satu kolom kategorik.
    Mencakup: count, unique, mode, mode_freq, mode_pct, missing, missing_pct.
    """
    clean = series.dropna()
    missing = int(series.isna().sum())
    missing_pct = round((missing / total_rows) * 100, 2) if total_rows > 0 else 0
    freq = clean.value_counts()

    top_values = [[str(k), int(v)] for k, v in freq.head(10).items()]

    return {
        "count":      int(len(clean)),
        "unique":     int(clean.nunique()),
        "unique_count": int(clean.nunique()),
        "mode":       str(freq.index[0]) if len(freq) > 0 else "N/A",
        "mode_freq":  int(freq.iloc[0]) if len(freq) > 0 else 0,
        "mode_count": int(freq.iloc[0]) if len(freq) > 0 else 0,
        "mode_pct":   round((int(freq.iloc[0]) / total_rows) * 100, 2) if len(freq) > 0 else 0,
        "missing":    missing,
        "missing_pct": missing_pct,
        "top_values": top_values,
    }


def compute_all_categorical_stats(df: pd.DataFrame, col_types: dict) -> dict:
    """Hitung stats untuk semua kolom kategorik di DataFrame."""
    total_rows = len(df)
    result = {}
    for col, ctype in col_types.items():
        if ctype == 'categorical':
            result[col] = categorical_stats(df[col], total_rows)
    return result


def value_counts_table(df: pd.DataFrame, col: str, top_n: int = 20) -> list:
    """Kembalikan frekuensi nilai sebagai list of dict untuk ditampilkan di tabel."""
    vc = df[col].value_counts().head(top_n)
    total = len(df[col].dropna())
    return [
        {
            'value': str(v),
            'count': int(c),
            'pct': round(c / total * 100, 2) if total > 0 else 0,
        }
        for v, c in vc.items()
    ]
