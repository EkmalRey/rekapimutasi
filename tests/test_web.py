import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from rekapimutasi.web import Handler, parse_multipart

BOUNDARY = "----testboundary1234"
BODY = (
    "--" + BOUNDARY + "\r\n"
    'Content-Disposition: form-data; name="file"; filename="stmt.csv"\r\n'
    "Content-Type: text/csv\r\n\r\n"
    '"No. rekening : 0350000001"\r\n'
    '"Nama : PT ACME TEKNOLOGI"\r\n'
    '"Periode : 13/05/2026 - 14/05/2026"\r\n'
    '"Tanggal Transaksi","Keterangan","Cabang","Jumlah","Saldo"\r\n'
    '"13/05/2026","TRSF E-BANKING","0000","3,528,964.00 CR","25,441,156.00"\r\n'
    '"Saldo Awal : 21,912,192.00"\r\n'
    '"Saldo Akhir : 25,441,156.00"\r\n'
    "--" + BOUNDARY + "--\r\n"
).encode()

CSV_BODY = (
    "--" + BOUNDARY + "\r\n"
    'Content-Disposition: form-data; name="file"; filename="stmt.csv"\r\n'
    "Content-Type: text/csv\r\n\r\n"
    '"No. rekening : 0350000001"\r\n'
    '"Nama : PT ACME TEKNOLOGI"\r\n'
    '"Periode : 13/05/2026 - 14/05/2026"\r\n'
    '"Tanggal Transaksi","Keterangan","Cabang","Jumlah","Saldo"\r\n'
    '"13/05/2026","TRSF E-BANKING","0000","3,528,964.00 CR","25,441,156.00"\r\n'
    '"Saldo Awal : 21,912,192.00"\r\n'
    '"Saldo Akhir : 25,441,156.00"\r\n'
    "--" + BOUNDARY + "\r\n"
    'Content-Disposition: form-data; name="format"\r\n\r\n'
    "csv\r\n"
    "--" + BOUNDARY + "--\r\n"
).encode()


class ParseMultipartTest(unittest.TestCase):
    def test_parses_file_and_fields(self):
        ctype = f"multipart/form-data; boundary={BOUNDARY}"
        fields = parse_multipart(ctype, BODY)
        self.assertEqual(fields["file"]["filename"], "stmt.csv")
        self.assertIn(b"PT ACME TEKNOLOGI", fields["file"]["data"])

    def test_rejects_non_multipart(self):
        with self.assertRaises(ValueError):
            parse_multipart("application/json", b"{}")


class WebServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _post(self, body, ctype, path):
        req = Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=body,
            headers={"Content-Type": ctype},
            method="POST",
        )
        try:
            resp = urlopen(req)
            return resp.status, resp.read()
        except HTTPError as e:
            return e.code, e.read()

    def test_parse_endpoint(self):
        ctype = f"multipart/form-data; boundary={BOUNDARY}"
        status, body = self._post(BODY, ctype, "/api/parse")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["bank"], "BCA_BISNIS")
        self.assertEqual(data["account_name"], "PT ACME TEKNOLOGI")
        self.assertEqual(len(data["rows"]), 1)

    def test_parse_rejects_bad_file(self):
        bad = BODY.replace(b"stmt.csv", b"bad.exe")
        ctype = f"multipart/form-data; boundary={BOUNDARY}"
        status, body = self._post(bad, ctype, "/api/parse")
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(body))

    def test_download_csv(self):
        ctype = f"multipart/form-data; boundary={BOUNDARY}"
        status, body = self._post(CSV_BODY, ctype, "/api/download")
        self.assertEqual(status, 200)
        self.assertIn(b"2026-05-13", body)
        self.assertIn(b"3528964", body)

    def test_index_served(self):
        req = Request(f"http://127.0.0.1:{self.port}/", method="GET")
        resp = urlopen(req)
        self.assertEqual(resp.status, 200)
        self.assertIn(b"rekapimutasi", resp.read())


if __name__ == "__main__":
    unittest.main()
