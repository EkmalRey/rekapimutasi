#!/usr/bin/env python3
"""Build script for GitHub Pages static deployment using Pyodide (client-side WebAssembly)."""

import hashlib
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
    except Exception:  # noqa: BLE001
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


def _build_package_zip(zip_path: Path) -> str:
    """Bundle rekapimutasi and pure-Python dependencies into a self-contained zip, returning its short SHA-256."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(REKAP):
            rel_root = os.path.relpath(root, ROOT)
            if "__pycache__" in rel_root or "web" in rel_root:
                continue
            for f in sorted(files):
                if f.endswith(".py") and f not in ("cli.py", "web.py"):
                    full_p = Path(root) / f
                    arc_p = Path(rel_root) / f
                    z.write(full_p, str(arc_p))

        modules_to_bundle = []
        for mod_name in ("pypdf", "openpyxl", "et_xmlfile"):
            try:
                modules_to_bundle.append(__import__(mod_name))
            except ImportError:
                print(f"Warning: {mod_name} not installed")

        for mod in modules_to_bundle:
            mod_dir = Path(mod.__file__).parent
            pkg_name = mod_dir.name
            print(f"Bundling {pkg_name} from {mod_dir}")
            for root, dirs, files in os.walk(mod_dir):
                if "__pycache__" in root:
                    continue
                for f in sorted(files):
                    if f.endswith((".py", ".json", ".xml")):
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

    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()[:10]
    print(f"Created self-contained {zip_path} ({zip_path.stat().st_size} bytes, v={digest})")
    return digest


def _render_worker_js(build_version: str) -> str:
    return f"""// Web Worker for client-side Python statement parsing using Pyodide (WASM)
importScripts("https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js");

const BUILD_VERSION = "{build_version}";
let pyodide = null;
let parseDataFn = null;
let clearStmtsFn = null;
let removeStmtFn = null;
let getXlsxFn = null;
let getCsvFn = null;
let getZipFn = null;
let getViewXlsxFn = null;
let getViewCsvFn = null;

async function init() {{
  try {{
    postMessage({{ type: 'status', step: 1, text: 'Memuat runtime Python WebAssembly...' }});
    pyodide = await loadPyodide({{
      indexURL: "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/"
    }});

    postMessage({{ type: 'status', step: 2, text: 'Menyiapkan modul rekapimutasi, pypdf & openpyxl...' }});
    const resp = await fetch("rekapimutasi_pkg.zip?v=" + BUILD_VERSION);
    if (!resp.ok) throw new Error("Gagal mengunduh bundle modul rekapimutasi.");
    const buf = await resp.arrayBuffer();
    pyodide.unpackArchive(buf, "zip");

    // BCA e-statements are AES-256 encrypted; pypdf needs cryptography for that.
    postMessage({{ type: 'status', step: 3, text: 'Memuat modul AES & menginisialisasi engine parser mutasi...' }});
    await pyodide.loadPackage('cryptography');

    postMessage({{ type: 'status', step: 3, text: 'Menginisialisasi engine parser mutasi...' }});
    await pyodide.runPythonAsync(`
import sys, os, json
sys.path.insert(0, os.getcwd())
sys.path.insert(0, "/home/pyodide")

import openpyxl
import pypdf
import rekapimutasi
from rekapimutasi.export import (
    flatten_statement,
    xlsx_bytes,
    csv_bytes,
    multi_xlsx_bytes,
    multi_csv_bytes,
    multi_csv_zip_bytes,
    rows_xlsx_bytes,
    rows_csv_bytes,
)
from rekapimutasi.errors import RekapimutasiError, PasswordProtectedError, WrongPasswordError

_current_stmts = {{}}

def wasm_clear_stmts():
    global _current_stmts
    _current_stmts = {{}}

def wasm_remove_stmt(index):
    global _current_stmts
    _current_stmts.pop(int(index), None)

def wasm_parse_file(filepath, password="", index=0):
    global _current_stmts
    try:
        stmt = rekapimutasi.parse_file(filepath, password=password if password else None)
        _current_stmts[int(index)] = stmt
        data = flatten_statement(stmt)
        return json.dumps({{"ok": True, "data": data}})
    except WrongPasswordError as e:
        return json.dumps({{"ok": False, "requires_password": True, "wrong_password": True, "error": str(e)}})
    except PasswordProtectedError as e:
        return json.dumps({{"ok": False, "requires_password": True, "error": str(e)}})
    except RekapimutasiError as e:
        return json.dumps({{"ok": False, "error": f"Format file tidak dikenali atau tidak memiliki text layer: {{e}}"}})
    except Exception as e:
        return json.dumps({{"ok": False, "error": str(e)}})

def _select_stmts(keys_json=""):
    if keys_json:
        keys = [int(k) for k in json.loads(keys_json)]
        stmts = [_current_stmts[k] for k in keys if k in _current_stmts]
    else:
        stmts = [stmt for _, stmt in sorted(_current_stmts.items())]
    if not stmts:
        raise ValueError("Belum ada mutasi yang diproses.")
    return stmts

def wasm_get_xlsx(mode="multi_sheet", keys_json=""):
    stmts = _select_stmts(keys_json)
    if len(stmts) == 1:
        return xlsx_bytes(stmts[0])
    return multi_xlsx_bytes(stmts, mode=mode)

def wasm_get_csv(keys_json=""):
    stmts = _select_stmts(keys_json)
    if len(stmts) == 1:
        return csv_bytes(stmts[0]).decode('utf-8')
    return multi_csv_bytes(stmts).decode('utf-8')

def wasm_get_zip(keys_json=""):
    stmts = _select_stmts(keys_json)
    return multi_csv_zip_bytes(stmts)

def wasm_get_view_xlsx(view_json):
    view = json.loads(view_json)
    return rows_xlsx_bytes(view.get("columns") or [], view.get("rows") or [], sheet_name=view.get("sheet_name") or "Transactions")

def wasm_get_view_csv(view_json):
    view = json.loads(view_json)
    return rows_csv_bytes(view.get("columns") or [], view.get("rows") or []).decode('utf-8')
`);

    parseDataFn = pyodide.globals.get('wasm_parse_file');
    clearStmtsFn = pyodide.globals.get('wasm_clear_stmts');
    removeStmtFn = pyodide.globals.get('wasm_remove_stmt');
    getXlsxFn = pyodide.globals.get('wasm_get_xlsx');
    getCsvFn = pyodide.globals.get('wasm_get_csv');
    getZipFn = pyodide.globals.get('wasm_get_zip');
    getViewXlsxFn = pyodide.globals.get('wasm_get_view_xlsx');
    getViewCsvFn = pyodide.globals.get('wasm_get_view_csv');

    postMessage({{ type: 'ready' }});
  }} catch (err) {{
    postMessage({{ type: 'error', text: 'Gagal menginisialisasi engine Python: ' + (err.message || err) }});
  }}
}}

