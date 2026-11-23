#!/usr/bin/env python3
"""Build script for GitHub Pages static deployment using Pyodide (client-side WebAssembly)."""

import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
REKAP = ROOT / "rekapimutasi"


def get_git_commit_timestamp(root: Path) -> str:
    """Extract latest Git commit timestamp in ISO-8601 format."""
    try:
        out = subprocess.check_output(
            ["git", "log", "-1", "--format=%cI"],
            cwd=str(root),
            stderr=subprocess.DEVNULL,
            encoding="utf-8",
        ).strip()
        if out:
            return out
    except (subprocess.SubprocessError, OSError):
        return os.environ.get("GIT_COMMIT_TIMESTAMP", "").strip()
    return os.environ.get("GIT_COMMIT_TIMESTAMP", "").strip()


def format_commit_timestamp(iso_ts: str) -> str:
    """Format ISO timestamp into human-readable Indonesian text (e.g. '14 Agustus 2026, 19:21 WIB')."""
    if not iso_ts:
        return ""
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(iso_ts)
        months = [
            "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
            "Juli", "Agustus", "September", "Oktober", "November", "Desember"
        ]
        month_name = months[dt.month]
        time_str = dt.strftime("%H:%M")
        tz_offset = dt.utcoffset()
        tz_name = ""
        if tz_offset is not None:
            secs = int(tz_offset.total_seconds())
            if secs == 7 * 3600:
                tz_name = " WIB"
            elif secs == 8 * 3600:
                tz_name = " WITA"
            elif secs == 9 * 3600:
                tz_name = " WIT"
            elif secs == 0:
                tz_name = " UTC"
            else:
                sign = "+" if secs >= 0 else "-"
                hours = abs(secs) // 3600
                mins = (abs(secs) % 3600) // 60
                tz_name = f" GMT{sign}{hours:02d}:{mins:02d}"
        return f"{dt.day} {month_name} {dt.year}, {time_str}{tz_name}"
    except Exception:
        return iso_ts.replace("T", " ")


def embed_commit_timestamp(html_text: str, iso_ts: str) -> str:
    """Embed or replace the <time id="lastUpdated"> tag with the commit timestamp."""
    if not iso_ts:
        return html_text
    display_ts = format_commit_timestamp(iso_ts)
    time_tag = f'<time id="lastUpdated" datetime="{iso_ts}">{display_ts}</time>'
    if 'id="lastUpdated"' in html_text:
        return re.sub(r'<time\s+id="lastUpdated"[^>]*>.*?</time>', time_tag, html_text)
    if '<p class="colophon__meta">' in html_text:
        return html_text.replace(
            '<p class="colophon__meta">',
            f'<p class="colophon__meta"><a href="https://github.com/EkmalRey/rekapimutasi" target="_blank" rel="noopener noreferrer" class="tooltip">rekapimutasi<span class="tooltip__content" role="tooltip">Source Code di GitHub</span></a> · <span class="tooltip" tabindex="0">MIT<span class="tooltip__content" role="tooltip">Lisensi MIT: Bebas digunakan, dipelajari, dimodifikasi, dan didistribusikan untuk keperluan apa pun (sumber terbuka).</span></span> · Terakhir diperbarui: {time_tag} · ',
            1,
        )
    return html_text


