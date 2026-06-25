# -*- coding: utf-8 -*-
"""
export_report.py — PDF (reportlab), Excel, CSV export
"""
import io, json, math
from datetime import datetime
import pandas as pd
from io import BytesIO

# ── ReportLab imports ────────────────────────────────────────────────────────
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, Image as RLImage
)

# ── Matplotlib (chart generation) ────────────────────────────────────────────
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _safe(v):
    if v is None:
        return '—'
    try:
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return '—'
    except Exception:
        pass
    return str(v)


def _fmt_num(v):
    """Format angka dengan pemisah ribuan agar mudah dibaca di tabel laporan."""
    if v is None:
        return '—'
    try:
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return '—'
        if isinstance(v, (int, float)):
            if float(v).is_integer():
                return f'{int(v):,}'
            return f'{v:,.2f}'
    except Exception:
        pass
    return str(v)


def _generate_chart(df, col, chart_type='hist'):
    """Generate matplotlib chart dan kembalikan sebagai BytesIO PNG."""
    fig, ax = plt.subplots(figsize=(6, 3))

    if chart_type == 'hist' and pd.api.types.is_numeric_dtype(df[col]):
        df[col].dropna().hist(ax=ax, bins=20, color='#4F81BD', edgecolor='white')
        ax.set_title(f'Distribution: {col}', fontsize=10, fontweight='bold')
        ax.set_xlabel(col, fontsize=8)
        ax.set_ylabel('Frequency', fontsize=8)
    elif chart_type == 'bar':
        vc = df[col].value_counts().head(10)
        vc.plot(kind='bar', ax=ax, color='#9b59b6')
        ax.set_title(f'Top Values: {col}', fontsize=10, fontweight='bold')
        ax.set_xlabel(col, fontsize=8)
        ax.set_ylabel('Count', fontsize=8)
        plt.xticks(rotation=45, ha='right', fontsize=7)

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.tick_params(labelsize=7)
    plt.tight_layout()

    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=120, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf


def _detect_date_columns(df):
    """Deteksi kolom datetime dalam DataFrame — lebih agresif agar konsisten dengan dashboard."""
    import re
    date_cols = []
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            date_cols.append(col)
            continue
        # Cek nama kolom yang mengandung kata date/time/tanggal/tgl/bulan/tahun
        col_lower = col.lower()
        if any(k in col_lower for k in ['date', 'time', 'tanggal', 'tgl', 'bulan', 'tahun', 'year', 'month']):
            # Coba parse sebagai datetime
            try:
                parsed = pd.to_datetime(df[col].dropna().head(20), errors='coerce')
                if parsed.notna().mean() > 0.5:
                    date_cols.append(col)
                    continue
            except Exception:
                pass
        if df[col].dtype == object:
            sample = df[col].dropna().head(20).astype(str)
            patterns = [
                r'^\d{4}[-/]\d{2}[-/]\d{2}',
                r'^\d{2}[-/]\d{2}[-/]\d{4}',
                r'^\d{4}[-/]\d{2}[-/]\d{2}\s\d{2}:\d{2}',
                r'^\d{4}-\d{2}-\d{2}T',
                r'^\w{3}\s+\d{1,2}\s+\d{4}',
            ]
            for pat in patterns:
                if sample.str.match(pat).mean() > 0.5:
                    date_cols.append(col)
                    break
            else:
                # Last resort: try pd.to_datetime on sample
                try:
                    parsed = pd.to_datetime(sample, errors='coerce')
                    if parsed.notna().mean() > 0.7:
                        date_cols.append(col)
                except Exception:
                    pass
    return date_cols


