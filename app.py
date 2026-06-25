"""
app.py – Main Flask Application: Auto EDA Analytics Dashboard
SD-1306 Data Science Programming 
Visualization: Plotly (interactive, lightweight, web-native)
"""
from flask import Flask, render_template, request, Response, redirect, url_for, session
from flask_cors import CORS
import pandas as pd
import numpy as np
import json, math, io, warnings, os
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import plotly.utils
from scipy import stats
warnings.filterwarnings('ignore')

from backend.data_loader        import load_file, get_file_info
from backend.preprocessing      import standardize_nulls, remove_duplicates, fix_dtypes, impute_missing, cap_outliers, auto_clean, drop_empty_cols, diagnose_dataset, custom_clean 
from backend.descriptive_stats  import detect_types, numeric_stats, compute_all_numeric_stats
from backend.categorical_analysis import categorical_stats, compute_all_categorical_stats
from backend.insight_generator  import generate_basic_insights
from backend.time_series        import compute_time_series, detect_date_columns

app = Flask(__name__)
CORS(app)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.secret_key = 'eda_secret_key_2025'
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # disable static file caching

import time as _time
@app.context_processor
def inject_version():
    return {'static_version': str(int(_time.time()))}

_last_df        = None
_last_raw_df    = None
_last_col_types = None
_last_num_stats = None
_last_cat_stats = None

# ── Plotly theme ────────────────────────────────────────────
PLOTLY_LAYOUT = dict(
    paper_bgcolor='rgba(0,0,0,0)',
    plot_bgcolor='rgba(0,0,0,0)',
    font=dict(family='Inter, sans-serif', size=11, color='#374151'),
    margin=dict(l=40, r=20, t=40, b=40),
    colorway=['#2d6a9f','#e07b39','#3a9e6f','#c94040','#7a5ca8',
              '#b5883a','#3090b5','#d65c8a','#4a8c45','#555555'],
    xaxis=dict(gridcolor='#f3f4f6', linecolor='#e5e7eb', zerolinecolor='#e5e7eb'),
    yaxis=dict(gridcolor='#f3f4f6', linecolor='#e5e7eb', zerolinecolor='#e5e7eb'),
    hoverlabel=dict(bgcolor='#1e3a5f', font_color='white', font_size=12),
)

def fig_json(fig):
    """Convert Plotly figure to JSON string."""
    fig.update_layout(**PLOTLY_LAYOUT)
    return json.loads(plotly.utils.PlotlyJSONEncoder().encode(fig))


def clean_numeric(series: pd.Series) -> pd.Series:
    """
    Bersihkan kolom numerik dari format apapun sebelum visualisasi.
    Handles: 'Rp 1.234.567', '$1,234.56', '1.234,56', '188905', dll.
    Returns: pd.Series of float, NaN untuk yang tidak bisa di-parse.
    """
    s = series.astype(str).str.strip()
    # Hapus simbol mata uang dan whitespace
    s = s.str.replace(r'[Rp$€£¥₹\s]', '', regex=True)
    # Deteksi format: pakai titik sebagai pemisah ribuan (e.g. '1.234.567' atau '1.234,56')
    # Jika ada koma setelah titik -> koma adalah desimal (European style)
    european = s.str.match(r'^\d{1,3}(\.\d{3})+(,\d+)?$')
    if european.sum() > len(s) * 0.3:
        # Format European: hapus titik ribuan, ganti koma desimal jadi titik
        s = s.str.replace(r'\.(?=\d{3})', '', regex=True)
        s = s.str.replace(',', '.', regex=False)
    else:
        # Format standard: hapus koma sebagai pemisah ribuan
        s = s.str.replace(',', '', regex=False)
    return pd.to_numeric(s, errors='coerce')


class SafeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):  return int(obj)
        if isinstance(obj, np.floating):
            v = float(obj)
            return None if (math.isnan(v) or math.isinf(v)) else v
        if isinstance(obj, np.bool_):    return bool(obj)
        if isinstance(obj, pd.Timestamp):
            return obj.strftime('%Y-%m-%d %H:%M:%S') if (obj.hour or obj.minute or obj.second) else obj.strftime('%Y-%m-%d')
        if isinstance(obj, np.ndarray):  return obj.tolist()
        import datetime
        if isinstance(obj, (datetime.datetime, datetime.date)): return str(obj)
        return super().default(obj)

def clean_val(obj):
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):  return {k: clean_val(v) for k, v in obj.items()}
    if isinstance(obj, list):  return [clean_val(i) for i in obj]
    return obj

def safe_jsonify(data):
    return Response(json.dumps(clean_val(data), cls=SafeEncoder), mimetype='application/json')


def serialize_preview(df):
    rows = []
    for _, row in df.iterrows():
        r = {}
        for col, val in row.items():
            try:   is_na = pd.isna(val)
            except: is_na = False
            if is_na: r[col] = None
            elif isinstance(val, pd.Timestamp):
                r[col] = val.strftime('%Y-%m-%d %H:%M:%S') if (val.hour or val.minute or val.second) else val.strftime('%Y-%m-%d')
            elif isinstance(val, np.integer): r[col] = int(val)
            elif isinstance(val, np.floating):
                v = float(val); r[col] = None if (math.isnan(v) or math.isinf(v)) else round(v, 4)
            else: r[col] = val
        rows.append(r)
    return rows


def detect_time_series_cols(df):
    ts_cols = []
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            ts_cols.append({'col': col, 'reason': 'datetime type'})
        elif df[col].dtype == object:
            sample = df[col].dropna().head(20).astype(str)
            date_like = sample.str.match(r'^\d{4}[-/]\d{2}[-/]\d{2}').mean()
            if date_like > 0.5:
                ts_cols.append({'col': col, 'reason': 'date-like strings'})
    return ts_cols


def build_cleaning_table(log_all):
    step_map = {
        '[1] STANDARDIZE NULLS': {'step': 1, 'name': 'Standardize Nulls', 'color': 'blue'},
        '[2] REMOVE DUPLICATES': {'step': 2, 'name': 'Remove Duplicates', 'color': 'purple'},
        '[3] FIX DATA TYPES':    {'step': 3, 'name': 'Fix Data Types',    'color': 'teal'},
        '[4] IMPUTE MISSING VALUES': {'step': 4, 'name': 'Impute Missing', 'color': 'orange'},
        '[5] CAP OUTLIERS (IQR)': {'step': 5, 'name': 'Cap Outliers (IQR)', 'color': 'red'},
    }
    rows = []
    current_step = None
    current_meta = {}
    for entry in log_all:
        if entry in step_map:
            current_step = entry
            current_meta = step_map[entry]
        else:
            rows.append({
                'step': current_meta.get('step', 0),
                'step_name': current_meta.get('name', ''),
                'color': current_meta.get('color', 'gray'),
                'detail': entry,
                'status': 'ok' if ('No ' in entry or 'already' in entry.lower() or '0 ' in entry) else 'action',
            })
    return rows


# ══════════════════════════════════════════════════════════════
# PLOTLY VISUALIZATION FUNCTIONS — REBUILT TOTAL
# Semua chart: clean data → warna auto-cycle → readable
# ══════════════════════════════════════════════════════════════

# ── Palette 24 warna, auto-cycle, tidak pernah hitam ─────────
PALETTE = [
    '#2d6a9f','#e07b39','#3a9e6f','#c94040','#7a5ca8',
    '#b5883a','#3090b5','#d65c8a','#4a8c45','#e6994d',
    '#5b9bd5','#70ad47','#ff7c80','#00b0d8','#ffc000',
    '#7030a0','#00b050','#ff0000','#0070c0','#ff6600',
    '#339966','#993366','#cc3300','#006699',
]

def _palette(n):
    """Return list of n colors, cycling PALETTE if needed."""
    return [PALETTE[i % len(PALETTE)] for i in range(n)]

def _is_id_like(df, col):
    """
    Deteksi kolom numerik yang sebenarnya identifier (ID/index/key),
    bukan measure yang bermakna untuk dirata-rata.
    """
    name = col.lower()
    if any(k in name for k in ['id', 'index', 'key', 'nomor', 'no_', '_no', 'kode']):
        return True
    nunique = df[col].nunique(dropna=True)
    if nunique > 0 and nunique / max(len(df), 1) > 0.9:
        return True
    return False


def _smart_cat_col(df, col, top_n=15):
    """
    Untuk kolom kategorik: skip jika ID-like (unique ratio > 85%).
    Return (filtered_vc, is_id_col).
    """
    vc = df[col].value_counts()
    unique_ratio = len(vc) / max(len(df), 1)
    if unique_ratio > 0.85 and len(vc) > 20:
        return vc.head(top_n), True   # ID-like tapi tetap tampil top N
    return vc.head(top_n), False

def _is_id_like(df, col):
    """
    Deteksi kolom numerik yang sebenarnya identifier (ID/index/key),
    bukan measure yang bermakna untuk dirata-rata.
    """
    name = col.lower()
    if any(k in name for k in ['id', 'index', 'key', 'nomor', 'no_', '_no', 'kode']):
        return True
    nunique = df[col].nunique(dropna=True)
    if nunique > 0 and nunique / max(len(df), 1) > 0.9:
        return True
    return False
    

def _fmt_num(v):
    """Format angka besar jadi lebih readable: 1500000 → 1.5M"""
    try:
        v = float(v)
        if abs(v) >= 1_000_000:   return f'{v/1_000_000:.2f}M'
        if abs(v) >= 1_000:       return f'{v/1_000:.1f}K'
        if v == int(v):           return str(int(v))
        return f'{v:.2f}'
    except:
        return str(v)