const readyPromise = init();

onmessage = async (e) => {{
  await readyPromise;
  if (!pyodide || !parseDataFn) {{
    postMessage({{ id: e.data.id, error: 'Engine Python belum siap.' }});
    return;
  }}

  const {{ id, action, filename, data, format, mode, scope, keys, view_data, reset, password, index }} = e.data;

  if (action === 'clear') {{
    if (clearStmtsFn) clearStmtsFn();
    postMessage({{ id, ok: true }});
  }} else if (action === 'remove') {{
    if (removeStmtFn) removeStmtFn(index || 0);
    postMessage({{ id, ok: true }});
  }} else if (action === 'parse') {{
    try {{
      if (reset && clearStmtsFn) clearStmtsFn();
      const ext = filename.toLowerCase().endsWith('.csv') ? '.csv' : '.pdf';
      const inPath = '/tmp/input_' + id + ext;
      pyodide.FS.writeFile(inPath, new Uint8Array(data));

      const resultJson = parseDataFn(inPath, password || '', index || 0);
      try {{ pyodide.FS.unlink(inPath); }} catch (_) {{}}
      const parsed = JSON.parse(resultJson);
      if (!parsed.ok) {{
        postMessage({{
          id,
          error: parsed.error,
          requires_password: !!parsed.requires_password,
          wrong_password: !!parsed.wrong_password
        }});
      }} else {{
        postMessage({{ id, data: parsed.data }});
      }}
    }} catch (err) {{
      postMessage({{ id, error: err.message || String(err) }});
    }}
  }} else if (action === 'download') {{
    try {{
      if (scope === 'view') {{
        const viewJson = JSON.stringify(view_data || {{}});
        if (format === 'xlsx') {{
          const xlsxBytes = getViewXlsxFn(viewJson);
          postMessage({{ id, buffer: xlsxBytes.toJs(), format: 'xlsx' }});
        }} else {{
          const csvStr = getViewCsvFn(viewJson);
          postMessage({{ id, text: csvStr, format: 'csv' }});
        }}
        return;
      }}
      const keysJson = keys ? JSON.stringify(keys) : '';
      if (format === 'xlsx') {{
        const xlsxBytes = getXlsxFn(mode || 'multi_sheet', keysJson);
        postMessage({{ id, buffer: xlsxBytes.toJs(), format: 'xlsx' }});
      }} else if (format === 'zip' || (format === 'csv' && mode === 'multi_sheet')) {{
        const zipBytes = getZipFn(keysJson);
        postMessage({{ id, buffer: zipBytes.toJs(), format: 'zip' }});
      }} else if (format === 'csv') {{
        const csvStr = getCsvFn(keysJson);
        postMessage({{ id, text: csvStr, format: 'csv' }});
      }}
    }} catch (err) {{
      postMessage({{ id, error: 'Download gagal: ' + (err.message || String(err)) }});
    }}
  }}
}};
"""


def _render_wasm_transport_script(build_version: str) -> str:
    return f"""<script id="rekap-transport">
  (function () {{
    const BUILD_VERSION = "{build_version}";
    const wasmInitStart = performance.now();
    const worker = new Worker('worker.js?v=' + BUILD_VERSION);
    let reqId = 0;
    const pendingRequests = new Map();
    let readyCb = null;
    let errorCb = null;

    function emitTrack(name, params) {{
      if (typeof window.gtag === 'function') window.gtag('event', name, params);
    }}

    function sendWorker(action, payload) {{
      return new Promise((resolve) => {{
        const id = ++reqId;
        pendingRequests.set(id, resolve);
        worker.postMessage({{ id, action, ...payload }});
      }});
    }}

    worker.onerror = (e) => {{
      const engineBanner = document.getElementById('engineBanner');
      const errMsg = (e && e.message) ? e.message : 'Worker error';
      emitTrack('wasm_error', {{ error_message: errMsg }});
      if (engineBanner) {{
        engineBanner.innerHTML = `
          <div class="engine-banner__icon" style="color:#ef4444;">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
          </div>
          <div class="engine-banner__text">
            <strong style="color:#ef4444;">Gagal memuat Engine WebAssembly</strong>
            <span>${{errMsg}} Silakan coba refresh halaman.</span>
          </div>
        `;
      }}
      if (errorCb) errorCb('Gagal memuat engine WebAssembly: ' + errMsg);
    }};

    worker.onmessage = (e) => {{
      const msg = e.data;
      const engineBanner = document.getElementById('engineBanner');
      const engineTitle = document.getElementById('engineTitle');
      const engineSub = document.getElementById('engineSub');
      const noteEl = document.querySelector('.mast__note');

      if (msg.type === 'status') {{
        if (engineTitle) engineTitle.textContent = msg.text;
        if (engineSub) engineSub.textContent = `Langkah ${{msg.step || 1}} dari 3 (hanya diunduh sekali di awal)`;
        if (noteEl) noteEl.textContent = msg.text;
      }} else if (msg.type === 'ready') {{
        const durationMs = Math.round(performance.now() - wasmInitStart);
        emitTrack('wasm_ready', {{ duration_ms: durationMs, duration_sec: Number((durationMs / 1000).toFixed(1)) }});
        if (engineBanner) {{
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
          setTimeout(() => {{
            engineBanner.classList.add('is-hidden');
            setTimeout(() => {{ engineBanner.remove(); }}, 350);
          }}, 3500);
        }}
        if (noteEl) noteEl.innerHTML = '<span style="color:#16a34a">●</span> 100% Client-side (Data aman di browser)';
        if (readyCb) readyCb();
      }} else if (msg.type === 'error') {{
        emitTrack('wasm_error', {{ error_message: msg.text || 'Wasm initialization error' }});
        if (engineBanner) {{ engineBanner.classList.add('is-hidden'); setTimeout(() => {{ engineBanner.remove(); }}, 350); }}
        if (errorCb) errorCb(msg.text);
      }} else if (msg.id && pendingRequests.has(msg.id)) {{
        const resolver = pendingRequests.get(msg.id);
        pendingRequests.delete(msg.id);
        resolver(msg);
      }}
    }};

    window.REKAP_TRANSPORT = {{
      mode: 'wasm',
      init(handlers) {{
        readyCb = handlers && handlers.onReady;
        errorCb = handlers && handlers.onError;
      }},
      async clear() {{
        await sendWorker('clear', {{}});
      }},
      async remove(key) {{
        await sendWorker('remove', {{ index: key }});
      }},
      async parse({{ key, file, buffer, password }}) {{
        const res = await sendWorker('parse', {{
          index: key,
          filename: file.name,
          data: buffer,
          password: password || ''
        }});
        if (res.error || !res.data) {{
          return {{
            ok: false,
            requires_password: !!res.requires_password,
            wrong_password: !!res.wrong_password,
            error: res.error || 'Terjadi kesalahan.'
          }};
        }}
        return {{ ok: true, data: res.data }};
      }},
      async downloadAll({{ items, format, mode }}) {{
        const res = await sendWorker('download', {{
          scope: 'all',
          keys: items.map(i => i.key),
          format,
          mode
        }});
        if (res.error) throw new Error(res.error);
        if (res.format === 'zip') {{
          return {{ blob: new Blob([res.buffer], {{ type: 'application/zip' }}), filename: 'rekapimutasi-csv-files.zip' }};
        }}
        if (format === 'xlsx') {{
          return {{ blob: new Blob([res.buffer], {{ type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }}), filename: '' }};
        }}
        return {{ blob: new Blob([res.text], {{ type: 'text/csv;charset=utf-8' }}), filename: '' }};
      }},
      async downloadView({{ columns, rows, format, filenamePrefix, sheetName }}) {{
        const res = await sendWorker('download', {{
          scope: 'view',
          format,
          view_data: {{ columns, rows, sheet_name: sheetName }}
        }});
        if (res.error) throw new Error(res.error);
        const ext = format === 'xlsx' ? 'xlsx' : 'csv';
        const mime = format === 'xlsx'
          ? 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
          : 'text/csv;charset=utf-8';
        const content = format === 'xlsx' ? res.buffer : res.text;
        return {{ blob: new Blob([content], {{ type: mime }}), filename: `${{filenamePrefix}}.${{ext}}` }};
      }}
    }};
  }})();
