"""
insight_generator.py — Advanced Auto Insights Generator
SD-1306 Data Science Programming | Meeting 15
"""
import pandas as pd
import numpy as np


def generate_basic_insights(df: pd.DataFrame, col_types: dict,
                             num_stats: dict, cat_stats: dict) -> list:
    insights = []
    total_rows = len(df)
    total_cols = len(df.columns)

    num_cols = [c for c, t in col_types.items() if t == 'numeric']
    cat_cols = [c for c, t in col_types.items() if t == 'categorical']
    dt_cols  = [c for c, t in col_types.items() if t == 'datetime']

    # ── 1. RINGKASAN DATASET ─────────────────────────────────
    size_label = 'kecil' if total_rows < 500 else 'sedang' if total_rows < 10000 else 'besar'
    insights.append({
        'type': 'info', 'icon': '', 'title': 'Ringkasan Dataset',
        'message': (
            f"Dataset berukuran {size_label}: {total_rows:,} baris × {total_cols} kolom. "
            f"Terdiri dari {len(num_cols)} kolom numerik, {len(cat_cols)} kategorik"
            + (f", dan {len(dt_cols)} datetime." if dt_cols else ".")
            + (" Cocok untuk analisis statistik dan machine learning." if total_rows >= 100 else
               " Dataset kecil — pertimbangkan augmentasi data untuk modeling.")
        )
    })

    # ── 2. MISSING VALUES ────────────────────────────────────
    total_missing = int(df.isna().sum().sum())
    missing_pct = round(total_missing / max(total_rows * total_cols, 1) * 100, 1)
    if total_missing == 0:
        insights.append({
            'type': 'success', 'icon': '', 'title': 'Data 100% Lengkap',
            'message': "Tidak ada missing values. Dataset siap digunakan tanpa imputasi tambahan."
        })
    elif missing_pct < 5:
        missing_cols = df.isna().sum()
        missing_cols = missing_cols[missing_cols > 0].sort_values(ascending=False)
        top3 = ', '.join([f"'{c}' ({round(v/total_rows*100,1)}%)" for c, v in missing_cols.head(3).items()])
        insights.append({
            'type': 'warning', 'icon': '', 'title': f'Missing Values Ringan ({missing_pct}%)',
            'message': f"{total_missing:,} sel kosong ({missing_pct}% dari total). Kolom terparah: {top3}. "
                       "Auto cleaning telah mengisi dengan median/mode."
        })
    else:
        missing_cols = df.isna().sum()
        missing_cols = missing_cols[missing_cols > 0].sort_values(ascending=False)
        top3 = ', '.join([f"'{c}' ({round(v/total_rows*100,1)}%)" for c, v in missing_cols.head(3).items()])
        insights.append({
            'type': 'error', 'icon': '', 'title': f'Missing Values Signifikan ({missing_pct}%)',
            'message': f"Total {total_missing:,} missing values ({missing_pct}%). "
                       f"Kolom kritis: {top3}. Pertimbangkan validasi sumber data."
        })

    # ── 3. DUPLIKAT ──────────────────────────────────────────
    dup_count = int(df.duplicated().sum())
    if dup_count == 0:
        insights.append({
            'type': 'success', 'icon': '', 'title': 'Tidak Ada Duplikat',
            'message': "Setiap baris data adalah unik — tidak ada pengulangan data."
        })
    else:
        pct = round(dup_count / total_rows * 100, 1)
        insights.append({
            'type': 'warning', 'icon': '', 'title': f'{dup_count:,} Baris Duplikat ({pct}%)',
            'message': f"Ditemukan {dup_count:,} baris duplikat ({pct}%). "
                       "Auto cleaning telah menghapus semua duplikat."
        })

    # ── 4. KUALITAS DATA KESELURUHAN ─────────────────────────
    total_cells = total_rows * total_cols
    remaining_missing = int(df.isna().sum().sum())
    quality = round((1 - remaining_missing / max(total_cells, 1)) * 100, 1)
    q_label = 'Sangat Baik' if quality >= 95 else 'Baik' if quality >= 85 else 'Cukup' if quality >= 70 else 'Perlu Perhatian'
    q_type = 'success' if quality >= 95 else 'info' if quality >= 85 else 'warning' if quality >= 70 else 'error'
    insights.append({
        'type': q_type, 'icon': '', 'title': f'Kualitas Data: {q_label} ({quality}%)',
        'message': (f"Skor kualitas data mencapai {quality}% — {q_label.lower()}. "
                    + ("Dataset bersih dan siap untuk analisis lanjutan." if quality >= 95
                       else "Beberapa kolom masih perlu perhatian, cek Data Quality Report."))
    })

    # ── 5. OUTLIER ───────────────────────────────────────────
    if num_stats:
        outlier_cols = {c: s['outliers'] for c, s in num_stats.items() if s.get('outliers', 0) > 0}
        if outlier_cols:
            total_out = sum(outlier_cols.values())
            top_out = ', '.join([f"'{c}' ({v} data)" for c, v in sorted(outlier_cols.items(), key=lambda x: -x[1])[:3]])
            insights.append({
                'type': 'warning', 'icon': '', 'title': f'{total_out} Outlier di {len(outlier_cols)} Kolom',
                'message': (f"Outlier terdeteksi pada: {top_out}. "
                            "IQR capping + validasi logis telah diterapkan. "
                            "Cek visualisasi Box Plot untuk detail distribusi.")
            })
        else:
            insights.append({
                'type': 'success', 'icon': '', 'title': 'Tidak Ada Outlier Signifikan',
                'message': "Seluruh kolom numerik berada dalam batas IQR normal."
            })

    # ── 6. DISTRIBUSI & NORMALITAS ────────────────────────────
    not_normal = []
    normal_list = []
    highly_skewed = []

    if num_stats:
        for c, s in num_stats.items():
            is_n = s.get('is_normal', False)
            skew = s.get('skewness', 0) or 0
            if is_n:
                normal_list.append(c)
            else:
                not_normal.append(c)
            if abs(skew) > 2:
                highly_skewed.append((c, round(skew, 2)))

        if normal_list:
            insights.append({
                'type': 'success', 'icon': '', 'title': f'{len(normal_list)} Kolom Berdistribusi Normal',
                'message': (f"Kolom: {', '.join(normal_list[:5])}{'...' if len(normal_list) > 5 else ''}. "
                            "Cocok untuk analisis parametrik: t-test, ANOVA, regresi linear.")
            })
        if not_normal:
            insights.append({
                'type': 'info', 'icon': '', 'title': f'{len(not_normal)} Kolom Tidak Normal (Skewed)',
                'message': (f"Kolom: {', '.join(not_normal[:5])}{'...' if len(not_normal) > 5 else ''}. "
                            "Gunakan metode non-parametrik (Mann-Whitney, Kruskal-Wallis) "
                            "atau transformasi log/sqrt sebelum modeling.")
            })
        if highly_skewed:
            skew_str = ', '.join([f"'{c}' (skew={v})" for c, v in highly_skewed[:3]])
            insights.append({
                'type': 'warning', 'icon': '', 'title': 'Skewness Ekstrem (>2)',
                'message': (f"Kolom dengan kemiringan ekstrem: {skew_str}. "
                            "Sangat disarankan transformasi log1p atau Box-Cox sebelum modeling.")
            })

    # ── 7. STATISTIK HIGHLIGHT ────────────────────────────────
    if num_stats:
        try:
            max_mean_col = max(num_stats, key=lambda c: num_stats[c].get('mean') or 0)
            max_std_col  = max(num_stats, key=lambda c: num_stats[c].get('std') or 0)
            max_range_col = max(num_stats, key=lambda c:
                                (num_stats[c].get('max') or 0) - (num_stats[c].get('min') or 0))
            rng = round((num_stats[max_range_col].get('max') or 0) - (num_stats[max_range_col].get('min') or 0), 2)
            mean_val = round(num_stats[max_mean_col].get('mean', 0), 2)
            std_val = round(num_stats[max_std_col].get('std', 0), 2)
            insights.append({
                'type': 'info', 'icon': '', 'title': 'Sorotan Statistik Deskriptif',
                'message': (f"Nilai rata-rata terbesar: '{max_mean_col}' (mean={mean_val:,}). "
                            f"Variabilitas tertinggi: '{max_std_col}' (std={std_val:,}). "
                            f"Range terlebar: '{max_range_col}' (range={rng:,}).")
            })
        except Exception:
            pass

    # ── 8. ANALISIS KATEGORIK ─────────────────────────────────
    if cat_stats:
        for col, s in list(cat_stats.items())[:4]:
            dom_pct = s.get('mode_pct', 0) or 0
            dom_val = s.get('mode', '—')
            unique  = s.get('unique', 0)

            if unique == 1:
                insights.append({
                    'type': 'error', 'icon': '', 'title': f"Kolom Konstan: '{col}'",
                    'message': (f"'{col}' hanya memiliki 1 nilai unik ('{dom_val}'). "
                                "Kolom ini tidak informatif dan sebaiknya dihapus dari analisis/modeling.")
                })
            elif dom_pct > 80:
                insights.append({
                    'type': 'warning', 'icon': '', 'title': f"Kategori Tidak Seimbang: '{col}'",
                    'message': (f"'{dom_val}' mendominasi {dom_pct:.1f}% dari {unique} kategori di kolom '{col}'. "
                                "Data tidak seimbang — pertimbangkan oversampling/undersampling untuk ML.")
                })
            else:
                insights.append({
                    'type': 'info', 'icon': '', 'title': f"Distribusi Kategori: '{col}'",
                    'message': (f"'{col}': {unique} kategori unik. "
                                f"Kategori paling sering: '{dom_val}' ({dom_pct:.1f}%). "
                                + ("Distribusi seimbang — ideal untuk klasifikasi." if dom_pct < 60 else ""))
                })

    # ── 9. HIGH CARDINALITY ───────────────────────────────────
    if cat_stats:
        high_card = [(c, s['unique']) for c, s in cat_stats.items()
                     if s.get('unique', 0) > 0.5 * total_rows]
        if high_card:
            cols_str = ', '.join([f"'{c}' ({u} unique)" for c, u in high_card[:3]])
            insights.append({
                'type': 'warning', 'icon': '', 'title': 'Kolom Kardinalitas Tinggi',
                'message': (f"Kolom dengan >50% nilai unik: {cols_str}. "
                            "Kemungkinan kolom ID/kode unik. Exclude dari feature ML, "
                            "tapi berguna sebagai identifier dalam join/merge.")
            })

    # ── 10. KORELASI ─────────────────────────────────────────
    if len(num_cols) >= 2:
        try:
            corr = df[num_cols].apply(pd.to_numeric, errors='coerce').corr()
            high_corr = []
            perfect_corr = []
            for i in range(len(num_cols)):
                for j in range(i+1, len(num_cols)):
                    c1, c2 = num_cols[i], num_cols[j]
                    val = corr.loc[c1, c2]
                    if pd.notna(val):
                        if abs(val) >= 0.95:
                            perfect_corr.append((c1, c2, round(val, 3)))
                        elif abs(val) >= 0.8:
                            high_corr.append((c1, c2, round(val, 3)))

            if perfect_corr:
                pairs = ', '.join([f"'{a}'↔'{b}' (r={v})" for a, b, v in perfect_corr[:2]])
                insights.append({
                    'type': 'error', 'icon': '', 'title': 'Korelasi Sempurna Ditemukan',
                    'message': (f"Korelasi sangat tinggi (|r|≥0.95): {pairs}. "
                                "Kemungkinan kolom yang sama / derived feature — "
                                "salah satu harus dihapus sebelum modeling.")
                })
            if high_corr:
                pairs = ', '.join([f"'{a}'↔'{b}' (r={v})" for a, b, v in high_corr[:3]])
                insights.append({
                    'type': 'warning', 'icon': '', 'title': 'Korelasi Tinggi (Multikolinearitas)',
                    'message': (f"Korelasi tinggi (|r|≥0.8): {pairs}. "
                                "Waspadai multikolinearitas pada regresi linear. "
                                "Pertimbangkan PCA atau regularization (Ridge/Lasso).")
                })
            if not high_corr and not perfect_corr:
                insights.append({
                    'type': 'success', 'icon': '', 'title': 'Tidak Ada Multikolinearitas',
                    'message': "Tidak ada korelasi tinggi antar fitur numerik (|r| < 0.8). "
                               "Dataset bebas multikolinearitas — aman untuk regresi."
                })
        except Exception:
            pass

    # ── 11. TIME SERIES ──────────────────────────────────────
    if dt_cols:
        insights.append({
            'type': 'info', 'icon': '', 'title': f'Kolom Waktu Terdeteksi: {", ".join(dt_cols[:3])}',
            'message': (f"Ditemukan {len(dt_cols)} kolom datetime. "
                        "Gunakan fitur Time Series Analytics untuk analisis tren, "
                        "seasonality, dan forecasting.")
        })

    # ── 12. REKOMENDASI AKHIR ────────────────────────────────
    recs = []
    if total_missing > 0:
        recs.append("validasi sumber data untuk mengurangi missing values")
    if num_stats and any(s.get('outliers', 0) > 0 for s in num_stats.values()):
        recs.append("review outlier di Box Plot sebelum modeling")
    if not_normal:
        recs.append(f"transformasi log/sqrt pada {len(not_normal)} kolom skewed")
    if dt_cols:
        recs.append("eksplorasi Time Series Analytics untuk analisis tren")
    if cat_stats and any(s.get('mode_pct', 0) > 80 for s in cat_stats.values()):
        recs.append("tangani class imbalance sebelum training model klasifikasi")
    if len(num_cols) >= 5:
        recs.append("coba PCA untuk reduksi dimensi")

    if recs:
        insights.append({
            'type': 'info', 'icon': '', 'title': 'Rekomendasi Langkah Selanjutnya',
            'message': "Saran analisis lanjutan: " + " | ".join(
                [f"({i+1}) {r}" for i, r in enumerate(recs)]
            ) + "."
        })
    else:
        insights.append({
            'type': 'success', 'icon': '', 'title': 'Dataset Siap Analisis',
            'message': ("Data bersih, lengkap, dan tidak ada isu serius. "
                        "Lanjutkan ke Descriptive Stats, Visualisasi, atau Export Report.")
        })

    return insights