# ── a) NUMERICAL VISUALIZATION ──────────────────────────────

def make_histogram(df, col):
    """Histogram dengan distribusi & statistik ringkas di subtitle."""
    data = clean_numeric(df[col]).dropna()
    if len(data) == 0:
        return None
    mean_v = data.mean()
    std_v  = data.std()
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=data, nbinsx=25,
        marker=dict(color=PALETTE[0], line=dict(color='white', width=0.8)),
        opacity=0.88, name=col,
        hovertemplate='Nilai: %{x}<br>Frekuensi: %{y}<extra></extra>'
    ))
    fig.add_vline(x=mean_v, line_dash='dash', line_color=PALETTE[3], line_width=2,
                  annotation_text=f'Mean: {_fmt_num(mean_v)}',
                  annotation_position='top right',
                  annotation_font=dict(size=10, color=PALETTE[3]))
    fig.update_layout(
        title=dict(text=f'Histogram — <b>{col}</b>', font=dict(size=14)),
        xaxis_title=col,
        yaxis_title='Frekuensi',
        bargap=0.05,
        annotations=[dict(
            text=f'n={len(data):,}  |  Mean={_fmt_num(mean_v)}  |  Std={_fmt_num(std_v)}',
            xref='paper', yref='paper', x=0, y=-0.15,
            showarrow=False, font=dict(size=10, color='#6b7280')
        )]
    )
    return fig_json(fig)


def make_boxplot(df, col):
    """Boxplot horizontal dengan label Q1/Median/Q3 yang jelas."""
    data = clean_numeric(df[col]).dropna()
    if len(data) == 0:
        return None
    q1, med, q3 = data.quantile(0.25), data.quantile(0.5), data.quantile(0.75)
    fig = go.Figure()
    fig.add_trace(go.Box(
        x=data, name=col,
        marker=dict(color=PALETTE[0], size=4, opacity=0.5),
        line=dict(color=PALETTE[0], width=2),
        fillcolor=f'rgba(45,106,159,0.15)',
        boxmean=True, boxpoints='outliers',
        orientation='h',
        hovertemplate='Nilai: %{x}<extra></extra>'
    ))
    fig.update_layout(
        title=dict(text=f'Boxplot — <b>{col}</b>', font=dict(size=14)),
        xaxis_title=col,
        yaxis_showticklabels=False,
        annotations=[dict(
            text=f'Q1={_fmt_num(q1)}  |  Median={_fmt_num(med)}  |  Q3={_fmt_num(q3)}  |  IQR={_fmt_num(q3-q1)}',
            xref='paper', yref='paper', x=0, y=-0.18,
            showarrow=False, font=dict(size=10, color='#6b7280')
        )]
    )
    return fig_json(fig)


def make_violin(df, col):
    """Violin Plot — distribusi bentuk kurva tanpa box."""
    data = clean_numeric(df[col]).dropna()
    if len(data) < 3:
        return None
    q1, med, q3 = data.quantile(0.25), data.quantile(0.5), data.quantile(0.75)
    fig = go.Figure()
    fig.add_trace(go.Violin(
        y=data,
        name=col,
        meanline=dict(visible=True, color=PALETTE[3], width=2),
        fillcolor='rgba(122,92,168,0.25)',
        line=dict(color=PALETTE[4], width=2),
        points='outliers',
        marker=dict(color=PALETTE[4], size=4, opacity=0.5),
        hovertemplate=f'{col}: %{{y}}<extra></extra>'
    ))
    fig.update_layout(
        title=dict(text=f'Violin Plot — <b>{col}</b>', font=dict(size=14)),
        yaxis_title=col,
        xaxis_showticklabels=False,
        showlegend=False,
        annotations=[dict(
            text=f'Q1={_fmt_num(q1)}  |  Median={_fmt_num(med)}  |  Q3={_fmt_num(q3)}  |  IQR={_fmt_num(q3-q1)}',
            xref='paper', yref='paper', x=0, y=-0.15,
            showarrow=False, font=dict(size=10, color='#6b7280')
        )]
    )
    return fig_json(fig)


def make_density(df, col):
    """Density Plot menggunakan KDE (Kernel Density Estimation)."""
    data = clean_numeric(df[col]).dropna()
    if len(data) < 3:
        return None

    from scipy.stats import gaussian_kde
    import numpy as np

    kde = gaussian_kde(data, bw_method='scott')
    x_range = np.linspace(data.min(), data.max(), 300)
    y_density = kde(x_range)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x_range,
        y=y_density,
        mode='lines',
        fill='tozeroy',
        fillcolor='rgba(58,158,111,0.2)',
        line=dict(color=PALETTE[2], width=2),
        name='Density',
        hovertemplate='Nilai: %{x:.2f}<br>Density: %{y:.4f}<extra></extra>'
    ))

    mean_val = data.mean()
    fig.add_vline(
        x=mean_val,
        line=dict(color=PALETTE[3], width=2, dash='dash'),
        annotation_text=f'Mean: {mean_val:.2f}',
        annotation_position='top right',
        annotation_font=dict(size=10)
    )

    fig.update_layout(
        title=dict(text=f'Density Plot — <b>{col}</b>', font=dict(size=14)),
        xaxis_title=col,
        yaxis_title='Density',
        showlegend=False,
        annotations=[dict(
            text='Tinggi kurva = kepadatan data pada nilai tersebut',
            xref='paper', yref='paper', x=0, y=-0.18,
            showarrow=False, font=dict(size=10, color='#6b7280')
        )]
    )
    return fig_json(fig)


def make_qqplot(df, col):
    """QQ Plot: titik data vs garis normal ideal."""
    data = clean_numeric(df[col]).dropna()
    if len(data) < 4:
        return None
    (osm, osr), (slope, intercept, r) = stats.probplot(data, dist='norm')
    normal = 'Normal' if abs(float(data.skew())) < 0.5 else 'Tidak Normal'
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=list(osm), y=list(osr), mode='markers',
        marker=dict(color=PALETTE[0], size=5, opacity=0.65,
                    line=dict(color='white', width=0.5)),
        name='Data',
        hovertemplate='Theoretical: %{x:.2f}<br>Sample: %{y:.2f}<extra></extra>'
    ))
    lx = [float(min(osm)), float(max(osm))]
    fig.add_trace(go.Scatter(
        x=lx, y=[slope * v + intercept for v in lx],
        mode='lines', line=dict(color=PALETTE[3], width=2, dash='dash'),
        name='Garis Normal'
    ))
    fig.update_layout(
        title=dict(text=f'QQ Plot — <b>{col}</b>', font=dict(size=14)),
        xaxis_title='Theoretical Quantiles (Normal)',
        yaxis_title='Sample Quantiles',
        legend=dict(orientation='h', y=1.08, x=0),
        annotations=[dict(
            text=f'Distribusi: <b>{normal}</b>  |  R²={r**2:.3f}  (semakin dekat ke garis = semakin normal)',
            xref='paper', yref='paper', x=0, y=-0.18,
            showarrow=False, font=dict(size=10, color='#6b7280')
        )]
    )
    return fig_json(fig)


def make_box_violin(df, col):
    """Box + Violin combined — Violin dengan boxplot built-in di tengah (kompatibel semua versi Plotly)."""
    data = clean_numeric(df[col]).dropna()
    if len(data) < 3:
        return None
    q1, med, q3 = data.quantile(0.25), data.quantile(0.5), data.quantile(0.75)
    fig = go.Figure()
    fig.add_trace(go.Violin(
        y=data,
        name=col,
        box=dict(visible=True, fillcolor='rgba(45,106,159,0.3)', line=dict(color=PALETTE[0], width=2)),
        meanline=dict(visible=True, color=PALETTE[3], width=2),
        fillcolor='rgba(122,92,168,0.18)',
        line=dict(color=PALETTE[4], width=2),
        points='outliers',
        marker=dict(color=PALETTE[0], size=4, opacity=0.5),
        hovertemplate=f'{col}: %{{y}}<extra></extra>'
    ))
    fig.update_layout(
        title=dict(text=f'Box + Violin — <b>{col}</b>', font=dict(size=14)),
        yaxis_title=col,
        xaxis_showticklabels=False,
        showlegend=False,
        annotations=[dict(
            text=f'Q1={_fmt_num(q1)}  |  Median={_fmt_num(med)}  |  Q3={_fmt_num(q3)}  |  IQR={_fmt_num(q3-q1)}',
            xref='paper', yref='paper', x=0, y=-0.15,
            showarrow=False, font=dict(size=10, color='#6b7280')
        )]
    )
    return fig_json(fig)

# ── b) CATEGORICAL VISUALIZATION ────────────────────────────

def make_barchart(df, col):
    """Bar Chart vertikal, top 15 kategori, label count di atas bar."""
    vc, is_id = _smart_cat_col(df, col, top_n=15)
    n = len(vc)
    colors = _palette(n)
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[str(v)[:20] for v in vc.index],
        y=vc.values,
        marker=dict(color=colors, line=dict(color='white', width=0.8)),
        text=[f'{v:,}' for v in vc.values],
        textposition='outside',
        hovertemplate='%{x}<br>Count: %{y:,}<extra></extra>'
    ))
    note = ' (Top 15 dari banyak kategori — kolom ini mungkin ID)' if is_id else ''
    fig.update_layout(
        title=dict(text=f'Bar Chart — <b>{col}</b>{note}', font=dict(size=14)),
        xaxis=dict(title=col, tickangle=-35 if n > 6 else 0),
        yaxis=dict(title='Jumlah', range=[0, max(vc.values) * 1.15]),
        bargap=0.25,
    )
    return fig_json(fig)


