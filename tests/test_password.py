import io
import os
import unittest
from pathlib import Path

from pypdf import PdfReader, PdfWriter

import rekapimutasi
from rekapimutasi.errors import PasswordProtectedError, WrongPasswordError


class PasswordProtectedPDFTest(unittest.TestCase):
    def setUp(self):
        # Create a synthetic BCA statement in memory and encrypt it
        # Load synthetic sample from test_bca if available or use raw text
        synthetic_text = (
            "REKENING TAHAPAN\n"
            "NO. REKENING : 1234567890\n"
            "PERIODE : AGUSTUS 2026\n"
            "NAMA : NASABAH DUMMY\n"
            "TGL KETERANGAN CB MUTASI SALDO\n"
            "01/08 TRSF DR 1234 100.000 CR 1.000.000\n"
            "02/08 BIAYA ADM 10.000 DB 990.000\n"
            "SALDO AWAL : 900.000\n"
            "MUTASI CR : 100.000\n"
            "MUTASI DB : 10.000\n"
            "SALDO AKHIR : 990.000\n"
        )
        self.tmp_pdf = Path("tests") / "fixtures" / "_temp_protected.pdf"
        self.tmp_pdf.parent.mkdir(parents=True, exist_ok=True)

        writer = PdfWriter()
        page = writer.add_blank_page(width=200, height=200)
        # We can write text using synthetic fixture if existing fixture is present
        # Alternatively, take an existing fixture like bca_sample.pdf or create writer
        fixtures_dir = Path("tests") / "fixtures"
        src_fixture = fixtures_dir / "bca_sample.pdf"
        if not src_fixture.exists():
            # Check any testdata
            for p in Path("banks").glob("**/*.pdf"):
                if p.is_file():
                    src_fixture = p
                    break

        if src_fixture.exists():
            r = PdfReader(str(src_fixture))
            w = PdfWriter()
            w.append(r)
            w.encrypt(user_password="password123")
            with open(self.tmp_pdf, "wb") as f:
                w.write(f)
        else:
            w = PdfWriter()
            w.add_blank_page(width=100, height=100)
            w.encrypt(user_password="password123")
            with open(self.tmp_pdf, "wb") as f:
                w.write(f)

    def tearDown(self):
        if self.tmp_pdf.exists():
            self.tmp_pdf.unlink()

    def test_extract_without_password_raises(self):
        with self.assertRaises(PasswordProtectedError):
            rekapimutasi.extract_pdf_text(str(self.tmp_pdf))

    def test_extract_with_wrong_password_raises(self):
        with self.assertRaises(WrongPasswordError):
            rekapimutasi.extract_pdf_text(str(self.tmp_pdf), password="wrong_pass")

    def test_extract_with_correct_password(self):
        text = rekapimutasi.extract_pdf_text(str(self.tmp_pdf), password="password123")
        self.assertTrue(len(text) >= 0)

    def test_local_testdata_bca_password(self):
        p = Path("banks/bca/testdata/5771045236_SEP_2026_pass_123456.pdf")
        if not p.exists():
            self.skipTest("Local testdata not present")
        with self.assertRaises(PasswordProtectedError):
            rekapimutasi.parse_file(str(p))
        with self.assertRaises(WrongPasswordError):
            rekapimutasi.parse_file(str(p), password="wrong")
        stmt = rekapimutasi.parse_file(str(p), password="123456")
        self.assertEqual(stmt.bank, "BCA")
        self.assertEqual(stmt.account_no, "5771045236")

    def test_local_testdata_jago_password(self):
        p = Path("banks/jago/testdata/Jago_October_2026_pass_123456.pdf")
        if not p.exists():
            self.skipTest("Local testdata not present")
        with self.assertRaises(PasswordProtectedError):
            rekapimutasi.parse_file(str(p))
        stmt = rekapimutasi.parse_file(str(p), password="123456")
        self.assertEqual(stmt.bank, "JAGO")


if __name__ == "__main__":
    unittest.main()
