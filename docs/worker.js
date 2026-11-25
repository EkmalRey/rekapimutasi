// Web Worker for client-side Python statement parsing using Pyodide (WASM)
importScripts("https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js");

const BUILD_VERSION = "1ed006146c";
let pyodide = null;
let parseDataFn = null;
let clearStmtsFn = null;
let removeStmtFn = null;
let getXlsxFn = null;
let getCsvFn = null;
let getZipFn = null;
let getViewXlsxFn = null;
let getViewCsvFn = null;

async function init() {
  try {
    postMessage({ type: 'status', step: 1, text: 'Memuat runtime Python WebAssembly...' });
    pyodide = await loadPyodide({
      indexURL: "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/"
    });

    postMessage({ type: 'status', step: 2, text: 'Menyiapkan modul rekapimutasi, pypdf & openpyxl...' });
    const resp = await fetch("rekapimutasi_pkg.zip?v=" + BUILD_VERSION);
    if (!resp.ok) throw new Error("Gagal mengunduh bundle modul rekapimutasi.");
    const buf = await resp.arrayBuffer();
    pyodide.unpackArchive(buf, "zip");

    // BCA e-statements are AES-256 encrypted; pypdf needs cryptography for that.
    postMessage({ type: 'status', step: 3, text: 'Memuat modul AES & menginisialisasi engine parser mutasi...' });
    await pyodide.loadPackage('cryptography');

    postMessage({ type: 'status', step: 3, text: 'Menginisialisasi engine parser mutasi...' });
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

_current_stmts = {}

def wasm_clear_stmts():
    global _current_stmts
    _current_stmts = {}

def wasm_remove_stmt(index):
    global _current_stmts
    _current_stmts.pop(int(index), None)

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

  const { id, action, filename, data, format, mode, scope, keys, view_data, reset, password, index } = e.data;

  if (action === 'clear') {
    if (clearStmtsFn) clearStmtsFn();
    postMessage({ id, ok: true });
  } else if (action === 'remove') {
    if (removeStmtFn) removeStmtFn(index || 0);
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
      if (scope === 'view') {
        const viewJson = JSON.stringify(view_data || {});
        if (format === 'xlsx') {
          const xlsxBytes = getViewXlsxFn(viewJson);
          postMessage({ id, buffer: xlsxBytes.toJs(), format: 'xlsx' });
        } else {
          const csvStr = getViewCsvFn(viewJson);
          postMessage({ id, text: csvStr, format: 'csv' });
        }
        return;
      }
      const keysJson = keys ? JSON.stringify(keys) : '';
      if (format === 'xlsx') {
        const xlsxBytes = getXlsxFn(mode || 'multi_sheet', keysJson);
        postMessage({ id, buffer: xlsxBytes.toJs(), format: 'xlsx' });
      } else if (format === 'zip' || (format === 'csv' && mode === 'multi_sheet')) {
        const zipBytes = getZipFn(keysJson);
        postMessage({ id, buffer: zipBytes.toJs(), format: 'zip' });
      } else if (format === 'csv') {
        const csvStr = getCsvFn(keysJson);
        postMessage({ id, text: csvStr, format: 'csv' });
      }
    } catch (err) {
      postMessage({ id, error: 'Download gagal: ' + (err.message || String(err)) });
    }
  }
};
