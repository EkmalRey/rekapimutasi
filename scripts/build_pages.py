#!/usr/bin/env python3
"""Build script for GitHub Pages static deployment using Pyodide (client-side WebAssembly)."""

import os
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
REKAP = ROOT / "rekapimutasi"


def main():
    if DOCS.exists():
        shutil.rmtree(DOCS)
    DOCS.mkdir(parents=True, exist_ok=True)

    # 1. Create a 100% self-contained zip of rekapimutasi + pure-Python dependencies (pypdf, openpyxl, et_xmlfile)
    zip_path = DOCS / "rekapimutasi_pkg.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        # Package rekapimutasi
        for root, dirs, files in os.walk(REKAP):
            rel_root = os.path.relpath(root, ROOT)
            if "__pycache__" in rel_root or "web" in rel_root:
                continue
            for f in files:
                if f.endswith(".py") and f not in ("cli.py", "web.py"):
                    full_p = Path(root) / f
                    arc_p = Path(rel_root) / f
                    z.write(full_p, str(arc_p))

        # Bundle pure-Python dependencies directly
        modules_to_bundle = []
        try:
            import pypdf
            modules_to_bundle.append(pypdf)
        except ImportError:
            print("Warning: pypdf not installed")

        try:
            import openpyxl
            modules_to_bundle.append(openpyxl)
        except ImportError:
            print("Warning: openpyxl not installed")

        try:
            import et_xmlfile
            modules_to_bundle.append(et_xmlfile)
        except ImportError:
            print("Warning: et_xmlfile not installed")

        for mod in modules_to_bundle:
            mod_dir = Path(mod.__file__).parent
            pkg_name = mod_dir.name
            print(f"Bundling {pkg_name} from {mod_dir}")
            for root, dirs, files in os.walk(mod_dir):
                if "__pycache__" in root:
                    continue
                for f in files:
                    if f.endswith(".py") or f.endswith(".json") or f.endswith(".xml"):
                        full_p = Path(root) / f
                        arc_p = Path(pkg_name) / os.path.relpath(full_p, mod_dir)
                        z.write(full_p, str(arc_p))

    print(f"Created self-contained {zip_path} ({zip_path.stat().st_size} bytes)")

    # 2. Copy assets & favicons
    assets_dst = DOCS / "assets"
    assets_dst.mkdir(parents=True, exist_ok=True)
    if (ROOT / "assets").exists():
        for f in (ROOT / "assets").iterdir():
            if f.is_file():
                shutil.copy2(f, assets_dst / f.name)

    for fav in ("favicon.svg", "favicon.ico", "favicon.png"):
        fav_src = REKAP / "web" / fav
        if fav_src.exists():
            shutil.copy2(fav_src, DOCS / fav)

    # 3. Create Web Worker script (worker.js)
    worker_js = """// Web Worker for client-side Python statement parsing using Pyodide (WASM)
importScripts("https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js");

let pyodide = null;
let parseDataFn = null;
let getXlsxFn = null;
let getCsvFn = null;

async function init() {
  try {
    postMessage({ type: 'status', step: 1, text: 'Memuat runtime Python WebAssembly...' });
    pyodide = await loadPyodide({
      indexURL: "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/"
    });

    postMessage({ type: 'status', step: 2, text: 'Menyiapkan modul rekapimutasi, pypdf & openpyxl...' });
    // Fetch and unpack the 100% self-contained python package zip into virtual filesystem
    const resp = await fetch("rekapimutasi_pkg.zip?v=" + Date.now());
    if (!resp.ok) throw new Error("Gagal mengunduh bundle modul rekapimutasi.");
    const buf = await resp.arrayBuffer();
    pyodide.unpackArchive(buf, "zip");

    postMessage({ type: 'status', step: 3, text: 'Menginisialisasi engine parser mutasi...' });
    // Initialize python bridge with persistent global helper functions
    await pyodide.runPythonAsync(`
import sys, os, json
sys.path.insert(0, os.getcwd())
sys.path.insert(0, "/home/pyodide")

import openpyxl
import pypdf
import rekapimutasi
from rekapimutasi.export import flatten_statement, xlsx_bytes, csv_bytes, sanitize_filename
from rekapimutasi.errors import RekapimutasiError

_current_stmt = None

def wasm_parse_file(filepath):
    global _current_stmt
    try:
        _current_stmt = rekapimutasi.parse_file(filepath)
        data = flatten_statement(_current_stmt)
        return json.dumps({"ok": True, "data": data})
    except RekapimutasiError as e:
        return json.dumps({"ok": False, "error": f"Format file tidak dikenali atau tidak memiliki text layer: {e}"})
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)})

def wasm_get_xlsx():
    global _current_stmt
    if _current_stmt is None:
        raise ValueError("Belum ada mutasi yang diproses.")
    return xlsx_bytes(_current_stmt)

def wasm_get_csv():
    global _current_stmt
    if _current_stmt is None:
        raise ValueError("Belum ada mutasi yang diproses.")
    return csv_bytes(_current_stmt).decode('utf-8')
`);

    parseDataFn = pyodide.globals.get('wasm_parse_file');
    getXlsxFn = pyodide.globals.get('wasm_get_xlsx');
    getCsvFn = pyodide.globals.get('wasm_get_csv');

    postMessage({ type: 'ready' });
  } catch (err) {
    postMessage({ type: 'error', text: 'Gagal menginisialisasi engine Python: ' + (err.message || err) });
  }
}

const readyPromise = init();

onmessage = async (e) => {
  await readyPromise;
  if (!pyodide || !parseDataFn) {
    postMessage({ id: e.data.id, error: 'Engine Python belum siap.' });
    return;
  }

  const { id, action, filename, data, format } = e.data;

  if (action === 'parse') {
    try {
      const ext = filename.toLowerCase().endsWith('.csv') ? '.csv' : '.pdf';
      const inPath = '/tmp/input' + ext;
      pyodide.FS.writeFile(inPath, new Uint8Array(data));

      const resultJson = parseDataFn(inPath);
      const parsed = JSON.parse(resultJson);
      if (!parsed.ok) {
        postMessage({ id, error: parsed.error });
      } else {
        postMessage({ id, data: parsed.data });
      }
    } catch (err) {
      postMessage({ id, error: err.message || String(err) });
    }
  } else if (action === 'download') {
    try {
      if (format === 'xlsx') {
        const xlsxBytes = getXlsxFn();
        postMessage({ id, buffer: xlsxBytes.toJs(), format: 'xlsx' });
      } else if (format === 'csv') {
        const csvStr = getCsvFn();
        postMessage({ id, text: csvStr, format: 'csv' });
      }
    } catch (err) {
      postMessage({ id, error: 'Download gagal: ' + (err.message || String(err)) });
    }
  }
};
"""
    (DOCS / "worker.js").write_text(worker_js, encoding="utf-8")
    print("Created docs/worker.js")

    # 4. Generate docs/index.html with interactive loading state & progress indicator
    index_html = (REKAP / "web" / "index.html").read_text(encoding="utf-8")

    # Inject additional CSS for the engine loader & status
    loader_css = """
/* ---- engine loader banner ------------------------------------------- */
.engine-banner {
  margin-top: var(--space-8);
  padding: var(--space-4) var(--space-6);
  border: 1px solid var(--color-rule-2);
  background: var(--color-paper-2);
  display: flex;
  align-items: center;
  gap: var(--space-4);
  transition: opacity 0.3s ease, transform 0.3s ease;
}
.engine-banner.is-hidden {
  opacity: 0;
  pointer-events: none;
  transform: translateY(-4px);
  position: absolute;
}
.engine-banner__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-accent);
}
.spin {
  animation: rotate 1.5s linear infinite;
}
@keyframes rotate {
  100% { transform: rotate(360deg); }
}
.engine-banner__text strong {
  display: block;
  font-size: var(--text-sm);
  color: var(--color-ink);
  font-weight: 500;
}
.engine-banner__text span {
  display: block;
  font-size: var(--text-xs);
  color: var(--color-muted);
  margin-top: 2px;
}
.dropzone.is-loading-engine {
  cursor: wait;
  opacity: 0.85;
}
.dropzone.is-loading-engine .dropzone__glyph {
  animation: pulse 1.8s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 1; }
}
"""
    style_end = index_html.find("</style>")
    if style_end != -1:
        index_html = index_html[:style_end] + "\n" + loader_css + "\n" + index_html[style_end:]

    banner_html = """
  <div class="engine-banner reveal" style="--i:2" id="engineBanner">
    <div class="engine-banner__icon">
      <svg class="spin" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M2 12h4m12 0h4M4.93 19.07l2.83-2.83m8.48-8.48l2.83-2.83"/>
      </svg>
    </div>
    <div class="engine-banner__text">
      <strong id="engineTitle">Menyiapkan Engine WebAssembly...</strong>
      <span id="engineSub">Memuat Python runtime & parser (100% di browser kamu, data tidak dikirim ke mana pun)</span>
    </div>
  </div>
"""
    dropzone_pos = index_html.find('<div class="dropzone')
    if dropzone_pos != -1:
        index_html = index_html[:dropzone_pos] + banner_html + "\n  " + index_html[dropzone_pos:]

    client_js = """
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('fileInput');
  const errorBox = document.getElementById('error');
  const resultBox = document.getElementById('result');
  const engineBanner = document.getElementById('engineBanner');
  const engineTitle = document.getElementById('engineTitle');
  const engineSub = document.getElementById('engineSub');

  let currentFile = null;
  let pendingFile = null;
  let busyTimer = null;
  let pdfUrl = null;
  let isWorkerReady = false;

  dropzone.classList.add('is-loading-engine');

  // Initialize Pyodide Web Worker (with timestamp cache-buster)
  const worker = new Worker('worker.js?v=' + Date.now());
  let reqId = 0;
  const pendingRequests = new Map();

  worker.onmessage = (e) => {
    const msg = e.data;
    if (msg.type === 'status') {
      if (engineTitle) engineTitle.textContent = msg.text;
      if (engineSub) engineSub.textContent = `Langkah ${msg.step || 1} dari 3 (hanya diunduh sekali di awal)`;
      const noteEl = document.querySelector('.mast__note');
      if (noteEl) noteEl.textContent = msg.text;
    } else if (msg.type === 'ready') {
      isWorkerReady = true;
      dropzone.classList.remove('is-loading-engine');
      if (engineBanner) {
        engineBanner.innerHTML = `
          <div class="engine-banner__icon" style="color:var(--color-accent);">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
          </div>
          <div class="engine-banner__text">
            <strong style="color:var(--color-accent-2);">Engine WebAssembly Siap!</strong>
            <span>100% Client-side — File mutasi bank kamu aman dan tidak pernah diunggah ke server mana pun.</span>
          </div>
        `;
        setTimeout(() => {
          engineBanner.classList.add('is-hidden');
        }, 3500);
      }
      const noteEl = document.querySelector('.mast__note');
      if (noteEl) noteEl.innerHTML = '<span style="color:#16a34a">●</span> 100% Client-side (Data aman di browser)';
      
      // If a user dropped a file while loading, parse it immediately!
      if (pendingFile) {
        const f = pendingFile;
        pendingFile = null;
        handleFile(f);
      }
    } else if (msg.type === 'error') {
      dropzone.classList.remove('is-loading-engine');
      if (engineBanner) engineBanner.classList.add('is-hidden');
      showError(msg.text);
    } else if (msg.id && pendingRequests.has(msg.id)) {
      const resolver = pendingRequests.get(msg.id);
      pendingRequests.delete(msg.id);
      resolver(msg);
    }
  };

  function sendWorker(action, payload) {
    return new Promise((resolve) => {
      const id = ++reqId;
      pendingRequests.set(id, resolve);
      worker.postMessage({ id, action, ...payload });
    });
  }

  const idr = new Intl.NumberFormat('id-ID');
  const fmtMoney = v => 'Rp' + idr.format(Math.abs(v));
  const fmtSigned = (v, type) =>
    (type === 'CR' ? '+' : '\\u2212') + 'Rp' + idr.format(Math.abs(v));

  function setBusy(on, text) {
    clearTimeout(busyTimer);
    const pendingEl = document.querySelector('.dropzone__pending');
    if (pendingEl && text) pendingEl.textContent = text;
    if (on) {
      busyTimer = setTimeout(() => dropzone.classList.add('is-busy'), 50);
    } else {
      dropzone.classList.remove('is-busy');
      if (pendingEl) pendingEl.textContent = 'Memeriksa format…';
    }
  }

  function showError(msg) {
    errorBox.textContent = msg;
    errorBox.hidden = false;
  }
  function clearError() { errorBox.hidden = true; errorBox.textContent = ''; }

  dropzone.addEventListener('click', () => fileInput.click());
  dropzone.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); }
  });
  fileInput.addEventListener('change', () => { if (fileInput.files[0]) handleFile(fileInput.files[0]); });

  ['dragenter', 'dragover'].forEach(ev =>
    dropzone.addEventListener(ev, e => { e.preventDefault(); dropzone.classList.add('is-dragover'); }));
  ['dragleave', 'drop'].forEach(ev =>
    dropzone.addEventListener(ev, e => { e.preventDefault(); dropzone.classList.remove('is-dragover'); }));
  dropzone.addEventListener('drop', e => { if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]); });

  async function handleFile(file) {
    currentFile = file;
    setPdfButton(file);
    clearError();
    resultBox.hidden = true;

    if (!isWorkerReady) {
      pendingFile = file;
      setBusy(true, 'File disimpan! Menunggu engine WebAssembly selesai disiapkan...');
      return;
    }

    setBusy(true, 'Mengekstrak transaksi mutasi…');

    try {
      const buffer = await file.arrayBuffer();
      const res = await sendWorker('parse', {
        filename: file.name,
        data: buffer
      });

      if (res.error) {
        showError(res.error || 'Terjadi kesalahan.');
        return;
      }
      render(res.data);
    } catch (e) {
      showError('Gagal memproses file: ' + (e.message || String(e)));
    } finally {
      setBusy(false);
    }
  }

  function render(data) {
    const total = data.rows.length;
    let cr = 0, db = 0;
    for (const row of data.rows) {
      const v = parseInt(row[3].replace(/[^0-9-]/g, ''), 10) || 0;
      if (v > 0) cr += v; else db += -v;
    }

    const items = [
      item('Bank', data.bank),
      item('Nama rekening', data.account_name),
      item('No. rekening', data.account_no),
      item('Periode', data.period),
      item('Transaksi', String(total)),
      item('Masuk', fmtMoney(cr), 'is-cr'),
      item('Keluar', fmtMoney(db), 'is-db'),
    ];
    if (data.pockets && data.pockets.length > 1) {
      items.push(`<div class="meta__item meta__pockets"><span class="meta__label">Kantong</span>` +
        `<span class="meta__value">${escapeHtml(data.pockets.join(' · '))}</span></div>`);
    }
    document.getElementById('meta').innerHTML = items.join('');

    const table = document.getElementById('table');
    table.innerHTML = '';
    const thead = document.createElement('thead');
    const headRow = document.createElement('tr');
    const labels = [];
    data.columns.forEach(c => {
      const th = document.createElement('th');
      th.textContent = c;
      headRow.appendChild(th);
      labels.push(c);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    for (const row of data.rows) {
      const tr = document.createElement('tr');
      row.forEach((cell, i) => {
        const td = document.createElement('td');
        td.dataset.label = labels[i] || '';
        if (i === 3) { // Amount
          td.classList.add('cell-num', 'cell-amt', 'is-' + (row[2] === 'CR' ? 'cr' : 'db'));
          td.textContent = cell === '' ? '' : fmtSigned(parseInt(cell, 10), row[2]);
        } else if (i === 4) { // Balance
          td.classList.add('cell-num', 'cell-amt');
          td.textContent = cell === '' ? '' : fmtMoney(parseInt(cell, 10));
        } else if (i === 2) { // Type
          td.classList.add('cell-type', 'is-' + (cell === 'CR' ? 'cr' : 'db'));
          td.textContent = cell;
        } else if (i === 1 || i === 0) { // Date / Time
          td.classList.add('cell-num');
          td.textContent = cell;
        } else {
          td.classList.add('cell-desc');
          const span = document.createElement('span');
          span.textContent = cell;
          td.appendChild(span);
        }
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);

    document.getElementById('empty').hidden = total > 0;
    resultBox.hidden = false;
  }

  function item(label, value, cls) {
    const v = escapeHtml(value || '\\u2014');
    return `<div class="meta__item"><span class="meta__label">${label}</span>` +
      `<span class="meta__value ${cls || ''}">${v}</span></div>`;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
  }

  function setPdfButton(file) {
    if (pdfUrl) { URL.revokeObjectURL(pdfUrl); pdfUrl = null; }
    const isPdf = file && (file.type === 'application/pdf' || /\\.pdf$/i.test(file.name));
    document.getElementById('dlPdf').hidden = !isPdf;
  }

  async function download(format) {
    if (!currentFile) return;
    const btn = format === 'xlsx' ? document.getElementById('dlXlsx') : document.getElementById('dlCsv');
    btn.disabled = true;
    try {
      const res = await sendWorker('download', { format });
      if (res.error) {
        showError(res.error);
        return;
      }
      let blob;
      if (format === 'xlsx') {
        blob = new Blob([res.buffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
      } else {
        blob = new Blob([res.text], { type: 'text/csv;charset=utf-8' });
      }
      const base = (currentFile.name || 'statement').replace(/\\.[^.]+$/, '');
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = base + '.' + format;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      showError('Download gagal.');
    } finally {
      btn.disabled = false;
    }
  }

  document.getElementById('dlXlsx').addEventListener('click', () => download('xlsx'));
  document.getElementById('dlCsv').addEventListener('click', () => download('csv'));
  document.getElementById('dlPdf').addEventListener('click', () => {
    if (!currentFile) return;
    if (!pdfUrl) pdfUrl = URL.createObjectURL(currentFile);
    window.open(pdfUrl, '_blank', 'noopener');
  });
"""

    # Replace the <script> body in index.html
    script_start = index_html.find("<script>")
    script_end = index_html.rfind("</script>")
    if script_start != -1 and script_end != -1:
        docs_html = (
            index_html[: script_start + len("<script>")]
            + "\n"
            + client_js
            + "\n"
            + index_html[script_end:]
        )
    else:
        docs_html = index_html

    docs_html = docs_html.replace(
        '<p class="mast__note">Parsing berjalan lokal</p>',
        '<p class="mast__note"><span style="color:#eab308">●</span> Memuat engine WebAssembly...</p>',
    )
    docs_html = docs_html.replace(
        "data tidak dikirim ke server mana pun",
        "🔒 100% Client-side WebAssembly — Data tidak pernah dikirim ke server mana pun",
    )

    (DOCS / "index.html").write_text(docs_html, encoding="utf-8")
    print("Created docs/index.html with self-contained bundle!")


if __name__ == "__main__":
    main()
