import os
import unittest

from rekapimutasi import BankCode
from rekapimutasi.banks.bca import BisnisParser, PDFParser, PersonalParser
from rekapimutasi.extractor import extract_pdf_text

PERSONAL_INPUT = """Account No.,=,'0111222333
Name,=,JOHN DOE
Currency,=,IDR

Date,Description,Branch,Amount,,Balance
'02/05/2026,TRSF E-BANKING CR 0205/FTSCY/WS95031         108400.00Transfer pembayaran invoice           ACME CORPORATION,'0000,108400.00,CR,1042939.96
Starting Balance,=,934539.96
Credit,=,108400.00
Debet,=,
Ending Balance,=,1042939.96
"""

BISNIS_INPUT = '"Informasi Rekening - Mutasi Rekening"," "," "," "," ",\n' \
    '\n' \
    '"No. rekening : 0350000001"\n' \
    '"Nama : PT ACME TEKNOLOGI"\n' \
    '"Periode : 13/05/2026 - 14/05/2026"\n' \
    '"Kode Mata Uang : Rp"\n' \
    '"Tanggal Transaksi","Keterangan","Cabang","Jumlah","Saldo"\n' \
    '"13/05/2026","KR OTOMATIS NTRF@0000000001X0Z 035@BCA26051800001  @IFP acme.co.id @AFR  PaymentGateway      ","0000","3,528,964.00 CR","25,441,156.00"\n' \
    '"Saldo Awal : 21,912,192.00"\n' \
    '"Mutasi Debet : 0.00","0"\n' \
    '"Mutasi Kredit : 3,528,964.00","1"\n' \
    '"Saldo Akhir : 25,441,156.00"\n'


class BCACSVTest(unittest.TestCase):
    def test_personal_parser(self):
        parser = PersonalParser()
        self.assertTrue(parser.can_parse(PERSONAL_INPUT))

        stmt = parser.parse(PERSONAL_INPUT)
        self.assertEqual(stmt.bank, BankCode.BCA)
        self.assertEqual(stmt.account_no, "0111222333")
        self.assertEqual(stmt.account_name, "JOHN DOE")

        self.assertEqual(len(stmt.pockets), 1)
        pocket = stmt.pockets[0]
        self.assertEqual(pocket.name, "Personal")
        self.assertEqual(len(pocket.transactions), 1)

        tx = pocket.transactions[0]
        self.assertEqual(tx.date, "2026-05-02")
        self.assertEqual(tx.mutation_type, "CR")
        self.assertEqual(tx.amount.value, 108400)
        self.assertEqual(tx.balance.value, 1042939)

    def test_bisnis_parser(self):
        parser = BisnisParser()
        self.assertTrue(parser.can_parse(BISNIS_INPUT))

        stmt = parser.parse(BISNIS_INPUT)
        self.assertEqual(stmt.bank, BankCode.BCA_BISNIS)
        self.assertEqual(stmt.account_no, "0350000001")
        self.assertEqual(stmt.account_name, "PT ACME TEKNOLOGI")
        self.assertEqual(stmt.period, "13/05/2026 - 14/05/2026")

        self.assertEqual(len(stmt.pockets), 1)
        pocket = stmt.pockets[0]
        self.assertEqual(pocket.name, "Business")
        self.assertEqual(len(pocket.transactions), 1)

        tx = pocket.transactions[0]
        self.assertEqual(tx.date, "2026-05-13")
        self.assertEqual(tx.mutation_type, "CR")
        self.assertEqual(tx.amount.value, 3528964)
        self.assertEqual(tx.balance.value, 25441156)

    def test_can_parse_negative(self):
        self.assertFalse(PersonalParser().can_parse("random text without bank identifiers"))
        self.assertFalse(BisnisParser().can_parse("random text without bank identifiers"))


BCA_REAL = "banks/bca/testdata/5771045236_JUL_2026.pdf"


@unittest.skipUnless(os.path.exists(BCA_REAL), "real BCA fixture not present")
class BCAPDFRealSampleTest(unittest.TestCase):
    def test_real_sample(self):
        text = extract_pdf_text(BCA_REAL)
        parser = PDFParser()
        self.assertTrue(parser.can_parse(text))

        stmt = parser.parse(text)
        self.assertEqual(stmt.bank, BankCode.BCA)
        self.assertEqual(stmt.account_name, "EKMAL REYHAN TARIHORAN")
        self.assertEqual(stmt.account_no, "5771045236")
        self.assertEqual(stmt.period, "JULI 2026")

        self.assertEqual(len(stmt.pockets), 1)
        txs = stmt.pockets[0].transactions
        self.assertEqual(len(txs), 17)

        first = txs[0]
        self.assertEqual(first.date, "2026-07-01")
        self.assertEqual(first.mutation_type, "DB")
        self.assertEqual(first.amount.value, -23000)
        self.assertEqual(first.balance.value, 535419)

        last = txs[-1]
        self.assertEqual(last.date, "2026-07-31")
        self.assertEqual(last.mutation_type, "CR")
        self.assertEqual(last.balance.value, 2085794)

        # Statement reconciliation: opening + credits - debits = closing.
        cr = sum(tx.amount.value for tx in txs if tx.mutation_type == "CR")
        db = sum(-tx.amount.value for tx in txs if tx.mutation_type == "DB")
        ending = 558419 + cr - db
        # cent truncation allows a small tolerance on summed amounts
        self.assertGreaterEqual(ending, 2085794 - 20)
        self.assertLessEqual(ending, 2085794)

    def test_can_parse_negative(self):
        parser = PDFParser()
        self.assertFalse(parser.can_parse("random text without bank identifiers"))
        self.assertFalse(
            parser.can_parse("Account No.,=,'0111222333\nName,=,JOHN DOE\nStarting Balance")
        )


if __name__ == "__main__":
    unittest.main()
