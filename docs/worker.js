// Web Worker for client-side Python statement parsing using Pyodide (WASM)
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