def _generate_timeseries_chart(df, date_col, val_col):
    """Generate time series chart dengan MA dan trend line."""
    try:
        df2 = df[[date_col, val_col]].copy()
        df2[date_col] = pd.to_datetime(df2[date_col], errors='coerce')
        df2 = df2.dropna(subset=[date_col]).sort_values(date_col)
        df2[val_col] = pd.to_numeric(df2[val_col], errors='coerce')
        df2 = df2.dropna(subset=[val_col])

        if len(df2) < 2:
            return None

        # Jika terlalu banyak titik, resample atau subsample
        if len(df2) > 500:
            df2 = df2.iloc[::len(df2)//500 + 1]

        x = df2[date_col]
        y = df2[val_col]

        fig, ax = plt.subplots(figsize=(12, 4))

        # Raw values
        ax.plot(x, y, color='#2d6a9f', linewidth=1, alpha=0.7, label='Actual')

        # Moving average 7
        if len(y) >= 7:
            ma7 = y.rolling(window=7, min_periods=1).mean()
            ax.plot(x, ma7, color='#c94040', linewidth=1.5, label='MA-7')

        # Trend line
        idx = np.arange(len(y))
        z = np.polyfit(idx, y.values, 1)
        trend = np.poly1d(z)(idx)
        ax.plot(x, trend, color='#e07b39', linewidth=1.5, linestyle='--', label='Trend')

        ax.set_title(f'Time Series: {val_col} over {date_col}', fontsize=10, fontweight='bold')
        ax.set_xlabel(date_col, fontsize=8)
        ax.set_ylabel(val_col, fontsize=8)
        ax.legend(fontsize=7, loc='upper left')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.tick_params(labelsize=7)
        plt.xticks(rotation=30, ha='right', fontsize=7)
        plt.tight_layout()

        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=120, bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception as e:
        plt.close('all')
        return None

def _generate_scatter_matrix(df, cols):
    """Generate scatter matrix untuk kolom numerik."""
    try:
        n = len(cols)
        fig, axes = plt.subplots(n, n, figsize=(10, 10))
        if n == 1:
            axes = [[axes]]
        for i, col_i in enumerate(cols):
            for j, col_j in enumerate(cols):
                ax = axes[i][j]
                if i == j:
                    df[col_i].dropna().hist(ax=ax, bins=15, color='#4F81BD', edgecolor='white')
                else:
                    ax.scatter(
                        df[col_j].dropna()[:500], df[col_i].dropna()[:500],
                        alpha=0.3, s=5, color='#2d6a9f'
                    )
                if i == n - 1:
                    ax.set_xlabel(col_j, fontsize=6)
                if j == 0:
                    ax.set_ylabel(col_i, fontsize=6)
                ax.tick_params(labelsize=5)
                ax.spines['top'].set_visible(False)
                ax.spines['right'].set_visible(False)
        plt.suptitle('Scatter Matrix', fontsize=11, fontweight='bold', y=1.01)
        plt.tight_layout()
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=110, bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception:
        plt.close('all')
        return None


def _generate_heatmap(df, num_cols):
    """Generate correlation heatmap."""
    try:
        corr = df[num_cols].corr()
        n = len(corr)
        fig, ax = plt.subplots(figsize=(max(6, n * 0.8), max(5, n * 0.7)))
        im = ax.imshow(corr.values, cmap='coolwarm', vmin=-1, vmax=1, aspect='auto')
        plt.colorbar(im, ax=ax, shrink=0.8)
        ax.set_xticks(range(n))
        ax.set_yticks(range(n))
        ax.set_xticklabels(corr.columns, rotation=45, ha='right', fontsize=7)
        ax.set_yticklabels(corr.columns, fontsize=7)
        for i in range(n):
            for j in range(n):
                ax.text(j, i, f"{corr.values[i, j]:.2f}",
                        ha='center', va='center', fontsize=6,
                        color='white' if abs(corr.values[i, j]) > 0.5 else 'black')
        ax.set_title('Correlation Matrix', fontsize=10, fontweight='bold')
        plt.tight_layout()
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=110, bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception:
        plt.close('all')
        return None


def _generate_grouped_bar(df, cat_col, num_col):
    """Generate grouped bar chart: rata-rata num_col per kategori cat_col."""
    try:
        top_cats = df[cat_col].value_counts().head(8).index
        grouped = df[df[cat_col].isin(top_cats)].groupby(cat_col)[num_col].mean().reindex(top_cats)
        fig, ax = plt.subplots(figsize=(10, 3.5))
        colors_list = plt.cm.Set2(np.linspace(0, 1, len(grouped)))
        ax.bar(grouped.index.astype(str), grouped.values, color=colors_list)
        ax.set_title(f'Avg {num_col} by {cat_col}', fontsize=10, fontweight='bold')
        ax.set_xlabel(cat_col, fontsize=8)
        ax.set_ylabel(f'Avg {num_col}', fontsize=8)
        plt.xticks(rotation=30, ha='right', fontsize=7)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.tick_params(labelsize=7)
        plt.tight_layout()
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=110, bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception:
        plt.close('all')
        return None


# ─────────────────────────────────────────────────────────────────────────────
# PDF EXPORT
# ─────────────────────────────────────────────────────────────────────────────

def export_pdf(df: pd.DataFrame,
               num_stats: dict = None,
               cat_stats: dict = None,
               col_types: dict = None,
               insights=None,
               filename: str = None,
               selected_charts: list = None,
               max_num_cols: int = 4,
               max_cat_cols: int = 4) -> BytesIO:
    # Default: semua chart aktif
    if selected_charts is None:
        selected_charts = ['histogram', 'bar', 'scatter', 'heatmap', 'grouped_bar']

    """
    Buat laporan EDA LENGKAP dalam format PDF (cover, daftar isi otomatis,
    pendahuluan, isi analisis, kesimpulan & rekomendasi, nomor halaman)
    dan kembalikan sebagai BytesIO.

    Panggil dari Flask route seperti ini:

        buf = export_pdf(df, num_stats, cat_stats, col_types, insights, fname)
        return send_file(buf, mimetype='application/pdf',
                         as_attachment=True, download_name='EDA_Report.pdf')
    """
    from reportlab.platypus import (
        BaseDocTemplate, PageTemplate, Frame, PageBreak, KeepTogether
    )
    from reportlab.platypus.tableofcontents import TableOfContents
    import ast

    buffer = BytesIO()

    # ── Custom doc template: enables auto Table-of-Contents + page numbers ──
    class ReportDocTemplate(BaseDocTemplate):
        def afterFlowable(self, flowable):
            if isinstance(flowable, Paragraph):
                style_name = flowable.style.name
                text = flowable.getPlainText()
                if style_name == 'H1':
                    level = 0
                elif style_name == 'H2':
                    level = 1
                else:
                    return
                key = f'toc-{id(flowable)}-{self.page}'
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(text, key, level=level, closed=False)
                self.notify('TOCEntry', (level, text, self.page, key))

    def _draw_page(canvas, doc_):
        canvas.saveState()
        # Header tipis & netral (bukan halaman cover) — laporan formal biasa
        if doc_.page > 1:
            canvas.setStrokeColor(colors.HexColor('#cccccc'))
            canvas.setLineWidth(0.5)
            canvas.line(2 * cm, A4[1] - 1.4 * cm, A4[0] - 2 * cm, A4[1] - 1.4 * cm)
            canvas.setFont('Helvetica', 8)
            canvas.setFillColor(colors.HexColor('#888888'))
            canvas.drawString(2 * cm, A4[1] - 1.2 * cm, 'Auto EDA Analytics Report')
            canvas.drawRightString(A4[0] - 2 * cm, A4[1] - 1.2 * cm,
                                    datetime.now().strftime('%d %B %Y'))
        # Footer (di semua halaman termasuk cover)
        canvas.setStrokeColor(colors.HexColor('#cccccc'))
        canvas.setLineWidth(0.5)
        canvas.line(2 * cm, 1.5 * cm, A4[0] - 2 * cm, 1.5 * cm)
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#888888'))
        canvas.drawString(2 * cm, 1.1 * cm, 'Auto EDA Analytics Dashboard')
        canvas.drawRightString(A4[0] - 2 * cm, 1.1 * cm, f'Halaman {doc_.page}')
        canvas.restoreState()

    doc = ReportDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2.6 * cm,
        bottomMargin=2.2 * cm,
        title='EDA Analytics Report',
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='normal')
    doc.addPageTemplates([
        PageTemplate(id='Normal', frames=[frame], onPage=_draw_page),
    ])

    styles = getSampleStyleSheet()

    # ── Custom styles ──────────────────────────────────────────────────────
    cover_title_style = ParagraphStyle(
        'CoverTitle', parent=styles['Title'],
        fontSize=24, textColor=colors.HexColor('#1a1a2e'),
        spaceAfter=10, fontName='Helvetica-Bold', alignment=1,
    )
    cover_sub_style = ParagraphStyle(
        'CoverSub', parent=styles['Normal'],
        fontSize=12, textColor=colors.HexColor('#555555'),
        alignment=1, spaceAfter=6,
    )
    cover_meta_style = ParagraphStyle(
        'CoverMeta', parent=styles['Normal'],
        fontSize=10, textColor=colors.HexColor('#555555'),
        alignment=1, spaceAfter=4,
    )
    title_style = ParagraphStyle(
        'CustomTitle', parent=styles['Title'],
        fontSize=20, textColor=colors.HexColor('#1a1a2e'),
        spaceAfter=6, fontName='Helvetica-Bold'
    )
    h1_style = ParagraphStyle(
        'H1', parent=styles['Heading1'],
        fontSize=14, textColor=colors.HexColor('#4F81BD'),
        spaceBefore=16, spaceAfter=6, fontName='Helvetica-Bold'
    )
    h2_style = ParagraphStyle(
        'H2', parent=styles['Heading2'],
        fontSize=11, textColor=colors.HexColor('#2c3e50'),
        spaceBefore=10, spaceAfter=4, fontName='Helvetica-Bold'
    )
    body_style = ParagraphStyle(
        'Body', parent=styles['Normal'],
        fontSize=9, textColor=colors.HexColor('#333333'),
        spaceAfter=4, leading=14
    )
    label_style = ParagraphStyle(
        'Label', parent=styles['Normal'],
        fontSize=8, textColor=colors.HexColor('#666666'),
    )
    toc_h_style = ParagraphStyle(
        'TOCHeading', parent=styles['Title'],
        fontSize=16, textColor=colors.HexColor('#1a1a2e'),
        spaceAfter=14, fontName='Helvetica-Bold'
    )

    story = []

    # ════════════════════════════════════════════════════════════════════
    # COVER PAGE
    # ════════════════════════════════════════════════════════════════════
    import os

    # Logo ITB
    logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'img', 'logo-itb.png')
    if os.path.exists(logo_path):
        from PIL import Image as PILImage
        story.append(Spacer(1, 1.5 * cm))
        try:
            with PILImage.open(logo_path) as pil_img:
                orig_w, orig_h = pil_img.size
            # Scale to fit 8cm wide, preserve aspect ratio
            target_w = 8 * cm
            target_h = target_w * orig_h / orig_w
            # Cap height at 3.5cm so it doesn't dominate the page
            if target_h > 3.5 * cm:
                target_h = 3.5 * cm
                target_w = target_h * orig_w / orig_h
        except Exception:
            target_w, target_h = 8 * cm, 3 * cm
        logo_img = RLImage(logo_path, width=target_w, height=target_h)
        logo_img.hAlign = 'CENTER'
        story.append(logo_img)
        story.append(Spacer(1, 1 * cm))
    else:
        story.append(Spacer(1, 6 * cm))

    story.append(Paragraph('LAPORAN EXPLORATORY DATA ANALYSIS', cover_title_style))
    story.append(Paragraph('(Auto EDA Analytics Report)', cover_sub_style))
    story.append(Spacer(1, 1 * cm))
    story.append(Spacer(1, 1 * cm))
    if filename:
        story.append(Paragraph(f'Dataset: <b>{filename}</b>', cover_meta_style))
    story.append(Paragraph(f'{df.shape[0]:,} baris &middot; {df.shape[1]} kolom', cover_meta_style))
    story.append(Paragraph(f'Tanggal dibuat: {datetime.now().strftime("%d %B %Y, %H:%M")}', cover_meta_style))

    # Nama Kelompok
    story.append(Spacer(1, 1.5 * cm))
    story.append(Spacer(1, 0.5 * cm))

    cover_group_title_style = ParagraphStyle(
        'CoverGroupTitle', parent=styles['Normal'],
        fontSize=11, textColor=colors.HexColor('#1a1a2e'),
        alignment=1, spaceAfter=6, fontName='Helvetica-Bold',
    )
    cover_member_style = ParagraphStyle(
        'CoverMember', parent=styles['Normal'],
        fontSize=10, textColor=colors.HexColor('#333333'),
        alignment=1, spaceAfter=3,
    )

    story.append(Paragraph('Disusun oleh:', cover_group_title_style))
    story.append(Spacer(1, 0.3 * cm))

    members = [
        ('Roni Kurniawan', '52250020'),
        ('Nakeisha Aulia Zahra', '52250021'),
        ('Jihan Ramadhani Deandri', '52250024'),
        ('Anindya Kristianingputri', '52250025'),
    ]
    for name, nim in members:
        story.append(Paragraph(f'{name} &nbsp;&nbsp;|&nbsp;&nbsp; <font color="#888888">{nim}</font>', cover_member_style))

    story.append(Spacer(1, 1 * cm))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph('Data Science Programming &middot; Bakti Siregar, M.Sc.', cover_meta_style))
    story.append(Paragraph('Auto EDA Analytics Dashboard', cover_meta_style))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # DAFTAR ISI (Table of Contents — auto page numbers via 2-pass build)
    # ════════════════════════════════════════════════════════════════════
    story.append(Paragraph('Daftar Isi', toc_h_style))
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle(name='TOCLevel0', fontSize=10.5, leading=16,
                       textColor=colors.HexColor('#1a1a2e'), fontName='Helvetica-Bold'),
        ParagraphStyle(name='TOCLevel1', fontSize=9.5, leading=14, leftIndent=14,
                       textColor=colors.HexColor('#444444')),
    ]
    toc.dotsMinLevel = 0  # titik-titik (leader) muncul di semua level, termasuk judul utama
    story.append(toc)
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # HEADER (judul laporan di tiap section utama)
    # ════════════════════════════════════════════════════════════════════
    story.append(Paragraph('Auto EDA Analytics Report', title_style))
    story.append(Paragraph('Data Science Programming &middot; Bakti Siregar, M.Sc.', label_style))
    if filename:
        story.append(Paragraph(f'File: {filename}', label_style))
    story.append(HRFlowable(width='100%', thickness=2, color=colors.HexColor('#4F81BD')))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(f'Generated: {datetime.now().strftime("%d %B %Y, %H:%M")}', label_style))
    story.append(Spacer(1, 0.5 * cm))

    # ── Auto-cast kolom yang sebenarnya numerik tapi tersimpan sbg string ──
    df = df.copy()
    for _col in df.select_dtypes(include='object').columns:
        _try = pd.to_numeric(df[_col], errors='coerce')
        # Jika >60% baris berhasil di-parse, anggap numerik
        if _try.notna().mean() > 0.6:
            df[_col] = _try

    num_cols = df.select_dtypes(include='number').columns.tolist()
    date_cols = _detect_date_columns(df)
    # Kolom kategorikal "asli" = object/string TAPI bukan kolom tanggal,
    # supaya tidak menghasilkan tabel/chart kategori dengan ratusan nilai unik (mis. kolom Date).
    cat_cols = [c for c in df.select_dtypes(include='object').columns.tolist() if c not in date_cols]
    missing_total = int(df.isnull().sum().sum())
    quality_pct = round(100 - (missing_total / (df.shape[0] * df.shape[1]) * 100), 2) if df.shape[0] and df.shape[1] else 100

    # ── SECTION: PENDAHULUAN ─────────────────────────────────────────────
    story.append(Paragraph('1. Pendahuluan', h1_style))
    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#cccccc')))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph('1.1 Latar Belakang', h2_style))
    story.append(Paragraph(
        'Laporan ini disusun secara otomatis oleh Auto EDA Analytics Dashboard untuk '
        'memberikan gambaran menyeluruh mengenai karakteristik dataset yang diunggah, '
        'mencakup struktur data, kualitas data, distribusi nilai, hubungan antar variabel, '
        'serta pola atau anomali yang dapat diidentifikasi secara otomatis.', body_style
    ))
    story.append(Paragraph('1.2 Tujuan', h2_style))
    story.append(Paragraph(
        'Tujuan dari laporan Exploratory Data Analysis (EDA) ini adalah untuk membantu '
        'pengguna memahami isi dataset sebelum melakukan analisis lanjutan atau pemodelan, '
        'mendeteksi masalah kualitas data (missing value, tipe data tidak konsisten, dll.), '
        'dan menyajikan insight awal yang dapat menjadi dasar pengambilan keputusan.', body_style
    ))
    story.append(Paragraph('1.3 Ruang Lingkup Data', h2_style))
    story.append(Paragraph(
        f'Dataset yang dianalisis terdiri dari <b>{df.shape[0]:,} baris</b> dan '
        f'<b>{df.shape[1]} kolom</b>, dengan rincian <b>{len(num_cols)} kolom numerik</b>, '
        f'<b>{len(cat_cols)} kolom kategorikal</b>'
        + (f', dan <b>{len(date_cols)} kolom tanggal/waktu</b>' if date_cols else '')
        + f'. Tingkat kelengkapan data secara keseluruhan adalah <b>{quality_pct}%</b> '
        f'({missing_total:,} sel kosong dari total {df.shape[0]*df.shape[1]:,} sel).',
        body_style
    ))
    story.append(Paragraph('1.4 Sistematika Laporan', h2_style))
    story.append(Paragraph(
        'Laporan ini terdiri dari beberapa bagian utama: pratinjau data, ringkasan statistik '
        'numerik dan kategorikal, evaluasi kualitas data, analisis deret waktu (jika tersedia), '
        'insight otomatis, serta kesimpulan dan rekomendasi tindak lanjut.', body_style
    ))
    story.append(Spacer(1, 0.4 * cm))

    # ── SECTION: DATA PREVIEW ────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph('2. Data Preview', h1_style))
    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#cccccc')))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        f'Dataset: <b>{df.shape[0]:,} rows &times; {df.shape[1]} columns</b>',
        body_style
    ))
    story.append(Spacer(1, 0.2 * cm))

    preview_df = df.head(10)
    col_names = list(preview_df.columns)
    max_cols = 7
    if len(col_names) > max_cols:
        col_names = col_names[:max_cols]
        story.append(Paragraph(
            f'(Menampilkan {max_cols} kolom pertama dari {df.shape[1]} kolom)',
            label_style
        ))

    table_data = [col_names]
    for _, row in preview_df[col_names].iterrows():
        table_data.append([_safe(v)[:15] for v in row.values])

    col_width = (17 * cm) / len(col_names)
    tbl = Table(table_data, colWidths=[col_width] * len(col_names))
    tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0), colors.HexColor('#4F81BD')),
        ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
        ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, -1), 7),
        ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f4f8')]),
        ('GRID',          (0, 0), (-1, -1), 0.3, colors.HexColor('#cccccc')),
        ('ALIGN',         (0, 0), (-1, -1), 'LEFT'),
        ('PADDING',       (0, 0), (-1, -1), 4),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 0.5 * cm))

    # ── SECTION: NUMERICAL SUMMARY ───────────────────────────────────────
    if num_cols:
        story.append(PageBreak())
        story.append(Paragraph('3. Numerical Summary', h1_style))
        story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#cccccc')))
        story.append(Spacer(1, 0.2 * cm))

        desc = df[num_cols].describe().round(3)
        _max_num_cols_disp = 6
        disp_cols = list(desc.columns[:_max_num_cols_disp])
        desc_data = [['Statistic'] + disp_cols]
        for idx in desc.index:
            desc_data.append([idx] + [_fmt_num(v) for v in desc.loc[idx, disp_cols].values])

        col_w = (17 * cm) / len(desc_data[0])
        tbl2 = Table(desc_data, colWidths=[col_w] * len(desc_data[0]))
        tbl2.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0), colors.HexColor('#34495e')),
            ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
            ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE',      (0, 0), (-1, -1), 7),
            ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, colors.HexColor('#f4f6f7')]),
            ('GRID',          (0, 0), (-1, -1), 0.3, colors.HexColor('#cccccc')),
            ('PADDING',       (0, 0), (-1, -1), 4),
        ]))
        story.append(tbl2)
        story.append(Spacer(1, 0.3 * cm))

        # Distribution charts (histogram)
        if 'histogram' in selected_charts:
            story.append(Paragraph('Distribution Charts', h2_style))
            _max_n = max_num_cols if max_num_cols else len(num_cols)
            chart_cols = num_cols[:_max_n]
            for i in range(0, len(chart_cols), 2):
                batch = chart_cols[i:i + 2]
                row_imgs = []
                for col in batch:
                    buf = _generate_chart(df, col, 'hist')
                    row_imgs.append(RLImage(buf, width=8 * cm, height=4.5 * cm))
                if len(row_imgs) == 1:
                    buf_single = _generate_chart(df, batch[0], 'hist')
                    story.append(RLImage(buf_single, width=14 * cm, height=5.5 * cm))
                else:
                    widths = [8.5 * cm] * len(row_imgs)
                    img_tbl = Table([row_imgs], colWidths=widths)
                    img_tbl.setStyle(TableStyle([
                        ('ALIGN',  (0, 0), (-1, -1), 'CENTER'),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ]))
                    story.append(img_tbl)
                story.append(Spacer(1, 0.3 * cm))

        # Scatter Matrix
        if 'scatter' in selected_charts and len(num_cols) >= 2:
            story.append(Paragraph('Scatter Matrix', h2_style))
            scatter_cols = num_cols[:min(4, len(num_cols))]
            buf = _generate_scatter_matrix(df, scatter_cols)
            if buf:
                story.append(RLImage(buf, width=17 * cm, height=14 * cm))
            story.append(Spacer(1, 0.3 * cm))

        # Correlation Heatmap
        if 'heatmap' in selected_charts and len(num_cols) >= 2:
            story.append(Paragraph('Correlation Heatmap', h2_style))
            buf = _generate_heatmap(df, num_cols)
            if buf:
                story.append(RLImage(buf, width=15 * cm, height=11 * cm))
            story.append(Spacer(1, 0.3 * cm))

        story.append(Spacer(1, 0.5 * cm))

    # ── SECTION: CATEGORICAL SUMMARY ─────────────────────────────────────
    if cat_cols:
        story.append(PageBreak())
        story.append(Paragraph('4. Categorical Summary', h1_style))
        story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#cccccc')))
        story.append(Spacer(1, 0.2 * cm))

        cat_data = [['Column', 'Unique Values', 'Most Frequent', 'Frequency']]
        for col in cat_cols[:10]:
            vc = df[col].value_counts()
            cat_data.append([
                col,
                str(df[col].nunique()),
                _safe(vc.index[0]) if len(vc) > 0 else '—',
                str(vc.iloc[0]) if len(vc) > 0 else '—',
            ])

        tbl3 = Table(cat_data, colWidths=[5 * cm, 4 * cm, 5 * cm, 3 * cm])
        tbl3.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0), colors.HexColor('#9b59b6')),
            ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
            ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE',      (0, 0), (-1, -1), 8),
            ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f0ff')]),
            ('GRID',          (0, 0), (-1, -1), 0.3, colors.HexColor('#cccccc')),
            ('PADDING',       (0, 0), (-1, -1), 5),
        ]))
        story.append(tbl3)
        story.append(Spacer(1, 0.3 * cm))

        # Hanya kolom dengan kardinalitas wajar yang layak divisualisasikan sebagai bar chart
        chartable_cat_cols = [c for c in cat_cols if df[c].nunique() <= 20]

        # Bar charts untuk kategorikal
        if 'bar' in selected_charts and chartable_cat_cols:
            story.append(Paragraph('Categorical Distribution Charts', h2_style))
            _max_c = max_cat_cols if max_cat_cols else len(chartable_cat_cols)
            bar_cols = chartable_cat_cols[:_max_c]
            for i in range(0, len(bar_cols), 2):
                batch_c = bar_cols[i:i + 2]
                row_imgs = []
                for col in batch_c:
                    buf = _generate_chart(df, col, 'bar')
                    row_imgs.append(RLImage(buf, width=8 * cm, height=4.5 * cm))
                if len(row_imgs) == 1:
                    buf_single = _generate_chart(df, batch_c[0], 'bar')
                    story.append(RLImage(buf_single, width=14 * cm, height=5.5 * cm))
                else:
                    widths = [8.5 * cm] * len(row_imgs)
                    img_tbl = Table([row_imgs], colWidths=widths)
                    img_tbl.setStyle(TableStyle([
                        ('ALIGN',  (0, 0), (-1, -1), 'CENTER'),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ]))
                    story.append(img_tbl)
                story.append(Spacer(1, 0.3 * cm))

        # Grouped Bar (numerik per kategori)
        if 'grouped_bar' in selected_charts and chartable_cat_cols and num_cols:
            story.append(Paragraph('Grouped Bar Charts', h2_style))
            _max_c = max_cat_cols if max_cat_cols else len(chartable_cat_cols)
            for cat_col in chartable_cat_cols[:min(2, _max_c)]:
                for num_col in num_cols[:2]:
                    buf = _generate_grouped_bar(df, cat_col, num_col)
                    if buf:
                        story.append(Paragraph(
                            f'<b>{num_col}</b> by <b>{cat_col}</b>', body_style
                        ))
                        story.append(RLImage(buf, width=17 * cm, height=5 * cm))
                        story.append(Spacer(1, 0.2 * cm))
            story.append(Spacer(1, 0.3 * cm))

        story.append(Spacer(1, 0.5 * cm))

    # ── SECTION: DATA QUALITY ────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph('5. Data Quality', h1_style))
    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#cccccc')))
    story.append(Spacer(1, 0.2 * cm))

    missing = df.isnull().sum()
    missing_pct = (missing / len(df) * 100).round(2)
    dtypes = df.dtypes.astype(str)

    quality_data = [['Column', 'Data Type', 'Missing Count', 'Missing %', 'Status']]
    for col in df.columns:
        pct = missing_pct[col]
        status = 'OK' if pct == 0 else ('Low (<10%)' if pct < 10 else 'HIGH')
        quality_data.append([
            col[:20],
            str(dtypes[col]),
            str(missing[col]),
            f'{pct}%',
            status,
        ])

    tbl4 = Table(quality_data, colWidths=[5 * cm, 3 * cm, 3 * cm, 3 * cm, 3 * cm])
    tbl4.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0), colors.HexColor('#e74c3c')),
        ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
        ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, -1), 8),
        ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, colors.HexColor('#fff5f5')]),
        ('GRID',          (0, 0), (-1, -1), 0.3, colors.HexColor('#cccccc')),
        ('PADDING',       (0, 0), (-1, -1), 5),
    ]))
    story.append(tbl4)
    story.append(Spacer(1, 0.5 * cm))

    # ── SECTION: TIME SERIES (jika ada kolom tanggal) ────────────────────
    section_num = 6
    if date_cols and num_cols:
        story.append(PageBreak())
        story.append(Paragraph(f'{section_num}. Time Series Analysis', h1_style))
        story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#cccccc')))
        story.append(Spacer(1, 0.2 * cm))

        ts_added = 0
        for date_col in date_cols[:2]:
            val_candidates = [c for c in num_cols if c != date_col]
            if not val_candidates:
                continue
            for val_col in val_candidates[:4]:
                story.append(Paragraph(
                    f'<b>{val_col}</b> vs <b>{date_col}</b>', body_style
                ))
                chart_buf = _generate_timeseries_chart(df, date_col, val_col)
                if chart_buf:
                    img = RLImage(chart_buf, width=17 * cm, height=6 * cm)
                    story.append(img)
                    story.append(Spacer(1, 0.4 * cm))
                    ts_added += 1
            if ts_added > 0:
                break  # cukup 1 date_col dengan semua val_cols

        if ts_added == 0:
            # Fallback: coba paksa parse kolom date lalu generate chart
            story.append(Paragraph(
                'Mencoba deteksi otomatis kolom tanggal...', body_style
            ))
            for col in df.columns:
                try:
                    tmp = df.copy()
                    tmp[col] = pd.to_datetime(tmp[col], errors='coerce')
                    if tmp[col].notna().mean() > 0.5:
                        val_candidates = [c for c in num_cols if c != col]
                        for val_col in val_candidates[:2]:
                            chart_buf = _generate_timeseries_chart(tmp, col, val_col)
                            if chart_buf:
                                story.append(Paragraph(f'<b>{val_col}</b> vs <b>{col}</b>', body_style))
                                story.append(RLImage(chart_buf, width=17 * cm, height=6 * cm))
                                story.append(Spacer(1, 0.4 * cm))
                                ts_added += 1
                        if ts_added > 0:
                            break
                except Exception:
                    continue

        if ts_added == 0:
            story.append(Paragraph(
                'Tidak ada kombinasi kolom tanggal + numerik yang valid untuk time series.',
                body_style
            ))
        story.append(Spacer(1, 0.5 * cm))
        section_num += 1

    # ── SECTION: AUTO INSIGHTS ───────────────────────────────────────────
    if insights:
        story.append(PageBreak())
        story.append(Paragraph(f'{section_num}. Auto Insights', h1_style))
        story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#cccccc')))
        story.append(Spacer(1, 0.2 * cm))

        raw = insights
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = [{'type': 'info', 'title': '', 'message': raw}]
        if not isinstance(raw, list):
            raw = [raw]

        item_label_style = ParagraphStyle(
            'ILabel', parent=styles['Normal'],
            fontSize=8.5, fontName='Helvetica-Bold',
            textColor=colors.HexColor('#1a1a2e'),
            spaceAfter=2, leading=12,
        )
        item_body_style = ParagraphStyle(
            'IBody', parent=styles['Normal'],
            fontSize=8, textColor=colors.HexColor('#444444'),
            spaceAfter=0, leading=13,
        )

        for i, item in enumerate(raw[:20], start=1):
            if isinstance(item, str):
                try:
                    item = ast.literal_eval(item)
                except Exception:
                    item = {'type': 'info', 'title': '', 'message': item}

            title   = item.get('title', '')   if isinstance(item, dict) else ''
            message = item.get('message', '') if isinstance(item, dict) else str(item)
            message = message.replace('....', '').replace('...', '').strip()

            card = []
            if title.strip():
                card.append(Paragraph(f'<b>{i}. {title}</b>', item_label_style))
            card.append(Paragraph(message, item_body_style))
            card.append(Spacer(1, 0.25 * cm))
            story.append(KeepTogether(card))

        story.append(Spacer(1, 0.3 * cm))
        section_num += 1

    # ── SECTION: KESIMPULAN & REKOMENDASI ────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph(f'{section_num}. Kesimpulan & Rekomendasi', h1_style))
    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#cccccc')))
    story.append(Spacer(1, 0.2 * cm))

    conclusion_points = []
    conclusion_points.append(
        f'Dataset terdiri dari {df.shape[0]:,} baris dan {df.shape[1]} kolom, dengan '
        f'tingkat kelengkapan data sebesar {quality_pct}%.'
    )
    if missing_total > 0:
        worst_col = missing_pct.idxmax()
        conclusion_points.append(
            f'Terdapat {missing_total:,} sel dengan nilai kosong. Kolom dengan persentase '
            f'missing value tertinggi adalah <b>{worst_col}</b> ({missing_pct[worst_col]}%). '
            f'Disarankan untuk melakukan penanganan missing value (imputasi atau penghapusan) '
            f'sebelum analisis atau pemodelan lebih lanjut.'
        )
    else:
        conclusion_points.append('Tidak ditemukan nilai kosong pada dataset ini — kualitas data tergolong sangat baik.')

    if num_cols:
        conclusion_points.append(
            f'Terdapat {len(num_cols)} kolom numerik yang dapat digunakan untuk analisis statistik '
            f'lanjutan, seperti korelasi, regresi, atau deteksi outlier.'
        )
    if cat_cols:
        conclusion_points.append(
            f'Terdapat {len(cat_cols)} kolom kategorikal yang dapat digunakan untuk segmentasi '
            f'atau analisis perbandingan antar kelompok.'
        )
    if date_cols:
        conclusion_points.append(
            f'Dataset memiliki {len(date_cols)} kolom bertipe tanggal/waktu sehingga memungkinkan '
            f'dilakukan analisis tren atau deret waktu (time series) lebih lanjut.'
        )
    conclusion_points.append(
        'Rekomendasi langkah selanjutnya: (1) tindak lanjuti temuan pada bagian Auto Insights, '
        '(2) bersihkan/standardisasi data sesuai catatan pada bagian Data Quality, '
        '(3) lakukan analisis lanjutan (statistik inferensial atau machine learning) sesuai '
        'kebutuhan bisnis.'
    )

    for pt in conclusion_points:
        story.append(Paragraph(f'&bull; {pt}', body_style))
    story.append(Spacer(1, 0.4 * cm))

    # ── FOOTER PENUTUP ────────────────────────────────────────────────────
    story.append(HRFlowable(width='100%', thickness=1, color=colors.HexColor('#4F81BD')))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        'Auto EDA Analytics Dashboard &middot; Data Science Programming &middot; Bakti Siregar, M.Sc.',
        label_style
    ))

    doc.multiBuild(story)
    buffer.seek(0)
    return buffer



