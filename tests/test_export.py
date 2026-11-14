import io
import unittest
from openpyxl import load_workbook

from rekapimutasi.export import (
    compact_statement,
    csv_bytes,
    flatten_statement,
    multi_csv_bytes,
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

    def test_multi_xlsx_single_sheet_mode(self):
        stmt1 = _make_dummy_statement(bank="BCA", acc_no="111", acc_name="Alice", period="Jan 2026")
        stmt2 = _make_dummy_statement(bank="JAGO", acc_no="222", acc_name="Bob", period="Feb 2026")

        raw_bytes = multi_xlsx_bytes([stmt1, stmt2], mode="single_sheet")
        wb = load_workbook(io.BytesIO(raw_bytes))
        self.assertEqual(wb.sheetnames, ["Semua Transaksi"])
        ws = wb.active
        # Header check
        self.assertEqual(ws.cell(row=1, column=1).value, "Bank")
        self.assertEqual(ws.cell(row=1, column=2).value, "No. Rekening")
        self.assertEqual(ws.cell(row=1, column=6).value, "Date")

        # Row 1 values
        self.assertEqual(ws.cell(row=2, column=1).value, "BCA")
        self.assertEqual(ws.cell(row=2, column=2).value, "111")
        # Row 2 values
        self.assertEqual(ws.cell(row=3, column=1).value, "JAGO")
        self.assertEqual(ws.cell(row=3, column=2).value, "222")

    def test_multi_csv_bytes(self):
        stmt1 = _make_dummy_statement(bank="BCA", acc_no="111")
        stmt2 = _make_dummy_statement(bank="JAGO", acc_no="222")

        data = multi_csv_bytes([stmt1, stmt2]).decode("utf-8")
        lines = [line.strip() for line in data.strip().splitlines()]
        self.assertIn("Bank,No. Rekening,Nama Rekening", lines[0])
        self.assertIn("BCA,111,Alice", lines[1])
        self.assertIn("JAGO,222,Alice", lines[2])

    def test_compact_and_flatten_statement(self):
        stmt = _make_dummy_statement()
        compact = compact_statement(stmt)
        self.assertIn("BCA account 1234567890 (Alice)", compact)

        flat = flatten_statement(stmt)
        self.assertEqual(flat["bank"], "BCA")
        self.assertEqual(flat["account_no"], "1234567890")
        self.assertEqual(len(flat["rows"]), 1)


if __name__ == "__main__":
    unittest.main()
