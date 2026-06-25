#  Auto EDA Analytics Dashboard

**Final Exam — SD-1306 Data Science Programming**  
Dosen: Bakti Siregar, M.Sc.  
Institut Teknologi Sains Bandung (ITSB)  
Kota Deltamas Lot-A1 CBD, Jl. Ganesha Boulevard No.1, Pasirranji, Kec. Cikarang Pusat, Kabupaten Bekasi, Jawa Barat 17530.

---

##  Deskripsi Proyek

Dashboard ini adalah **Intelligent Data Analytics Platform** yang dikembangkan sebagai proyek UAS mata kuliah SD-1306 Data Science Programming. Platform ini mampu melakukan **Exploratory Data Analysis (EDA) secara otomatis**, mirip dengan tools profesional seperti Tableau dan Microsoft Power BI.

Sistem dibangun menggunakan:
- **Backend**: Python (Flask) + modul analitik terpisah di folder `backend/`
- **Frontend**: HTML / CSS / JavaScript dengan visualisasi interaktif berbasis Plotly
- **Visualisasi**: Plotly (interactive, web-native, ringan)

---

##  Struktur Folder

```
bismillah2/
│
├── app.py                        ← Aplikasi utama Flask (routing & integrasi)
├── requirements.txt              ← Daftar library Python
├── README.md                     ← Dokumentasi proyek ini
│
├── backend/                      ← Modul analitik terpisah
│   ├── __init__.py
│   ├── data_loader.py            ← Membaca file & info dataset
│   ├── preprocessing.py          ← Cleaning & transformasi data
│   ├── descriptive_stats.py      ← Statistik deskriptif numerik
│   ├── categorical_analysis.py   ← Statistik deskriptif kategorik
│   ├── visualization.py          ← Pembuatan chart (Matplotlib/Seaborn)
│   ├── time_series.py            ← Analisis time series & deteksi kolom tanggal
│   ├── insight_generator.py      ← Generasi insight otomatis
│   └── export_report.py          ← Export laporan PDF/HTML/Excel
│
├── templates/                    ← Halaman HTML (Jinja2 templates)
│   ├── landing.html              ← Halaman landing/beranda
│   ├── login.html                ← Halaman login
│   ├── index.html                ← Halaman utama dashboard
│   ├── dashboard.html            ← Tampilan dashboard analitik
│   ├── upload.html               ← Halaman upload data
│   └── report.html               ← Halaman laporan hasil analisis
│
├── static/
│   ├── css/
│   │   └── style.css             ← Semua styling dashboard
│   ├── js/
│   │   └── script.js             ← Logika interaktif frontend
│   └── img/
│       ├── logo-itb.png
│       └── logo-itsb.png
│
├── data/
│   ├── raw/                      ← Data mentah yang diupload (ecommerce.xlsx, dll)
│   └── sample_dataset/           ← Dataset contoh untuk pengujian
│       ├── sales_data.csv
│       ├── sales_data.txt
│       └── sales_data.xlsx
│
├── docs/
│   └── dashboard_screenshot/     ← Screenshot tampilan dashboard
│
└── tests/                        ← Unit test
    ├── test_upload.py
    ├── test_statistics.py
    └── test_visualization.py
```

---

## Cara Menjalankan

### 1. Ekstrak Proyek

```bash
unzip FINNAL_EXAM_PSD.zip
cd bismillah2
```

### 2. (Opsional) Buat Virtual Environment

```bash
python -m venv venv
source venv/bin/activate        # Linux/macOS
venv\Scripts\activate           # Windows
```

### 3. Install Dependensi

```bash
pip install -r requirements.txt
```

### 4. Jalankan Server Flask

```bash
python app.py
```

### 5. Buka di Browser

```
http://localhost:5000
```

> **Catatan:** File HTML menggunakan Jinja2 template milik Flask. **Tidak bisa** dibuka langsung di browser tanpa menjalankan `app.py` terlebih dahulu.

---

##  Library yang Digunakan

| Library | Kegunaan |
|---------|---------|
| `Flask` | Web framework Python untuk server backend |
| `Pandas` | Manipulasi dan analisis data tabular |
| `NumPy` | Komputasi numerik dan array |
| `SciPy` | Uji statistik normalitas dan regresi |
| `Plotly` | Visualisasi interaktif berbasis web |
| `OpenPyXL` | Membaca dan menulis file Excel `.xlsx` |
| `fpdf2` | Pembuatan laporan PDF |