def make_piechart(df, col):
    """Donut Chart top 8 kategori, legenda di kanan."""
    vc, _ = _smart_cat_col(df, col, top_n=8)
    n = len(vc)
    labels = [str(v)[:20] for v in vc.index]
    fig = go.Figure()
    fig.add_trace(go.Pie(
        labels=labels, values=vc.values,
        marker=dict(colors=_palette(n), line=dict(color='white', width=2)),
        hole=0.4,
        textinfo='label+percent',
        textfont=dict(size=11),
        hovertemplate='%{label}<br>Count: %{value:,}<br>%{percent}<extra></extra>',
        pull=[0.03] * n,
    ))
    fig.update_layout(
        title=dict(text=f'Pie Chart — <b>{col}</b> (Top {n})', font=dict(size=14)),
        legend=dict(orientation='v', x=1.02, y=0.5),
        annotations=[dict(text=f'Total<br>{len(df[col].dropna()):,}',
                          x=0.5, y=0.5, font=dict(size=12, color='#374151'),
                          showarrow=False)]
    )
    return fig_json(fig)


def make_countplot(df, col):
    """Count Plot vertikal — seperti seaborn default."""
    vc, is_id = _smart_cat_col(df, col, top_n=15)
    n = len(vc)
    colors = _palette(n)
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[str(v)[:25] for v in vc.index],
        y=vc.values,
        marker=dict(color=colors, line=dict(color='white', width=0.8)),
        text=[f'{v:,}' for v in vc.values],
        textposition='outside',
        hovertemplate='%{x}<br>Count: %{y:,}<extra></extra>'
    ))
    fig.update_layout(
        title=dict(text=f'Count Plot — <b>{col}</b>', font=dict(size=14)),
        xaxis=dict(title=col),
        yaxis=dict(title='Jumlah', range=[0, max(vc.values) * 1.2]),
        bargap=0.3,
        height=max(300, n * 32 + 100),
    )
    return fig_json(fig)

def make_pareto(df, col):
    """Pareto Chart: bar frekuensi + garis kumulatif %, garis 80%."""
    vc, _ = _smart_cat_col(df, col, top_n=15)
    n = len(vc)
    labels = [str(v)[:20] for v in vc.index]
    cumulative = (vc.cumsum() / vc.sum() * 100).values
    fig = make_subplots(specs=[[{'secondary_y': True}]])
    fig.add_trace(go.Bar(
        x=labels, y=vc.values,
        marker=dict(color=_palette(n), line=dict(color='white', width=0.8)),
        name='Count',
        text=[f'{v:,}' for v in vc.values],
        textposition='outside',
        hovertemplate='%{x}<br>Count: %{y:,}<extra></extra>'
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=labels, y=cumulative,
        mode='lines+markers',
        line=dict(color=PALETTE[3], width=2.5),
        marker=dict(size=6, color=PALETTE[3], line=dict(color='white', width=1)),
        name='Kumulatif %',
        hovertemplate='%{x}<br>Kumulatif: %{y:.1f}%<extra></extra>'
    ), secondary_y=True)
    fig.add_hline(y=80, line_dash='dot', line_color='#9ca3af', line_width=1.5,
                  secondary_y=True,
                  annotation_text='80%', annotation_position='right',
                  annotation_font=dict(size=10, color='#9ca3af'))
    fig.update_layout(
        title=dict(text=f'Pareto Chart — <b>{col}</b>', font=dict(size=14)),
        xaxis=dict(tickangle=-35 if n > 6 else 0),
        legend=dict(orientation='h', y=1.08, x=0),
        bargap=0.25,
    )
    fig.update_yaxes(title_text='Jumlah', secondary_y=False)
    fig.update_yaxes(title_text='Kumulatif (%)', range=[0, 112], secondary_y=True)
    return fig_json(fig)


# ── c) BIVARIATE & MULTIVARIATE ─────────────────────────────

def make_scatter(df, cx, cy):
    """Scatter Plot dengan warna gradient density & trendline opsional."""
    x = clean_numeric(df[cx])
    y = clean_numeric(df[cy])
    mask = x.notna() & y.notna()
    xv, yv = x[mask].values, y[mask].values
    if len(xv) == 0:
        return None
    # Hitung korelasi
    r_val = float(np.corrcoef(xv, yv)[0, 1]) if len(xv) > 1 else 0
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=xv, y=yv, mode='markers',
        marker=dict(
            color=yv, colorscale='Blues', size=6, opacity=0.65,
            colorbar=dict(title=cy, thickness=10),
            line=dict(color='white', width=0.4)
        ),
        hovertemplate=f'{cx}: %{{x}}<br>{cy}: %{{y}}<extra></extra>'
    ))
    fig.update_layout(
        title=dict(text=f'Scatter Plot — <b>{cx}</b> vs <b>{cy}</b>', font=dict(size=14)),
        xaxis_title=cx, yaxis_title=cy,
        annotations=[dict(
            text=f'Korelasi Pearson r = {r_val:.3f}',
            xref='paper', yref='paper', x=0, y=-0.15,
            showarrow=False, font=dict(size=10, color='#6b7280')
        )]
    )
    return fig_json(fig)


def make_heatmap(df, num_cols):
    """Correlation Heatmap dengan annotasi nilai r dan interpretasi warna."""
    cols = [c for c in num_cols if len(clean_numeric(df[c]).dropna()) > 1][:12]
    if len(cols) < 2:
        return None
    clean_df = pd.concat([clean_numeric(df[c]).rename(c) for c in cols], axis=1)
    corr = clean_df.corr().round(2)
    fig = go.Figure(go.Heatmap(
        z=corr.values, x=cols, y=cols,
        colorscale='RdBu_r', zmid=0, zmin=-1, zmax=1,
        text=corr.values,
        texttemplate='%{text:.2f}',
        textfont=dict(size=10),
        hovertemplate='%{y} × %{x}<br>r = %{z:.3f}<extra></extra>',
        colorbar=dict(title='r', thickness=12, len=0.8)
    ))
    h = max(350, len(cols) * 42 + 100)
    fig.update_layout(
        title=dict(text='Correlation Heatmap — Semua Variabel Numerik', font=dict(size=14)),
        xaxis=dict(tickangle=-35),
        height=h,
        annotations=[dict(
            text='Merah = korelasi positif | Biru = korelasi negatif | Nilai mendekati ±1 = korelasi kuat',
            xref='paper', yref='paper', x=0, y=-0.12,
            showarrow=False, font=dict(size=10, color='#6b7280')
        )]
    )
    return fig_json(fig)


def make_pairplot(df, num_cols):
    """Pair Plot bersih: tiap cell punya label kolom di axis, tidak tumpang tindih."""
    cols = [c for c in num_cols if len(clean_numeric(df[c]).dropna()) > 1][:4]
    if len(cols) < 2:
        return None
    data = pd.concat([clean_numeric(df[c]).rename(c) for c in cols], axis=1).dropna()
    if len(data) == 0:
        return None

    n = len(cols)
    sample = data if len(data) <= 300 else data.sample(300, random_state=42)

    def short(name, maxlen=10):
        return name if len(name) <= maxlen else name[:maxlen] + '…'

    short_cols = [short(c) for c in cols]

    cell = 200
    fig = make_subplots(
        rows=n, cols=n,
        shared_xaxes=False, shared_yaxes=False,
        horizontal_spacing=0.06,
        vertical_spacing=0.08,
    )

    for i in range(n):
        for j in range(n):
            clr = PALETTE[i % len(PALETTE)]
            if i == j:
                fig.add_trace(go.Histogram(
                    x=data[cols[i]],
                    marker=dict(color=clr, opacity=0.85, line=dict(color='white', width=0.5)),
                    showlegend=False, nbinsx=18,
                    hovertemplate=f'%{{x}}<br>Count: %{{y}}<extra>{short_cols[i]}</extra>'
                ), row=i+1, col=j+1)
            else:
                fig.add_trace(go.Scatter(
                    x=sample[cols[j]], y=sample[cols[i]], mode='markers',
                    marker=dict(color=clr, size=4, opacity=0.5,
                                line=dict(color='rgba(255,255,255,0.3)', width=0.5)),
                    showlegend=False,
                    hovertemplate=f'%{{x:.2f}}, %{{y:.2f}}<extra></extra>'
                ), row=i+1, col=j+1)

            # Set axis titles only on edges
            ax_x = f'x{i*n+j+1}' if (i*n+j+1) > 1 else 'x'
            ax_y = f'y{i*n+j+1}' if (i*n+j+1) > 1 else 'y'

            # Bottom row: show x label
            if i == n - 1:
                fig.update_xaxes(
                    title_text=short_cols[j],
                    title_font=dict(size=10, color='#aaaaaa'),
                    row=i+1, col=j+1
                )
            # Left col: show y label
            if j == 0:
                fig.update_yaxes(
                    title_text=short_cols[i],
                    title_font=dict(size=10, color='#aaaaaa'),
                    row=i+1, col=j+1
                )

    # Hide all tick labels to keep it clean
    fig.update_xaxes(
        showticklabels=False,
        showgrid=True, gridcolor='rgba(255,255,255,0.06)',
        zeroline=False, tickfont=dict(size=8)
    )
    fig.update_yaxes(
        showticklabels=False,
        showgrid=True, gridcolor='rgba(255,255,255,0.06)',
        zeroline=False, tickfont=dict(size=8)
    )

    fig.update_layout(
        title=dict(
            text='Pair Plot',
            font=dict(size=14, color='#e0e0e0'),
            x=0.5, xanchor='center'
        ),
        height=n * cell + 60,
        showlegend=False,
        margin=dict(l=70, r=20, t=55, b=60),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
    )

    return fig_json(fig)