def main():
    iso_ts = get_git_commit_timestamp(ROOT)
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
                        if f == "_cryptography.py" and "pypdf" in str(arc_p):
                            content = full_p.read_text(encoding="utf-8")
                            content = content.replace(
                                "from cryptography.hazmat.decrepit.ciphers.algorithms import ARC4",
                                "try:\n    from cryptography.hazmat.decrepit.ciphers.algorithms import ARC4\nexcept ImportError:\n    from cryptography.hazmat.primitives.ciphers.algorithms import ARC4",
                            )
                            z.writestr(str(arc_p), content)
                        else:
                            z.write(full_p, str(arc_p))

    print(f"Created self-contained {zip_path} ({zip_path.stat().st_size} bytes)")

    # 2. Copy assets & favicons
    assets_dst = DOCS / "assets"
    assets_dst.mkdir(parents=True, exist_ok=True)
    if (ROOT / "assets").exists():
        for f in (ROOT / "assets").iterdir():
            if f.is_file():
                shutil.copy2(f, assets_dst / f.name)

    for f_name in ("favicon.svg", "favicon.ico", "favicon.png", "robots.txt", "sitemap.xml", "manifest.webmanifest", "sw.js"):
        src = REKAP / "web" / f_name
        if src.exists():
            if f_name == "sitemap.xml" and iso_ts:
                content = src.read_text(encoding="utf-8")
                date_part = iso_ts.split("T")[0]
                content = re.sub(r"<lastmod>.*?</lastmod>", f"<lastmod>{date_part}</lastmod>", content)
                (DOCS / f_name).write_text(content, encoding="utf-8")
            else:
                shutil.copy2(src, DOCS / f_name)

    # 3. Create Web Worker script (worker.js)
    worker_js = """// Web Worker for client-side Python statement parsing using Pyodide (WASM)
importScripts("https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js");

let pyodide = null;
let parseDataFn = null;
let clearStmtsFn = null;
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

    // BCA e-statements are AES-256 encrypted; pypdf needs cryptography for that.
    postMessage({ type: 'status', step: 3, text: 'Memuat modul AES & menginisialisasi engine parser mutasi...' });
    await pyodide.loadPackage('cryptography');

    postMessage({ type: 'status', step: 3, text: 'Menginisialisasi engine parser mutasi...' });
    // Initialize python bridge with persistent global helper functions
    await pyodide.runPythonAsync(`
import sys, os, json
sys.path.insert(0, os.getcwd())
sys.path.insert(0, "/home/pyodide")

import openpyxl
import pypdf
import rekapimutasi
from rekapimutasi.export import flatten_statement, xlsx_bytes, csv_bytes, multi_xlsx_bytes, multi_csv_bytes, multi_csv_zip_bytes
from rekapimutasi.errors import RekapimutasiError, PasswordProtectedError, WrongPasswordError

_current_stmts = {}

def wasm_clear_stmts():
    global _current_stmts
    _current_stmts = {}

def wasm_parse_file(filepath, password="", index=0):
    global _current_stmts
    try:
        stmt = rekapimutasi.parse_file(filepath, password=password if password else None)
        _current_stmts[int(index)] = stmt
        data = flatten_statement(stmt)
        return json.dumps({"ok": True, "data": data})
    except WrongPasswordError as e:
        return json.dumps({"ok": False, "requires_password": True, "wrong_password": True, "error": str(e)})
    except PasswordProtectedError as e:
        return json.dumps({"ok": False, "requires_password": True, "error": str(e)})
    except RekapimutasiError as e:
        return json.dumps({"ok": False, "error": f"Format file tidak dikenali atau tidak memiliki text layer: {e}"})
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)})

def wasm_get_xlsx(mode="multi_sheet"):
    global _current_stmts
    stmts = [stmt for _, stmt in sorted(_current_stmts.items())]
    if not stmts:
        raise ValueError("Belum ada mutasi yang diproses.")
    if len(stmts) == 1:
        return xlsx_bytes(stmts[0])
    return multi_xlsx_bytes(stmts, mode=mode)

def wasm_get_csv():
    global _current_stmts
    stmts = [stmt for _, stmt in sorted(_current_stmts.items())]
    if not stmts:
        raise ValueError("Belum ada mutasi yang diproses.")
    if len(stmts) == 1:
        return csv_bytes(stmts[0]).decode('utf-8')
    return multi_csv_bytes(stmts).decode('utf-8')

def wasm_get_zip():
    global _current_stmts
    stmts = [stmt for _, stmt in sorted(_current_stmts.items())]
    if not stmts:
        raise ValueError("Belum ada mutasi yang diproses.")
    return multi_csv_zip_bytes(stmts)
`);

    parseDataFn = pyodide.globals.get('wasm_parse_file');
    clearStmtsFn = pyodide.globals.get('wasm_clear_stmts');
    getXlsxFn = pyodide.globals.get('wasm_get_xlsx');
    getCsvFn = pyodide.globals.get('wasm_get_csv');
    getZipFn = pyodide.globals.get('wasm_get_zip');

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

  const { id, action, filename, data, format, mode, reset, password, index } = e.data;

  if (action === 'clear') {
    if (clearStmtsFn) clearStmtsFn();
    postMessage({ id, ok: true });
  } else if (action === 'parse') {
    try {
      if (reset && clearStmtsFn) clearStmtsFn();
      const ext = filename.toLowerCase().endsWith('.csv') ? '.csv' : '.pdf';
      const inPath = '/tmp/input_' + id + ext;
      pyodide.FS.writeFile(inPath, new Uint8Array(data));

      const resultJson = parseDataFn(inPath, password || '', index || 0);
      try { pyodide.FS.unlink(inPath); } catch (_) {}
      const parsed = JSON.parse(resultJson);
      if (!parsed.ok) {
        postMessage({
          id,
          error: parsed.error,
          requires_password: !!parsed.requires_password,
          wrong_password: !!parsed.wrong_password
        });
      } else {
        postMessage({ id, data: parsed.data });
      }
    } catch (err) {
      postMessage({ id, error: err.message || String(err) });
    }
  } else if (action === 'download') {
    try {
      if (format === 'xlsx') {
        const xlsxBytes = getXlsxFn(mode || 'multi_sheet');
        postMessage({ id, buffer: xlsxBytes.toJs(), format: 'xlsx' });
      } else if (format === 'zip' || (format === 'csv' && mode === 'multi_sheet')) {
        const zipBytes = getZipFn();
        postMessage({ id, buffer: zipBytes.toJs(), format: 'zip' });
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
    iso_ts = get_git_commit_timestamp(ROOT)
    master_html = (REKAP / "web" / "index.html").read_text(encoding="utf-8")
    if iso_ts:
        updated_master = embed_commit_timestamp(master_html, iso_ts)
        if updated_master != master_html:
            (REKAP / "web" / "index.html").write_text(updated_master, encoding="utf-8")
        index_html = updated_master
    else:
        index_html = master_html

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
.dropzone.is-queued .dropzone__pending { display: block; }
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

    client_js = r"""
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('fileInput');
  const errorBox = document.getElementById('error');
  const resultBox = document.getElementById('result');
  const splitDownload = document.getElementById('splitDownload');
  const btnDownloadMain = document.getElementById('btnDownloadMain');
  const btnDownloadToggle = document.getElementById('btnDownloadToggle');
  const downloadMenu = document.getElementById('downloadMenu');
  const fileSelectBar = document.getElementById('fileSelectBar');
  const fileSelect = document.getElementById('fileSelect');
  const engineBanner = document.getElementById('engineBanner');
  const engineTitle = document.getElementById('engineTitle');
  const engineSub = document.getElementById('engineSub');

  // Password Modal elements
  const pwdModal = document.getElementById('pwdModal');
  const pwdModalTitle = document.getElementById('pwdModalTitle');
  const pwdModalSub = document.getElementById('pwdModalSub');
  const pwdModalFileBadge = document.getElementById('pwdModalFileBadge');
  const pwdModalLockedList = document.getElementById('pwdModalLockedList');
  const pwdModalLockedUl = document.getElementById('pwdModalLockedUl');
  const pwdForm = document.getElementById('pwdForm');
  const pwdInput = document.getElementById('pwdInput');
  const pwdToggleVisibility = document.getElementById('pwdToggleVisibility');
  const pwdEyeOpen = document.getElementById('pwdEyeOpen');
  const pwdEyeClosed = document.getElementById('pwdEyeClosed');
  const pwdError = document.getElementById('pwdError');
  const pwdBtnCancel = document.getElementById('pwdBtnCancel');
  const pwdBtnSkip = document.getElementById('pwdBtnSkip');
  const pwdBtnSubmit = document.getElementById('pwdBtnSubmit');
  const pwdModalBackdrop = document.getElementById('pwdModalBackdrop');

  let currentFiles = [];
  let multiResults = [];
  let consolidatedData = null;
  let activeFileIdx = -1;
  let pendingFiles = null;
  let busyTimer = null;
  let pdfUrl = null;
  let isWorkerReady = false;
  let pwdModalResolve = null;

  // Initialize Pyodide Web Worker (with timestamp cache-buster)
  const wasmInitStart = performance.now();
  const worker = new Worker('worker.js?v=' + Date.now());
  let reqId = 0;
  const pendingRequests = new Map();

  worker.onerror = (e) => {
    console.error('Worker error:', e);
    trackEvent('wasm_error', { error_message: (e && e.message) ? e.message : 'Worker error' });
    dropzone.classList.remove('is-queued');
    if (engineBanner) {
      engineBanner.innerHTML = `
        <div class="engine-banner__icon" style="color:#ef4444;">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
        </div>
        <div class="engine-banner__text">
          <strong style="color:#ef4444;">Gagal memuat Engine WebAssembly</strong>
          <span>${(e && e.message) ? e.message : 'Terjadi kendala saat mengunduh runtime WebAssembly.'} Silakan coba refresh halaman.</span>
        </div>
      `;
    }
    showError('Gagal memuat engine WebAssembly: ' + ((e && e.message) || 'Worker error'));
  };

  worker.onmessage = (e) => {
    const msg = e.data;
    if (msg.type === 'status') {
      if (engineTitle) engineTitle.textContent = msg.text;
      if (engineSub) engineSub.textContent = `Langkah ${msg.step || 1} dari 3 (hanya diunduh sekali di awal)`;
      const noteEl = document.querySelector('.mast__note');
      if (noteEl) noteEl.textContent = msg.text;
    } else if (msg.type === 'ready') {
      isWorkerReady = true;
      const durationMs = Math.round(performance.now() - wasmInitStart);
      const durationSec = Number((durationMs / 1000).toFixed(1));
      trackEvent('wasm_ready', { duration_ms: durationMs, duration_sec: durationSec });
      dropzone.classList.remove('is-queued');
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
          setTimeout(() => { engineBanner.remove(); }, 350);
        }, 3500);
      }
      const noteEl = document.querySelector('.mast__note');
      if (noteEl) noteEl.innerHTML = '<span style="color:#16a34a">●</span> 100% Client-side (Data aman di browser)';
      
      // If a user dropped a file while loading, parse it immediately!
      if (pendingFiles && pendingFiles.length) {
        const fs = pendingFiles;
        pendingFiles = null;
        handleFiles(fs);
      }
    } else if (msg.type === 'error') {
      trackEvent('wasm_error', { error_message: msg.text || 'Wasm initialization error' });
      dropzone.classList.remove('is-queued');
      if (engineBanner) { engineBanner.classList.add('is-hidden'); setTimeout(() => { engineBanner.remove(); }, 350); }
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

  const idr = new Intl.NumberFormat('id-ID', { maximumFractionDigits: 2 });
  // amounts arrive as plain decimal strings ("108400", "-235.20"); keep cents
  const toNum = v => parseFloat(String(v).replace(/[^0-9.-]/g, '')) || 0;
  const fmtMoney = v => 'Rp' + idr.format(Math.abs(v));
  const fmtSigned = (v, type) =>
    (type === 'CR' ? '+' : '−') + 'Rp' + idr.format(Math.abs(v));

  function trackEvent(name, params) {
    if (typeof window.gtag === 'function') {
      window.gtag('event', name, params);
    }
  }

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

  if (pwdToggleVisibility) {
    pwdToggleVisibility.addEventListener('click', (e) => {
      e.preventDefault();
      const isShowing = pwdToggleVisibility.classList.toggle('is-showing-password');
      pwdInput.type = isShowing ? 'text' : 'password';
      pwdToggleVisibility.setAttribute('aria-label', isShowing ? 'Sembunyikan password' : 'Tampilkan password');
      pwdInput.focus();
    });
  }

  if (pwdInput) {
    pwdInput.addEventListener('input', () => {
      pwdInput.classList.remove('is-invalid');
      if (pwdError) {
        pwdError.hidden = true;
        pwdError.innerHTML = '';
      }
    });
  }

  function closePasswordModal() {
    if (pwdModal) pwdModal.hidden = true;
    if (pwdToggleVisibility) {
      pwdToggleVisibility.classList.remove('is-showing-password');
      pwdToggleVisibility.setAttribute('aria-label', 'Tampilkan password');
    }
    if (pwdInput) {
      pwdInput.value = '';
      pwdInput.classList.remove('is-invalid');
      pwdInput.type = 'password';
    }
    if (pwdError) {
      pwdError.hidden = true;
      pwdError.innerHTML = '';
    }
    if (pwdBtnSubmit) {
      pwdBtnSubmit.disabled = false;
      pwdBtnSubmit.textContent = 'Buka & Proses';
    }
  }

  function showPasswordModalError(msg) {
    if (pwdError) {
      pwdError.innerHTML = `
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;">
          <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
        <span>${escapeHtml(msg || 'Password salah. Silakan coba lagi.')}</span>
      `;
      pwdError.hidden = false;
    }
    if (pwdInput) {
      pwdInput.classList.add('is-invalid');
      pwdInput.select();
      pwdInput.focus();
    }
  }

  function promptPasswordModal(currentFile, remainingQueue, totalLockedCount, currentIndex, attemptFn) {
    return new Promise((resolve) => {
      if (pwdModalSub) {
        if (totalLockedCount > 1) {
          pwdModalSub.textContent = `File ${currentIndex + 1} dari ${totalLockedCount} file terkunci memerlukan password.`;
        } else {
          pwdModalSub.textContent = 'File memerlukan password untuk diekstrak.';
        }
      }
      if (pwdModalFileBadge) {
        pwdModalFileBadge.textContent = '📄 ' + currentFile.name;
      }
      if (pwdModalLockedList && pwdModalLockedUl) {
        const others = remainingQueue.slice(1);
        if (others.length > 0) {
          pwdModalLockedList.hidden = false;
          pwdModalLockedUl.innerHTML = others
            .map(item => `<li>${escapeHtml(item.file.name)}</li>`)
            .join('');
        } else {
          pwdModalLockedList.hidden = true;
          pwdModalLockedUl.innerHTML = '';
        }
      }
      if (pwdError) {
        pwdError.hidden = true;
        pwdError.innerHTML = '';
      }
      if (pwdToggleVisibility) {
        pwdToggleVisibility.classList.remove('is-showing-password');
        pwdToggleVisibility.setAttribute('aria-label', 'Tampilkan password');
      }
      if (pwdInput) {
        pwdInput.classList.remove('is-invalid');
        pwdInput.value = '';
        pwdInput.type = 'password';
      }
      if (pwdBtnSubmit) { pwdBtnSubmit.disabled = false; pwdBtnSubmit.textContent = 'Buka & Proses'; }

      if (pwdModal) pwdModal.hidden = false;
      setTimeout(() => { if (pwdInput) pwdInput.focus(); }, 60);

      const cleanup = () => {
        if (pwdForm) pwdForm.removeEventListener('submit', onSubmit);
        if (pwdBtnSkip) pwdBtnSkip.removeEventListener('click', onSkip);
        if (pwdBtnCancel) pwdBtnCancel.removeEventListener('click', onCancel);
        if (pwdModalBackdrop) pwdModalBackdrop.removeEventListener('click', onCancel);
      };

      const onSubmit = async (e) => {
        e.preventDefault();
        const pwd = pwdInput.value;
        if (!pwd) {
          pwdInput.focus();
          return;
        }
        if (pwdBtnSubmit) {
          pwdBtnSubmit.disabled = true;
          pwdBtnSubmit.textContent = 'Memeriksa…';
        }
        if (pwdError) pwdError.hidden = true;

        try {
          const res = await attemptFn(pwd);
          if (res.ok && res.data) {
            cleanup();
            closePasswordModal();
            resolve({ action: 'submit', password: pwd, data: res.data });
          } else {
            if (pwdBtnSubmit) {
              pwdBtnSubmit.disabled = false;
              pwdBtnSubmit.textContent = 'Buka & Proses';
            }
            if (res.wrong_password || res.requires_password) {
              showPasswordModalError('Password salah untuk file ini. Silakan coba lagi.');
            } else {
              showPasswordModalError(res.error || 'Password salah atau format file tidak cocok.');
            }
          }
        } catch (err) {
          if (pwdBtnSubmit) {
            pwdBtnSubmit.disabled = false;
            pwdBtnSubmit.textContent = 'Buka & Proses';
          }
          showPasswordModalError(err.message || String(err));
        }
      };

      const onSkip = () => {
        cleanup();
        closePasswordModal();
        resolve({ action: 'skip' });
      };

      const onCancel = () => {
        cleanup();
        closePasswordModal();
        resolve({ action: 'cancel' });
      };

      if (pwdForm) pwdForm.addEventListener('submit', onSubmit);
      if (pwdBtnSkip) pwdBtnSkip.addEventListener('click', onSkip);
      if (pwdBtnCancel) pwdBtnCancel.addEventListener('click', onCancel);
      if (pwdModalBackdrop) pwdModalBackdrop.addEventListener('click', onCancel);
    });
  }

  dropzone.addEventListener('click', () => fileInput.click());
  dropzone.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); }
  });
  fileInput.addEventListener('change', () => { if (fileInput.files.length) handleFiles(fileInput.files); });

  ['dragenter', 'dragover'].forEach(ev =>
    dropzone.addEventListener(ev, e => { e.preventDefault(); dropzone.classList.add('is-dragover'); }));
  ['dragleave', 'drop'].forEach(ev =>
    dropzone.addEventListener(ev, e => { e.preventDefault(); dropzone.classList.remove('is-dragover'); }));
  dropzone.addEventListener('drop', e => { if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files); });

  async function handleFiles(fileList) {
    currentFiles = Array.from(fileList);
    if (!currentFiles.length) return;
    const parseStartTime = performance.now();
    trackEvent('files_uploaded', { file_count: currentFiles.length });
    clearError();
    resultBox.hidden = true;

    if (!isWorkerReady) {
      pendingFiles = currentFiles;
      const pendingEl = document.querySelector('.dropzone__pending');
      if (pendingEl) pendingEl.textContent = `${currentFiles.length} file diterima · menunggu engine siap…`;
      dropzone.classList.add('is-queued');
      return;
    }

    dropzone.classList.remove('is-queued');
    await sendWorker('clear');

    setBusy(true, `Memeriksa ${currentFiles.length} file…`);

    const parsedList = [];
    const lockedQueue = [];

    try {
      // PASS 1: Parse all files without password first
      for (let i = 0; i < currentFiles.length; i++) {
        const file = currentFiles[i];
        setBusy(true, `Memproses ${i + 1} dari ${currentFiles.length}: ${file.name}…`);
        const buffer = await file.arrayBuffer();
        const res = await sendWorker('parse', {
          index: i,
          filename: file.name,
          data: buffer,
          password: ''
        });

        if (res.requires_password) {
          trackEvent('password_prompted', { file_type: 'pdf' });
          lockedQueue.push({ file, fileIndex: i, buffer });
        } else if (res.error) {
          trackEvent('parse_error', { error_message: res.error, file_type: file.name.endsWith('.csv') ? 'csv' : 'pdf' });
          showError(`File «${file.name}»: ${res.error}`);
          setBusy(false);
          return;
        } else {
          parsedList.push({ file, fileIndex: i, data: res.data });
        }
      }

      // PASS 2: If there are locked files, resolve them
      if (lockedQueue.length > 0) {
        let rememberedPassword = '';
        const totalLocked = lockedQueue.length;
        let unlockedCount = 0;

        while (lockedQueue.length > 0) {
          const item = lockedQueue[0];
          let unlocked = false;

          // 1. Try remembered password automatically if available
          if (rememberedPassword) {
            setBusy(true, `Membuka ${item.file.name} dengan password tersimpan…`);
            const res = await sendWorker('parse', {
              index: item.fileIndex,
              filename: item.file.name,
              data: item.buffer,
              password: rememberedPassword
            });

            if (!res.error && res.data) {
              trackEvent('password_unlocked', { method: 'auto' });
              parsedList.push({ file: item.file, fileIndex: item.fileIndex, data: res.data });
              lockedQueue.shift();
              unlockedCount++;
              unlocked = true;
              continue; // Auto-unlocked silently!
            } else {
              rememberedPassword = '';
            }
          }

          // 2. Prompt user via modal
          setBusy(false);
          const choice = await promptPasswordModal(
            item.file,
            lockedQueue,
            totalLocked,
            unlockedCount,
            async (pwd) => {
              const res = await sendWorker('parse', {
                index: item.fileIndex,
                filename: item.file.name,
                data: item.buffer,
                password: pwd
              });
              if (!res.error && res.data) {
                return { ok: true, data: res.data };
              }
              if (res.wrong_password || res.requires_password) {
                trackEvent('password_failed', { reason: 'wrong_password' });
              }
              return {
                ok: false,
                wrong_password: !!(res.wrong_password || res.requires_password),
                error: res.error
              };
            }
          );

          if (choice.action === 'cancel') {
            lockedQueue.length = 0;
            break;
          } else if (choice.action === 'skip') {
            lockedQueue.shift();
            unlockedCount++;
          } else if (choice.action === 'submit') {
            trackEvent('password_unlocked', { method: 'manual' });
            rememberedPassword = choice.password;
            parsedList.push({ file: item.file, fileIndex: item.fileIndex, data: choice.data });
            lockedQueue.shift();
            unlockedCount++;
          }
        }
      }

      setBusy(false);

      if (!parsedList.length) {
        showError('Tidak ada file statement yang berhasil diproses.');
        return;
      }

      parsedList.sort((a, b) => a.fileIndex - b.fileIndex);
      multiResults = parsedList;
      currentFiles = parsedList.map(p => p.file);

      const parseDurationMs = Math.round(performance.now() - parseStartTime);
      // Track statement parsing in analytics (100% anonymized metadata only)
      for (const p of parsedList) {
        trackEvent('statement_parsed', {
          bank: p.data && p.data.bank ? p.data.bank : 'Unknown',
          tx_count: p.data && p.data.rows ? p.data.rows.length : 0,
          file_type: p.file && p.file.name && p.file.name.toLowerCase().endsWith('.csv') ? 'csv' : 'pdf',
          parse_duration_ms: parseDurationMs,
        });
      }

      if (parsedList.length === 1) {
        setPdfButton(parsedList[0].file);
        renderSingle(parsedList[0].data);
      } else {
        setPdfButton(null);
        renderMulti(parsedList);
      }
    } catch (e) {
      trackEvent('parse_error', { error_message: (e.message || String(e)), file_type: 'unknown' });
      showError('Gagal memproses file: ' + (e.message || String(e)));
    } finally {
      setBusy(false);
    }
  }

  function buildConsolidatedData(results) {
    const columns = ['Bank', 'No. Rekening', 'Nama Rekening', 'Periode', 'Kantong', 'Date', 'Time', 'Type', 'Amount', 'Balance', 'Source/Destination', 'Details', 'Notes', 'Transaction ID'];
    const rows = [];
    let cr = 0, db = 0;
    const banks = new Set();
    const periods = new Set();
    for (const item of results) {
      const d = item.data;
      if (d.bank) banks.add(d.bank);
      if (d.period) periods.add(d.period);
      const rowPockets = d.row_pockets || [];
      d.rows.forEach((r, idx) => {
        const pocketName = rowPockets[idx] || (d.pockets && d.pockets.length === 1 ? (d.pockets[0] || '') : '');
        rows.push([
          d.bank || '',
          d.account_no || '',
          d.account_name || '',
          d.period || '',
          pocketName,
          r[0] || '',
          r[1] || '',
          r[2] || '',
          r[3] || '',
          r[4] || '',
          r[5] || '',
          r[6] || '',
          r[7] || '',
          r[8] || '',
        ]);
        const v = toNum(r[3]);
        if (v > 0) cr += v; else db += -v;
      });
    }

    // Default sort by Date (index 5) and Time (index 6) from oldest to newest
    rows.sort((a, b) => {
      const da = (a[5] || '') + ' ' + (a[6] || '').replace('.', ':');
      const db = (b[5] || '') + ' ' + (b[6] || '').replace('.', ':');
      return da.localeCompare(db);
    });

    return {
      isMulti: true,
      bank: Array.from(banks).join(' · '),
      account_name: results.length + ' File Statement',
      account_no: Array.from(new Set(results.map(r => r.data.account_no).filter(Boolean))).join(', ') || '—',
      period: Array.from(periods).join(' · ') || '—',
      columns: columns,
      rows: rows,
      totalCr: cr,
      totalDb: db,
    };
  }

  function scrollToResults() {
    requestAnimationFrame(() => {
      const target = (fileSelectBar && !fileSelectBar.hidden) ? fileSelectBar : document.querySelector('.actions');
      if (target) {
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  }

  function renderSingle(data) {
    multiResults = [{ file: currentFiles[0] || { name: 'File' }, data }];
    consolidatedData = null;
    activeFileIdx = 0;
    if (fileSelectBar) fileSelectBar.hidden = true;
    setPdfButton(currentFiles[0] || (multiResults[0] && multiResults[0].file));
    renderData(data, false);
    scrollToResults();
  }

  function renderMulti(results) {
    consolidatedData = buildConsolidatedData(results);
    activeFileIdx = -1;
    if (fileSelectBar) fileSelectBar.hidden = false;
    setPdfButton(null);
    updateFileSelect();
    renderData(consolidatedData, true);
    scrollToResults();
  }

  function updateFileSelect() {
    if (!fileSelect) return;
    fileSelect.innerHTML = '';
    const allOpt = document.createElement('option');
    allOpt.value = '-1';
    allOpt.textContent = `Semua File (Gabungan: ${consolidatedData.rows.length} transaksi)`;
    fileSelect.appendChild(allOpt);

    multiResults.forEach((item, idx) => {
      const opt = document.createElement('option');
      opt.value = String(idx);
      const label = `[${idx + 1}] ${item.data.bank} · ${item.data.period || item.file.name || 'File ' + (idx + 1)} (${item.data.rows.length} transaksi)`;
      opt.textContent = label;
      fileSelect.appendChild(opt);
    });
    fileSelect.value = String(activeFileIdx);
  }

  if (fileSelect) {
    fileSelect.addEventListener('change', () => {
      activeFileIdx = parseInt(fileSelect.value, 10);
      if (activeFileIdx === -1) {
        setPdfButton(null);
        renderData(consolidatedData, true);
      } else {
        const item = multiResults[activeFileIdx];
        setPdfButton(item ? item.file : null);
        renderData(item.data, false);
      }
    });
  }

  let parsedData = null;
  let sortCol = null;
  let sortDir = 1;
  let activeTypeFilter = 'all';

  function resetFilterPills() {
    activeTypeFilter = 'all';
    document.querySelectorAll('.filter-pills .pill').forEach(btn => {
      btn.classList.toggle('is-active', btn.dataset.type === 'all');
    });
  }

  function renderData(data, isCombined) {
    parsedData = data;
    // Default sort: Date column (5 for combined, 0 for single), oldest to newest
    sortCol = isCombined ? 5 : 0;
    sortDir = 1;
    const filterEl = document.getElementById('filter');
    if (filterEl) filterEl.value = '';
    resetFilterPills();

    const total = data.rows.length;
    let cr = 0, db = 0;
    if (isCombined) {
      cr = data.totalCr || 0;
      db = data.totalDb || 0;
    } else {
      for (const row of data.rows) {
        const v = toNum(row[3]);
        if (v > 0) cr += v; else db += -v;
      }
    }

    const net = Math.round((cr - db) * 100) / 100;
    const netStr = net === 0 ? 'Rp0' : (net > 0 ? '+' : '−') + fmtMoney(Math.abs(net));
    const netCls = net > 0 ? 'is-cr' : (net < 0 ? 'is-db' : '');

    const items = [
      item(isCombined ? 'Total File' : 'Bank', isCombined ? `${multiResults.length} file (${data.bank})` : data.bank),
      item(isCombined ? 'Rekening' : 'Nama rekening', isCombined ? data.account_no : data.account_name),
      item(isCombined ? 'Periode File' : 'No. rekening', isCombined ? data.period : data.account_no),
      ...(isCombined ? [] : [item('Periode', data.period)]),
      item('Transaksi', String(total)),
      item('Masuk', fmtMoney(cr), 'is-cr'),
      item('Keluar', fmtMoney(db), 'is-db'),
      item('Selisih (Net)', netStr, netCls),
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
    data.columns.forEach((c, i) => {
      const th = document.createElement('th');
      th.textContent = c;
      th.dataset.col = i;
      th.classList.add('sortable');
      if (i === sortCol) th.classList.add('sorted-asc');
      th.tabIndex = 0;
      th.addEventListener('click', () => toggleSort(i));
      th.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleSort(i); }
      });
      headRow.appendChild(th);
      labels.push(c);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);
    table.dataset.labels = JSON.stringify(labels);

    drawTable();
    resultBox.hidden = false;
  }

  function currentRows() {
    const filterEl = document.getElementById('filter');
    const q = (filterEl ? filterEl.value : '').trim().toLowerCase();
    const isComb = parsedData && parsedData.isMulti;
    const typeIdx = isComb ? 7 : 2;

    let rows = parsedData.rows.filter(r => {
      if (activeTypeFilter !== 'all' && (r[typeIdx] || '') !== activeTypeFilter) {
        return false;
      }
      return !q || r.some(c => String(c).toLowerCase().includes(q));
    });
    if (sortCol !== null) {
      const isComb = parsedData && parsedData.isMulti;
      const amtIdx = isComb ? 8 : 3;
      const balIdx = isComb ? 9 : 4;
      const dateIdx = isComb ? 5 : 0;
      const timeIdx = isComb ? 6 : 1;
      const num = sortCol === amtIdx || sortCol === balIdx;
      const isDate = sortCol === dateIdx;
      rows = rows.slice().sort((a, b) => {
        if (isDate) {
          const da = (a[dateIdx] || '') + ' ' + (a[timeIdx] || '').replace('.', ':');
          const db = (b[dateIdx] || '') + ' ' + (b[timeIdx] || '').replace('.', ':');
          return da.localeCompare(db) * sortDir;
        }
        const av = num ? toNum(a[sortCol]) : String(a[sortCol]).toLowerCase();
        const bv = num ? toNum(b[sortCol]) : String(b[sortCol]).toLowerCase();
        return (av < bv ? -1 : av > bv ? 1 : 0) * sortDir;
      });
    }
    return rows;
  }

  function buildRow(row, labels) {
    const tr = document.createElement('tr');
    const isComb = parsedData && parsedData.isMulti;
    const typeIdx = isComb ? 7 : 2;
    const amtIdx = isComb ? 8 : 3;
    const balIdx = isComb ? 9 : 4;
    const typeVal = row[typeIdx] || '';

    row.forEach((cell, i) => {
      const td = document.createElement('td');
      td.dataset.label = labels[i] || '';
      if (i === amtIdx) {
        td.classList.add('cell-num', 'cell-amt', 'is-' + (typeVal === 'CR' ? 'cr' : 'db'));
        td.textContent = cell === '' ? '' : fmtSigned(toNum(cell), typeVal);
      } else if (i === balIdx) {
        td.classList.add('cell-num', 'cell-amt');
        td.textContent = cell === '' ? '' : fmtMoney(toNum(cell));
      } else if (i === typeIdx) {
        td.classList.add('cell-type', 'is-' + (cell === 'CR' ? 'cr' : 'db'));
        td.textContent = cell;
      } else if ((!isComb && (i === 1 || i === 0)) || (isComb && (i === 5 || i === 6))) {
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
    return tr;
  }

  function drawTable() {
    const table = document.getElementById('table');
    const labels = JSON.parse(table.dataset.labels || '[]');
    const rows = currentRows();
    const oldTbody = table.querySelector('tbody');
    if (oldTbody) oldTbody.remove();

    const tbody = document.createElement('tbody');
    for (const row of rows) tbody.appendChild(buildRow(row, labels));
    table.appendChild(tbody);

    document.getElementById('empty').hidden = rows.length > 0;
    const countEl = document.getElementById('rowCount');
    if (countEl) {
      const q = document.getElementById('filter').value.trim();
      const isFiltered = q || activeTypeFilter !== 'all';
      countEl.textContent = isFiltered ? `${rows.length} dari ${parsedData.rows.length}` : `${parsedData.rows.length} transaksi`;
    }
  }

  function toggleSort(i) {
    if (sortCol === i) sortDir *= -1; else { sortCol = i; sortDir = 1; }
    document.querySelectorAll('#table thead th').forEach(th => {
      th.classList.remove('sorted-asc', 'sorted-desc');
      if (parseInt(th.dataset.col, 10) === sortCol) {
        th.classList.add(sortDir === 1 ? 'sorted-asc' : 'sorted-desc');
      }
    });
    drawTable();
  }

  const filterEl = document.getElementById('filter');
  if (filterEl) filterEl.addEventListener('input', drawTable);

  document.querySelectorAll('.filter-pills .pill').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.filter-pills .pill').forEach(b => b.classList.remove('is-active'));
      btn.classList.add('is-active');
      activeTypeFilter = btn.dataset.type || 'all';
      drawTable();
    });
  });

  function item(label, value, cls) {
    const v = escapeHtml(value || '—');
    return `<div class="meta__item"><span class="meta__label">${label}</span>` +
      `<span class="meta__value ${cls || ''}">${v}</span></div>`;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
  }

  let activePdfFile = null;
  function setPdfButton(file) {
    if (pdfUrl) { URL.revokeObjectURL(pdfUrl); pdfUrl = null; }
    activePdfFile = file;
    const isPdf = file && (file.type === 'application/pdf' || /\\.pdf$/i.test(file.name));
    const btn = document.getElementById('dlPdf');
    if (btn) btn.hidden = !isPdf;
  }

  async function download(format = 'xlsx', mode = 'multi_sheet') {
    if (!currentFiles.length) return;
    const btn = document.getElementById('btnDownloadMain');
    btn.disabled = true;
    try {
      const res = await sendWorker('download', { format, mode });
      if (res.error) {
        showError(res.error);
        return;
      }
      let blob;
      let filename;
      if (res.format === 'zip') {
        blob = new Blob([res.buffer], { type: 'application/zip' });
        filename = 'rekapimutasi-csv-files.zip';
      } else if (format === 'xlsx') {
        blob = new Blob([res.buffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
        if (currentFiles.length === 1) {
          filename = (currentFiles[0].name || 'statement').replace(/\\.[^.]+$/, '') + '.xlsx';
        } else {
          filename = `rekapimutasi-gabungan-${mode}.xlsx`;
        }
      } else {
        blob = new Blob([res.text], { type: 'text/csv;charset=utf-8' });
        if (currentFiles.length === 1) {
          filename = (currentFiles[0].name || 'statement').replace(/\\.[^.]+$/, '') + '.csv';
        } else {
          filename = 'rekapimutasi-gabungan.csv';
        }
      }
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      a.click();
      URL.revokeObjectURL(a.href);

      // Track download in analytics
      const banks = Array.from(new Set(multiResults.map(p => p.data && p.data.bank).filter(Boolean))).join(', ');
      trackEvent('file_downloaded', {
        format: format,
        mode: mode,
        bank: banks || 'Unknown',
        file_count: currentFiles.length,
      });
    } catch (e) {
      showError('Download gagal.');
    } finally {
      btn.disabled = false;
    }
  }

  if (btnDownloadMain) btnDownloadMain.addEventListener('click', () => download('xlsx', 'multi_sheet'));
  if (btnDownloadToggle) {
    btnDownloadToggle.addEventListener('click', (e) => {
      e.stopPropagation();
      const isClosed = downloadMenu.hidden;
      downloadMenu.hidden = !isClosed;
      btnDownloadToggle.setAttribute('aria-expanded', isClosed ? 'true' : 'false');
    });
  }

  document.addEventListener('click', (e) => {
    if (splitDownload && !splitDownload.contains(e.target)) {
      if (downloadMenu) downloadMenu.hidden = true;
      if (btnDownloadToggle) btnDownloadToggle.setAttribute('aria-expanded', 'false');
    }
  });

  document.querySelectorAll('.split-btn__opt').forEach(opt => {
    opt.addEventListener('click', () => {
      const fmt = opt.dataset.format;
      const mode = opt.dataset.mode;
      if (downloadMenu) downloadMenu.hidden = true;
      if (btnDownloadToggle) btnDownloadToggle.setAttribute('aria-expanded', 'false');
      download(fmt, mode);
    });
  });

  document.getElementById('dlPdf').addEventListener('click', () => {
    if (!activePdfFile) return;
    if (pdfUrl) URL.revokeObjectURL(pdfUrl);
    pdfUrl = URL.createObjectURL(activePdfFile);
    window.open(pdfUrl, '_blank', 'noopener');
  });

  const btnCopy = document.getElementById('btnCopy');
  if (btnCopy) {
    btnCopy.addEventListener('click', async () => {
      if (!parsedData || !parsedData.rows) return;
      const rows = currentRows();
      if (!rows.length) return;
      trackEvent('table_copied', {
        bank: (parsedData && parsedData.bank) ? parsedData.bank : 'Unknown',
        tx_count: rows.length,
      });
      const tsvLines = [parsedData.columns.join('\t')];
      for (const row of rows) {
        tsvLines.push(row.map(cell => String(cell).replace(/[\t\r\n]/g, ' ')).join('\t'));
      }
      const text = tsvLines.join('\n');
      const copySuccess = () => {
        const orig = btnCopy.textContent;
        btnCopy.textContent = '✓ Tersalin!';
        btnCopy.classList.add('btn--copied');
        setTimeout(() => {
          btnCopy.textContent = orig;
          btnCopy.classList.remove('btn--copied');
        }, 2000);
      };
      try {
        await navigator.clipboard.writeText(text);
        copySuccess();
      } catch (err) {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        copySuccess();
      }
    });
  }

  window.addEventListener('appinstalled', () => {
    trackEvent('pwa_installed');
  });

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('./sw.js').catch(() => {});
    });
  }
"""

    # Replace the <script> body in index.html (find the application script at the bottom)
    script_start = index_html.rfind("<script>")
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
    if iso_ts:
        docs_html = embed_commit_timestamp(docs_html, iso_ts)

    (DOCS / "index.html").write_text(docs_html, encoding="utf-8")
    print("Created docs/index.html with self-contained bundle!")


if __name__ == "__main__":
    main()
