/* ============================================================
   AUTO EDA ANALYTICS — script.js  v2.0 (Meeting 15)
   SD-1306 Data Science Programming
   ============================================================ */

let state = {};

/* ── Auth Guard ──────────────────────────────────────────── */
(function () {
  const user = sessionStorage.getItem('eda_user');
  if (!user) { window.location.href = '/login'; return; }
  try {
    const u = JSON.parse(user);
    const el = document.getElementById('popupUserInfo');
    if (el) el.textContent = u.name + ' (' + u.nim + ')';
  } catch (e) { }
})();

function doLogout() {
  sessionStorage.removeItem('eda_user');
  window.location.href = '/login';
}

/* ── Group Popup ─────────────────────────────────────────── */
function toggleGroupPopup() {
  const popup = document.getElementById('groupPopup');
  const overlay = document.getElementById('groupPopupOverlay');
  const isHidden = popup.classList.contains('hidden');
  if (isHidden) {
    popup.classList.remove('hidden');
    overlay.classList.remove('hidden');
  } else {
    popup.classList.add('hidden');
    overlay.classList.add('hidden');
  }
}

/* ── Sidebar Submenu ─────────────────────────────────────── */
function toggleSub(id) {
  const sub = document.getElementById(id);
  const caretId = id.replace('sub-', 'caret-');
  const caret = document.getElementById(caretId);
  if (!sub) return;
  const isOpen = sub.classList.contains('open');
  sub.classList.toggle('open', !isOpen);
  if (caret) caret.style.transform = isOpen ? '' : 'rotate(180deg)';
}

/* ── New Structured Viz Group Toggle ─────────────────────── */
function toggleVizGroup(groupId) {
  const group = document.getElementById(groupId);
  if (!group) return;
  group.classList.toggle('open');
}

function showVizTab(tab) {
  showSection('viz');
  if (state.charts) filterViz(tab);
}

/* ── File Upload ─────────────────────────────────────────── */
function handleDrop(e) {
  e.preventDefault();
  const zone = document.getElementById('uploadZone');
  if (zone) zone.classList.remove('dragover');
  const file = e.dataTransfer.files[0];
  if (file) handleFile(file);
}

// Simpan file terakhir untuk dipakai saat tombol Proses diklik
var _pendingFile = null;

function handleFile(file) {
  if (!file) return;
  _pendingFile = file;

  // Reset UI diagnosis
  var diagLoading = document.getElementById('diagLoadingInline');
  var diagCard    = document.getElementById('diagCardInline');
  var modeSection = document.getElementById('modeSectionInline');
  var prosesBtn   = document.getElementById('btnProsesDataset');

  if (diagLoading) diagLoading.style.display = 'block';
  if (diagCard)    diagCard.style.display = 'none';
  if (modeSection) modeSection.style.display = 'none';
  if (prosesBtn)   prosesBtn.style.display = 'none';

  // Update upload zone tampilan
  var zone = document.getElementById('uploadZone');
  if (zone) {
    zone.style.borderColor = '#27ae60';
    zone.style.background  = 'rgba(39,174,96,0.04)';
  }
  var subText = document.getElementById('uploadSubText');
  if (subText) subText.textContent = '📄 ' + file.name + ' — pilih mode lalu klik Proses';

  // Panggil /diagnose
  var fd = new FormData();
  fd.append('file', file);
  fetch('/diagnose', { method: 'POST', body: fd })
    .then(function(r) { return r.json(); })
    .then(function(diag) {
      if (diagLoading) diagLoading.style.display = 'none';
      if (diag.error) {
        if (subText) subText.textContent = '❌ Gagal analisa: ' + diag.error;
        return;
      }
      renderDiagInline(diag.diagnosis);
      renderFeatureBadgesInline(diag.diagnosis.cleaning_features);
      if (modeSection) modeSection.style.display = 'block';
      // Tampilkan tombol Proses
      if (prosesBtn)   prosesBtn.style.display = 'block';
      // Pastikan mode yang aktif terpilih dengan visual yang benar
      selectCleanModeNew(_cleanMode || 'auto');
    })
    .catch(function(err) {
      if (diagLoading) diagLoading.style.display = 'none';
      if (subText) subText.textContent = '❌ Error: ' + err;
    });
}

// Dipanggil saat tombol "Proses Dataset" diklik
function prosesDataset() {
  if (!_pendingFile) { alert('Pilih file terlebih dahulu.'); return; }
  _doUpload(_pendingFile);
}

function _doUpload(file) {
  var modeLabel = _cleanMode === 'auto'   ? 'Auto Cleaning'
    : _cleanMode === 'custom' ? 'Custom Cleaning'
    : 'Raw (tanpa cleaning)';
  showLoading('Memproses dataset... Mode: ' + modeLabel);

  var fd = new FormData();
  fd.append('file', file);
  fd.append('clean_mode', _cleanMode);

  if (_cleanMode === 'custom') {
    ['remove_duplicates','impute_missing','fix_dtypes','cap_outliers','drop_empty_cols'].forEach(function(id) {
      var el = document.getElementById('ifeat_' + id);
      fd.append('feat_' + id, (el && el.checked) ? '1' : '0');
    });
  }

  fetch('/upload', { method: 'POST', body: fd })
    .then(function(r) {
      if (!r.ok) return r.text().then(function() { throw new Error('Server error ' + r.status); });
      return r.json();
    })
    .then(function(data) {
      hideLoading();
      if (data.error) { alert('Error: ' + data.error); return; }
      _applyUploadResult(data);
    })
    .catch(function(err) { hideLoading(); alert('Upload gagal: ' + err); });
}

function _applyUploadResult(data) {
  state = data;
  state.charts = null;
  window._state = data;
  _previewShowAll = false;
  Object.keys(_vizLoaded).forEach(function(k) { _vizLoaded[k] = false; });
  _vizInfo = null;
  _fullDataCache = null;

  var vizContent = document.getElementById('vizContent');
  if (vizContent) vizContent.innerHTML =
    '<div class="empty-state"><div class="empty-icon">&#9638;</div>' +
    '<div class="empty-title">Klik menu visualisasi di sidebar untuk melihat chart</div></div>';
  var vizTabs = document.getElementById('vizTabs');
  if (vizTabs) vizTabs.style.display = 'none';

  renderDashboard(data);
  updateDashboardPreview(data);
  renderDashboardCharts(data);
  if (typeof syncNewKPIs === 'function') syncNewKPIs(data);

  // Update label mode di success bar
  var modeLabel = data.clean_mode === 'auto'   ? 'Auto Cleaning ✔'
    : data.clean_mode === 'custom' ? 'Custom Cleaning ✔'
    : 'Data Asli / Raw';
  var sb = document.getElementById('uploadSuccessBar');
  var sm = document.getElementById('uploadSuccessMsg');
  if (sb && sm) {
    sm.textContent = data.filename + ' — ' + data.total_rows.toLocaleString() + ' baris × ' + data.total_cols + ' kolom (' + modeLabel + ')';
    sb.style.display = 'flex';
  }

  // Reset tombol Proses & pending file
  _pendingFile = null;
  var prosesBtn = document.getElementById('btnProsesDataset');
  if (prosesBtn) prosesBtn.style.display = 'none';
}

/* ── Switch mode saat data sudah ada ─────────────────────── */
function _switchMode(mode) {
  if (!state || !state.filename) return;

  var modeLabel = mode === 'auto' ? 'Menerapkan Auto Cleaning...'
    : mode === 'custom' ? 'Menerapkan Custom Cleaning...'
    : 'Beralih ke Data Asli (Raw)...';
  showLoading(modeLabel);

  // Kumpulkan fitur custom
  var features = {};
  if (mode === 'custom') {
    ['remove_duplicates','impute_missing','fix_dtypes','cap_outliers','drop_empty_cols'].forEach(function(id) {
      var el = document.getElementById('ifeat_' + id);
      features[id] = el ? el.checked : true;
    });
  }

  fetch('/switch-mode', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode: mode, features: features })
  })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      hideLoading();
      if (data.error) { alert('Error switch mode: ' + data.error); return; }
      _applyUploadResult(data);
    })
    .catch(function(e) { hideLoading(); alert('Error: ' + e.message); });
}

/* ── Mode selector 3 pilihan: custom / auto / raw ─────────── */
var _cleanMode = 'auto';

function selectCleanModeNew(mode) {
  _cleanMode = mode;

  var cfgs = {
    custom: { card: 'modeCardCustom', dot: 'dotCustom', border: '#3b82f6', bg: 'rgba(59,130,246,.07)', dotClr: '#93c5fd' },
    auto:   { card: 'modeCardAuto',   dot: 'dotAuto',   border: '#27ae60', bg: 'rgba(39,174,96,.07)',  dotClr: '#27ae60' },
    raw:    { card: 'modeCardRaw',    dot: 'dotRaw',    border: '#f59e0b', bg: 'rgba(245,158,11,.07)', dotClr: '#f59e0b' },
  };

  Object.keys(cfgs).forEach(function(m) {
    var c    = cfgs[m];
    var card = document.getElementById(c.card);
    var dot  = document.getElementById(c.dot);
    var active = (m === mode);
    if (card) {
      card.style.borderColor = active ? c.border : '#d1d5db';
      card.style.background  = active ? c.bg : '#fff';
    }
    if (dot) {
      dot.style.background = active ? c.dotClr : 'transparent';
      dot.style.border     = active ? 'none' : '2px solid #d1d5db';
    }
  });

  var featPanel   = document.getElementById('featPanelInline');
  var featSummary = document.getElementById('featSummaryInline');
  if (featPanel)   featPanel.style.display   = (mode === 'custom') ? 'block' : 'none';
  if (featSummary) featSummary.style.display = (mode === 'custom') ? 'block' : 'none';
  if (mode === 'custom') updateSummaryInline();

  var subText = document.getElementById('uploadSubText');
  if (subText && !_pendingFile && (!state || !state.filename)) {
    subText.textContent = mode === 'auto'   ? 'Semua cleaning akan diterapkan otomatis'
      : mode === 'custom' ? 'Pilih fitur cleaning yang ingin diterapkan'
      : 'Data akan digunakan apa adanya tanpa cleaning (Raw Mode)';
  }

  // Kalau data sudah ada → langsung switch mode
  if (state && state.filename) {
    _switchMode(mode);
  }
}

/* ── selectCleanMode lama — backward compat ───────────────── */
function selectCleanMode(mode) {
  selectCleanModeNew(mode);
}

/* ── Render diagnosis card inline ─────────────────────────── */
function renderDiagInline(diag) {
  var card  = document.getElementById('diagCardInline');
  var badge = document.getElementById('diagBadgeInline');
  var items = document.getElementById('diagItemsInline');
  if (!card) return;
  card.style.display = 'block';

  if (diag.problem_count > 0) {
    badge.style.cssText = 'background:#c94040;color:#fff;font-size:11px;padding:2px 9px;border-radius:20px;font-weight:700;';
    badge.textContent = diag.problem_count + ' masalah ditemukan';
  } else {
    badge.style.cssText = 'background:#1a3d2b;color:#4ade80;font-size:11px;padding:2px 9px;border-radius:20px;font-weight:700;';
    badge.textContent = 'Dataset bersih ✓';
  }

  var dotColor = { error: '#c94040', warning: '#d97706', ok: '#3a9e6f' };
  var html = '';
  (diag.issues || []).forEach(function(issue) {
    html += '<div style="display:flex;align-items:flex-start;gap:10px;padding:12px 16px;border-bottom:1px solid #f0faf5;">'
      + '<div style="width:9px;height:9px;border-radius:50%;background:' + (dotColor[issue.severity] || '#ccc') + ';margin-top:4px;flex-shrink:0;"></div>'
      + '<div style="flex:1;">'
      + '<div style="font-size:13px;font-weight:600;color:#1a3a28;">' + issue.label + '</div>'
      + '<div style="font-size:11.5px;color:#6b9b7a;margin-top:2px;font-family:monospace;">' + issue.detail + '</div>'
      + '</div>'
      + '<div style="font-size:12px;color:#9ca3af;white-space:nowrap;">' + issue.count_label + '</div>'
      + '</div>';
  });
  if (!html) html = '<div style="padding:14px 16px;font-size:12px;color:#6b9b7a;">Tidak ada masalah terdeteksi.</div>';
  items.innerHTML = html;
}

/* ── Badge per fitur dari diagnosis ───────────────────────── */
function renderFeatureBadgesInline(features) {
  if (!features) return;
  function setBadge(id, count) {
    var el = document.getElementById('ibadge_' + id);
    if (!el) return;
    if (count > 0) {
      el.textContent = count + (id === 'fix_dtypes' || id === 'drop_empty_cols' ? ' kolom'
        : id === 'remove_duplicates' ? ' baris' : ' sel');
      el.style.display = 'inline';
    } else {
      el.textContent = 'Aman';
      el.style.background = '#1a3d2b';
      el.style.color = '#4ade80';
      el.style.display = 'inline';
    }
  }
  setBadge('remove_duplicates', features.remove_duplicates || 0);
  setBadge('impute_missing',    features.impute_missing    || 0);
  setBadge('fix_dtypes',        features.fix_dtypes        || 0);
  setBadge('cap_outliers',      features.cap_outliers      || 0);
  setBadge('drop_empty_cols',   features.drop_empty_cols   || 0);
}

/* ── Toggle semua fitur custom ────────────────────────────── */
function selectAllFeatsInline(val) {
  ['remove_duplicates','impute_missing','fix_dtypes','cap_outliers','drop_empty_cols'].forEach(function(id) {
    var el = document.getElementById('ifeat_' + id);
    if (el) el.checked = val;
  });
  updateSummaryInline();
}

/* ── Update summary bar fitur ─────────────────────────────── */
function updateSummaryInline() {
  var ids = ['remove_duplicates','impute_missing','fix_dtypes','cap_outliers','drop_empty_cols'];
  var checked = ids.filter(function(id) {
    var el = document.getElementById('ifeat_' + id);
    return el && el.checked;
  });
  var bar = document.getElementById('featSummaryInline');
  if (!bar) return;
  bar.style.display = 'block';

  var applyBtn = '';
  // Kalau data sudah ada, tampilkan tombol Terapkan
  if (state && state.filename) {
    applyBtn = ' <button onclick="_switchMode(\'custom\')" style="margin-left:10px;font-size:11px;padding:3px 12px;background:#27ae60;color:#fff;border:none;border-radius:20px;cursor:pointer;font-weight:700;">Terapkan Sekarang</button>';
  }

  if (checked.length === 0) {
    bar.innerHTML = '⚠ Tidak ada fitur yang dipilih — data tidak akan di-clean.' + applyBtn;
    bar.style.color = '#fbbf24';
  } else {
    bar.innerHTML = '✓ <span style="color:#9ca3af">' + checked.length + ' fitur cleaning dipilih.</span>' + applyBtn;
    bar.style.color = '#4ade80';
  }
}

