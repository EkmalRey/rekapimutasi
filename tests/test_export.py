import io
import unittest
import zipfile
from openpyxl import load_workbook

from rekapimutasi.export import (
    compact_statement,
    csv_bytes,
    flatten_statement,
    multi_csv_bytes,
    multi_csv_zip_bytes,
    multi_xlsx_bytes,
    write_csv,
    write_multi_xlsx,
    write_xlsx,
)
from rekapimutasi.model import Money, PocketGroup, Statement, Transaction


def _make_dummy_statement(bank="BCA", acc_no="1234567890", acc_name="Alice", period="Jan 2026"):
    return Statement(
        bank=bank,
        account_name=acc_name,
        account_no=acc_no,
        period=period,
        currency="IDR",
        pockets=[
            PocketGroup(
                name="Main Pocket",
                transactions=[
                    Transaction(
                        date="2026-01-01",
                        time="10:00:00",
                        mutation_type="CR",
                        amount=Money("IDR", "Rp100,000", 100000),
                        balance=Money("IDR", "Rp500,000", 500000),
                        source_destination="Bob",
                        transaction_detail="Transfer",
                        notes="Payment",
                        transaction_id="TX123",
                    )
                ],
            )
        ],
    )


class ExportTest(unittest.TestCase):
    def test_single_export_xlsx_and_csv(self):
        stmt = _make_dummy_statement()
        x_bytes = io.BytesIO()
        write_xlsx(stmt, x_bytes)
        wb = load_workbook(io.BytesIO(x_bytes.getvalue()))
        self.assertEqual(wb.sheetnames, ["Transactions"])
        ws = wb.active
        self.assertEqual(ws.cell(row=2, column=1).value, "2026-01-01")
        self.assertEqual(ws.cell(row=2, column=4).value, 100000)

        c_bytes = csv_bytes(stmt)
        self.assertIn(b"2026-01-01", c_bytes)
        self.assertIn(b"100000", c_bytes)

    def test_multi_xlsx_multi_sheet_mode(self):
        stmt1 = _make_dummy_statement(bank="BCA", period="Jan 2026")
        stmt2 = _make_dummy_statement(bank="JAGO", period="Feb 2026")
        stmt3 = _make_dummy_statement(bank="BCA", period="Jan 2026")  # duplicate title trigger

        buf = io.BytesIO()
        write_multi_xlsx([stmt1, stmt2, stmt3], buf, mode="multi_sheet")
        wb = load_workbook(io.BytesIO(buf.getvalue()))

        self.assertEqual(len(wb.sheetnames), 3)
        self.assertIn("BCA_Jan 2026", wb.sheetnames)
        self.assertIn("JAGO_Feb 2026", wb.sheetnames)
        # Collision resolved
        self.assertTrue(any(s.startswith("BCA_Jan 2026_") for s in wb.sheetnames))

    def test_multi_xlsx_single_sheet_mode_and_sorting(self):
        # Create statements with out-of-order dates
        tx1 = Transaction(date="2026-03-15", time="14:00", amount=Money("IDR", "Rp10,000", 10000), balance=Money("IDR", "Rp50,000", 50000))
        tx2 = Transaction(date="2026-01-05", time="09:00", amount=Money("IDR", "Rp20,000", 20000), balance=Money("IDR", "Rp70,000", 70000))
        tx3 = Transaction(date="2026-02-10", time="11:30", amount=Money("IDR", "Rp30,000", 30000), balance=Money("IDR", "Rp100,000", 100000))

        stmt1 = Statement(bank="BCA", account_no="111", account_name="Alice", pockets=[PocketGroup(name="", transactions=[tx1, tx2])])
        stmt2 = Statement(bank="JAGO", account_no="222", account_name="Bob", pockets=[PocketGroup(name="Bills", transactions=[tx3])])

        raw_bytes = multi_xlsx_bytes([stmt1, stmt2], mode="single_sheet")
        wb = load_workbook(io.BytesIO(raw_bytes))
        self.assertEqual(wb.sheetnames, ["Semua Transaksi"])
        ws = wb.active
        # Header check
        self.assertEqual(ws.cell(row=1, column=1).value, "Bank")
        self.assertEqual(ws.cell(row=1, column=2).value, "No. Rekening")
        self.assertEqual(ws.cell(row=1, column=5).value, "Kantong")
        self.assertEqual(ws.cell(row=1, column=6).value, "Date")

        # Sorted oldest to newest: 2026-01-05 -> 2026-02-10 -> 2026-03-15
        self.assertEqual(ws.cell(row=2, column=6).value, "2026-01-05")
        self.assertEqual(ws.cell(row=2, column=1).value, "BCA")
        self.assertIn(ws.cell(row=2, column=5).value, ("", None))

        self.assertEqual(ws.cell(row=3, column=6).value, "2026-02-10")
        self.assertEqual(ws.cell(row=3, column=1).value, "JAGO")
        self.assertEqual(ws.cell(row=3, column=5).value, "Bills")

        self.assertEqual(ws.cell(row=4, column=6).value, "2026-03-15")
        self.assertEqual(ws.cell(row=4, column=1).value, "BCA")

    def test_multi_csv_bytes_and_sorting(self):
        tx1 = Transaction(date="2026-03-15", time="14:00", amount=Money("IDR", "Rp10,000", 10000), balance=Money("IDR", "Rp50,000", 50000))
        tx2 = Transaction(date="2026-01-05", time="09:00", amount=Money("IDR", "Rp20,000", 20000), balance=Money("IDR", "Rp70,000", 70000))
        stmt1 = Statement(bank="BCA", account_no="111", account_name="Alice", pockets=[PocketGroup(transactions=[tx1])])
        stmt2 = Statement(bank="JAGO", account_no="222", account_name="Bob", pockets=[PocketGroup(transactions=[tx2])])

        data = multi_csv_bytes([stmt1, stmt2]).decode("utf-8")
        lines = [line.strip() for line in data.strip().splitlines()]
        self.assertIn("Bank,No. Rekening,Nama Rekening", lines[0])
        # Oldest first (2026-01-05 is row 1)
        self.assertIn("2026-01-05", lines[1])
        self.assertIn("JAGO,222,Bob", lines[1])
        # Newest second (2026-03-15 is row 2)
        self.assertIn("2026-03-15", lines[2])
        self.assertIn("BCA,111,Alice", lines[2])

    def test_multi_csv_zip_bytes(self):
        stmt1 = _make_dummy_statement(bank="BCA", period="Jan 2026")
        stmt2 = _make_dummy_statement(bank="JAGO", period="Feb 2026")
        zbuf = multi_csv_zip_bytes([stmt1, stmt2])
        with zipfile.ZipFile(io.BytesIO(zbuf)) as zf:
            names = zf.namelist()
            self.assertEqual(len(names), 2)
            self.assertTrue(any("BCA" in n for n in names))
            self.assertTrue(any("JAGO" in n for n in names))

    def test_compact_and_flatten_statement_with_pockets(self):
        tx_utama = Transaction(date="2026-07-01", time="09.00", amount=Money("IDR", "1000", 1000), balance=Money("IDR", "5000", 5000))
        tx_bills = Transaction(date="2026-07-02", time="10.00", amount=Money("IDR", "2000", 2000), balance=Money("IDR", "7000", 7000))
        stmt = Statement(
            bank="JAGO",
            account_no="101018375551",
            account_name="EKMAL",
            period="Juli 2026",
            currency="IDR",
            pockets=[
                PocketGroup(name="Kantong Utama", transactions=[tx_utama]),
                PocketGroup(name="Bills", transactions=[tx_bills]),
            ],
        )
        compact = compact_statement(stmt)
        self.assertIn("JAGO account 101018375551 (EKMAL)", compact)

        flat = flatten_statement(stmt)
        self.assertEqual(flat["bank"], "JAGO")
        self.assertEqual(len(flat["rows"]), 2)
        # Check row_pockets accurately maps each row to its individual pocket!
        self.assertEqual(flat["row_pockets"], ["Kantong Utama", "Bills"])


if __name__ == "__main__":
    unittest.main()