# ─────────────────────────────────────────────────────────────────────────────
# EXCEL EXPORT
# ─────────────────────────────────────────────────────────────────────────────

def export_excel(df: pd.DataFrame,
                 num_stats: dict = None,
                 cat_stats: dict = None,
                 col_types: dict = None) -> BytesIO:
    """Buat laporan Excel 4-sheet dan kembalikan sebagai BytesIO."""
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        # Sheet 1 – Data
        df.to_excel(writer, sheet_name='Data', index=False)

        # Sheet 2 – Numerical Summary
        num_cols = df.select_dtypes(include='number').columns.tolist()
        if num_cols:
            df[num_cols].describe().round(3).to_excel(
                writer, sheet_name='Numerical Summary'
            )

        # Sheet 3 – Categorical Summary
        cat_cols = df.select_dtypes(include='object').columns.tolist()
        if cat_cols:
            cat_rows = []
            for col in cat_cols:
                vc = df[col].value_counts()
                cat_rows.append({
                    'Column': col,
                    'Unique Values': df[col].nunique(),
                    'Most Frequent': vc.index[0] if len(vc) > 0 else None,
                    'Frequency': vc.iloc[0] if len(vc) > 0 else None,
                })
            pd.DataFrame(cat_rows).to_excel(
                writer, sheet_name='Categorical Summary', index=False
            )

        # Sheet 4 – Data Quality
        missing = df.isnull().sum()
        missing_pct = (missing / len(df) * 100).round(2)
        quality_df = pd.DataFrame({
            'Column': df.columns,
            'Data Type': df.dtypes.astype(str).values,
            'Missing Count': missing.values,
            'Missing %': missing_pct.values,
        })
        quality_df.to_excel(writer, sheet_name='Data Quality', index=False)

    buffer.seek(0)
    return buffer


# ─────────────────────────────────────────────────────────────────────────────
# CSV EXPORT
# ─────────────────────────────────────────────────────────────────────────────

def export_csv(df: pd.DataFrame) -> BytesIO:
    """Kembalikan DataFrame sebagai CSV dalam BytesIO (UTF-8 dengan BOM)."""
    buffer = BytesIO()
    df.to_csv(buffer, index=False, encoding='utf-8-sig')
    buffer.seek(0)
    return buffer