def make_regression(df, cx, cy):
    """Regression Plot: titik data + garis regresi linear + R² dan persamaan."""
    x = clean_numeric(df[cx])
    y = clean_numeric(df[cy])
    mask = x.notna() & y.notna()
    xv, yv = x[mask].values, y[mask].values
    if len(xv) < 2:
        return None
    m, b, r, p, _ = stats.linregress(xv, yv)
    xs = np.linspace(xv.min(), xv.max(), 300)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=xv, y=yv, mode='markers',
        marker=dict(color=PALETTE[0], size=6, opacity=0.55,
                    line=dict(color='white', width=0.5)),
        name='Data',
        hovertemplate=f'{cx}: %{{x}}<br>{cy}: %{{y}}<extra></extra>'
    ))
    fig.add_trace(go.Scatter(
        x=xs, y=m * xs + b, mode='lines',
        line=dict(color=PALETTE[3], width=2.5),
        name=f'Regresi (R²={r**2:.3f})'
    ))
    # Confidence band sederhana (±1 std residual)
    residuals = yv - (m * xv + b)
    std_res = residuals.std()
    fig.add_trace(go.Scatter(
        x=np.concatenate([xs, xs[::-1]]),
        y=np.concatenate([m*xs+b+std_res, (m*xs+b-std_res)[::-1]]),
        fill='toself', fillcolor='rgba(201,64,64,0.1)',
        line=dict(color='rgba(0,0,0,0)'), name='±1 Std Residual',
        hoverinfo='skip'
    ))
    fig.update_layout(
        title=dict(text=f'Regression Plot — <b>{cx}</b> vs <b>{cy}</b>', font=dict(size=14)),
        xaxis_title=cx, yaxis_title=cy,
        legend=dict(orientation='h', y=1.08, x=0),
        annotations=[dict(
            text=f'y = {m:.4f}x + {b:.4f}  |  R² = {r**2:.4f}  |  p-value = {p:.4f}',
            xref='paper', yref='paper', x=0, y=-0.15,
            showarrow=False, font=dict(size=10, color='#6b7280')
        )]
    )
    return fig_json(fig)


def make_bubble(df, cx, cy, cs):
    """Bubble Chart: x, y = numerik, ukuran bubble = kolom ke-3."""
    x = clean_numeric(df[cx])
    y = clean_numeric(df[cy])
    s = clean_numeric(df[cs])
    mask = x.notna() & y.notna() & s.notna()
    xv, yv, sv = x[mask].values, y[mask].values, s[mask].values
    if len(xv) == 0:
        return None
    sv_norm = (sv - sv.min()) / ((sv.max() - sv.min()) + 1e-9) * 45 + 6
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=xv, y=yv, mode='markers',
        marker=dict(
            size=sv_norm,
            color=sv,
            colorscale='Teal',
            opacity=0.65,
            colorbar=dict(title=cs, thickness=12),
            line=dict(color='white', width=0.8)
        ),
        text=[f'{cs}: {_fmt_num(v)}' for v in sv],
        hovertemplate=f'{cx}: %{{x}}<br>{cy}: %{{y}}<br>%{{text}}<extra></extra>'
    ))
    fig.update_layout(
        title=dict(text=f'Bubble Chart — <b>{cx}</b> vs <b>{cy}</b> (ukuran: {cs})', font=dict(size=14)),
        xaxis_title=cx, yaxis_title=cy,
        annotations=[dict(
            text=f'Ukuran bubble merepresentasikan nilai {cs}',
            xref='paper', yref='paper', x=0, y=-0.15,
            showarrow=False, font=dict(size=10, color='#6b7280')
        )]
    )
    return fig_json(fig)


# ── d) CATEGORICAL vs NUMERICAL ─────────────────────────────

def make_box_violin_by_cat(df, nc, cc):
    """Box + Violin combined per kategori."""
    cats = df[cc].value_counts().head(8).index.tolist()
    if not cats:
        return None
    fig = go.Figure()
    for i, cat in enumerate(cats):
        data = clean_numeric(df[df[cc] == cat][nc]).dropna()
        if len(data) < 3:
            continue
        c = PALETTE[i % len(PALETTE)]
        rgb = f'{int(c[1:3],16)},{int(c[3:5],16)},{int(c[5:7],16)}'
        # Violin dengan box built-in (kompatibel semua versi Plotly, tanpa side=)
        fig.add_trace(go.Violin(
            y=data, name=str(cat)[:20],
            box=dict(visible=True, fillcolor=f'rgba({rgb},0.3)', line=dict(color=c, width=1.5)),
            meanline=dict(visible=True, color=c, width=1.5),
            fillcolor=f'rgba({rgb},0.2)',
            line=dict(color=c, width=1.5),
            points='outliers',
            marker=dict(size=3, opacity=0.5, color=c),
            hovertemplate=f'{cc}: {cat}<br>{nc}: %{{y}}<extra></extra>'
        ))
    fig.update_layout(
        title=dict(text=f'Box + Violin — <b>{nc}</b> per <b>{cc}</b>', font=dict(size=14)),
        yaxis_title=nc, xaxis_title=cc,
        violingap=0, violinmode='overlay',
        legend_title=cc,
        annotations=[dict(
            text='Violin = distribusi data | Boxplot = IQR & outlier',
            xref='paper', yref='paper', x=0, y=-0.15,
            showarrow=False, font=dict(size=10, color='#6b7280')
        )]
    )
    return fig_json(fig)


def make_grouped_bar(df, nc, cc):
    """Grouped Bar Chart: mean nilai numerik per kategori, terurut."""
    cats = df[cc].value_counts().head(12).index.tolist()
    if not cats:
        return None
    means = [float(clean_numeric(df[df[cc] == c][nc]).mean()) for c in cats]
    raw_stds = [clean_numeric(df[df[cc] == c][nc]).std() for c in cats]
    stds = [float(s) if (s == s and s is not None) else 0.0 for s in raw_stds]
    # Sort descending
    sorted_pairs = sorted(zip(means, stds, cats), reverse=True)
    means_s  = [p[0] for p in sorted_pairs]
    stds_s   = [p[1] for p in sorted_pairs]
    cats_s   = [str(p[2])[:20] for p in sorted_pairs]
    n = len(cats_s)
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=cats_s, y=means_s,
        marker=dict(color=_palette(n), line=dict(color='white', width=0.8)),
        error_y=dict(type='data', array=stds_s, visible=True,
                     color='rgba(0,0,0,0.3)', thickness=1.5, width=4),
        text=[_fmt_num(m) for m in means_s],
        textposition='outside',
        hovertemplate='%{x}<br>Mean: %{y:.2f}<extra></extra>'
    ))
    fig.update_layout(
        title=dict(text=f'Grouped Bar — Mean <b>{nc}</b> per <b>{cc}</b>', font=dict(size=14)),
        xaxis=dict(title=cc, tickangle=-35 if n > 5 else 0),
        yaxis=dict(title=f'Mean {nc}', range=[0, max(means_s) * 1.2 if means_s else 1]),
        bargap=0.3,
        annotations=[dict(
            text='Bar diurutkan dari nilai tertinggi | Error bar = Std Deviasi',
            xref='paper', yref='paper', x=0, y=-0.18,
            showarrow=False, font=dict(size=10, color='#6b7280')
        )]
    )
    return fig_json(fig)


def make_strip(df, nc, cc):
    """Strip Plot: setiap titik = 1 data, jitter agar tidak overlap."""
    cats = df[cc].value_counts().head(8).index.tolist()
    if not cats:
        return None
    np.random.seed(42)
    fig = go.Figure()
    for i, cat in enumerate(cats):
        vals = clean_numeric(df[df[cc] == cat][nc]).dropna().values
        if len(vals) == 0:
            continue
        jitter = np.random.uniform(-0.25, 0.25, size=len(vals))
        c = PALETTE[i % len(PALETTE)]
        fig.add_trace(go.Scatter(
            x=[i + j for j in jitter], y=vals,
            mode='markers', name=str(cat)[:20],
            marker=dict(color=c, size=5, opacity=0.55,
                        line=dict(color='white', width=0.4)),
            hovertemplate=f'{cc}: {cat}<br>{nc}: %{{y}}<extra></extra>'
        ))
        # Tambah garis median per kategori
        med = float(np.median(vals))
        fig.add_shape(type='line',
                      x0=i - 0.3, x1=i + 0.3, y0=med, y1=med,
                      line=dict(color=c, width=2.5))
    fig.update_layout(
        title=dict(text=f'Strip Plot — <b>{nc}</b> per <b>{cc}</b>', font=dict(size=14)),
        yaxis_title=nc,
        xaxis=dict(
            title=cc,
            tickmode='array',
            tickvals=list(range(len(cats))),
            ticktext=[str(c)[:15] for c in cats]
        ),
        legend_title=cc,
        annotations=[dict(
            text='Setiap titik = 1 data | Garis horizontal = Median per kategori',
            xref='paper', yref='paper', x=0, y=-0.15,
            showarrow=False, font=dict(size=10, color='#6b7280')
        )]
    )
    return fig_json(fig)


