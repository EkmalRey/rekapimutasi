// Web Worker for client-side Python statement parsing using Pyodide (WASM)
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