Install semua sekaligus:

```bash
pip install flask pandas numpy openpyxl plotly scipy fpdf2
```

---

##  Fitur Utama

### 1. Data Management
- Upload file **Excel** (`.xlsx` / `.xls`), **CSV** (`.csv`), **Text** (`.txt`)
- Deteksi separator otomatis untuk file TXT
- Deteksi tipe data otomatis: `numeric`, `categorical`, `datetime`, `boolean`
- Preview 100 baris pertama dengan informasi tipe kolom

### 2. Auto Data Cleaning Pipeline

| Langkah | Keterangan |
|---------|------------|
| `standardize_nulls()` | Mengubah nilai kosong (`NA`, `null`, `-`, dll) → `NaN` standar |
| `remove_duplicates()` | Menghapus baris duplikat |
| `fix_dtypes()` | Konversi tipe data otomatis (string angka → numeric, string tanggal → datetime) |
| `impute_missing()` | Imputasi nilai kosong: median untuk numerik, modus untuk kategorik |
| `cap_outliers()` | Membatasi outlier menggunakan metode IQR |
| `auto_clean()` | Pipeline gabungan 5 langkah di atas |
| `drop_empty_cols()` | Menghapus kolom yang sepenuhnya kosong |
| `diagnose_dataset()` | Diagnosa kondisi dataset sebelum cleaning |
| `custom_clean()` | Opsi cleaning manual yang dapat dikonfigurasi |

### 3.  Statistik Deskriptif — Numerik

- Mean, Median, Minimum, Maximum
- Standard Deviation, Variance, Mode
- Skewness, Kurtosis
- Missing Value Count & Persentase (%)
- Normal Distribution Test (Normal / Not Normal)
- Jumlah Outlier (metode IQR)

### 4. Statistik Deskriptif — Kategorik

- Unique Categories, Mode
- Mode Frequency & Persentase (%)
- Missing Value Count & Persentase (%)

### 5. Automated Visualization Analytics

**Numerical (per kolom numerik, maks 6 kolom):**
- Histogram, Boxplot, Density Plot, QQ Plot, Violin Plot

**Categorical (per kolom kategorik, maks 4 kolom):**
- Bar Chart, Pie Chart, Count Plot, Pareto Chart

**Bivariate & Multivariate:**
- Scatter Plot, Correlation Heatmap, Pair Plot, Regression Plot, Bubble Chart

**Categorical vs Numerical:**
- Boxplot by Category, Violin Plot by Category, Grouped Bar Chart, Strip Plot

### 6. Data Quality Report
- Laporan kualitas per kolom: tipe, jumlah data, missing count & persentase, unique values
- Log hasil auto cleaning
- Quality score keseluruhan dataset (%)

### 7. Time Series Analytics
- Deteksi kolom tanggal otomatis (`detect_date_columns`)
- Analisis time series: trend, moving average, rolling mean

### 8. Intelligent Insight Generator
- Generasi insight otomatis berdasarkan pola statistik data
- Ditangani oleh modul `backend/insight_generator.py`

### 9. Export & Reporting
- Download laporan dalam format **PDF**, **HTML**, dan **Excel/CSV**
- Ditangani oleh modul `backend/export_report.py`

---

## Roadmap Pengembangan

| Fase | Target | Status |
|------|--------|--------|
| Meeting 14 | Upload, cleaning, statistik deskriptif, visualisasi otomatis, UI dashboard | Selesai |
| Meeting 15 | Modularisasi backend, peningkatan visualisasi & correlation analysis, insight awal | Selesai |
| Meeting 16 | Time series analytics, intelligent insight, reporting & export, optimasi final | Selesai |

---

## Endpoint API

| Method | Route | Keterangan |
|--------|-------|------------|
| `GET` | `/` | Landing page |
| `GET` | `/login` | Halaman login |
| `GET` | `/dashboard` | Halaman dashboard utama |
| `POST` | `/upload` | Upload file, jalankan cleaning & statistik |
| `POST` | `/visualize` | Generate semua visualisasi dari data yang sudah diupload |

---

Proyek ini dibuat untuk keperluan akademik — **Final Exam SD-1306 Data Science Programming**, Institut Teknologi Sains Bandung (ITSB).

---

*Auto EDA Analytics Dashboard — SD-1306 Data Science Programming — ITSB © 2025*