# ── Routes ────────────────────────────────────────────────────
@app.route('/')
def landing():
    return render_template('landing.html')

@app.route('/app')
def index():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    return render_template('index.html')

@app.route('/upload-page')
def upload_page():
    return render_template('upload.html')

@app.route('/report')
def report_page():
    return render_template('report.html')


@app.route('/upload', methods=['POST'])
def upload():
    global _last_df, _last_raw_df, _last_col_types, _last_num_stats, _last_cat_stats
    if 'file' not in request.files:
        return safe_jsonify({'error': 'No file uploaded'})
    file = request.files['file']
    if not file.filename:
        return safe_jsonify({'error': 'No file selected'})
    filename = file.filename
    try:
        df = load_file(file, filename)
        original_rows = len(df)
        original_cols = len(df.columns)
        original_missing = int(df.isna().sum().sum())

        # Simpan file asli (raw) ke folder data/raw/
        raw_dir = os.path.join(os.path.dirname(__file__), 'data', 'raw')
        os.makedirs(raw_dir, exist_ok=True)
        raw_save_path = os.path.join(raw_dir, filename)
        ext = filename.rsplit('.', 1)[-1].lower()
        if ext in ['xlsx', 'xls']:
            df.to_excel(raw_save_path, index=False)
        else:
            df.to_csv(raw_save_path, index=False)

        raw_col_types = detect_types(df)
        raw_num_cols = [c for c,t in raw_col_types.items() if t=='numeric']
        raw_cat_cols = [c for c,t in raw_col_types.items() if t=='categorical']
        raw_preview = serialize_preview(df.head(20))
        _last_raw_df = df.copy()

        # Cek pilihan mode cleaning dari form
        clean_mode = request.form.get('clean_mode', 'auto')
        if clean_mode == 'auto':
            df, cleaning_log = auto_clean(df)
        elif clean_mode == 'custom':
            # Custom cleaning — ambil fitur yang dipilih dari form
            features = {
                'remove_duplicates': request.form.get('feat_remove_duplicates') == '1',
                'impute_missing':    request.form.get('feat_impute_missing') == '1',
                'fix_dtypes':        request.form.get('feat_fix_dtypes') == '1',
                'cap_outliers':      request.form.get('feat_cap_outliers') == '1',
                'drop_empty_cols':   request.form.get('feat_drop_empty_cols') == '1',
            }
            df, cleaning_log = custom_clean(df, features)
        else:
            # Raw mode
            cleaning_log = ['[INFO] Auto cleaning dilewati — data digunakan apa adanya (raw mode)']
        cleaning_table = build_cleaning_table(cleaning_log)

        col_types = detect_types(df)
        # Auto-cast kolom yang sebenarnya numerik tapi masih tersimpan sbg string
        for _col in list(df.columns):
            if col_types.get(_col) == 'categorical':
                _try = pd.to_numeric(df[_col], errors='coerce')
                if _try.notna().mean() > 0.6:
                    df[_col] = _try
                    col_types[_col] = 'numeric'
        num_stats = compute_all_numeric_stats(df, col_types)
        cat_stats = compute_all_categorical_stats(df, col_types)

        _last_df        = df.copy()
        _last_df._eda_filename = filename
        _last_col_types = col_types.copy()
        _last_num_stats = num_stats.copy()
        _last_cat_stats = cat_stats.copy()

        total_rows = len(df)
        missing_cells = int(df.isna().sum().sum())
        total_cells   = total_rows * len(df.columns)
        quality_pct   = round((1 - missing_cells / max(total_cells, 1)) * 100, 1)
        preview       = serialize_preview(df.head(20))

        ts_cols = detect_time_series_cols(df)

        col_quality = []
        for col in df.columns:
            miss   = int(df[col].isna().sum())
            unique = int(df[col].nunique(dropna=True))
            col_quality.append({
                'column': col, 'type': col_types.get(col, 'categorical'),
                'count': total_rows, 'missing': miss,
                'missing_pct': round((miss / max(total_rows, 1)) * 100, 2),
                'unique': unique,
                'unique_pct': round((unique / max(total_rows, 1)) * 100, 2),
            })

        insights = generate_basic_insights(df, col_types, num_stats, cat_stats)

        return safe_jsonify({
            'success': True, 'filename': filename,
            'original_rows': original_rows, 'original_cols': original_cols,
            'original_missing': original_missing,
            'raw_num_cols': raw_num_cols, 'raw_cat_cols': raw_cat_cols,
            'raw_preview': raw_preview,
            'total_rows': total_rows,
            'total_cols': len(df.columns), 'columns': list(df.columns),
            'col_types': col_types, 'missing_cells': missing_cells,
            'quality_pct': quality_pct, 'cleaning_log': cleaning_log,
            'cleaning_table': cleaning_table,
            'preview': preview, 'num_stats': num_stats,
            'cat_stats': cat_stats, 'col_quality': col_quality,
            'insights': insights, 'ts_cols': ts_cols,
            'clean_mode': clean_mode,
        })
    except Exception as e:
        import traceback
        return safe_jsonify({'error': str(e), 'detail': traceback.format_exc()})

@app.route('/diagnose', methods=['POST'])
def diagnose():
    """Diagnosa dataset sebelum upload — return masalah yang ditemukan."""
    global _last_raw_df
    if 'file' not in request.files:
        return safe_jsonify({'error': 'No file uploaded'})
    file = request.files['file']
    if not file.filename:
        return safe_jsonify({'error': 'No file selected'})
    try:
        df = load_file(file, file.filename)
        _last_raw_df = df.copy()
        diagnosis = diagnose_dataset(df)
        return safe_jsonify({'success': True, 'diagnosis': diagnosis})
    except Exception as e:
        import traceback
        return safe_jsonify({'error': str(e), 'detail': traceback.format_exc()})

@app.route('/switch-mode', methods=['POST'])
def switch_mode():
    global _last_df, _last_raw_df, _last_col_types, _last_num_stats, _last_cat_stats
    if _last_raw_df is None:
        return safe_jsonify({'error': 'No data loaded. Upload a file first.'})
    try:
        data = request.get_json()
        mode = data.get('mode', 'auto')
        features = data.get('features', {})
        filename = getattr(_last_raw_df, '_eda_filename', getattr(_last_df, '_eda_filename', 'data'))

        if mode == 'auto':
            df, cleaning_log = auto_clean(_last_raw_df.copy())
        elif mode == 'custom':
            feats = {
                'remove_duplicates': bool(features.get('remove_duplicates', True)),
                'impute_missing':    bool(features.get('impute_missing', True)),
                'fix_dtypes':        bool(features.get('fix_dtypes', True)),
                'cap_outliers':      bool(features.get('cap_outliers', True)),
                'drop_empty_cols':   bool(features.get('drop_empty_cols', True)),
            }
            df, cleaning_log = custom_clean(_last_raw_df.copy(), feats)
        else:
            df = _last_raw_df.copy()
            cleaning_log = ['[INFO] Raw mode — data digunakan apa adanya tanpa cleaning']

        cleaning_table = build_cleaning_table(cleaning_log)
        col_types = detect_types(df)
        for _col in list(df.columns):
            if col_types.get(_col) == 'categorical':
                _try = pd.to_numeric(df[_col], errors='coerce')
                if _try.notna().mean() > 0.6:
                    df[_col] = _try
                    col_types[_col] = 'numeric'
        num_stats = compute_all_numeric_stats(df, col_types)
        cat_stats = compute_all_categorical_stats(df, col_types)

        _last_df = df.copy()
        _last_df._eda_filename = filename
        _last_col_types = col_types.copy()
        _last_num_stats = num_stats.copy()
        _last_cat_stats = cat_stats.copy()

        original_rows = len(_last_raw_df)
        total_rows = len(df)
        missing_cells = int(df.isna().sum().sum())
        total_cells = total_rows * len(df.columns)
        quality_pct = round((1 - missing_cells / max(total_cells, 1)) * 100, 1)
        preview = serialize_preview(df.head(20))
        raw_preview = serialize_preview(_last_raw_df.head(20))
        ts_cols = detect_time_series_cols(df)

        raw_col_types = detect_types(_last_raw_df)
        raw_num_cols = [c for c,t in raw_col_types.items() if t=='numeric']
        raw_cat_cols = [c for c,t in raw_col_types.items() if t=='categorical']
        original_missing = int(_last_raw_df.isna().sum().sum())

        col_quality = []
        for col in df.columns:
            miss = int(df[col].isna().sum())
            unique = int(df[col].nunique(dropna=True))
            col_quality.append({
                'column': col, 'type': col_types.get(col, 'categorical'),
                'count': total_rows, 'missing': miss,
                'missing_pct': round((miss / max(total_rows, 1)) * 100, 2),
                'unique': unique,
                'unique_pct': round((unique / max(total_rows, 1)) * 100, 2),
            })

        insights = generate_basic_insights(df, col_types, num_stats, cat_stats)
        return safe_jsonify({
            'success': True, 'filename': filename, 'clean_mode': mode,
            'original_rows': original_rows, 'original_cols': len(_last_raw_df.columns),
            'original_missing': original_missing,
            'raw_num_cols': raw_num_cols, 'raw_cat_cols': raw_cat_cols,
            'raw_preview': raw_preview,
            'total_rows': total_rows, 'total_cols': len(df.columns),
            'columns': list(df.columns), 'col_types': col_types,
            'missing_cells': missing_cells, 'quality_pct': quality_pct,
            'cleaning_log': cleaning_log, 'cleaning_table': cleaning_table,
            'preview': preview, 'num_stats': num_stats, 'cat_stats': cat_stats,
            'col_quality': col_quality, 'insights': insights, 'ts_cols': ts_cols,
        })
    except Exception as e:
        import traceback
        return safe_jsonify({'error': str(e), 'detail': traceback.format_exc()})


