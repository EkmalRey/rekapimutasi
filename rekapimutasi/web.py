"""Web app: drag-and-drop a statement PDF/CSV, preview parsed rows, download
as .xlsx or .csv. Single Python process, stdlib http.server, no framework."""
import argparse
import json
import os
import tempfile
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import csv_bytes, flatten_statement, parse_file, xlsx_bytes
from .errors import RekapimutasiError

MAX_UPLOAD = 25 * 1024 * 1024
WEB_DIR = Path(__file__).resolve().parent / "web"

_SANITIZE_TABLE = str.maketrans({"/": "-", "\\": "-", " ": "-", ":": "-"})


def sanitize_filename(name):
    return name.translate(_SANITIZE_TABLE).strip("-")


def parse_multipart(content_type, data):
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype != "multipart/form-data":
        raise ValueError("expected multipart/form-data")
    # BytesParser needs the Content-Type header to recognise the parts.
    head = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode()
    msg = BytesParser(policy=policy.default).parsebytes(head + data)
    fields = {}
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        if part.get_filename():
            fields[name] = {
                "filename": part.get_filename(),
                "data": part.get_payload(decode=True) or b"",
            }
        else:
            fields[name] = (part.get_payload(decode=True) or b"").decode("utf-8", "replace")
    return fields


class Handler(BaseHTTPRequestHandler):
    server_version = "rekapimutasi/1.0"

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = (WEB_DIR / "index.html").read_bytes()
            self._send(200, body, "text/html; charset=utf-8")
        elif self.path == "/favicon.svg":
            body = (WEB_DIR / "favicon.svg").read_bytes()
            self._send(200, body, "image/svg+xml")
        elif self.path == "/favicon.ico":
            body = (WEB_DIR / "favicon.ico").read_bytes()
            self._send(200, body, "image/x-icon")
        elif self.path == "/favicon.png":
            body = (WEB_DIR / "favicon.png").read_bytes()
            self._send(200, body, "image/png")
        else:
            self.send_error(404)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length <= 0 or length > MAX_UPLOAD:
                raise ValueError("file too large")
            fields = parse_multipart(self.headers.get("Content-Type", ""), self.rfile.read(length))
            file_part = fields.get("file")
            if not isinstance(file_part, dict) or not file_part.get("data"):
                raise ValueError("missing file upload")

            ext = os.path.splitext(file_part["filename"])[1].lower()
            if ext not in (".pdf", ".csv"):
                raise ValueError(f'unsupported file type "{ext}", expected .pdf or .csv')

            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(file_part["data"])
                tmp_path = tmp.name
            try:
                stmt = parse_file(tmp_path)
            finally:
                os.unlink(tmp_path)
        except Exception as e:  # noqa: BLE001 - always answer with a JSON error
            if isinstance(e, RekapimutasiError):
                self._send_json(422, {"error": f"Could not parse this file. Is it a supported bank statement with a text layer? ({e})"})
            else:
                self._send_json(400, {"error": str(e)})
            return

        if self.path == "/api/parse":
            self._send_json(200, flatten_statement(stmt))
        elif self.path == "/api/download":
            self._download(stmt, fields.get("format"))
        else:
            self.send_error(404)

    def _download(self, stmt, fmt):
        name = sanitize_filename(f"mutasi-{stmt.bank}-{stmt.account_no}")
        if fmt == "xlsx":
            self._send(
                200,
                xlsx_bytes(stmt),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                filename=f"{name}.xlsx",
            )
        elif fmt == "csv":
            self._send(200, csv_bytes(stmt), "text/csv; charset=utf-8", filename=f"{name}.csv")
        else:
            self._send_json(400, {"error": "format must be xlsx or csv"})

    def _send_json(self, status, obj):
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _send(self, status, body, content_type, filename=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(body)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="rekapimutasi-web")
    parser.add_argument("--addr", default=":8092", help="listen address (default :8092)")
    args = parser.parse_args(argv)

    host, _, port = args.addr.rpartition(":")
    server = ThreadingHTTPServer((host or "0.0.0.0", int(port) or 8092), Handler)
    print(f"rekapimutasi web listening on {args.addr}")
    server.serve_forever()


if __name__ == "__main__":
    main()