/* ── Render Dashboard ────────────────────────────────────── */
function renderDashboard(d) {
  const numCols = Object.entries(d.col_types).filter(([, t]) => t === 'numeric').length;
  const catCols = Object.entries(d.col_types).filter(([, t]) => t === 'categorical').length;
  const dateCols = Object.entries(d.col_types).filter(([, t]) => t === 'datetime').length;

  const rawMissingPct = d.original_missing > 0
    ? ((d.original_missing / (d.original_rows * d.original_cols)) * 100).toFixed(1) : '0.0';
  const cleanedMissingPct = d.missing_cells > 0
    ? ((d.missing_cells / (d.total_rows * d.total_cols)) * 100).toFixed(1) : '0.0';
  const rowsRemoved = d.original_rows - d.total_rows;

  document.getElementById('kpiGrid').innerHTML = `
    <div class="kpi-card kpi-compare">
      <div class="kpi-compare-label">TOTAL ROWS</div>
      <div class="kpi-compare-row">
        <div class="kpi-half"><div class="kpi-tag raw-tag">RAW</div><div class="kpi-value" style="color:#9ca3af">${d.original_rows.toLocaleString()}</div></div>
        <div class="kpi-divider"></div>
        <div class="kpi-half"><div class="kpi-tag clean-tag">CLEANED</div><div class="kpi-value">${d.total_rows.toLocaleString()}</div></div>
      </div>
      <div class="kpi-sub">${rowsRemoved > 0 ? rowsRemoved + ' rows removed' : 'No rows removed'}</div>
    </div>
    <div class="kpi-card kpi-compare">
      <div class="kpi-compare-label">TOTAL COLUMNS</div>
      <div class="kpi-compare-row">
        <div class="kpi-half"><div class="kpi-tag raw-tag">RAW</div><div class="kpi-value" style="color:#9ca3af">${d.original_cols}</div></div>
        <div class="kpi-divider"></div>
        <div class="kpi-half"><div class="kpi-tag clean-tag">CLEANED</div><div class="kpi-value">${d.total_cols}</div></div>
      </div>
      <div class="kpi-sub">${dateCols} datetime col${dateCols !== 1 ? 's' : ''}</div>
    </div>
    <div class="kpi-card kpi-compare">
      <div class="kpi-compare-label">NUMERIC / CATEGORICAL</div>
      <div class="kpi-compare-row">
        <div class="kpi-half">
          <div class="kpi-tag" style="background:#dbeafe;color:#1e40af;border:1px solid #93c5fd">NUM</div>
          <div class="kpi-value" style="color:#2d6a9f">${numCols}</div>
        </div>
        <div class="kpi-divider"></div>
        <div class="kpi-half">
          <div class="kpi-tag" style="background:#ede9fe;color:#5b21b6;border:1px solid #c4b5fd">CAT</div>
          <div class="kpi-value" style="color:#7c3aed">${catCols}</div>
        </div>
      </div>
    </div>
    <div class="kpi-card kpi-compare">
      <div class="kpi-compare-label">MISSING CELLS</div>
      <div class="kpi-compare-row">
        <div class="kpi-half"><div class="kpi-tag raw-tag">RAW</div><div class="kpi-value" style="color:#9ca3af">${d.original_missing}</div><div style="font-size:10px;color:#9ca3af">${rawMissingPct}%</div></div>
        <div class="kpi-divider"></div>
        <div class="kpi-half"><div class="kpi-tag clean-tag">CLEAN</div><div class="kpi-value" style="color:${d.missing_cells === 0 ? '#166534' : '#92400e'}">${d.missing_cells}</div><div style="font-size:10px;color:#9ca3af">${cleanedMissingPct}%</div></div>
      </div>
    </div>
  `;

  // File info bar
  document.getElementById('fileInfoBar').innerHTML = `
    <div class="file-info-item"><span class="file-info-label">File:</span><span class="file-info-value">${d.filename}</span></div>
    <div class="file-info-item"><span class="file-info-label">Rows:</span><span class="file-info-value">${d.total_rows.toLocaleString()}</span></div>
    <div class="file-info-item"><span class="file-info-label">Cols:</span><span class="file-info-value">${d.total_cols}</span></div>
    <div class="file-info-item"><span class="file-info-label">Quality:</span><span class="file-info-value" style="color:${d.quality_pct >= 90 ? '#166534' : d.quality_pct >= 70 ? '#92400e' : '#991b1b'}">${d.quality_pct}%</span></div>
    <div class="file-info-item" style="margin-left:auto"><span class="file-info-label">Numeric:</span><span class="file-info-value">${numCols}</span></div>
    <div class="file-info-item"><span class="file-info-label">Categorical:</span><span class="file-info-value">${catCols}</span></div>
  `;

  // Quality bar
  const q = d.quality_pct;
  const qClass = q >= 90 ? 'q-good' : q >= 70 ? 'q-warn' : 'q-bad';
  document.getElementById('qualityBar').innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
      <span style="font-size:12px;font-weight:700;color:var(--text)">Data Quality Score</span>
      <span class="qtag ${qClass}">${q}% Complete</span>
    </div>
    <div class="quality-track"><div class="quality-fill" style="width:${q}%"></div></div>
    <div class="quality-tags">
      <span class="qtag ${numCols > 0 ? 'q-good' : 'q-warn'}">${numCols} Numeric Cols</span>
      <span class="qtag ${catCols > 0 ? 'q-good' : 'q-warn'}">${catCols} Categorical Cols</span>
      <span class="qtag ${d.missing_cells === 0 ? 'q-good' : 'q-warn'}">${d.missing_cells} Missing Cells</span>
      <span class="qtag ${dateCols > 0 ? 'q-good' : 'q-bad'}">${dateCols} Datetime Cols</span>
    </div>
  `;

  // Raw preview
  if (d.raw_preview) {
    renderTable(d.raw_preview, d.columns, 'rawPreviewContent', true);
    if (document.getElementById('rawPreviewContentFull'))
      renderTable(d.raw_preview, d.columns, 'rawPreviewContentFull', true);
  }

  // Success bar
  const sb = document.getElementById('uploadSuccessBar');
  sb.style.display = 'flex';
  document.getElementById('uploadSuccessMsg').textContent =
    `${d.filename} — ${d.total_rows.toLocaleString()} rows × ${d.total_cols} cols loaded`;

  document.getElementById('postUpload').classList.remove('hidden');

  // Populate all other sections (guard each call — some elements may not exist on every page)
  if (document.getElementById('previewContent')) {
    renderTable(d.preview, d.columns, 'previewContent', false);
    const previewInfo = document.getElementById('previewInfo');
    if (previewInfo) previewInfo.textContent = `Showing ${(d.preview || []).length} of ${d.total_rows?.toLocaleString() || '?'} rows — klik View All Data untuk lihat semua`;
  }
  if (document.getElementById('statsContent')) renderStats(d, 'statsContent');
  if (document.getElementById('statsNumericContent')) renderStatsToSplit(d);
  if (document.getElementById('typesContent')) renderTypes(d);
  if (document.getElementById('qualityContent')) renderQuality(d);
  if (document.getElementById('insightsContent')) renderInsights(d.insights, 'insightsContent');
  if (document.getElementById('tsContent')) renderTimeSeries(d);
  if (document.getElementById('reportContent')) renderReport(d);

  const statusEl = document.getElementById('statusText');
  if (statusEl) statusEl.textContent = 'Data loaded — ' + d.filename;

  // Update file pill (nd-file-pill) — nama file, rows/cols, badge Loaded
  const fpName = document.getElementById('nd-fp-name');
  const fpMeta = document.getElementById('nd-fp-meta');
  const fpBadge = document.getElementById('nd-fp-badge');
  const fpPill = document.getElementById('nd-file-pill');
  if (fpName) fpName.textContent = d.filename || '—';
  if (fpMeta) fpMeta.textContent = 'Rows: ' + (d.total_rows || 0).toLocaleString() + '  Cols: ' + (d.total_cols || 0);
  if (fpBadge) fpBadge.style.display = 'inline-block';
  if (fpPill) fpPill.style.display = 'flex';

  // Update nd-kpi-* stat cards
  const fmt = function (n) { return n != null ? Number(n).toLocaleString() : '—'; };
  const numCount = d.col_types ? Object.values(d.col_types).filter(t => t === 'numeric').length : 0;
  const catCount = d.col_types ? Object.values(d.col_types).filter(t => t === 'categorical').length : 0;
  const missCount = d.missing_cells != null ? d.missing_cells : 0;
  const el_rows = document.getElementById('nd-kpi-rows'); if (el_rows) el_rows.textContent = fmt(d.total_rows);
  const el_cols = document.getElementById('nd-kpi-cols'); if (el_cols) el_cols.textContent = fmt(d.total_cols);
  const el_num = document.getElementById('nd-kpi-num'); if (el_num) el_num.textContent = numCount;
  const el_cat = document.getElementById('nd-kpi-cat'); if (el_cat) el_cat.textContent = catCount;
  const el_miss = document.getElementById('nd-kpi-miss'); if (el_miss) el_miss.textContent = missCount + (d.quality_pct != null ? ' (' + (100 - d.quality_pct).toFixed(1) + '%)' : '');

  // Enable viz tabs
  const vizTabsEl = document.getElementById('vizTabs');
  if (vizTabsEl) vizTabsEl.style.display = 'flex';
}

/* ── Table Renderer ──────────────────────────────────────── */
function renderTable(rows, columns, containerId, isRaw) {
  const containerEl = document.getElementById(containerId);
  if (!containerEl) return;
  if (!rows || rows.length === 0) {
    containerEl.innerHTML =
      '<div class="empty-state"><div class="empty-icon">⊞</div><div class="empty-title">No data</div></div>';
    return;
  }
  const headers = columns.map(c => `<th>${c}</th>`).join('');
  const bodyRows = rows.map((row, i) => {
    const cells = columns.map(c => {
      const v = row[c];
      if (v === null || v === undefined) {
        return `<td class="${isRaw ? 'raw-null' : 'null-cell'}">NULL</td>`;
      }
      return `<td title="${String(v)}">${String(v)}</td>`;
    }).join('');
    return `<tr><td class="row-num">${i + 1}</td>${cells}</tr>`;
  }).join('');

  containerEl.innerHTML = `
    <div class="table-wrapper">
      <div class="table-toolbar">
        <span style="font-size:12px;font-weight:700;">${isRaw ? 'Raw Data (sebelum cleaning)' : 'Cleaned Data'}</span>
        <span style="font-size:11px;font-family:'Space Mono',monospace;color:var(--text3)">${rows.length} rows shown</span>
      </div>
      <div class="table-scroll">
        <table>
          <thead><tr><th>#</th>${headers}</tr></thead>
          <tbody>${bodyRows}</tbody>
        </table>
      </div>
    </div>
  `;
}

/* ── Stats ───────────────────────────────────────────────── */
function renderStats(d, containerId) {
  let html = '<div class="stats-grid">';
  const numStats = d.num_stats;
  const catStats = d.cat_stats;

  if (numStats && Object.keys(numStats).length > 0) {
    const rows = Object.entries(numStats).map(([col, s]) => {
      const skewClass = Math.abs(s.skewness || 0) > 1 ? 'val-skewness-warn' : 'val-skewness-ok';
      const missClass = s.missing > 0 ? 'val-missing-warn' : 'val-missing-ok';
      const outClass = s.outliers > 0 ? 'val-outlier-warn' : 'val-outlier-ok';
      const normChip = s.is_normal
        ? `<span class="normality-chip norm-normal">Normal</span>`
        : `<span class="normality-chip norm-notnormal">Skewed</span>`;
      return `<tr>
        <td class="col-name">${col}</td>
        <td class="num-val val-mean">${fmt(s.mean)}</td>
        <td class="num-val val-median">${fmt(s.median)}</td>
        <td class="num-val val-min">${fmt(s.min)}</td>
        <td class="num-val val-max">${fmt(s.max)}</td>
        <td class="num-val val-std">${fmt(s.std)}</td>
        <td class="num-val val-mode">${fmt(s.mode)}</td>
        <td class="num-val ${skewClass}">${fmt(s.skewness)}</td>
        <td class="num-val val-kurtosis">${fmt(s.kurtosis)}</td>
        <td class="num-val ${missClass}">${s.missing ?? 0}</td>
        <td class="num-val ${outClass}">${s.outliers ?? 0}</td>
        <td>${normChip}</td>
      </tr>`;
    }).join('');
    html += `
      <div class="stats-card">
        <div class="stats-card-header">
          <span class="stats-card-title">Numerical Variables</span>
          <span class="scbadge badge-num">df.describe()</span>
        </div>
        <div style="overflow-x:auto">
          <table class="stats-table">
            <thead><tr>
              <th>Column</th>
              <th class="th-mean">Mean</th><th class="th-median">Median</th>
              <th class="th-minmax">Min</th><th class="th-minmax">Max</th>
              <th class="th-std">Std</th><th class="th-mode">Mode</th>
              <th class="th-skew">Skewness</th><th class="th-kurt">Kurtosis</th>
              <th class="th-miss">Missing</th><th class="th-out">Outliers</th>
              <th class="th-norm">Normality</th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>`;
  }

  if (catStats && Object.keys(catStats).length > 0) {
    const rows = Object.entries(catStats).map(([col, s]) => `
      <tr>
        <td class="col-name">${col}</td>
        <td class="cat-val">${s.unique}</td>
        <td style="font-size:11px;max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${s.mode}">${s.mode}</td>
        <td class="cat-val">${s.mode_freq}</td>
        <td class="cat-val">${s.mode_pct}%</td>
        <td class="cat-val" style="color:${s.missing === 0 ? '#166534' : '#92400e'}">${s.missing}</td>
        <td class="cat-val" style="color:${s.missing_pct === 0 ? '#166534' : '#92400e'}">${s.missing_pct}%</td>
      </tr>`).join('');
    html += `
      <div class="stats-card">
        <div class="stats-card-header">
          <span class="stats-card-title">Categorical Variables</span>
          <span class="scbadge badge-cat">describe(include="object")</span>
        </div>
        <div style="overflow-x:auto">
          <table class="stats-table">
            <thead><tr>
              <th>Column</th><th>Unique</th><th>Mode</th>
              <th>Mode Freq</th><th>Mode %</th><th>Missing</th><th>Missing %</th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>`;
  }
  html += '</div>';
  const _statsEl = document.getElementById(containerId);
  if (_statsEl) _statsEl.innerHTML = html;
}

function renderStatsToSplit(d) {
  // Guard: elements may not exist yet, skip silently
  if (!document.getElementById('statsNumericContent')) return;
  // Numeric tab
  let htmlNum = '<div class="stats-grid">';
  const numStats = d.num_stats;
  if (numStats && Object.keys(numStats).length > 0) {
    const rows = Object.entries(numStats).map(([col, s]) => {
      const skewClass = Math.abs(s.skewness || 0) > 1 ? 'val-skewness-warn' : 'val-skewness-ok';
      const missClass = s.missing > 0 ? 'val-missing-warn' : 'val-missing-ok';
      const outClass = s.outliers > 0 ? 'val-outlier-warn' : 'val-outlier-ok';
      const normChip = s.is_normal
        ? `<span class="normality-chip norm-normal">Normal</span>`
        : `<span class="normality-chip norm-notnormal">Skewed</span>`;
      return `<tr>
        <td class="col-name">${col}</td>
        <td class="num-val val-mean">${fmt(s.mean)}</td>
        <td class="num-val val-median">${fmt(s.median)}</td>
        <td class="num-val val-min">${fmt(s.min)}</td>
        <td class="num-val val-max">${fmt(s.max)}</td>
        <td class="num-val val-std">${fmt(s.std)}</td>
        <td class="num-val val-mode">${fmt(s.mode)}</td>
        <td class="num-val ${skewClass}">${fmt(s.skewness)}</td>
        <td class="num-val val-kurtosis">${fmt(s.kurtosis)}</td>
        <td class="num-val ${missClass}">${s.missing ?? 0}</td>
        <td class="num-val ${outClass}">${s.outliers ?? 0}</td>
        <td>${normChip}</td>
      </tr>`;
    }).join('');
    htmlNum += `<div class="stats-card"><div class="stats-card-header"><span class="stats-card-title">Numerical Variables</span><span class="scbadge badge-num">df.describe()</span></div><div style="overflow-x:auto"><table class="stats-table"><thead><tr><th>Column</th><th class="th-mean">Mean</th><th class="th-median">Median</th><th class="th-minmax">Min</th><th class="th-minmax">Max</th><th class="th-std">Std</th><th class="th-mode">Mode</th><th class="th-skew">Skewness</th><th class="th-kurt">Kurtosis</th><th class="th-miss">Missing</th><th class="th-out">Outliers</th><th class="th-norm">Normality</th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
  } else {
    htmlNum += '<div class="empty-state"><div class="empty-icon">√</div><div class="empty-title">No numeric columns found</div></div>';
  }
  htmlNum += '</div>';
  const numEl = document.getElementById('statsNumericContent');
  if (numEl) numEl.innerHTML = htmlNum;
  else console.warn('statsNumericContent not found');

  // Categorical tab
  let htmlCat = '<div class="stats-grid">';
  const catStats = d.cat_stats;
  if (catStats && Object.keys(catStats).length > 0) {
    const rows = Object.entries(catStats).map(([col, s]) => `
      <tr>
        <td class="col-name">${col}</td>
        <td class="cat-val">${s.unique}</td>
        <td style="font-size:11px;max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${s.mode}">${s.mode}</td>
        <td class="cat-val">${s.mode_freq}</td>
        <td class="cat-val">${s.mode_pct}%</td>
        <td class="cat-val" style="color:${s.missing === 0 ? '#166534' : '#92400e'}">${s.missing}</td>
        <td class="cat-val" style="color:${s.missing_pct === 0 ? '#166534' : '#92400e'}">${s.missing_pct}%</td>
      </tr>`).join('');
    htmlCat += `<div class="stats-card"><div class="stats-card-header"><span class="stats-card-title">Categorical Variables</span><span class="scbadge badge-cat">describe(include="object")</span></div><div style="overflow-x:auto"><table class="stats-table"><thead><tr><th>Column</th><th>Unique</th><th>Mode</th><th>Mode Freq</th><th>Mode %</th><th>Missing</th><th>Missing %</th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
  } else {
    htmlCat += '<div class="empty-state"><div class="empty-icon">◫</div><div class="empty-title">No categorical columns found</div></div>';
  }
  htmlCat += '</div>';
  const catEl = document.getElementById('statsCategoricalContent');
  if (catEl) catEl.innerHTML = htmlCat;
}

function fmt(v) {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'number') return Number.isInteger(v) ? v.toLocaleString() : v.toFixed(4);
  return v;
}

/* ── Types ───────────────────────────────────────────────── */
function renderTypes(d) {
  const colors = { numeric: '#1e40af', categorical: '#6d28d9', datetime: '#1a7a3c', boolean: '#c2410c' };
  const bgPill = { numeric: '#eff6ff', categorical: '#f5f3ff', datetime: '#e8f5ed', boolean: '#fff7ed' };
  const labelMap = { numeric: 'Numeric', categorical: 'Categorical', datetime: 'DateTime', boolean: 'Boolean' };
  const tsColNames = (d.ts_cols || []).map(t => t.col);

  // Summary pill row
  const summary = {};
  Object.values(d.col_types).forEach(t => summary[t] = (summary[t] || 0) + 1);
  const tsb = document.getElementById('typeSummaryBar');
  if (tsb) {
    const pills = Object.entries(summary).map(([t, cnt]) =>
      `<span style="display:inline-flex;align-items:center;gap:5px;background:${bgPill[t] || '#f3f4f6'};` +
      `color:${colors[t] || '#374151'};border:1px solid ${colors[t] || '#d1d5db'}44;` +
      `padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600;margin-right:6px;">` +
      `<span style="width:8px;height:8px;border-radius:50%;background:${colors[t] || '#9ca3af'};display:inline-block;"></span>` +
      `${cnt} ${labelMap[t] || t}</span>`).join('');
    tsb.innerHTML = `<div style="margin-bottom:10px;">${pills}</div>`;
  }

  // Table
  const rows = d.columns.map((col, idx) => {
    const t = d.col_types[col] || 'categorical';
    const isTS = tsColNames.includes(col);
    const qInfo = d.col_quality ? d.col_quality.find(c => c.column === col) : null;
    const uniquePct = qInfo ? qInfo.unique_pct.toFixed(1) : '—';
    const uniqueCnt = qInfo ? qInfo.unique : '—';
    const missPct = qInfo ? qInfo.missing_pct.toFixed(1) : '—';
    const missCnt = qInfo ? qInfo.missing : '—';
    const rowBg = idx % 2 === 0 ? '#fafafa' : '#fff';
    const tLabel = labelMap[t] || t;
    const tsTag = isTS ? ' <span style="color:#1a7a3c;font-size:9px;font-weight:700;">[TS]</span>' : '';
    const missColor = missCnt > 0 ? '#dc2626' : '#22c55e';
    return `<tr style="background:${rowBg}">` +
      `<td style="padding:6px 10px;font-size:11px;color:#374151;font-family:monospace;">${col}${tsTag}</td>` +
      `<td style="padding:6px 10px;"><span style="display:inline-block;background:${bgPill[t] || '#f3f4f6'};color:${colors[t] || '#374151'};` +
      `border:1px solid ${colors[t] || '#d1d5db'}44;padding:2px 8px;border-radius:12px;font-size:10px;font-weight:700;">${tLabel}</span></td>` +
      `<td style="padding:6px 10px;font-size:11px;color:#6b7280;text-align:center;">${uniqueCnt}</td>` +
      `<td style="padding:6px 10px;font-size:11px;color:#6b7280;text-align:center;">${uniquePct}%</td>` +
      `<td style="padding:6px 10px;font-size:11px;color:${missColor};text-align:center;">${missCnt}</td>` +
      `<td style="padding:6px 10px;font-size:11px;color:${missColor};text-align:center;">${missPct}%</td>` +
      `</tr>`;
  }).join('');

  const tcEl = document.getElementById('typesContent');
  if (tcEl) tcEl.innerHTML =
    `<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:11px;">` +
    `<thead><tr style="background:#f0f5f2;">` +
    `<th style="padding:7px 10px;text-align:left;color:#1a3a28;font-weight:700;border-bottom:2px solid #c8e6d4;">Column Name</th>` +
    `<th style="padding:7px 10px;text-align:left;color:#1a3a28;font-weight:700;border-bottom:2px solid #c8e6d4;">Detected Type</th>` +
    `<th style="padding:7px 10px;text-align:center;color:#1a3a28;font-weight:700;border-bottom:2px solid #c8e6d4;">Unique Count</th>` +
    `<th style="padding:7px 10px;text-align:center;color:#1a3a28;font-weight:700;border-bottom:2px solid #c8e6d4;">Unique %</th>` +
    `<th style="padding:7px 10px;text-align:center;color:#1a3a28;font-weight:700;border-bottom:2px solid #c8e6d4;">Missing</th>` +
    `<th style="padding:7px 10px;text-align:center;color:#1a3a28;font-weight:700;border-bottom:2px solid #c8e6d4;">Missing %</th>` +
    `</tr></thead><tbody>${rows}</tbody></table></div>`;
}
/* ── Quality ─────────────────────────────────────────────── */
function renderQuality(d) {
  // Overview cards
  const totalMissing = d.col_quality.reduce((s, c) => s + c.missing, 0);
  const totalCells = d.total_rows * d.total_cols;
  const qualPct = d.quality_pct || (totalMissing === 0 ? 100 : Math.round((1 - totalMissing / totalCells) * 100));
  const numCols = Object.values(d.col_types || {}).filter(t => t === 'numeric').length;
  const catCols = Object.values(d.col_types || {}).filter(t => t === 'categorical').length;
  const missingCols = d.col_quality.filter(c => c.missing > 0).length;

  const qovEl = document.getElementById('qualityOverview');
  if (qovEl) qovEl.innerHTML = `
    <div class="quality-overview" style="margin-bottom:20px;">
      <div class="qov-card qov-green"><div class="qov-val">${qualPct}%</div><div class="qov-lbl">Data Quality</div></div>
      <div class="qov-card qov-blue"><div class="qov-val">${d.total_rows.toLocaleString()}</div><div class="qov-lbl">Total Rows</div></div>
      <div class="qov-card qov-purple"><div class="qov-val">${d.total_cols}</div><div class="qov-lbl">Columns</div></div>
      <div class="qov-card qov-orange"><div class="qov-val">${missingCols}</div><div class="qov-lbl">Has Missing</div></div>
    </div>`;

  // Quality track
  const trackColor = qualPct >= 90 ? '#22a854' : qualPct >= 70 ? '#f59e0b' : '#ef4444';

  const rows = d.col_quality.map(c => {
    const missClass = c.missing === 0 ? 'miss-ok' : c.missing_pct > 30 ? 'miss-bad' : 'miss-warn';
    const missLabel = c.missing === 0
      ? '<span class="qtag q-good">Complete</span>'
      : `<span class="qtag q-${c.missing_pct > 30 ? 'bad' : 'warn'}">${c.missing_pct}% missing</span>`;
    return `<tr>
      <td><span style="font-weight:700;color:var(--text)">${c.column}</span></td>
      <td><span class="col-type type-${c.type === 'datetime' ? 'date' : c.type}">${c.type}</span></td>
      <td style="font-family:'JetBrains Mono',monospace;font-size:11px">${c.count.toLocaleString()}</td>
      <td>${missLabel}</td>
      <td style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text2)">${c.unique.toLocaleString()}</td>
      <td>
        <div class="miss-bar-wrap">
          <div class="miss-bar-track">
            <div class="miss-bar-fill ${missClass}" style="width:${100 - c.missing_pct}%"></div>
          </div>
          <span class="miss-pct">${(100 - c.missing_pct).toFixed(1)}%</span>
        </div>
      </td>
    </tr>`;
  }).join('');

  const qcEl = document.getElementById('qualityContent');
  if (qcEl) qcEl.innerHTML = `
    <div style="background:var(--surface2);border-radius:8px;padding:12px 16px;margin-bottom:16px;display:flex;align-items:center;gap:12px;">
      <span style="font-size:12px;font-weight:600;color:var(--text2)">Overall Quality</span>
      <div style="flex:1;height:8px;background:var(--surface3);border-radius:4px;overflow:hidden;">
        <div style="width:${qualPct}%;height:100%;background:${trackColor};border-radius:4px;transition:width 0.8s;"></div>
      </div>
      <span style="font-size:13px;font-weight:800;font-family:'JetBrains Mono',monospace;color:${trackColor}">${qualPct}%</span>
    </div>
    <div class="quality-table-wrap">
      <table class="quality-table">
        <thead><tr><th>Column</th><th>Type</th><th>Rows</th><th>Missing Status</th><th>Unique</th><th>Completeness</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}
/* ── Insights ────────────────────────────────────────────── */
function renderInsights(insights, containerId) {
  const insEl = document.getElementById(containerId);
  if (!insEl) return;
  if (!insights || insights.length === 0) {
    insEl.innerHTML = '<div class="empty-state"><div class="empty-icon">✦</div><div class="empty-title">No insights available</div></div>';
    return;
  }
  const typeColors = { info: '#2d6a9f', success: '#059669', warning: '#d97706', error: '#dc2626' };
  const typeBg = { info: '#eff6ff', success: '#ecfdf5', warning: '#fffbeb', error: '#fef2f2' };
  const cards = insights.map(ins => `
    <div class="insight-card" style="border-left:4px solid ${typeColors[ins.type] || '#aaa'};background:${typeBg[ins.type] || '#f5f5f5'}">
      <span class="insight-icon">${ins.icon || '•'}</span>
      <div>
        <div class="insight-title">${ins.title || ''}</div>
        <div class="insight-body">${ins.message}</div>
      </div>
    </div>`).join('');
  insEl.innerHTML = `<div style="display:grid;gap:10px;">${cards}</div>`;
}

/* ── Visualizations ──────────────────────────────────────── */
// ── State untuk lazy loading ──────────────────────────────────
const _vizLoaded = { numerical: false, categorical: false, bivariate: false, catnum: false };
let _vizInfo = null;

function loadVisualizations() {
  if (!state.filename) { alert('Please upload a file first.'); return; }
  showSection('viz');
  _vizInfo = null;
  // Fetch info dulu (ringan, tidak generate chart)
  fetch('/visualize/info', { method: 'POST' })
    .then(r => r.json())
    .then(d => {
      if (d.error) { alert(d.error); return; }
      _vizInfo = d;
      document.getElementById('vizTabs').style.display = 'flex';
      filterViz('all');
    })
    .catch(err => alert('Error: ' + err));
}

// ── Plotly helpers ────────────────────────────────────────────
let _plotlyLoaded = false;
function ensurePlotly(cb) {
  if (window.Plotly) { cb(); return; }
  if (_plotlyLoaded) { setTimeout(() => ensurePlotly(cb), 50); return; }
  _plotlyLoaded = true;
  const s = document.createElement('script');
  s.src = 'https://cdn.plot.ly/plotly-2.32.0.min.js';
  s.onload = cb;
  document.head.appendChild(s);
}

let _chartIdCounter = 0;
function plotlyCard(title, figData, wide) {
  if (!figData) return '';
  const id = 'plt_' + (++_chartIdCounter);
  const wideClass = wide ? ' viz-wide' : '';
  // Store figData on window to render after DOM insert
  window._pendingPlots = window._pendingPlots || {};
  window._pendingPlots[id] = figData;
  return `<div class="viz-card${wideClass}">
    <div class="viz-card-header">${title}</div>
    <div id="${id}" style="width:100%;height:300px;"></div>
  </div>`;
}

function flushPlotly() {
  ensurePlotly(() => {
    const pending = window._pendingPlots || {};
    const cfg = {
      responsive: true, displayModeBar: true,
      modeBarButtonsToRemove: ['lasso2d', 'select2d'],
      displaylogo: false
    };
    Object.entries(pending).forEach(([id, fig]) => {
      const el = document.getElementById(id);
      if (el && fig) Plotly.newPlot(el, fig.data || [], fig.layout || {}, cfg);
    });
    window._pendingPlots = {};
  });
}

// ── SLIDE STATE ──────────────────────────────────────────────
const _slides = {};  // key: slideId -> { figs: [{title, figData}], current: 0 }

function buildSlide(slideId, label, badge, figs) {
  // figs: array of {title, figData}
  const validFigs = figs.filter(f => f.figData);
  if (validFigs.length === 0) return '';
  _slides[slideId] = { figs: validFigs, current: 0 };
  return `
  <div class="slide-wrapper" id="slide_${slideId}">
    <div class="slide-header">
      <span class="slide-label">${label}</span>
      <span class="viz-section-badge">${badge}</span>
      <span class="slide-counter" id="sc_${slideId}">1 / ${validFigs.length}</span>
    </div>
    <div class="slide-chart-area">
      <button class="slide-btn slide-btn-prev" onclick="slideNav('${slideId}',-1)">&#8249;</button>
      <div class="slide-chart" id="sc_chart_${slideId}">
        <div class="slide-chart-title" id="sc_title_${slideId}">${validFigs[0].title}</div>
        <div id="sc_plot_${slideId}" style="width:100%;height:${Math.max(420, (validFigs[0].figData?.layout?.height || 420))}px;"></div>
      </div>
      <button class="slide-btn slide-btn-next" onclick="slideNav('${slideId}',1)">&#8250;</button>
    </div>
    <div class="slide-dots" id="sd_${slideId}">
      ${validFigs.map((f, i) => `<span class="slide-dot ${i === 0 ? 'active' : ''}" onclick="slideTo('${slideId}',${i})" title="${f.title}"></span>`).join('')}
    </div>
  </div>`;
}

function slideNav(id, dir) {
  const s = _slides[id]; if (!s) return;
  slideTo(id, (s.current + dir + s.figs.length) % s.figs.length);
}

function slideTo(id, idx) {
  const s = _slides[id]; if (!s) return;
  s.current = idx;
  // Update title
  document.getElementById('sc_title_' + id).textContent = s.figs[idx].title;
  // Update counter
  document.getElementById('sc_' + id).textContent = (idx + 1) + ' / ' + s.figs.length;
  // Update dots
  document.querySelectorAll('#sd_' + id + ' .slide-dot').forEach((d, i) => d.classList.toggle('active', i === idx));
  // Render plotly
  const el = document.getElementById('sc_plot_' + id);
  if (el && s.figs[idx].figData) {
    // Adjust height for this slide's chart
    const h = s.figs[idx].figData?.layout?.height;
    if (h) el.style.height = Math.max(420, h) + 'px';
    ensurePlotly(() => {
      const cfg = {
        responsive: true, displayModeBar: true,
        modeBarButtonsToRemove: ['lasso2d', 'select2d'], displaylogo: false
      };
      Plotly.react(el, s.figs[idx].figData.data || [], s.figs[idx].figData.layout || {}, cfg);
    });
  }
}

function flushSlides() {
  ensurePlotly(() => {
    const cfg = {
      responsive: true, displayModeBar: true,
      modeBarButtonsToRemove: ['lasso2d', 'select2d'], displaylogo: false
    };
    Object.entries(_slides).forEach(([id, s]) => {
      const el = document.getElementById('sc_plot_' + id);
      if (el && s.figs[0]?.figData)
        Plotly.newPlot(el, s.figs[0].figData.data || [], s.figs[0].figData.layout || {}, cfg);
    });
  });
}

// ── THUMBNAIL GRID VISUALIZATION SYSTEM ─────────────────────
// Stores all fig data keyed by thumbId for modal expand
window._thumbFigs = {};
let _thumbIdCounter = 0;

function buildThumbId() { return 'th_' + (++_thumbIdCounter); }

function buildThumbCard(label, figData) {
  if (!figData) return '';
  const id = buildThumbId();
  window._thumbFigs[id] = { label, figData };

  const dashIdx = label.indexOf(' — ');
  const chartType = dashIdx > -1 ? label.slice(0, dashIdx) : label;
  const colName = dashIdx > -1 ? label.slice(dashIdx + 3) : '';

  // Baris atas: ALL CAPS seperti PDF  e.g. "HISTOGRAM — UNIT_PRICE"
  const topText = (colName ? chartType + ' — ' + colName : chartType).toUpperCase();

  // Baris bawah: "Histogram — unit_price" dengan nama kolom bold hijau
  const bottomHtml = colName
    ? `${chartType} — <span class="th-col">${colName}</span>`
    : `<span class="th-col">${chartType}</span>`;

  return `<div class="thumb-card" onclick="openVizModal('${id}')" title="${label}">
    <div class="thumb-header">
      <div class="thumb-header-top">${topText}</div>
      <div class="thumb-header-bottom">${bottomHtml}</div>
    </div>
    <div class="thumb-plot" id="${id}"></div>
    <div class="thumb-expand-hint">🔍 Klik untuk perbesar</div>
  </div>`;
}

function buildCategorySection(title, badge, badgeColor, thumbsHtml, totalCount, extraHtml) {
  if (!thumbsHtml && !extraHtml) return '';
  return `<div class="viz-category-section">
    <div class="viz-cat-header">
      <div class="viz-cat-title-group">
        <span class="viz-cat-badge" style="background:${badgeColor}">${badge}</span>
        <span class="viz-cat-title">${title}</span>
      </div>
      <span class="viz-cat-count">${totalCount} chart${totalCount > 1 ? 's' : ''}</span>
    </div>
    ${extraHtml || ''}
    ${thumbsHtml ? `<div class="thumb-grid">
      ${thumbsHtml}
    </div>` : ''}
  </div>`;
}

// ── CUSTOM VISUALIZATION SELECTOR (pengguna pilih variabel sendiri) ──
// Definisi tiap chart: fields yang harus dipilih user, jenis kolom, label
const CUSTOM_CHART_DEFS = {
  numerical: [
    { key: 'histogram', label: 'Histogram',   fields: [{ name: 'col', label: 'Kolom Numerik', type: 'num' }] },
    { key: 'box',       label: 'Box Plot',    fields: [{ name: 'col', label: 'Kolom Numerik', type: 'num' }] },
    { key: 'violin',    label: 'Violin Plot', fields: [{ name: 'col', label: 'Kolom Numerik', type: 'num' }] },
    { key: 'density',   label: 'Density Plot',fields: [{ name: 'col', label: 'Kolom Numerik', type: 'num' }] },
    { key: 'qqplot',    label: 'QQ Plot',     fields: [{ name: 'col', label: 'Kolom Numerik', type: 'num' }] },
  ],
  
  categorical: [
    { key: 'barchart', label: 'Bar Chart', fields: [{ name: 'col', label: 'Kolom Kategorik', type: 'cat' }] },
    { key: 'piechart', label: 'Pie Chart', fields: [{ name: 'col', label: 'Kolom Kategorik', type: 'cat' }] },
    { key: 'countplot', label: 'Count Plot', fields: [{ name: 'col', label: 'Kolom Kategorik', type: 'cat' }] },
    { key: 'pareto', label: 'Pareto Chart', fields: [{ name: 'col', label: 'Kolom Kategorik', type: 'cat' }] },
  ],
  bivariate: [
    { key: 'scatter', label: 'Scatter Plot', fields: [{ name: 'cx', label: 'Kolom X (Numerik)', type: 'num' }, { name: 'cy', label: 'Kolom Y (Numerik)', type: 'num' }] },
    { key: 'regression', label: 'Regression Plot', fields: [{ name: 'cx', label: 'Kolom X (Numerik)', type: 'num' }, { name: 'cy', label: 'Kolom Y (Numerik)', type: 'num' }] },
    { key: 'bubble', label: 'Bubble Chart', fields: [{ name: 'cx', label: 'Kolom X (Numerik)', type: 'num' }, { name: 'cy', label: 'Kolom Y (Numerik)', type: 'num' }, { name: 'cs', label: 'Kolom Size (Numerik)', type: 'num' }] },
    { key: 'heatmap', label: 'Correlation Heatmap', fields: [{ name: 'col_x', label: 'Kolom X (Numerik)', type: 'num' }, { name: 'col_y', label: 'Kolom Y (Numerik)', type: 'num' }] },
    { key: 'pairplot', label: 'Pair Plot', fields: [{ name: 'num_cols', label: 'Kolom Numerik (2-4)', type: 'num_multi' }] },
  ],
  catnum: [
    { key: 'box_violin_by_cat', label: 'Box + Violin by Category', fields: [{ name: 'nc', label: 'Kolom Numerik', type: 'num' }, { name: 'cc', label: 'Kolom Kategorik', type: 'cat' }] },
    { key: 'grouped_bar', label: 'Grouped Bar Chart', fields: [{ name: 'nc', label: 'Kolom Numerik', type: 'num' }, { name: 'cc', label: 'Kolom Kategorik', type: 'cat' }] },
    { key: 'strip_plot', label: 'Strip Plot', fields: [{ name: 'nc', label: 'Kolom Numerik', type: 'num' }, { name: 'cc', label: 'Kolom Kategorik', type: 'cat' }] },
  ],
  pdf_report: [
    { key: 'histogram',   label: 'Histogram (Numerik)',    fields: [{ name: 'cols', label: 'Kolom Numerik', type: 'num_multi' }] },
    { key: 'bar',         label: 'Bar Chart (Kategorik)',  fields: [{ name: 'cols', label: 'Kolom Kategorik', type: 'cat_multi' }] },
    { key: 'scatter',     label: 'Scatter Matrix',         fields: [{ name: 'cols', label: 'Kolom Numerik (min 2)', type: 'num_multi' }] },
    { key: 'heatmap',     label: 'Correlation Heatmap',    fields: [{ name: 'cols', label: 'Kolom Numerik (min 2)', type: 'num_multi' }] },
    { key: 'grouped_bar', label: 'Grouped Bar Chart',      fields: [{ name: 'nc', label: 'Kolom Numerik', type: 'num' }, { name: 'cc', label: 'Kolom Kategorik', type: 'cat' }] },
  ],
};


function _customFieldOptions(type, numCols, catCols) {
  if (type === 'num' || type === 'num_multi') return numCols;
  if (type === 'cat' || type === 'cat_multi') return catCols;
  return [];
}


// Mapping dari (tab, chartKey lama) -> key di CUSTOM_CHART_DEFS
const SINGLE_CHART_KEY_MAP = {
  numerical:   { histogram: 'histogram', box: 'box', violin: 'violin', density: 'density', qqplot: 'qqplot' },
  categorical: { bar: 'barchart', pie: 'piechart', count: 'countplot', pareto: 'pareto' },
  bivariate: { scatter: 'scatter', heatmap: 'heatmap', pairplot: 'pairplot', regression: 'regression', bubble: 'bubble' },
  catnum: { box_violin_by_cat: 'box_violin_by_cat', grouped_bar: 'grouped_bar', strip_plot: 'strip_plot' },
};

function buildCustomPanel(category, selectedKey) {
  if (!_vizInfo) return '';
  const numCols = _vizInfo.all_num_cols || [];
  const catCols = _vizInfo.all_cat_cols || [];
  const defs = CUSTOM_CHART_DEFS[category] || [];
  if (!defs.length) return '';

  // Filter chart yang field-nya bisa dipenuhi (cukup kolom tersedia)
  let usable = defs.filter(d => d.fields.every(f => {
    const opts = _customFieldOptions(f.type, numCols, catCols);
    if (f.type === 'num_multi') return opts.length >= 2;
    return opts.length >= 1;
  }));
  if (!usable.length) return '';

  // Kalau ada selectedKey (dari sidebar), tampilkan hanya chart itu saja
  if (selectedKey) {
    const found = usable.find(d => d.key === selectedKey);
    if (found) usable = [found];
  }

  return usable.map(chartDef => `<div class="viz-custom-panel" id="custom-panel-${category}-${chartDef.key}">
    <div class="viz-custom-panel-title"> ${chartDef.label} </div>
    <div class="viz-custom-row">
      <div id="custom-${category}-${chartDef.key}-fields" class="viz-custom-row" style="flex:1;">
        ${buildCustomFieldsHtml(category, chartDef, numCols, catCols)}
      </div>
      <button class="viz-custom-generate-btn" id="custom-${category}-${chartDef.key}-btn" onclick="generateCustomChart('${category}', '${chartDef.key}')" disabled>▶ Generate</button>
    </div>
    <div class="viz-custom-result" id="custom-${category}-${chartDef.key}-result"></div>
  </div>`).join('');
}

function buildCustomFieldsHtml(category, chartDef, numCols, catCols) {
  const onchangeAttr = `onchange="updateGenerateBtnState('${category}','${chartDef.key}')"`;
  return chartDef.fields.map(f => {
    const opts = _customFieldOptions(f.type, numCols, catCols);
    const fieldId = `custom-${category}-${chartDef.key}-${f.name}`;

 if (f.type === 'num_multi' || f.type === 'cat_multi') {
  const optsHtml = opts.map(c => `<option value="${c}">${c}</option>`).join('');
  const makeSelect = (idx, required) => `
    <div class="viz-custom-field">
      <label>${f.label} ${idx} ${required ? '' : '<span style="color:var(--text3);font-weight:400;">(opsional)</span>'}</label>
      <select id="${fieldId}_${idx}" data-field="${f.name}" ${onchangeAttr}>
        <option value="" selected ${required ? 'disabled' : ''}>— Pilih kolom —</option>
        ${optsHtml}
      </select>
    </div>`;
  return makeSelect(1, true) + makeSelect(2, true) + makeSelect(3, false) + makeSelect(4, false);
}

    const optsHtml = opts.map(c => `<option value="${c}">${c}</option>`).join('');
    return `<div class="viz-custom-field">
      <label>${f.label}</label>
      <select id="${fieldId}" data-field="${f.name}" ${onchangeAttr}>
        <option value="" selected disabled>— Pilih kolom —</option>
        ${optsHtml}
      </select>
    </div>`;
  }).join('');
}


function updateGenerateBtnState(category, chartKey) {
  const chartDef = (CUSTOM_CHART_DEFS[category] || []).find(d => d.key === chartKey);
  const btn = document.getElementById(`custom-${category}-${chartKey}-btn`);
  if (!chartDef || !btn) return;
  const allFilled = chartDef.fields.every(f => {
    if (f.type === 'num_multi' || f.type === 'cat_multi') {
      const el1 = document.getElementById(`custom-${category}-${chartKey}-${f.name}_1`);
      const el2 = document.getElementById(`custom-${category}-${chartKey}-${f.name}_2`);
      return el1 && el2 && !!el1.value && !!el2.value;
    }
    const el = document.getElementById(`custom-${category}-${chartKey}-${f.name}`);
    if (!el) return false;
    return !!el.value;
  });
  btn.disabled = !allFilled;
}

function generateCustomChart(category, chartKey) {
  const chartDef = (CUSTOM_CHART_DEFS[category] || []).find(d => d.key === chartKey);
  if (!chartDef) return;

 const payload = { chart_type: chartKey };
  for (const f of chartDef.fields) {
    const fieldId = `custom-${category}-${chartDef.key}-${f.name}`;
    if (f.type === 'num_multi' || f.type === 'cat_multi') {
      const cols = [1,2,3,4]
        .map(i => document.getElementById(fieldId + '_' + i)?.value)
        .filter(Boolean);
      payload[f.name] = cols;
    } else {
      const el = document.getElementById(fieldId);
      if (!el) continue;
      payload[f.name] = el.value;
    }
  }

  // Konversi heatmap: col_x + col_y → num_cols array
  if (chartKey === 'heatmap' && payload.col_x && payload.col_y) {
    payload.num_cols = [payload.col_x, payload.col_y];
    delete payload.col_x;
    delete payload.col_y;
  }

  const resultEl = document.getElementById(`custom-${category}-${chartKey}-result`);
  resultEl.innerHTML = '<div style="text-align:center;padding:24px;color:#2d6a9f;font-size:12px;">⏳ Membuat visualisasi...</div>';


  fetch('/visualize/custom', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
    .then(r => r.json())
    .then(d => {
      if (d.error) {
        resultEl.innerHTML = `<div class="viz-custom-error">⚠ ${d.error}</div>`;
        return;
      }
      const plotId = `custom_plot_${category}_${++_chartIdCounter}`;
      // Pairplot & heatmap dengan banyak kolom butuh tinggi lebih besar
      const baseH = (d.chart.layout && d.chart.layout.height) ? d.chart.layout.height : 460;
      const plotHeight = Math.max(460, baseH);
      resultEl.innerHTML = `
        <div class="viz-custom-result-header">${d.label}</div>
        <div class="viz-custom-plot-wrap">
          <div id="${plotId}" style="width:100%;height:${plotHeight}px;"></div>
        </div>`;
      ensurePlotly(() => {
        const cfg = { responsive: true, displayModeBar: true, modeBarButtonsToRemove: ['lasso2d', 'select2d'], displaylogo: false };
        const origMargin = (d.chart.layout && d.chart.layout.margin) || {};
        const layout = Object.assign({}, d.chart.layout || {}, {
          height: plotHeight,
          paper_bgcolor: 'rgba(0,0,0,0)',
          plot_bgcolor: 'rgba(0,0,0,0)',
          margin: Object.assign({ l: 50, r: 30, t: 50, b: 70 }, origMargin, { b: Math.max(origMargin.b || 0, 70) }),
        });
        Plotly.newPlot(plotId, d.chart.data || [], layout, cfg);
      });
    })
    .catch(err => {
      resultEl.innerHTML = `<div class="viz-custom-error">⚠ Error: ${err.message}</div>`;
    });
}

const CATEGORY_META = {
  numerical: { title: 'Numerical (Univariate)', badge: 'NUMERICAL', color: '#2563eb' },
  categorical: { title: 'Categorical (Univariate)', badge: 'CATEGORICAL', color: '#7c3aed' },
  bivariate: { title: 'Numerical vs Numerical (Bivariate)', badge: 'BIVARIATE', color: '#059669' },
  catnum: { title: 'Categorical vs Numerical', badge: 'CAT×NUM', color: '#d97706' },
};

/* Render hanya panel "pilih variabel + Generate" untuk satu/semua kategori.
   Tidak ada chart yang otomatis muncul — chart baru render setelah klik Generate. */
function renderVisualizations(charts, filter, presetKey) {
  _chartIdCounter = 0;
  let html = '';
  const showAll = !filter || filter === 'all';
  const categories = showAll ? Object.keys(CATEGORY_META) : [filter];

  categories.forEach(cat => {
    const meta = CATEGORY_META[cat];
    if (!meta) return;
    const selectedKey = (filter === cat) ? presetKey : undefined;
    const panel = buildCustomPanel(cat, selectedKey);
    if (!panel) return;
    html += `<div class="viz-category-section">
      <div class="viz-cat-header">
        <div class="viz-cat-title-group">
          <span class="viz-cat-badge" style="background:${meta.color}">${meta.badge}</span>
          <span class="viz-cat-title">${meta.title}</span>
        </div>
      </div>
      ${panel}
    </div>`;
  });

  if (!html) html = '<div class="empty-state"><div class="empty-icon">▦</div><div class="empty-title">Not enough columns to visualize</div></div>';
  document.getElementById('vizContent').innerHTML = html;
}

// ── VIZ MODAL ───────────────────────────────────────────────
function openVizModal(thumbId) {
  const obj = window._thumbFigs[thumbId];
  if (!obj) return;
  let modal = document.getElementById('vizModal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'vizModal';
    modal.className = 'viz-modal-overlay';
    modal.innerHTML = `
      <div class="viz-modal-box">
        <div class="viz-modal-header">
          <span class="viz-modal-title" id="vizModalTitle"></span>
          <button class="viz-modal-close" onclick="closeVizModal()">✕</button>
        </div>
        <div id="vizModalPlot" style="width:100%;height:520px;"></div>
      </div>`;
    modal.addEventListener('click', e => { if (e.target === modal) closeVizModal(); });
    document.body.appendChild(modal);
  }
  document.getElementById('vizModalTitle').textContent = obj.label;
  modal.style.display = 'flex';
  document.body.style.overflow = 'hidden';
  const plotEl = document.getElementById('vizModalPlot');
  plotEl.innerHTML = '';
  ensurePlotly(() => {
    const fig = obj.figData;
    const layout = Object.assign({}, fig.layout || {}, {
      height: 500,
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      autosize: true,
      margin: { t: 40, b: 60, l: 60, r: 30 },
    });
    Plotly.newPlot(plotEl, fig.data || [], layout,
      { responsive: true, displayModeBar: true, modeBarButtonsToRemove: ['lasso2d', 'select2d'], displaylogo: false });
  });
}

function closeVizModal() {
  const modal = document.getElementById('vizModal');
  if (modal) modal.style.display = 'none';
  document.body.style.overflow = '';
}
function filterViz(tab) {
  if (!state.filename) { alert('Upload file dulu!'); return; }
  if (!_vizInfo) {
    fetch('/visualize/info', { method: 'POST' })
      .then(r => r.json())
      .then(d => {
        if (d.error) { alert(d.error); return; }
        _vizInfo = d;
        document.getElementById('vizTabs').style.display = 'flex';
        filterViz(tab);
      })
      .catch(err => alert('Error: ' + err));
    return;
  }
  document.querySelectorAll('.viz-tab').forEach(t => t.classList.remove('active'));
  const el = document.getElementById('vtab-' + tab);
  if (el) el.classList.add('active');
  renderVisualizations(state.charts, tab);
}

/* ── showVizChart: tampilkan panel pilih variabel untuk SATU jenis chart ── */
function showVizChart(tab, chartKey, clickedEl) {
  if (!state.filename) { alert('Upload file dulu!'); return; }
  showSection('viz');

  // Highlight sidebar item
  document.querySelectorAll('.nav-sub-item').forEach(el => el.classList.remove('active'));
  if (clickedEl) clickedEl.classList.add('active');
  document.querySelectorAll('.viz-tab').forEach(t => t.classList.remove('active'));

  const mappedKey = (SINGLE_CHART_KEY_MAP[tab] || {})[chartKey];

  const doRender = () => {
    renderVisualizations(state.charts, tab, mappedKey);
  };

  if (!_vizInfo) {
    fetch('/visualize/info', { method: 'POST' })
      .then(r => r.json())
      .then(d => {
        if (d.error) { alert(d.error); return; }
        _vizInfo = d;
        document.getElementById('vizTabs').style.display = 'flex';
        doRender();
      })
      .catch(err => alert('Error: ' + err));
  } else {
    doRender();
  }
}

/* ── Time Series ─────────────────────────────────────────── */
function renderTimeSeries(d) {
  const container = document.getElementById('tsContent');
  if (!container) return;
  const dateCols = Object.entries(d.col_types || {}).filter(([, t]) => t === 'datetime').map(([c]) => c);
  const numCols = Object.entries(d.col_types || {}).filter(([, t]) => t === 'numeric').map(([c]) => c);

  if (dateCols.length === 0) {
    container.innerHTML = `<div class="empty-state"><div class="empty-icon">⏱</div><div class="empty-title">No Date column detected</div><div class="empty-sub">Upload dataset yang mengandung kolom tanggal untuk mengaktifkan Time Series analytics.</div></div>`;
    return;
  }
  const opts = dateCols.map(c => `<option value="${c}">${c}</option>`).join('');
  const numOpts = numCols.map(c => `<option value="${c}">${c}</option>`).join('');
  container.innerHTML = `
    <div class="ts-banner">⏱ Time Series terdeteksi — kolom tanggal: ${dateCols.map(c => `<span class="ts-col-badge">${c}</span>`).join('')}</div>
    <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px;align-items:flex-end;">
      <div>
        <label style="font-size:11px;font-weight:700;color:var(--text2);display:block;margin-bottom:5px;">Kolom Tanggal</label>
        <select id="tsDateCol" style="padding:8px 12px;border-radius:8px;border:1.5px solid var(--border);font-size:12px;font-family:'Inter',sans-serif;">${opts}</select>
      </div>
      <div>
        <label style="font-size:11px;font-weight:700;color:var(--text2);display:block;margin-bottom:5px;">Nilai (Y)</label>
        <select id="tsValCol" style="padding:8px 12px;border-radius:8px;border:1.5px solid var(--border);font-size:12px;font-family:'Inter',sans-serif;">${numOpts}</select>
      </div>
      <div>
        <label style="font-size:11px;font-weight:700;color:var(--text2);display:block;margin-bottom:5px;">MA Window</label>
        <input id="tsMaWindow" type="number" value="7" min="2" max="90" style="padding:8px 12px;border-radius:8px;border:1.5px solid var(--border);font-size:12px;width:80px;">
      </div>
      <button onclick="loadTimeSeries()" style="background:var(--accent);color:#fff;border:none;padding:9px 20px;border-radius:8px;cursor:pointer;font-size:12px;font-weight:700;font-family:'Inter',sans-serif;">Generate Charts</button>
    </div>
    <div id="tsChartArea"><div class="empty-state"><div class="empty-icon">⏱</div><div class="empty-title">Pilih kolom lalu klik Generate Charts</div></div></div>`;
}

function loadTimeSeries() {
  const dateCol = document.getElementById('tsDateCol')?.value || '';
  const valCol = document.getElementById('tsValCol')?.value || '';
  const maWin = parseInt(document.getElementById('tsMaWindow')?.value) || 7;
  const area = document.getElementById('tsChartArea');
  if (!area) return;
  area.innerHTML = `<div style="text-align:center;padding:40px;color:var(--accent);font-family:'Space Mono',monospace;">Generating Time Series charts...</div>`;
  fetch('/timeseries', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ date_col: dateCol, val_col: valCol, ma_window: maWin })
  })
    .then(r => r.json())
    .then(d => {
      if (d.error) { area.innerHTML = `<p style="color:red;padding:16px">${d.error}</p>`; return; }
      window._pendingPlots = window._pendingPlots || {};
      _chartIdCounter = _chartIdCounter || 0;
      const mkCard = (title, fig) => {
        if (!fig) return '';
        const id = 'plt_ts_' + (++_chartIdCounter);
        window._pendingPlots[id] = fig;
        return `<div class="viz-card viz-wide"><div class="viz-card-header">${title}</div><div id="${id}" style="width:100%;height:300px;"></div></div>`;
      };
      area.innerHTML = `<div style="display:grid;gap:14px;">
      ${mkCard('Time Series Line Chart', d.line_chart)}
      ${mkCard('Moving Average (' + maWin + '-period)', d.ma_chart)}
      ${mkCard('Trend Line', d.trend_chart)}
      ${mkCard('Rolling Mean (30-period)', d.roll30_chart)}
    </div>`;
      flushPlotly();
    })
    .catch(e => { area.innerHTML = `<p style="color:red;padding:16px">Error: ${e.message}</p>`; });
}

/* ── Report Section ──────────────────────────────────────── */
function renderReport(d) {
  document.getElementById('reportContent').innerHTML = `
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px;margin-bottom:20px;">
      <div style="background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:20px;text-align:center;">
        <div style="font-size:28px;margin-bottom:8px;">⬇</div>
        <div style="font-size:13px;font-weight:700;margin-bottom:4px;">Export CSV</div>
        <div style="font-size:11px;color:var(--text3);margin-bottom:14px;">Download cleaned dataset</div>
        <button onclick="exportCSV()" style="background:var(--accent);color:#fff;border:none;padding:8px 20px;border-radius:8px;cursor:pointer;font-size:12px;font-weight:700;font-family:'Inter',sans-serif;">Download CSV</button>
      </div>
      <div style="background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:20px;text-align:center;">
        <div style="font-size:28px;margin-bottom:8px;">
        
        </div>
        <div style="font-size:13px;font-weight:700;margin-bottom:4px;">Dataset Summary</div>
        <div style="font-size:11px;color:var(--text3);margin-bottom:14px;">${d.total_rows.toLocaleString()} rows × ${d.total_cols} columns</div>
        <div style="font-size:20px;font-weight:800;font-family:'Space Mono',monospace;color:var(--accent)">${d.quality_pct}%</div>
        <div style="font-size:10px;color:var(--text3)">Quality Score</div>
      </div>
    </div>
    <div style="background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:16px;">
      <div style="font-size:12px;font-weight:700;margin-bottom:8px;">Dataset Info</div>
      <table style="width:100%;font-size:12px;border-collapse:collapse;">
        <tr><td style="padding:5px 0;color:var(--text3)">File</td><td style="font-family:'Space Mono',monospace;font-weight:600">${d.filename}</td></tr>
        <tr><td style="padding:5px 0;color:var(--text3)">Rows</td><td style="font-family:'Space Mono',monospace;font-weight:600">${d.total_rows.toLocaleString()}</td></tr>
        <tr><td style="padding:5px 0;color:var(--text3)">Columns</td><td style="font-family:'Space Mono',monospace;font-weight:600">${d.total_cols}</td></tr>
        <tr><td style="padding:5px 0;color:var(--text3)">Missing Cells</td><td style="font-family:'Space Mono',monospace;font-weight:600">${d.missing_cells}</td></tr>
        <tr><td style="padding:5px 0;color:var(--text3)">Quality Score</td><td style="font-family:'Space Mono',monospace;font-weight:600">${d.quality_pct}%</td></tr>
      </table>
    </div>`;
}

function exportCSV() {
  window.location.href = '/export-csv';
}

/* ── Navigation ──────────────────────────────────────────── */
function showSection(name) {
  const sections = ['dashboard','upload','preview','stats','types','quality','insights','timeseries','viz','report'];
  sections.forEach(s => {
    const el = document.getElementById('section-' + s);
    if (el) { el.classList.add('hidden'); el.style.display = 'none'; }
  });
  const target = document.getElementById('section-' + name);
  if (target) { target.classList.remove('hidden'); target.style.display = ''; }
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  const nav = document.getElementById('nav-' + name);
  if (nav) { nav.classList.add('active'); }

  // Resize semua plotly chart setelah section tampil
  setTimeout(() => {
    if (window.Plotly) {
      document.querySelectorAll('[id^="plt_"], [id^="db-c"], [id^="db-chart"]').forEach(el => {
        try { Plotly.relayout(el, { autosize: true }); } catch(e) {}
      });
    }
  }, 50);

  // Re-render content when section opened
  if (state) {
    if (name === 'stats' && state.num_stats) renderStatsToSplit(state);
    if (name === 'types') renderTypes(state);
    if (name === 'quality') renderQuality(state);
    if (name === 'insights' && state.insights) renderInsights(state.insights, 'insightsContent');
    if (name === 'preview') renderTable(state.preview, state.columns, 'previewContent', false);
    if (name === 'viz') _autoGenerateViz();
  }
}

function _autoGenerateViz() {
  if (!state || _vizLoaded['numerical']) return;
  var numCols = Object.keys(state.col_types || {}).filter(function(c) { return state.col_types[c] === 'numeric'; });
  var catCols = Object.keys(state.col_types || {}).filter(function(c) { return state.col_types[c] === 'categorical'; });
  if (numCols.length === 0 && catCols.length === 0) return;
  var promises = [];
  if (numCols.length > 0) {
    promises.push(fetch('/visualize/numerical', { method: 'POST', headers: {'Content-Type':'application/json'}, body: '{}' })
      .then(function(r) { return r.json(); }).then(function(d) { if (d.success) { _vizLoaded['numerical'] = true; renderNumericalCharts(d); } }));
  }
  if (catCols.length > 0) {
    promises.push(fetch('/visualize/categorical', { method: 'POST', headers: {'Content-Type':'application/json'}, body: '{}' })
      .then(function(r) { return r.json(); }).then(function(d) { if (d.success) { _vizLoaded['categorical'] = true; renderCategoricalCharts(d); } }));
  }
  if (numCols.length >= 2) {
    promises.push(fetch('/visualize/bivariate', { method: 'POST', headers: {'Content-Type':'application/json'}, body: '{}' })
      .then(function(r) { return r.json(); }).then(function(d) { if (d.success) { _vizLoaded['bivariate'] = true; renderBivariateCharts(d); } }));
  }
}

function showLoading(text) {
  const ltEl = document.getElementById('loadingText');
  const loEl = document.getElementById('loadingOverlay');
  if (ltEl) ltEl.textContent = text;
  if (loEl) { loEl.classList.remove('hidden'); loEl.style.display = 'flex'; }
}
function hideLoading() {
  const loEl = document.getElementById('loadingOverlay');
  if (loEl) { loEl.classList.add('hidden'); loEl.style.display = 'none'; }
}

// ── Dashboard Preview Charts (setelah upload) ─────────────────
// Helper to safely set textContent/style on an element that may not exist
function _safeSet(id, fn) { const el = document.getElementById(id); if (el) fn(el); }

function updateDashboardPreview(d) {
  // If none of the db-* elements exist, this page doesn't have a dashboard preview — skip
  if (!document.getElementById('db-rows')) return;

  // KPI cards
  const fmt = n => (typeof n === 'number') ? n.toLocaleString('id-ID') : (n || '—');
  _safeSet('db-rows', el => el.textContent = fmt(d.total_rows));
  _safeSet('db-cols', el => el.textContent = fmt(d.total_cols));
  const numCount = d.col_types ? Object.values(d.col_types).filter(t => t === 'numeric').length : '—';
  const catCount = d.col_types ? Object.values(d.col_types).filter(t => t === 'categorical').length : '—';
  _safeSet('db-num', el => el.textContent = numCount);
  _safeSet('db-cat', el => el.textContent = catCount);
  _safeSet('db-quality', el => el.textContent = (d.quality_pct || '—') + '%');

  // Show main dashboard, hide hero & before-upload quick actions
  _safeSet('db-hero', el => el.style.display = 'none');
  _safeSet('db-quick-before', el => el.style.display = 'none');
  _safeSet('db-main', el => el.style.display = 'block');

  // Quality score
  const qpct = d.quality_pct || 0;
  _safeSet('db-quality-score', el => { el.textContent = qpct + '%'; el.style.color = qpct >= 90 ? '#059669' : qpct >= 70 ? '#d97706' : '#c94040'; });
  _safeSet('db-quality-label', el => el.textContent = qpct >= 90 ? '✅ Excellent — Data in great condition' : qpct >= 70 ? '⚠️ Fair — Beberapa kolom perlu cleaning' : '❌ Poor — Data perlu banyak cleaning');

  // Quality bars (missing per col)
  if (d.col_quality) {
    const barsEl = document.getElementById('db-quality-bars');
    if (barsEl) barsEl.innerHTML = d.col_quality.slice(0, 5).map(c => `
      <div style="margin-bottom:6px;">
        <div style="display:flex;justify-content:space-between;font-size:10px;color:#6b7280;margin-bottom:2px;">
          <span>${c.column.length > 14 ? c.column.slice(0, 13) + '…' : c.column}</span>
          <span>${c.missing_pct.toFixed(1)}% missing</span>
        </div>
        <div style="height:5px;background:#f3f4f6;border-radius:3px;overflow:hidden;">
          <div style="width:${Math.max(c.missing_pct, 0)}%;height:100%;background:${c.missing_pct > 30 ? '#c94040' : c.missing_pct > 10 ? '#e07b39' : '#059669'};border-radius:3px;"></div>
        </div>
      </div>`).join('');
  }

  // Data preview table
  if (d.preview && d.columns) {
    const thead = document.querySelector('#db-preview-table thead');
    const tbody = document.querySelector('#db-preview-table tbody');
    const cols = d.columns.slice(0, 7); // max 7 cols
    thead.innerHTML = '<tr>' + ['No', ...cols].map(c =>
      `<th title="${c}">${c.length > 10 ? c.slice(0, 9) + '…' : c}</th>`).join('') + '</tr>';
    tbody.innerHTML = d.preview.map((row, i) =>
      '<tr><td>' + (i + 1) + '</td>' + cols.map(c => {
        const v = row[c]; const s = String(v ?? '');
        return `<td title="${s}">${s.length > 12 ? s.slice(0, 11) + '…' : s}</td>`;
      }).join('') + '</tr>').join('');
  }

  // Numerical summary table
  if (d.num_stats) {
    const numCols = Object.keys(d.num_stats).slice(0, 4);
    const metrics = ['count', 'mean', 'median', 'std', 'min', 'max', 'missing_pct'];
    const metricLabel = { count: 'Count', mean: 'Mean', median: 'Median', std: 'Std Dev', min: 'Min', max: 'Max', missing_pct: 'Missing(%)' };
    const thead = document.querySelector('#db-num-summary thead');
    const tbody = document.querySelector('#db-num-summary tbody');
    thead.innerHTML = '<tr>' + ['Statistic', ...numCols].map(c =>
      `<th title="${c}">${c.length > 10 ? c.slice(0, 9) + '…' : c}</th>`).join('') + '</tr>';
    tbody.innerHTML = metrics.map(m => '<tr><td style="font-weight:600;color:#374151;">' + (metricLabel[m] || m) + '</td>' +
      numCols.map(col => {
        const v = d.num_stats[col]?.[m];
        const s = v == null ? '—' : typeof v === 'number' ? (Math.abs(v) >= 1000 ? v.toLocaleString('id-ID', { maximumFractionDigits: 0 }) : v.toFixed(2)) : String(v);
        return `<td>${s}</td>`;
      }).join('') + '</tr>').join('');
  }

  // Categorical summary table
  if (d.cat_stats) {
    const catCols = Object.keys(d.cat_stats).slice(0, 4);
    const thead = document.querySelector('#db-cat-summary thead');
    const tbody = document.querySelector('#db-cat-summary tbody');
    thead.innerHTML = '<tr><th>Variable</th><th>Unique</th><th>Mode</th><th>Mode%</th><th>Missing%</th></tr>';
    tbody.innerHTML = catCols.map(col => {
      const s = d.cat_stats[col] || {};
      const mode = String(s.mode || '—'); const modeShort = mode.length > 10 ? mode.slice(0, 9) + '…' : mode;
      return `<tr>
        <td style="font-weight:600;" title="${col}">${col.length > 12 ? col.slice(0, 11) + '…' : col}</td>
        <td>${s.unique_count || '—'}</td>
        <td title="${mode}">${modeShort}</td>
        <td>${s.mode_pct != null ? s.mode_pct.toFixed(1) + '%' : '—'}</td>
        <td>${s.missing_pct != null ? s.missing_pct.toFixed(1) + '%' : '—'}</td>
      </tr>`;
    }).join('');
  }

  // Insights list
  if (d.insights && d.insights.length > 0) {
    const el = document.getElementById('db-insights-list');
    el.innerHTML = d.insights.slice(0, 5).map(ins => {
      const msg = typeof ins === 'string' ? ins : (ins.message || ins.title || JSON.stringify(ins));
      const icon = typeof ins === 'object' && ins.icon ? ins.icon : '✓';
      return `<div class="db-insight-item"><span class="db-insight-dot">${icon}</span><span>${msg}</span></div>`;
    }).join('');
  }

  // Mini charts — render sequential setelah DOM ready
  // Bersihkan dulu sebelum render ulang
  ['db-chart1', 'db-chart2', 'db-chart3'].forEach(id => {
    const el = document.getElementById(id);
    if (el && window.Plotly) try { Plotly.purge(el); } catch (e) { }
    if (el) el.innerHTML = '';
  });

  const cfg = { responsive: true, displayModeBar: false, staticPlot: false };
  const BASE = {
    paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
    font: { family: 'DM Sans,sans-serif', size: 10, color: '#374151' },
    xaxis: { gridcolor: '#f0f0f0', linecolor: '#e5e7eb', zeroline: false },
    yaxis: { gridcolor: '#f0f0f0', linecolor: '#e5e7eb', zeroline: false },
  };

  function plotChart1() {
    const numCols = d.col_types
      ? Object.entries(d.col_types).filter(([, t]) => t === 'numeric').map(([c]) => c)
      : [];
    const el1 = document.getElementById('db-chart1');
    if (!el1) return;
    if (numCols.length > 0 && d.num_stats) {
      const cols = numCols.slice(0, 8);
      const means = cols.map(c => { const v = d.num_stats[c]?.mean; return typeof v === 'number' ? parseFloat(v.toFixed(2)) : 0; });
      const short = cols.map(c => c.length > 10 ? c.slice(0, 9) + '…' : c);
      _safeSet('db-chart1-col', el => el.textContent = cols[0] || '');
      Plotly.newPlot(el1, [{
        x: short, y: means, type: 'bar',
        marker: { color: '#1a7a3c', opacity: 0.85 },
        hovertemplate: '<b>%{x}</b><br>Mean: %{y}<extra></extra>'
      }], { ...BASE, height: 115, margin: { l: 36, r: 6, t: 4, b: 46 }, xaxis: { ...BASE.xaxis, tickangle: -35, tickfont: { size: 7 } }, yaxis: { ...BASE.yaxis, tickfont: { size: 7 } } }, cfg);
    } else {
      el1.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:200px;color:#9ca3af;font-size:11px;">Tidak ada kolom numerik</div>';
    }
  }

  function plotChart2() {
    const catCols = d.col_types
      ? Object.entries(d.col_types).filter(([, t]) => t === 'categorical').map(([c]) => c)
      : [];
    const el2 = document.getElementById('db-chart2');
    if (!el2) return;
    if (catCols.length > 0 && d.cat_stats) {
      const col = catCols[0];
      const cs = d.cat_stats[col] || {};
      _safeSet('db-chart2-col', el => el.textContent = col);
      const topVals = cs.top_values || (cs.mode ? [[cs.mode, cs.mode_count || 1]] : []);
      const labels = topVals.slice(0, 5).map(([k]) => String(k).length > 10 ? String(k).slice(0, 9) + '…' : String(k));
      const counts = topVals.slice(0, 5).map(([, v]) => v);
      const colors = ['#1a7a3c', '#22a854', '#059669', '#0891b2', '#7c3aed', '#d97706', '#c94040'];
      if (labels.length > 0) {
        Plotly.newPlot(el2, [{
          y: labels, x: counts, type: 'bar', orientation: 'h',
          marker: { color: colors.slice(0, labels.length) },
          hovertemplate: '<b>%{y}</b><br>Count: %{x}<extra></extra>'
        }], { ...BASE, height: 115, margin: { l: 62, r: 6, t: 4, b: 18 }, xaxis: { ...BASE.xaxis, tickfont: { size: 7 } }, yaxis: { ...BASE.yaxis, autorange: 'reversed', tickfont: { size: 7 } } }, cfg);
      } else {
        el2.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:200px;color:#9ca3af;font-size:11px;">Tidak ada data kategorikal</div>';
      }
    } else {
      el2.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:200px;color:#9ca3af;font-size:11px;">Tidak ada kolom kategorikal</div>';
    }
  }

  function plotChart3() {
    const el3 = document.getElementById('db-chart3');
    if (!el3) return;
    if (d.col_quality && d.col_quality.length > 0) {
      const sorted = [...d.col_quality].sort((a, b) => b.missing_pct - a.missing_pct).slice(0, 10);
      const labels = sorted.map(c => c.column.length > 13 ? c.column.slice(0, 12) + '…' : c.column);
      const values = sorted.map(c => parseFloat(c.missing_pct.toFixed(2)));
      const barClrs = values.map(v => v > 30 ? '#c94040' : v > 10 ? '#e07b39' : '#3a9e6f');
      Plotly.newPlot(el3, [{
        y: labels, x: values, type: 'bar', orientation: 'h',
        marker: { color: barClrs },
        hovertemplate: '<b>%{y}</b><br>Missing: %{x}%<extra></extra>'
      }], { ...BASE, height: 115, margin: { l: 62, r: 6, t: 4, b: 18 }, xaxis: { ...BASE.xaxis, range: [0, Math.max(...values, 1) * 1.2], tickfont: { size: 7 } }, yaxis: { ...BASE.yaxis, autorange: 'reversed', tickfont: { size: 7 } } }, cfg);
    } else {
      el3.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:200px;color:#9ca3af;font-size:11px;">Tidak ada data missing value</div>';
    }
  }

  function plotChartExtra1() {
    const numCols = d.col_types
      ? Object.entries(d.col_types).filter(([, t]) => t === 'numeric').map(([c]) => c)
      : [];
    const el = document.getElementById('db-chart-extra1');
    if (!el) return;
    if (numCols.length > 0 && d.num_stats) {
      const col = numCols[0];
      _safeSet('db-chart1-col', e2 => e2.textContent = col);
      const stats = d.num_stats[col] || {};
      const min = stats.min ?? 0, max = stats.max ?? 1, mean = stats.mean ?? 0, std = stats.std ?? 1;
      const bins = 8;
      const step = (max - min) / bins || 1;
      const xVals = Array.from({ length: bins }, (_, i) => parseFloat((min + step * i + step / 2).toFixed(2)));
      const yVals = xVals.map(x => {
        const z = (x - mean) / (std || 1);
        return parseFloat((Math.exp(-0.5 * z * z)).toFixed(4));
      });
      Plotly.newPlot(el, [{
        x: xVals, y: yVals, type: 'bar',
        marker: { color: '#2d9e6b', opacity: 0.8 },
        hovertemplate: '<b>%{x}</b><br>Rel. Freq: %{y}<extra></extra>'
      }], {
        ...BASE, height: 110,
        margin: { l: 36, r: 6, t: 4, b: 36 },
        xaxis: { ...BASE.xaxis, tickfont: { size: 7 } },
        yaxis: { ...BASE.yaxis, tickfont: { size: 7 } }
      }, cfg);
    } else {
      el.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:110px;color:#9ca3af;font-size:11px;">Tidak ada kolom numerik</div>';
    }
  }

  function plotChartExtra2() {
    const catCols = d.col_types
      ? Object.entries(d.col_types).filter(([, t]) => t === 'categorical').map(([c]) => c)
      : [];
    const el = document.getElementById('db-chart-extra2');
    if (!el) return;
    if (catCols.length > 0 && d.cat_stats) {
      const col = catCols[0];
      _safeSet('db-chart2-col', e2 => e2.textContent = col);
      const cs = d.cat_stats[col] || {};
      const topVals = cs.top_values || (cs.mode ? [[cs.mode, cs.mode_count || 1]] : []);
      const labels = topVals.slice(0, 6).map(([k]) => String(k).length > 12 ? String(k).slice(0, 11) + '...' : String(k));
      const counts = topVals.slice(0, 6).map(([, v]) => v);
      const colors = ['#1a7a3c', '#22a854', '#059669', '#0891b2', '#7c3aed', '#d97706'];
      if (labels.length > 0) {
        Plotly.newPlot(el, [{
          y: labels, x: counts, type: 'bar', orientation: 'h',
          marker: { color: colors.slice(0, labels.length) },
          hovertemplate: '<b>%{y}</b><br>Count: %{x}<extra></extra>'
        }], {
          ...BASE, height: 110,
          margin: { l: 72, r: 6, t: 4, b: 20 },
          xaxis: { ...BASE.xaxis, tickfont: { size: 7 } },
          yaxis: { ...BASE.yaxis, autorange: 'reversed', tickfont: { size: 7 } }
        }, cfg);
      } else {
        el.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:110px;color:#9ca3af;font-size:11px;">Tidak ada data</div>';
      }
    } else {
      el.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:110px;color:#9ca3af;font-size:11px;">Tidak ada kolom kategorik</div>';
    }
  }

  // Render sequential dengan delay kecil supaya DOM & display sudah settle
  ensurePlotly(() => {
    setTimeout(() => { plotChart1(); setTimeout(() => { try { const e = document.getElementById('db-chart1'); if (e) Plotly.relayout(e, { width: e.clientWidth }); } catch (x) { } }, 100); }, 50);
    setTimeout(() => { plotChart2(); setTimeout(() => { try { const e = document.getElementById('db-chart2'); if (e) Plotly.relayout(e, { width: e.clientWidth }); } catch (x) { } }, 100); }, 150);
    setTimeout(() => { plotChart3(); setTimeout(() => { try { const e = document.getElementById('db-chart3'); if (e) Plotly.relayout(e, { width: e.clientWidth }); } catch (x) { } }, 100); }, 250);
    setTimeout(() => { plotChartExtra1(); setTimeout(() => { try { const e = document.getElementById('db-chart-extra1'); if (e) Plotly.relayout(e, { width: e.clientWidth }); } catch (x) { } }, 100); }, 350);
    setTimeout(() => { plotChartExtra2(); setTimeout(() => { try { const e = document.getElementById('db-chart-extra2'); if (e) Plotly.relayout(e, { width: e.clientWidth }); } catch (x) { } }, 100); }, 450);
  });
}
// ── Preview toggle (show 20 / show full dataset) ──────────────────────
let _previewShowAll = false;
let _fullDataCache = null;

/* ── renderDashboardCharts: fetch real data & render beautiful charts ── */
function renderDashboardCharts(d) {
  const grid = document.getElementById('db-viz-preview-grid');
  if (!grid) return;

  // Show loading skeleton
  grid.innerHTML = Array.from({ length: 6 }, (_, i) => `
    <div class="nd-viz-card" style="animation:pulse 1.5s ease-in-out ${i * 0.1}s infinite alternate;">
      <div style="height:12px;background:#e8f5ed;border-radius:4px;width:70%;margin:0 auto 8px;"></div>
      <div style="height:280px;background:linear-gradient(135deg,#f0faf5 0%,#e8f5ed 100%);border-radius:6px;display:flex;align-items:center;justify-content:center;">
        <div style="width:28px;height:28px;border:3px solid #27ae60;border-top-color:transparent;border-radius:50%;animation:spin 0.8s linear infinite;"></div>
      </div>
    </div>`).join('');

  // Fetch real data from server
  fetch('/dashboard-charts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
    .then(r => r.json())
    .then(data => {
      if (data.error) { _renderDashboardFallback(grid, d); return; }
      _renderDashboardReal(grid, data);
    })
    .catch(() => _renderDashboardFallback(grid, d));
}

function _renderDashboardFallback(grid, d) {
  // Fallback: kosong dengan pesan
  grid.innerHTML = `<div class="nd-viz-card" style="grid-column:1/-1;text-align:center;padding:30px;color:#9ca3af;">
    <div style="font-size:28px;margin-bottom:8px;">📊</div>
    <div style="font-size:12px;">Visualisasi tidak tersedia — coba reload halaman</div>
  </div>`;
}

function _renderDashboardReal(grid, data) {
  // ── Palette & layout constants ──
  const PAL = ['#2563eb', '#16a34a', '#dc2626', '#d97706', '#7c3aed', '#0891b2', '#db2777', '#65a30d', '#ea580c', '#0d9488'];
  const PAL_LIGHT = ['rgba(37,99,235,0.15)', 'rgba(22,163,74,0.15)', 'rgba(220,38,38,0.15)', 'rgba(217,119,6,0.15)',
    'rgba(124,58,237,0.15)', 'rgba(8,145,178,0.15)', 'rgba(219,39,119,0.15)', 'rgba(101,163,13,0.15)'];
  const BASE = {
    paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
    font: { family: 'Inter,ui-sans-serif,sans-serif', size: 9, color: '#374151' },
    margin: { l: 36, r: 8, t: 10, b: 32 },
    xaxis: { gridcolor: '#f0faf5', linecolor: '#c8e6d4', zeroline: false, tickfont: { size: 8 } },
    yaxis: { gridcolor: '#f0faf5', linecolor: '#c8e6d4', zeroline: false, tickfont: { size: 8 } },
    showlegend: false, height: 280,
    hoverlabel: { bgcolor: '#1a3a28', font: { color: '#fff', size: 9 }, bordercolor: 'transparent' }
  };
  const CFG = { responsive: true, displayModeBar: false };

  // ── Build exactly 4 cards, 1 row ──
  // Priority: Histogram | Bar/Grouped | Violin | Scatter or Pie
  const cards = [];

  // Card 1: Histogram (numeric, best std)
  if (data.hist) {
    cards.push({
      id: 'db-c1',
      title: `<span style="color:#2563eb">▐</span> Distribusi ${_shortCol(data.hist.col)}`,
      type: 'hist'
    });
  }

  // Card 2: Pie chart kategorik (ganti grouped yang sering stuck)
if (data.pie && data.pie.labels && data.pie.labels.length > 0) {
  cards.push({id:'db-c2',
    title:`<span style="color:#16a34a">▐</span> ${_shortCol(data.pie.col)}`,
    type:'pie'});
}

  // Card 3: Violin (distribution shape)
  if (data.violin && data.violin.sample && data.violin.sample.length > 0) {
    cards.push({
      id: 'db-c3',
      title: `<span style="color:#7c3aed">▐</span> ${_shortCol(data.violin.col)}`,
      type: 'violin'
    });
  }

  // Card 4: Scatter if 2 numeric cols, else Bar chart
if (data.scatter && data.scatter.x && data.scatter.x.length > 0) {
  cards.push({id:'db-c4',
    title:`<span style="color:#dc2626">▐</span> ${_shortCol(data.scatter.col_x)} vs ${_shortCol(data.scatter.col_y)}`,
    type:'scatter'});
} else if (data.bar && data.bar.labels && data.bar.labels.length > 0) {
  cards.push({id:'db-c4',
    title:`<span style="color:#d97706">▐</span> Top ${_shortCol(data.bar.col)}`,
    type:'bar'});
}


  // Render grid HTML
  grid.innerHTML = cards.map(c => `
    <div class="nd-viz-card" style="border-radius:10px;border:1px solid #e8f5ed;background:#fff;
         padding:10px 10px 6px;box-shadow:0 1px 4px rgba(0,0,0,0.06);transition:box-shadow 0.2s;"
         onmouseover="this.style.boxShadow='0 4px 16px rgba(0,0,0,0.12)'"
         onmouseout="this.style.boxShadow='0 1px 4px rgba(0,0,0,0.06)'">
      <div style="font-size:9.5px;font-weight:700;color:#1a3a28;margin-bottom:4px;
           white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${c.title.replace(/<[^>]+>/g, '')}">${c.title}</div>
      <div id="${c.id}" style="height:280px;"></div>
      <a style="display:block;text-align:right;font-size:9px;color:#27ae60;cursor:pointer;margin-top:3px;text-decoration:none;"
         onmouseover="this.style.textDecoration='underline'" onmouseout="this.style.textDecoration='none'"
         onclick="scrollToSec('sec-viz')">View All →</a>
    </div>`).join('');

  // ── Render each chart ──
  ensurePlotly(() => {
    cards.forEach((card, idx) => {
      setTimeout(() => {
        const el = document.getElementById(card.id);
        if (!el) return;
        try {
          if (card.type === 'hist' || card.type === 'hist2') {
            const h = data.hist;
            const maxY = Math.max(...h.y);
            // Color bars by value — gradient from light to dark
            const colors = h.y.map(v => {
              const ratio = v / (maxY || 1);
              const r = Math.round(37 + (14 - 37) * ratio);
              const g = Math.round(99 + (163 - 99) * ratio);
              const b = Math.round(235 + (74 - 235) * ratio);
              return `rgba(${r},${g},${b},${0.5 + 0.5 * ratio})`;
            });
            const maxX = Math.max(...h.x);
            const histXFmt = maxX >= 1e6 ? '.2s' : maxX >= 1e3 ? '.2s' : '';
            Plotly.newPlot(el, [{
              x: h.x, y: h.y, type: 'bar',
              marker: { color: colors, line: { width: 0 } },
              hovertemplate: '<b>%{x:,.0f}</b><br>Count: %{y}<extra></extra>'
            }, {
              // Mean line
              x: [h.mean, h.mean], y: [0, maxY],
              type: 'scatter', mode: 'lines',
              line: { color: '#dc2626', width: 1.5, dash: 'dash' },
              hovertemplate: `Mean: ${h.mean}<extra></extra>`
            }], {
              ...BASE,
              xaxis: { ...BASE.xaxis, tickformat: histXFmt },
              shapes: [{
                type: 'line', x0: h.median, x1: h.median, y0: 0, y1: maxY,
                line: { color: '#d97706', width: 1.5, dash: 'dot' }
              }],
              annotations: [
                { x: h.mean, y: maxY * 1.05, xref: 'x', yref: 'y', text: 'μ', showarrow: false, font: { size: 9, color: '#dc2626' } },
                { x: h.median, y: maxY * 0.9, xref: 'x', yref: 'y', text: 'M', showarrow: false, font: { size: 9, color: '#d97706' } }
              ]
            }, CFG);

          } else if (card.type === 'grouped') {
            const g = data.grouped;
            const maxV = Math.max(...g.values);
            const colors = g.values.map((v, i) => PAL[i % PAL.length]);
            // Format label teks sesuai magnitude
            const fmtVal = v => {
              if (Math.abs(v) >= 1e9) return (v / 1e9).toFixed(1) + 'B';
              if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(1) + 'M';
              if (Math.abs(v) >= 1e3) return (v / 1e3).toFixed(1) + 'K';
              return v.toFixed(1);
            };
            // Pilih tickformat axis X sesuai magnitude
            const xTickFmt = maxV >= 1e6 ? '.2s' : maxV >= 1e3 ? '.2s' : '.2f';
            Plotly.newPlot(el, [{
              y: g.labels, x: g.values,
              type: 'bar', orientation: 'h',
              marker: {
                color: colors,
                opacity: 0.85,
                line: { width: 0 }
              },
              hovertemplate: '<b>%{y}</b><br>Avg: %{x:,.0f}<extra></extra>',
              text: g.values.map(v => fmtVal(v)),
              textposition: 'auto', textfont: { size: 8 }
            }], {
              ...BASE,
              margin: { ...BASE.margin, l: 75, r: 50, b: 20 },
              yaxis: { ...BASE.yaxis, autorange: 'reversed', tickfont: { size: 7.5 } },
              xaxis: { ...BASE.xaxis, tickformat: xTickFmt, range: [0, maxV * 1.25] }
            }, CFG);

          } else if (card.type === 'bar') {
            const b = data.bar;
            const maxBV = Math.max(...b.values);
            const fmtB = v => {
              if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(1) + 'M';
              if (Math.abs(v) >= 1e3) return (v / 1e3).toFixed(1) + 'K';
              return String(v);
            };
            const colors = b.labels.map((_, i) => PAL[i % PAL.length]);
            Plotly.newPlot(el, [{
              x: b.labels, y: b.values, type: 'bar',
              marker: { color: colors, opacity: 0.85, line: { width: 0 } },
              hovertemplate: '<b>%{x}</b><br>%{y:,.0f}<extra></extra>',
              text: b.values.map(v => fmtB(v)), textposition: 'outside', textfont: { size: 8 }
            }], {
              ...BASE,
              xaxis: { ...BASE.xaxis, tickangle: -32, tickfont: { size: 7.5 } },
              yaxis: { ...BASE.yaxis, tickformat: maxBV >= 1e3 ? '.2s' : '', range: [0, maxBV * 1.25] },
            }, CFG);

          } else if (card.type === 'violin') {
            const v = data.violin;
            Plotly.newPlot(el, [{
              y: v.sample, type: 'violin', name: '',
              box: { visible: true, fillcolor: 'rgba(124,58,237,0.3)', line: { color: '#7c3aed', width: 1.5 } },
              meanline: { visible: true, color: '#dc2626', width: 2 },
              fillcolor: 'rgba(124,58,237,0.12)',
              line: { color: '#7c3aed', width: 1.5 },
              points: 'outliers',
              marker: { color: '#7c3aed', size: 3, opacity: 0.5 },
              hovertemplate: '%{y:.2f}<extra></extra>'
            }], {
              ...BASE,
              xaxis: { ...BASE.xaxis, showticklabels: false },
              annotations: [{
                xref: 'paper', yref: 'paper', x: 0.02, y: 0.97,
                text: `Q1:${v.q1} | Med:${v.median} | Q3:${v.q3}`,
                showarrow: false, font: { size: 7.5, color: '#6b7280' },
                align: 'left'
              }]
            }, CFG);

          } else if (card.type === 'pie') {
            const p = data.pie;
            Plotly.newPlot(el, [{
              labels: p.labels, values: p.values,
              type: 'pie', hole: 0.42,
              marker: { colors: PAL.slice(0, p.labels.length), line: { color: '#fff', width: 2 } },
              hovertemplate: '<b>%{label}</b><br>%{value} (%{percent})<extra></extra>',
              textinfo: 'percent', textfont: { size: 8 },
              textposition: 'inside',
              insidetextorientation: 'auto'
            }], {
              ...BASE,
              margin: { l: 8, r: 8, t: 8, b: 8 },
              showlegend: true,
              legend: { orientation: 'v', x: 1, xanchor: 'left', y: 0.5, font: { size: 7.5 } },
            }, CFG);

          } else if (card.type === 'scatter') {
            const sc = data.scatter;
            const n = sc.x.length;
            // Color by density (approximate — distance from center)
            const mx = sc.x.reduce((a, b) => a + b, 0) / n;
            const my = sc.y.reduce((a, b) => a + b, 0) / n;
            const sdx = Math.sqrt(sc.x.map(x => (x - mx) ** 2).reduce((a, b) => a + b, 0) / n) || 1;
            const sdy = Math.sqrt(sc.y.map(y => (y - my) ** 2).reduce((a, b) => a + b, 0) / n) || 1;
            const colors = sc.x.map((x, i) => {
              const d = Math.sqrt(((x - mx) / sdx) ** 2 + ((sc.y[i] - my) / sdy) ** 2);
              const t = Math.min(1, d / 3);
              return `rgba(${Math.round(220 + 35 * t)},${Math.round(38 + 38 * (1 - t))},38,${0.6 + 0.35 * (1 - t)})`;
            });
            const maxScX = Math.max(...sc.x), maxScY = Math.max(...sc.y);
            const scXFmt = maxScX >= 1e6 ? '.2s' : maxScX >= 1e3 ? '.2s' : '';
            const scYFmt = maxScY >= 1e6 ? '.2s' : maxScY >= 1e3 ? '.2s' : '';
            Plotly.newPlot(el, [{
              x: sc.x, y: sc.y,
              mode: 'markers', type: 'scatter',
              marker: { color: colors, size: 5, opacity: 0.8, line: { width: 0 } },
              hovertemplate: `${_shortCol(sc.col_x)}: %{x:,.0f}<br>${_shortCol(sc.col_y)}: %{y:,.0f}<extra></extra>`
            }], {
              ...BASE,
              xaxis: { ...BASE.xaxis, title: { text: _shortCol(sc.col_x), font: { size: 8 } }, titlefont: { size: 8 }, tickformat: scXFmt },
              yaxis: { ...BASE.yaxis, title: { text: _shortCol(sc.col_y), font: { size: 8 } }, titlefont: { size: 8 }, tickformat: scYFmt },
              margin: { ...BASE.margin, l: 46, b: 36 },
              annotations: [{
                xref: 'paper', yref: 'paper', x: 0.98, y: 0.98,
                text: `r = ${sc.corr}`, showarrow: false,
                font: { size: 9, color: sc.corr > 0.5 ? '#16a34a' : sc.corr < -0.5 ? '#dc2626' : '#6b7280' },
                xanchor: 'right', bgcolor: 'rgba(255,255,255,0.8)', borderpad: 2
              }]
            }, CFG);
          }
        } catch (e) {
          if (el) el.innerHTML = `<div style="height:280px;display:flex;align-items:center;justify-content:center;color:#9ca3af;font-size:10px;flex-direction:column;gap:4px;"><span style="font-size:20px;">⚠️</span>Chart error</div>`;
        }
      }, idx * 60);
    });
  });
}

function _shortCol(col) {
  if (!col) return '';
  // Shorten like "Indeks Pembangunan Manusia_2020" -> "IPM 2020"
  const s = String(col);
  if (s.length <= 20) return s;
  // Try abbreviation
  const parts = s.split('_');
  if (parts.length >= 2) {
    const last = parts[parts.length - 1];
    const first = parts.slice(0, -1).map(w => w[0]?.toUpperCase() || '').join('');
    return `${first} ${last}`;
  }
  return s.slice(0, 18) + '…';
}


function togglePreviewAll() {
  if (!window._state) return;
  const btn = document.getElementById('btnToggleAll');
  if (!_previewShowAll) {
    // Switch to full data
    if (_fullDataCache) {
      _previewShowAll = true;
      if (btn) btn.textContent = 'Show Less';
      renderTable(_fullDataCache, window._state.columns, 'previewContent', false);
      const info = document.getElementById('previewInfo');
      if (info) info.textContent = `Showing ${_fullDataCache.length} of ${window._state.total_rows?.toLocaleString() || '?'} rows`;
    } else {
      if (btn) { btn.textContent = 'Loading...'; btn.disabled = true; }
      fetch('/fulldata')
        .then(r => r.json())
        .then(d => {
          if (d.error) { alert(d.error); if (btn) { btn.textContent = '⊞ View All Data'; btn.disabled = false; } return; }
          _fullDataCache = d.rows;
          _previewShowAll = true;
          if (btn) { btn.textContent = 'Show Less'; btn.disabled = false; }
          renderTable(_fullDataCache, window._state.columns, 'previewContent', false);
          const info = document.getElementById('previewInfo');
          if (info) info.textContent = `Showing ${_fullDataCache.length} of ${window._state.total_rows?.toLocaleString() || '?'} rows`;
        })
        .catch(err => { alert('Error: ' + err); if (btn) { btn.textContent = '⊞ View All Data'; btn.disabled = false; } });
    }
  } else {
    // Switch back to 20 rows
    _previewShowAll = false;
    if (btn) btn.textContent = '⊞ View All Data';
    const rows = window._state.preview || [];
    renderTable(rows, window._state.columns, 'previewContent', false);
    const info = document.getElementById('previewInfo');
    if (info) info.textContent = `Showing ${rows.length} of ${window._state.total_rows?.toLocaleString() || '?'} rows`;
  }
}

// ── TIME SERIES ───────────────────────────────────────────────
let _tsActiveTypes = new Set(['line_chart', 'ma_chart', 'trend_chart', 'roll30_chart']);
let _tsLastResult = null;
const TS_LABELS = {
  line_chart: 'Line Chart',
  ma_chart: 'Moving Average',
  trend_chart: 'Trend Line',
  roll30_chart: 'Rolling Mean'
};
const TS_BADGES = {
  line_chart: 'Raw',
  ma_chart: 'Smoothed',
  trend_chart: 'Regression',
  roll30_chart: 'Rolling'
};

function tsShowStatus(type, msg) {
  const bar = document.getElementById('tsStatusBar');
  if (!bar) return;
  bar.className = 'ts-status-bar' + (type !== 'info' ? ' ' + type : '');
  bar.textContent = (type === 'loading' ? '⏳ ' : type === 'error' ? '❌ ' : '✅ ') + msg;
  bar.style.display = 'block';
}

function tsInitSelects() {
  fetch('/ts-cols', { method: 'POST' })
    .then(r => r.json())
    .then(data => {
      if (data.error) { tsShowStatus('error', data.error); return; }
      const dateSel = document.getElementById('tsDateCol');
      const valSel = document.getElementById('tsValCol');
      dateSel.innerHTML = '<option value="">— Pilih kolom —</option>';
      valSel.innerHTML = '<option value="">— Pilih kolom —</option>';

      // Date cols: detected datetime cols first, then all cols as fallback
      const detected = data.ts_cols || [];
      if (detected.length > 0) {
        detected.forEach(tc => {
          dateSel.appendChild(new Option(`${tc.col} (${tc.reason})`, tc.col));
        });
      } else {
        (data.all_cols || []).forEach(c => dateSel.appendChild(new Option(c, c)));
      }

      // Numeric cols for value
      (data.num_cols || []).forEach(c => valSel.appendChild(new Option(c, c)));

      const nNum = (data.num_cols || []).length;
      tsShowStatus('info', `Dataset siap. ${nNum} kolom numerik tersedia.`);
    })
    .catch(() => tsShowStatus('error', 'Belum ada dataset. Upload file dulu.'));
}

function tsToggleType(btn) {
  const t = btn.dataset.type;
  if (_tsActiveTypes.has(t)) { _tsActiveTypes.delete(t); btn.classList.remove('active'); }
  else { _tsActiveTypes.add(t); btn.classList.add('active'); }
  if (_tsLastResult) tsRenderCharts(_tsLastResult);
}

async function tsGenerate() {
  const dateCol = document.getElementById('tsDateCol').value;
  const valCol = document.getElementById('tsValCol').value;
  const maWin = parseInt(document.getElementById('tsMaWindow').value);
  const rollWin = parseInt(document.getElementById('tsRollWindow').value);

  if (!dateCol || !valCol) { tsShowStatus('error', 'Pilih kolom tanggal dan kolom nilai dulu.'); return; }

  tsShowStatus('loading', 'Generating visualisasi...');
  const btn = document.getElementById('tsBtnGenerate');
  btn.disabled = true;

  try {
    const r = await fetch('/timeseries', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date_col: dateCol, val_col: valCol, ma_window: maWin, roll_window: rollWin })
    });
    const data = await r.json();
    if (data.error) { tsShowStatus('error', data.error); return; }
    _tsLastResult = data;
    tsRenderCharts(data);
    tsShowStatus('info', `Berhasil generate ${_tsActiveTypes.size} chart untuk "${valCol}" vs "${dateCol}"`);
  } catch (e) {
    tsShowStatus('error', 'Request gagal: ' + e.message);
  } finally {
    btn.disabled = false;
  }
}

function tsRenderCharts(data) {
  const area = document.getElementById('tsChartsArea');
  const layout = document.getElementById('tsLayout').value;
  area.innerHTML = '';
  area.className = 'ts-charts-area' + (layout === 'grid2' ? ' grid-2' : '');

  const toShow = layout === 'single'
    ? [Array.from(_tsActiveTypes)[0]].filter(Boolean)
    : Array.from(_tsActiveTypes);

  if (toShow.length === 0) {
    area.innerHTML = '<div class="empty-state"><div class="empty-icon">⏱</div><div class="empty-title">Pilih minimal satu tipe chart</div></div>';
    return;
  }

  ensurePlotly(() => {
    toShow.forEach(type => {
      if (!data[type]) return;
      const card = document.createElement('div');
      card.className = 'ts-chart-card';
      card.innerHTML = `
        <div class="ts-chart-card-header">
          <span class="ts-chart-card-title">${TS_LABELS[type] || type}</span>
          <span class="ts-chart-card-badge">${TS_BADGES[type] || ''}</span>
        </div>
        <div class="ts-chart-plot" id="tsplot_${type}" style="height:320px;"></div>`;
      area.appendChild(card);

      const pd = data[type];
      Plotly.newPlot(`tsplot_${type}`, pd.data, {
        ...pd.layout,
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        margin: { l: 52, r: 20, t: 32, b: 50 },
        font: { family: 'DM Sans, sans-serif', size: 11, color: '#374151' },
        height: 310,
        xaxis: { ...(pd.layout.xaxis || {}), gridcolor: '#f3f4f6', linecolor: '#e5e7eb' },
        yaxis: { ...(pd.layout.yaxis || {}), gridcolor: '#f3f4f6', linecolor: '#e5e7eb' },
        hoverlabel: { bgcolor: '#1e3a5f', font: { color: '#fff', size: 12 } },
      }, {
        responsive: true, displayModeBar: true, displaylogo: false,
        modeBarButtonsToRemove: ['select2d', 'lasso2d']
      });
    });
  });
}

// Init time series selects when section is opened
const _origShowSection = window.showSection;
window.showSection = function (name) {
  _origShowSection && _origShowSection(name);
  if (name === 'timeseries' && window._state) tsInitSelects();
};

// ── EXPORT FUNCTIONS ─────────────────────────────────────────
function doExport(type) {
  if (!window._state) {
    showExportStatus('error', '❌ Upload dataset dulu sebelum export.');
    return;
  }
  // Baca parameter chart selector dari section-report
  let pdfQuery = '';
  if (type === 'pdf') {
    const checked = Array.from(document.querySelectorAll('#section-report input[type=checkbox]:checked'))
                        .map(cb => cb.value).filter(Boolean);
    const charts    = checked.length ? checked.join(',') : 'histogram,bar,scatter,heatmap,grouped_bar';
    const maxCols    = (document.getElementById('pdf_max_cols')    || {}).value || '4';
    const maxCatCols = (document.getElementById('pdf_max_cat_cols') || {}).value || '4';
    pdfQuery = '?charts=' + encodeURIComponent(charts)
             + '&max_cols=' + encodeURIComponent(maxCols)
             + '&max_cat_cols=' + encodeURIComponent(maxCatCols);
  }
  const routes = { pdf: 'export-pdf' + pdfQuery, excel: 'export-excel', csv: 'export-csv' };

  const labels = { pdf: 'PDF Report', excel: 'Excel (.xlsx)', csv: 'CSV' };
  const route = routes[type];
  if (!route) return;

  showExportStatus('loading', `⏳ Menyiapkan ${labels[type]}...`);

  // Disable all buttons
  document.querySelectorAll('.export-btn').forEach(b => b.disabled = true);

  // Use <a> trick to trigger download
  const a = document.createElement('a');
  a.href = '/' + route;
  a.download = '';
  document.body.appendChild(a);

  fetch('/' + route)
    .then(res => {
      if (!res.ok) return res.json().then(e => { throw new Error(e.error || 'Server error'); });
      return res.blob();
    })
    .then(blob => {
      const url = URL.createObjectURL(blob);
      a.href = url;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 3000);
      showExportStatus('success', `✅ ${labels[type]} berhasil didownload!`);
    })
    .catch(err => {
      showExportStatus('error', `❌ Gagal export: ${err.message}`);
    })
    .finally(() => {
      document.body.removeChild(a);
      document.querySelectorAll('.export-btn').forEach(b => b.disabled = false);
    });
}

function showExportStatus(type, msg) {
  const bar = document.getElementById('exportStatusBar');
  if (!bar) return;
  bar.className = 'export-status-bar ' + type;
  bar.textContent = msg;
  bar.style.display = 'flex';
  if (type !== 'loading') setTimeout(() => { bar.style.display = 'none'; }, 5000);
}