@app.route('/clean-manual', methods=['POST'])
def clean_manual():
    global _last_df, _last_raw_df, _last_col_types, _last_num_stats, _last_cat_stats
    if _last_raw_df is None:
        return safe_jsonify({'error': 'No raw data. Upload a file first.'})
    try:
        data = request.get_json()
        steps = data.get('steps', [])
        df = _last_raw_df.copy()
        log_all = []

        if 'standardize_nulls' in steps:
            df, log = standardize_nulls(df); log_all += ['[1] STANDARDIZE NULLS'] + log
        if 'remove_duplicates' in steps:
            df, log = remove_duplicates(df); log_all += ['[2] REMOVE DUPLICATES'] + log
        if 'fix_dtypes' in steps:
            df, log = fix_dtypes(df); log_all += ['[3] FIX DATA TYPES'] + log
        if 'impute_missing' in steps:
            df, log = impute_missing(df); log_all += ['[4] IMPUTE MISSING VALUES'] + log
        if 'cap_outliers' in steps:
            df, log = cap_outliers(df); log_all += ['[5] CAP OUTLIERS (IQR)'] + log

        cleaning_table = build_cleaning_table(log_all)
        col_types = detect_types(df)
        num_stats = compute_all_numeric_stats(df, col_types)
        cat_stats = compute_all_categorical_stats(df, col_types)

        _last_df = df.copy()
        _last_df._eda_filename = getattr(_last_raw_df, '_eda_filename', 'data')
        _last_col_types = col_types.copy()
        _last_num_stats = num_stats.copy()
        _last_cat_stats = cat_stats.copy()

        total_rows = len(df)
        missing_cells = int(df.isna().sum().sum())
        total_cells = total_rows * len(df.columns)
        quality_pct = round((1 - missing_cells / max(total_cells, 1)) * 100, 1)
        preview = serialize_preview(df.head(20))
        ts_cols = detect_time_series_cols(df)

        col_quality = []
        for col in df.columns:
            miss = int(df[col].isna().sum())
            unique = int(df[col].nunique(dropna=True))
            col_quality.append({
                'column': col, 'type': col_types.get(col, 'categorical'),
                'count': total_rows, 'missing': miss,
                'missing_pct': round((miss / max(total_rows, 1)) * 100, 2),
                'unique': unique,
                'unique_pct': round((unique / max(total_rows, 1)) * 100, 2),
            })

        insights = generate_basic_insights(df, col_types, num_stats, cat_stats)
        return safe_jsonify({
            'success': True, 'cleaning_log': log_all, 'cleaning_table': cleaning_table,
            'total_rows': total_rows, 'total_cols': len(df.columns),
            'columns': list(df.columns), 'col_types': col_types,
            'missing_cells': missing_cells, 'quality_pct': quality_pct,
            'preview': preview, 'num_stats': num_stats, 'cat_stats': cat_stats,
            'col_quality': col_quality, 'insights': insights, 'ts_cols': ts_cols,
        })
    except Exception as e:
        import traceback
        return safe_jsonify({'error': str(e), 'detail': traceback.format_exc()})


@app.route('/visualize/info', methods=['POST'])
def visualize_info():
    global _last_df, _last_col_types
    if _last_df is None:
        return safe_jsonify({'error': 'No data loaded.'})
    num_cols = [c for c,t in _last_col_types.items() if t=='numeric']
    cat_cols = [c for c,t in _last_col_types.items() if t=='categorical']
    return safe_jsonify({
        'success': True,
        'num_cols': num_cols[:4], 'cat_cols': cat_cols[:3],
        'all_num_cols': num_cols, 'all_cat_cols': cat_cols,
        'num_cols_biv': num_cols[:2] if len(num_cols)>=2 else [],
        'cat_num_pair': [num_cols[0], cat_cols[0]] if num_cols and cat_cols else [],
        'has_bubble': len(num_cols) >= 3,
    })


# ── CUSTOM VISUALIZATION (pengguna pilih sendiri variabel) ──────
CUSTOM_CHART_REQUIREMENTS = {
    # numerical (univariate) — butuh 1 kolom numerik
    'histogram':  {'fields': ['col'],  'col_type': {'col': 'numeric'}},
    'box':        {'fields': ['col'],  'col_type': {'col': 'numeric'}},
    'violin':     {'fields': ['col'],  'col_type': {'col': 'numeric'}},
    'box_violin': {'fields': ['col'],  'col_type': {'col': 'numeric'}},
    'density':    {'fields': ['col'],  'col_type': {'col': 'numeric'}},
    'qqplot':     {'fields': ['col'],  'col_type': {'col': 'numeric'}},
    # categorical (univariate) — butuh 1 kolom kategorik
    'barchart':   {'fields': ['col'],  'col_type': {'col': 'categorical'}},
    'piechart':   {'fields': ['col'],  'col_type': {'col': 'categorical'}},
    'countplot':  {'fields': ['col'],  'col_type': {'col': 'categorical'}},
    'pareto':     {'fields': ['col'],  'col_type': {'col': 'categorical'}},
    # bivariate & multivariate — butuh 2-3 kolom numerik
    'scatter':    {'fields': ['cx', 'cy'], 'col_type': {'cx': 'numeric', 'cy': 'numeric'}},
    'regression': {'fields': ['cx', 'cy'], 'col_type': {'cx': 'numeric', 'cy': 'numeric'}},
    'bubble':     {'fields': ['cx', 'cy', 'cs'], 'col_type': {'cx': 'numeric', 'cy': 'numeric', 'cs': 'numeric'}},
    'heatmap':    {'fields': ['num_cols'], 'col_type': {}},
    'pairplot':   {'fields': ['num_cols'], 'col_type': {}},
    # categorical vs numerical — butuh 1 numerik + 1 kategorik
    'box_violin_by_cat': {'fields': ['nc', 'cc'], 'col_type': {'nc': 'numeric', 'cc': 'categorical'}},
    'grouped_bar':       {'fields': ['nc', 'cc'], 'col_type': {'nc': 'numeric', 'cc': 'categorical'}},
    'strip_plot':        {'fields': ['nc', 'cc'], 'col_type': {'nc': 'numeric', 'cc': 'categorical'}},
}

