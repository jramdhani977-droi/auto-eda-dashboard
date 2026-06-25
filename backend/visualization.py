"""
visualization.py — Module automated visualization
Semua fungsi chart Plotly yang digunakan di Auto EDA Analytics Dashboard.
Fungsi-fungsi ini di-import oleh app.py dan dapat digunakan secara standalone.
"""
import math
import json
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import plotly.utils


def clean_numeric(series: pd.Series) -> pd.Series:
    """
    Bersihkan kolom numerik dari format apapun sebelum visualisasi.
    Handles: 'Rp 1.234.567', '$1,234.56', '1.234,56', '188905', dll.
    Returns: pd.Series of float, NaN untuk yang tidak bisa di-parse.
    """
    s = series.astype(str).str.strip()
    s = s.str.replace(r'[Rp$€£¥₹\s]', '', regex=True)
    european = s.str.match(r'^\d{1,3}(\.\d{3})+(,\d+)?$')
    if european.sum() > len(s) * 0.3:
        s = s.str.replace(r'\.(?=\d{3})', '', regex=True)
        s = s.str.replace(',', '.', regex=False)
    else:
        s = s.str.replace(',', '', regex=False)
    return pd.to_numeric(s, errors='coerce')


def _fig_to_json(fig):
    """Convert Plotly figure to JSON-serializable dict."""
    return json.loads(plotly.utils.PlotlyJSONEncoder().encode(fig))


def _fmt_num(v):
    """Format angka: integer jika bulat, 2 desimal jika tidak."""
    try:
        if math.isnan(v) or math.isinf(v):
            return 'N/A'
        return str(int(v)) if v == int(v) else f'{v:,.2f}'
    except Exception:
        return str(v)



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


__all__ = [
    '_fmt_num',
    'make_histogram',
    'make_boxplot',
    'make_violin',
    'make_density',
    'make_qqplot',
    'make_box_violin',
    'make_barchart',
    'make_piechart',
    'make_countplot',
    'make_pareto',
    'make_scatter',
    'make_heatmap',
    'make_pairplot',
    'make_regression',
    'make_bubble',
    'make_box_violin_by_cat',
    'make_grouped_bar',
    'make_strip',
]
