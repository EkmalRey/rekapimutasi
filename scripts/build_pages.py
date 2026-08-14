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

    # 1. Create a clean zip of the Python package (excluding web, tests, caches)
    zip_path = DOCS / "rekapimutasi_pkg.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(REKAP):
            rel_root = os.path.relpath(root, ROOT)
            if "__pycache__" in rel_root or "web" in rel_root:
                continue
            for f in files:
                if f.endswith(".py") and f not in ("cli.py", "web.py"):
                    full_p = Path(root) / f
                    arc_p = Path(rel_root) / f
                    z.write(full_p, str(arc_p))

    print(f"Created {zip_path} ({zip_path.stat().st_size} bytes)")

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
let currentStmt = null;

async function init() {
  try {
    postMessage({ type: 'status', text: 'Memuat runtime Python WebAssembly...' });
    pyodide = await loadPyodide({
      indexURL: "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/"
    });

    postMessage({ type: 'status', text: 'Memuat dependencies (pypdf, openpyxl, cryptography)...' });
    await pyodide.loadPackage(["pypdf", "openpyxl", "cryptography"]);

    postMessage({ type: 'status', text: 'Menyiapkan modul rekapimutasi...' });
    // Fetch and unpack the python package zip into virtual filesystem
    const resp = await fetch("rekapimutasi_pkg.zip");
    if (!resp.ok) throw new Error("Gagal mengunduh modul rekapimutasi.");
    const buf = await resp.arrayBuffer();
    pyodide.unpackArchive(buf, "zip");

    // Initialize python bridge
    await pyodide.runPythonAsync(`
import sys
sys.path.insert(0, ".")
import rekapimutasi
from rekapimutasi.export import flatten_statement, xlsx_bytes, csv_bytes, sanitize_filename
from rekapimutasi.errors import RekapimutasiError
import tempfile, os, json
`);

    postMessage({ type: 'ready' });
  } catch (err) {
    postMessage({ type: 'error', text: 'Gagal menginisialisasi engine Python: ' + (err.message || err) });
  }
}

const readyPromise = init();

onmessage = async (e) => {
  await readyPromise;
  if (!pyodide) {
    postMessage({ id: e.data.id, error: 'Engine Python belum siap.' });
    return;
  }

  const { id, action, filename, data, format } = e.data;

  if (action === 'parse') {
    try {
      const ext = filename.toLowerCase().endsWith('.csv') ? '.csv' : '.pdf';
      pyodide.FS.writeFile('/tmp/input' + ext, new Uint8Array(data));

      const resultJson = await pyodide.runPythonAsync(`
try:
    _stmt = rekapimutasi.parse_file('/tmp/input${ext}')
    _data = flatten_statement(_stmt)
    _json_res = json.dumps({"ok": True, "data": _data})
except RekapimutasiError as e:
    _json_res = json.dumps({"ok": False, "error": f"Format file tidak dikenali atau tidak memiliki text layer: {e}"})
except Exception as e:
    _json_res = json.dumps({"ok": False, "error": str(e)})
_json_res
`);
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
        const xlsxBuf = await pyodide.runPythonAsync(`
_bytes = xlsx_bytes(_stmt)
_bytes
`);
        postMessage({ id, buffer: xlsxBuf.toJs(), format: 'xlsx' });
      } else if (format === 'csv') {
        const csvStr = await pyodide.runPythonAsync(`
_csv_b = csv_bytes(_stmt)
_csv_b.decode('utf-8')
`);
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

    # 4. Generate docs/index.html tailored for GitHub Pages (with Pyodide Worker status bar and 100% privacy badge)
    index_html = (REKAP / "web" / "index.html").read_text(encoding="utf-8")

    # Adjust title & copy slightly to emphasize 100% client-side privacy on GitHub Pages
    # and replace the fetch('/api/parse') calls with Pyodide Worker communication
    client_js = """
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('fileInput');
  const errorBox = document.getElementById('error');
  const resultBox = document.getElementById('result');
  let currentFile = null;
  let busyTimer = null;
  let pdfUrl = null;
  let isWorkerReady = false;
  let workerStatusText = 'Memuat engine...';

  // Initialize Pyodide Web Worker
  const worker = new Worker('worker.js');
  let reqId = 0;
  const pendingRequests = new Map();

  worker.onmessage = (e) => {
    const msg = e.data;
    if (msg.type === 'status') {
      workerStatusText = msg.text;
      const pendingEl = document.querySelector('.dropzone__pending');
      if (pendingEl) pendingEl.textContent = msg.text;
      const noteEl = document.querySelector('.mast__note');
      if (noteEl) noteEl.textContent = msg.text;
    } else if (msg.type === 'ready') {
      isWorkerReady = true;
      const noteEl = document.querySelector('.mast__note');
      if (noteEl) noteEl.innerHTML = '<span style="color:#16a34a">●</span> 100% Client-side (Data aman di browser)';
      const pendingEl = document.querySelector('.dropzone__pending');
      if (pendingEl) pendingEl.textContent = 'Memeriksa format…';
    } else if (msg.type === 'error') {
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
      setBusy(true, workerStatusText || 'Menyiapkan engine Python...');
    } else {
      setBusy(true, 'Mengekstrak transaksi...');
    }

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

    # Also update subtitle note
    docs_html = docs_html.replace(
        '<p class="mast__note">Parsing berjalan lokal</p>',
        '<p class="mast__note">Memuat engine WebAssembly...</p>',
    )
    docs_html = docs_html.replace(
        "data tidak dikirim ke server mana pun",
        "🔒 100% Client-side WebAssembly — Data tidak pernah dikirim ke server mana pun",
    )

    (DOCS / "index.html").write_text(docs_html, encoding="utf-8")
    print("Created docs/index.html")
    print("GitHub Pages build complete in docs/!")


if __name__ == "__main__":
    main()