@app.route('/visualize/custom', methods=['POST'])
def visualize_custom():
    """
    Generate satu chart berdasarkan variabel yang dipilih pengguna sendiri.
    Body JSON: { chart_type: str, col / cx / cy / cs / nc / cc / num_cols (sesuai chart) }
    """
    global _last_df, _last_col_types
    if _last_df is None:
        return safe_jsonify({'error': 'No data loaded.'})
    try:
        df = _last_df
        col_types = _last_col_types or {}
        req = request.get_json(silent=True) or {}
        chart_type = req.get('chart_type', '')

        spec = CUSTOM_CHART_REQUIREMENTS.get(chart_type)
        if not spec:
            return safe_jsonify({'error': f'Tipe chart tidak dikenal: {chart_type}'})

        # Validasi kolom: harus ada di dataframe & tipe sesuai
        for field, required_type in spec['col_type'].items():
            col = req.get(field)
            if not col or col not in df.columns:
                return safe_jsonify({'error': f'Kolom untuk "{field}" belum dipilih atau tidak valid.'})
            actual_type = col_types.get(col, 'categorical')
            if required_type == 'numeric' and actual_type != 'numeric':
                return safe_jsonify({'error': f'Kolom "{col}" bukan kolom numerik. Pilih kolom numerik untuk "{field}".'})
            if required_type == 'categorical' and actual_type == 'numeric':
                return safe_jsonify({'error': f'Kolom "{col}" adalah kolom numerik. Pilih kolom kategorik untuk "{field}".'})

        fig = None
        label_parts = []

        if chart_type == 'histogram':
            col = req['col']; fig = make_histogram(df, col); label_parts = ['Histogram', col]
        elif chart_type == 'box':
            col = req['col']; fig = make_boxplot(df, col); label_parts = ['Box Plot', col]
        elif chart_type == 'violin':
            col = req['col']; fig = make_violin(df, col); label_parts = ['Violin Plot', col]
        elif chart_type == 'box_violin':
            col = req['col']; fig = make_box_violin(df, col); label_parts = ['Box + Violin', col]
        elif chart_type == 'density':
            col = req['col']; fig = make_density(df, col); label_parts = ['Density Plot', col]
        elif chart_type == 'qqplot':
            col = req['col']; fig = make_qqplot(df, col); label_parts = ['QQ Plot', col]
        elif chart_type == 'barchart':
            col = req['col']; fig = make_barchart(df, col); label_parts = ['Bar Chart', col]
        elif chart_type == 'piechart':
            col = req['col']; fig = make_piechart(df, col); label_parts = ['Pie Chart', col]
        elif chart_type == 'countplot':
            col = req['col']; fig = make_countplot(df, col); label_parts = ['Count Plot', col]
        elif chart_type == 'pareto':
            col = req['col']; fig = make_pareto(df, col); label_parts = ['Pareto Chart', col]
        elif chart_type == 'scatter':
            cx, cy = req['cx'], req['cy']
            if cx == cy:
                return safe_jsonify({'error': 'Kolom X dan Y tidak boleh sama.'})
            fig = make_scatter(df, cx, cy); label_parts = ['Scatter Plot', f'{cx} vs {cy}']
        elif chart_type == 'regression':
            cx, cy = req['cx'], req['cy']
            if cx == cy:
                return safe_jsonify({'error': 'Kolom X dan Y tidak boleh sama.'})
            fig = make_regression(df, cx, cy); label_parts = ['Regression Plot', f'{cx} vs {cy}']
        elif chart_type == 'bubble':
            cx, cy, cs = req['cx'], req['cy'], req['cs']
            if len({cx, cy, cs}) < 3:
                return safe_jsonify({'error': 'Kolom X, Y, dan Size harus berbeda satu sama lain.'})
            fig = make_bubble(df, cx, cy, cs); label_parts = ['Bubble Chart', f'{cx} vs {cy} (size: {cs})']
        elif chart_type == 'heatmap':
            num_cols_sel = req.get('num_cols') or []
            num_cols_sel = [c for c in num_cols_sel if c in df.columns and col_types.get(c) == 'numeric']
            if len(num_cols_sel) < 2:
                return safe_jsonify({'error': 'Pilih minimal 2 kolom numerik untuk Correlation Heatmap.'})
            fig = make_heatmap(df, num_cols_sel); label_parts = ['Correlation Heatmap', ', '.join(num_cols_sel)]
        elif chart_type == 'pairplot':
            num_cols_sel = req.get('num_cols') or []
            num_cols_sel = [c for c in num_cols_sel if c in df.columns and col_types.get(c) == 'numeric']
            if len(num_cols_sel) < 2:
                return safe_jsonify({'error': 'Pilih minimal 2 kolom numerik untuk Pair Plot.'})
            if len(num_cols_sel) > 4:
                num_cols_sel = num_cols_sel[:4]
            fig = make_pairplot(df, num_cols_sel); label_parts = ['Pair Plot', ', '.join(num_cols_sel)]
        elif chart_type == 'box_violin_by_cat':
            nc, cc = req['nc'], req['cc']
            fig = make_box_violin_by_cat(df, nc, cc); label_parts = ['Box + Violin by Category', f'{nc} by {cc}']
        elif chart_type == 'grouped_bar':
            nc, cc = req['nc'], req['cc']
            fig = make_grouped_bar(df, nc, cc); label_parts = ['Grouped Bar Chart', f'{nc} by {cc}']
        elif chart_type == 'strip_plot':
            nc, cc = req['nc'], req['cc']
            fig = make_strip(df, nc, cc); label_parts = ['Strip Plot', f'{nc} by {cc}']

        if fig is None:
            return safe_jsonify({'error': 'Chart tidak dapat dibuat — data tidak cukup atau tidak valid untuk variabel ini.'})

        label = ' — '.join(label_parts)
        return safe_jsonify({'success': True, 'chart': fig, 'label': label, 'chart_type': chart_type})
    except Exception as e:
        import traceback
        return safe_jsonify({'error': str(e), 'detail': traceback.format_exc()})
    

@app.route('/visualize/numerical', methods=['POST'])
def visualize_numerical():
    global _last_df, _last_col_types
    if _last_df is None: return safe_jsonify({'error': 'No data loaded.'})
    try:
        df = _last_df
        num_cols = [c for c,t in _last_col_types.items() if t=='numeric']
        charts = {}
        for col in num_cols[:4]:
            charts[col] = {
                'histogram': make_histogram(df, col),
                'box_violin': make_box_violin(df, col),
                'density':   make_density(df, col),
                'qqplot':    make_qqplot(df, col),
            }
        return safe_jsonify({'success': True, 'charts': charts, 'num_cols': num_cols[:4]})
    except Exception as e:
        return safe_jsonify({'error': str(e)})

@app.route('/visualize/categorical', methods=['POST'])
def visualize_categorical():
    global _last_df, _last_col_types
    if _last_df is None: return safe_jsonify({'error': 'No data loaded.'})
    try:
        df = _last_df
        cat_cols = [c for c,t in _last_col_types.items() if t=='categorical']
        charts = {}
        for col in cat_cols[:3]:
            charts[col] = {
                'barchart':  make_barchart(df, col),
                'piechart':  make_piechart(df, col),
                'countplot': make_countplot(df, col),
                'pareto':    make_pareto(df, col),
            }
        return safe_jsonify({'success': True, 'charts': charts, 'cat_cols': cat_cols[:3]})
    except Exception as e:
        return safe_jsonify({'error': str(e)})

@app.route('/visualize/bivariate', methods=['POST'])
def visualize_bivariate():
    global _last_df, _last_col_types
    if _last_df is None: return safe_jsonify({'error': 'No data loaded.'})
    try:
        df = _last_df
        num_cols = [c for c,t in _last_col_types.items() if t=='numeric']
        biv = {}
        if len(num_cols) >= 2:
            biv['scatter']    = make_scatter(df, num_cols[0], num_cols[1])
            biv['regression'] = make_regression(df, num_cols[0], num_cols[1])
            biv['heatmap']    = make_heatmap(df, num_cols)
            biv['pairplot']   = make_pairplot(df, num_cols)
            if len(num_cols) >= 3:
                biv['bubble'] = make_bubble(df, num_cols[0], num_cols[1], num_cols[2])
        return safe_jsonify({'success': True, 'charts': biv,
                             'num_cols_biv': num_cols[:2] if len(num_cols)>=2 else []})
    except Exception as e:
        return safe_jsonify({'error': str(e)})

@app.route('/visualize/catnum', methods=['POST'])
def visualize_catnum():
    global _last_df, _last_col_types
    if _last_df is None: return safe_jsonify({'error': 'No data loaded.'})
    try:
        df = _last_df
        num_cols = [c for c,t in _last_col_types.items() if t=='numeric']
        cat_cols = [c for c,t in _last_col_types.items() if t=='categorical']
        cn = {}
        if num_cols and cat_cols:
            nc, cc = num_cols[0], cat_cols[0]
            cn['box_violin_by_cat'] = make_box_violin_by_cat(df, nc, cc)
            cn['grouped_bar']    = make_grouped_bar(df, nc, cc)
            cn['strip_plot']     = make_strip(df, nc, cc)
        pair = [num_cols[0], cat_cols[0]] if num_cols and cat_cols else []
        return safe_jsonify({'success': True, 'charts': cn, 'cat_num_pair': pair})
    except Exception as e:
        return safe_jsonify({'error': str(e)})


@app.route('/ts-cols', methods=['POST'])
def ts_cols():
    global _last_df
    if _last_df is None:
        return safe_jsonify({'error': 'No data loaded.'})
    try:
        ts_detected = detect_date_columns(_last_df)
        num_cols = [c for c, t in (_last_col_types or {}).items() if t == 'numeric']
        all_cols = list(_last_df.columns)
        return safe_jsonify({'ts_cols': ts_detected, 'num_cols': num_cols, 'all_cols': all_cols})
    except Exception as e:
        return safe_jsonify({'error': str(e)})


@app.route('/timeseries', methods=['POST'])
def timeseries():
    global _last_df, _last_col_types
    if _last_df is None:
        return safe_jsonify({'error': 'No dataset loaded. Please upload a file first.'})

    req      = request.get_json(silent=True) or {}
    date_col = req.get('date_col', '')
    val_col  = req.get('val_col', '')
    ma_win   = int(req.get('ma_window', 7))
    roll_win = int(req.get('roll_window', 30))

    df = _last_df.copy()
    if date_col not in df.columns or val_col not in df.columns:
        return safe_jsonify({'error': 'Invalid column selection.'})

    try:
        ts = compute_time_series(df, date_col, val_col, ma_window=ma_win, roll_window=roll_win)

        x          = ts['dates']
        y          = ts['values']
        ma         = ts['ma']
        roll       = ts['roll']
        trend_line = ts['trend_line']

        TS_COLOR    = '#2d6a9f'
        MA_COLOR    = '#c94040'
        TREND_COLOR = '#e07b39'
        ROLL_COLOR  = '#7a5ca8'

        result = {}

        # 1. Line Chart
        fig = go.Figure(go.Scatter(x=x, y=y, mode='lines',
                                    line=dict(color=TS_COLOR, width=1.5), name=val_col))
        fig.update_layout(title=f'Time Series: {val_col}', xaxis_title='Date', yaxis_title=val_col)
        result['line_chart'] = fig_json(fig)

        # 2. Moving Average
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=x, y=y, mode='lines', name='Original',
                                  line=dict(color=TS_COLOR, width=1), opacity=0.5))
        fig.add_trace(go.Scatter(x=x, y=ma, mode='lines', name=f'MA({ma_win})',
                                  line=dict(color=MA_COLOR, width=2.5)))
        fig.update_layout(title=f'Moving Average ({ma_win}-period)')
        result['ma_chart'] = fig_json(fig)

        # 3. Trend Line
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=x, y=y, mode='lines', name='Actual',
                                  line=dict(color=TS_COLOR, width=1), opacity=0.6))
        fig.add_trace(go.Scatter(x=x, y=trend_line, mode='lines', name='Trend',
                                  line=dict(color=TREND_COLOR, width=2.5, dash='dash')))
        fig.update_layout(title='Trend Line')
        result['trend_chart'] = fig_json(fig)

        # 4. Rolling Mean (custom window)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=x, y=y, mode='lines', name='Daily',
                                  line=dict(color=TREND_COLOR, width=0.8), opacity=0.4))
        fig.add_trace(go.Scatter(x=x, y=roll, mode='lines',
                                  name=f'Rolling Mean ({roll_win})',
                                  line=dict(color=ROLL_COLOR, width=2.5)))
        fig.update_layout(title=f'Rolling Mean ({roll_win}-period)')
        result['roll30_chart'] = fig_json(fig)

        result['ts_stats'] = ts['stats']
        return safe_jsonify(result)

    except Exception as e:
        import traceback
        return safe_jsonify({'error': str(e), 'detail': traceback.format_exc()})