</script>"""


def _render_sw_js(src_sw: str, build_version: str) -> str:
    """Update sw.js with deterministic cache name and precached WASM worker/package URLs."""
    sw = re.sub(
        r"const CACHE_NAME\s*=\s*['\"][^'\"]+['\"];",
        f"const CACHE_NAME = 'rekapimutasi-pages-{build_version}';",
        src_sw,
    )
    precache_block = (
        "const PRECACHE_URLS = [\n"
        "  './',\n"
        "  './index.html',\n"
        f"  './worker.js?v={build_version}',\n"
        f"  './rekapimutasi_pkg.zip?v={build_version}',\n"
        "  './favicon.svg',\n"
        "  './favicon.png',\n"
        "  './favicon.ico',\n"
        "  './manifest.webmanifest'\n"
        "];"
    )
    sw = re.sub(r"const PRECACHE_URLS\s*=\s*\[[\s\S]*?\];", precache_block, sw)
    return sw


def build_pages(output_dir: Path = DOCS, update_master: bool = True) -> Path:
    iso_ts = get_git_commit_timestamp(ROOT)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Create self-contained Python bundle zip and deterministic build version
    zip_path = output_dir / "rekapimutasi_pkg.zip"
    build_version = _build_package_zip(zip_path)

    # 2. Copy assets, favicons, and build-versioned Service Worker
    assets_dst = output_dir / "assets"
    assets_dst.mkdir(parents=True, exist_ok=True)
    if (ROOT / "assets").exists():
        for f in (ROOT / "assets").iterdir():
            if f.is_file():
                shutil.copy2(f, assets_dst / f.name)

    for f_name in ("favicon.svg", "favicon.ico", "favicon.png", "robots.txt", "sitemap.xml", "manifest.webmanifest", "sw.js"):
        src = REKAP / "web" / f_name
        if not src.exists():
            continue
        if f_name == "sitemap.xml" and iso_ts:
            content = src.read_text(encoding="utf-8")
            date_part = iso_ts.split("T")[0]
            content = re.sub(r"<lastmod>.*?</lastmod>", f"<lastmod>{date_part}</lastmod>", content)
            (output_dir / f_name).write_text(content, encoding="utf-8")
        elif f_name == "sw.js":
            sw_content = _render_sw_js(src.read_text(encoding="utf-8"), build_version)
            (output_dir / f_name).write_text(sw_content, encoding="utf-8")
        else:
            shutil.copy2(src, output_dir / f_name)

    # 3. Create Web Worker script (worker.js)
    (output_dir / "worker.js").write_text(_render_worker_js(build_version), encoding="utf-8")
    print(f"Created {output_dir / 'worker.js'}")

    # 4. Generate index.html using unified UI script + WASM transport adapter
    master_html = (REKAP / "web" / "index.html").read_text(encoding="utf-8")
    if iso_ts:
        updated_master = embed_commit_timestamp(master_html, iso_ts)
        if update_master and updated_master != master_html:
            (REKAP / "web" / "index.html").write_text(updated_master, encoding="utf-8")
        index_html = updated_master
    else:
        index_html = master_html

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

    transport_re = re.compile(r'<script id="rekap-transport">[\s\S]*?</script>')
    if not transport_re.search(index_html):
        raise RuntimeError('Missing <script id="rekap-transport"> placeholder in web/index.html')

    docs_html = transport_re.sub(lambda _: _render_wasm_transport_script(build_version), index_html, count=1)
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

    (output_dir / "index.html").write_text(docs_html, encoding="utf-8")
    print(f"Created {output_dir / 'index.html'} with unified frontend + WASM transport!")
    return output_dir


def main():
    build_pages(DOCS, update_master=True)


if __name__ == "__main__":
    main()