@app.route('/login')
def login_page():
    return render_template('login.html')

from backend.export_report import export_csv, export_excel, export_pdf

@app.route('/export-csv')
def route_export_csv():
    global _last_df
    if _last_df is None:
        return safe_jsonify({'error': 'No data loaded.'}), 400
    try:
        csv_bytes = export_csv(_last_df)
        fname = getattr(_last_df, '_eda_filename', 'data').rsplit('.',1)[0] + '.csv'
        return app.response_class(
            csv_bytes, mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename="{fname}"'})
    except Exception as e:
        return safe_jsonify({'error': str(e)}), 500

@app.route('/export-excel')
def route_export_excel():
    global _last_df, _last_num_stats, _last_cat_stats, _last_col_types
    if _last_df is None:
        return safe_jsonify({'error': 'No data loaded.'}), 400
    try:
        xls_bytes = export_excel(_last_df,
                                  _last_num_stats or {},
                                  _last_cat_stats  or {},
                                  _last_col_types  or {})
        fname = getattr(_last_df, '_eda_filename', 'data').rsplit('.',1)[0] + '.xlsx'
        return app.response_class(
            xls_bytes,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename="{fname}"'})
    except Exception as e:
        import traceback
        return safe_jsonify({'error': str(e), 'detail': traceback.format_exc()}), 500

@app.route('/export-pdf')
def route_export_pdf():
    global _last_df, _last_num_stats, _last_cat_stats, _last_col_types
    if _last_df is None:
        return safe_jsonify({'error': 'No data loaded.'}), 400
    try:
        fname = getattr(_last_df, '_eda_filename', 'data')
        insights = generate_basic_insights(_last_df, _last_col_types or {}, _last_num_stats or {}, _last_cat_stats or {})
        
        # Ambil parameter chart dari query string
        charts_param = request.args.get('charts', 'histogram,bar,scatter,heatmap,grouped_bar')
        selected_charts = [c.strip() for c in charts_param.split(',') if c.strip()]
        max_cols = request.args.get('max_cols', '4')
        max_cat_cols = request.args.get('max_cat_cols', '4')
        max_cols = None if max_cols == 'all' else int(max_cols)
        max_cat_cols = None if max_cat_cols == 'all' else int(max_cat_cols)
        
        pdf_bytes = export_pdf(_last_df, _last_num_stats or {}, _last_cat_stats or {},
                        _last_col_types or {}, insights, fname,
                        selected_charts=selected_charts,
                        max_num_cols=max_cols,
                        max_cat_cols=max_cat_cols)
        
        fname_out = getattr(_last_df, '_eda_filename', 'data').rsplit('.', 1)[0] + '_EDA_Report.pdf'
        return app.response_class(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'attachment; filename="{fname_out}"'}
        )
    except Exception as e:
        import traceback
        return safe_jsonify({'error': str(e), 'detail': traceback.format_exc()}), 500


@app.route('/fulldata', methods=['GET'])

def full_data():
    global _last_df, _last_col_types
    if _last_df is None:
        return safe_jsonify({'error': 'No data loaded. Upload a file first.'})
    try:
        rows = serialize_preview(_last_df.head(10000))
        return safe_jsonify({'rows': rows, 'total': len(_last_df), 'columns': list(_last_df.columns)})
    except Exception as e:
        import traceback
        return safe_jsonify({'error': str(e), 'detail': traceback.format_exc()})


@app.route('/dashboard-charts', methods=['POST'])
def dashboard_charts():
    """Kirim data nyata untuk 6 chart dashboard preview."""
    global _last_df, _last_col_types, _last_num_stats, _last_cat_stats
    if _last_df is None:
        return safe_jsonify({'error': 'No data loaded.'})
    try:
        df        = _last_df
        col_types = _last_col_types
        num_stats = _last_num_stats or {}
        cat_stats = _last_cat_stats or {}

        num_cols = [c for c, t in col_types.items() if t == 'numeric']
        cat_cols = [c for c, t in col_types.items() if t == 'categorical']
        dt_cols  = [c for c, t in col_types.items() if t == 'datetime']

        payload = {
            'num_cols': num_cols,
            'cat_cols': cat_cols,
            'dt_cols':  dt_cols,
        }

        # ── 1) Histogram: kolom numerik dengan std tertinggi ──
        if num_cols:
            best_num = max(num_cols, key=lambda c: (num_stats.get(c) or {}).get('std', 0))
            data = clean_numeric(df[best_num]).dropna()
            # Buat histogram bins manual (20 bins)
            mn, mx = float(data.min()), float(data.max())
            step = (mx - mn) / 20 if mx != mn else 1
            bins_x, bins_y = [], []
            for i in range(20):
                lo = mn + i * step
                hi = lo + step
                count = int(((data >= lo) & (data < hi)).sum())
                bins_x.append(round((lo + hi) / 2, 2))
                bins_y.append(count)
            payload['hist'] = {
                'col': best_num,
                'x': bins_x, 'y': bins_y,
                'mean': round(float(data.mean()), 2),
                'median': round(float(data.median()), 2),
            }

        # ── 2) Bar Chart: kolom kategorik terbaik ──
        if cat_cols:
            best_cat = cat_cols[0]
            vc = df[best_cat].value_counts().head(10)
            payload['bar'] = {
                'col': best_cat,
                'labels': [str(k)[:18] for k in vc.index.tolist()],
                'values': vc.values.tolist(),
            }

        # ── 3) Violin: kolom numerik terbaik ke-2 (atau pertama) ──
        if num_cols:
            col3 = num_cols[1] if len(num_cols) > 1 else num_cols[0]
            data3 = clean_numeric(df[col3]).dropna()
            if len(data3) > 0:
                # Pastikan sample adalah list float (bukan string/object)
                smp3 = data3.sample(min(300, len(data3)), random_state=42)
                sample_list = [round(float(v), 3) for v in smp3.tolist() if v == v]
                payload['violin'] = {
                    'col': col3,
                    'sample': sample_list,
                    'q1': round(float(data3.quantile(0.25)), 3),
                    'median': round(float(data3.median()), 3),
                    'q3': round(float(data3.quantile(0.75)), 3),
                    'mean': round(float(data3.mean()), 3),
                }

        # ── 4) Donut Pie: pilih kolom kategorik dengan 3-15 unique values ──
        if cat_cols:
            pie_col = None
            for cc in cat_cols:
                u = df[cc].nunique()
                if 3 <= u <= 15:
                    pie_col = cc
                    break
            if pie_col is None:
                pie_col = cat_cols[0]  # fallback
            vc_pie = df[pie_col].value_counts().head(7)
            payload['pie'] = {
                'col': pie_col,
                'labels': [str(k)[:16] for k in vc_pie.index.tolist()],
                'values': vc_pie.values.tolist(),
            }

        # ── 5) Scatter: dua kolom numerik terbaik ──
        if len(num_cols) >= 2:
            cx, cy = num_cols[0], num_cols[1]
            tmp = df[[cx, cy]].copy()
            tmp[cx] = clean_numeric(tmp[cx])
            tmp[cy] = clean_numeric(tmp[cy])
            tmp = tmp.dropna()
            # Sampel 200 titik
            smp = tmp.sample(min(200, len(tmp)), random_state=42)
            # Hitung korelasi
            try:
                corr = round(float(tmp[cx].corr(tmp[cy])), 3)
            except Exception:
                corr = 0.0
            payload['scatter'] = {
                'col_x': cx, 'col_y': cy,
                'x': [round(v, 3) for v in smp[cx].tolist()],
                'y': [round(v, 3) for v in smp[cy].tolist()],
                'corr': corr,
            }


       # ── 6) Grouped bar: avg numerik per kategori ──
        if num_cols and cat_cols:
            gn = num_cols[0]
            gc = None
            for cc in cat_cols:
                u = df[cc].nunique()
                if 2 <= u <= 30:
                    gc = cc
                    break
            if gc is None:
                gc = cat_cols[0]
            grp = df.groupby(gc).apply(lambda x: clean_numeric(x[gn]).mean()).dropna()
            grp = grp.sort_values(ascending=False).head(10)
            if len(grp) >= 2:
                payload['grouped'] = {
                    'col_cat': gc, 'col_num': gn,
                    'labels': [str(k)[:18] for k in grp.index.tolist()],
                    'values': [round(float(v), 2) for v in grp.values.tolist()],
                }

        return safe_jsonify({'success': True, **payload})
    except Exception as e:
        import traceback
        return safe_jsonify({'error': str(e), 'detail': traceback.format_exc()})


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)