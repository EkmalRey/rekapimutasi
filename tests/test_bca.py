import os
import unittest
from decimal import Decimal

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
        self.assertEqual(tx.balance.value, Decimal("1042939.96"))

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


# Synthetic statement modelled on how pypdf renders a BCA Tahapan e-statement
# (description and MUTASI/SALDO cells on separate lines). The running balance
# is printed only on some rows (BCA prints it once per day), debits carry a
# "DB" marker and descriptions contain misleading words such as "ESPAY DEBIT"
# or "KARTU KREDIT".
BCA_PDF_SIGN_INPUT = """REKENING TAHAPAN
JOHN DOE
NO. REKENING : 0123456789
PERIODE : JANUARI 2026
MATA UANG : IDR
TANGGAL KETERANGAN CBG MUTASI SALDO
01/01 SALDO AWAL 1,000,000.00
02/01 TRSF E-BANKING CR 0201/FTSCY/WS95051
500000.00
TRFDN-JANE ROE ESPAY DEBIT INDONE
500,000.00
02/01 KARTU KREDIT/PL 0201 WSID000000001
0100 BCA CARD
0000000000000000
JOHN DOE
111,000.00 DB
02/01 BI-FAST CR BIF TRANSFER DR 014
JANE ROE
11,000.00 1,400,000.00
03/01 TRSF E-BANKING CR 0301/FTSCY/WS95051
300000.00
JANE ROE
300,000.00
03/01 TRSF E-BANKING DB 0301/FTSCY/WS95051
150000.00
JANE ROE
150,000.00 DB 1,550,000.00
31/01 DR KOREKSI BUNGA 0.62 DB
31/01 BUNGA 1,175.99
31/01 PAJAK BUNGA 235.20 DB 1,550,940.17
SALDO AWAL : 1,000,000.00
MUTASI CR : 812,175.99
MUTASI DB : 261,235.82
SALDO AKHIR : 1,550,940.17
"""


class BCAPDFSignTest(unittest.TestCase):
    def setUp(self):
        parser = PDFParser()
        self.assertTrue(parser.can_parse(BCA_PDF_SIGN_INPUT))
        self.txs = parser.parse(BCA_PDF_SIGN_INPUT).pockets[0].transactions

    def test_mutation_types(self):
        self.assertEqual(
            [tx.mutation_type for tx in self.txs],
            ["CR", "DB", "CR", "CR", "DB", "DB", "CR", "DB"],
        )

    def test_credit_with_debit_word_in_description(self):
        # "TRSF E-BANKING CR ... ESPAY DEBIT INDONE" is incoming money
        self.assertEqual(self.txs[0].mutation_type, "CR")
        self.assertEqual(self.txs[0].amount.value, 500000)

    def test_credit_card_payment_is_debit(self):
        self.assertEqual(self.txs[1].mutation_type, "DB")
        self.assertEqual(self.txs[1].amount.value, -111000)

    def test_balance_chain_broken_by_unprinted_balance(self):
        # +300,000 (no balance printed) then -150,000 lands exactly
        # 150,000 above the last printed balance: still a debit.
        self.assertEqual(self.txs[4].mutation_type, "DB")

    def test_interest_rows_keep_cents(self):
        self.assertEqual(self.txs[5].amount.value, Decimal("-0.62"))
        self.assertEqual(self.txs[6].amount.value, Decimal("1175.99"))
        self.assertEqual(self.txs[7].amount.value, Decimal("-235.20"))
        self.assertEqual(self.txs[7].balance.value, Decimal("1550940.17"))

    def test_reconciles_to_the_cent(self):
        opening = Decimal("1000000.00")
        closing = Decimal("1550940.17")
        self.assertEqual(opening + sum(tx.amount.value for tx in self.txs), closing)


class BCAPDFNegativeTest(unittest.TestCase):
    def test_can_parse_negative(self):
        parser = PDFParser()
        self.assertFalse(parser.can_parse("random text without bank identifiers"))
        self.assertFalse(
            parser.can_parse("Account No.,=,'0111222333\nName,=,JOHN DOE\nStarting Balance")
        )


BCA_DIR = "banks/bca/testdata"
BCA_AGU = os.path.join(BCA_DIR, "5771045236_AGU_2026.pdf")
BCA_SEP = os.path.join(BCA_DIR, "5771045236_SEP_2026.pdf")
BCA_OCT = os.path.join(BCA_DIR, "5771045236_OKT_2026.pdf")
BCA_JUL = os.path.join(BCA_DIR, "5771045236_JUL_2026.pdf")


class BCAPDFRealSampleTest(unittest.TestCase):
    @unittest.skipUnless(os.path.exists(BCA_AGU), "real BCA August fixture not present")
    def test_august_sample(self):
        text = extract_pdf_text(BCA_AGU)
        parser = PDFParser()
        self.assertTrue(parser.can_parse(text))

        stmt = parser.parse(text)
        self.assertEqual(stmt.bank, BankCode.BCA)
        self.assertEqual(stmt.account_name, "EKMAL REYHAN TARIHORAN")
        self.assertEqual(stmt.account_no, "5771045236")
        self.assertEqual(stmt.period, "Agustus 2026")

        self.assertEqual(len(stmt.pockets), 1)
        txs = stmt.pockets[0].transactions
        self.assertEqual(len(txs), 43)

        cr = sum(tx.amount.value for tx in txs if tx.mutation_type == "CR")
        db = sum(-tx.amount.value for tx in txs if tx.mutation_type == "DB")
        opening = 2085794
        closing = 2331702
        self.assertLess(abs(opening + cr - db - closing), 1)

    @unittest.skipUnless(os.path.exists(BCA_SEP), "real BCA September fixture not present")
    def test_september_sample(self):
        text = extract_pdf_text(BCA_SEP)
        parser = PDFParser()
        self.assertTrue(parser.can_parse(text))

        stmt = parser.parse(text)
        self.assertEqual(stmt.bank, BankCode.BCA)
        self.assertEqual(stmt.account_name, "EKMAL REYHAN TARIHORAN")
        self.assertEqual(stmt.account_no, "5771045236")
        self.assertEqual(stmt.period, "September 2026")

        self.assertEqual(len(stmt.pockets), 1)
        txs = stmt.pockets[0].transactions
        self.assertEqual(len(txs), 67)

        cr = sum(tx.amount.value for tx in txs if tx.mutation_type == "CR")
        db = sum(-tx.amount.value for tx in txs if tx.mutation_type == "DB")
        opening = 2331702
        closing = 69498
        self.assertLess(abs(opening + cr - db - closing), 1)

    @unittest.skipUnless(os.path.exists(BCA_OCT), "real BCA October fixture not present")
    def test_october_sample(self):
        text = extract_pdf_text(BCA_OCT)
        parser = PDFParser()
        self.assertTrue(parser.can_parse(text))

        stmt = parser.parse(text)
        self.assertEqual(stmt.bank, BankCode.BCA)
        self.assertEqual(stmt.account_name, "EKMAL REYHAN TARIHORAN")
        self.assertEqual(stmt.account_no, "5771045236")
        self.assertEqual(stmt.period, "Oktober 2026")

        self.assertEqual(len(stmt.pockets), 1)
        txs = stmt.pockets[0].transactions
        self.assertEqual(len(txs), 45)

        cr = sum(tx.amount.value for tx in txs if tx.mutation_type == "CR")
        db = sum(-tx.amount.value for tx in txs if tx.mutation_type == "DB")
        opening = 69498
        closing = 5090531
        self.assertLess(abs(opening + cr - db - closing), 1)

    @unittest.skipUnless(os.path.exists(BCA_JUL), "real BCA July fixture not present")
    def test_real_sample(self):
        text = extract_pdf_text(BCA_JUL)
        parser = PDFParser()
        self.assertTrue(parser.can_parse(text))

        stmt = parser.parse(text)
        self.assertEqual(stmt.bank, BankCode.BCA)
        self.assertEqual(stmt.account_name, "EKMAL REYHAN TARIHORAN")
        self.assertEqual(stmt.account_no, "5771045236")
        self.assertEqual(stmt.period, "Juli 2026")

        self.assertEqual(len(stmt.pockets), 1)
        txs = stmt.pockets[0].transactions
        self.assertEqual(len(txs), 17)


if __name__ == "__main__":
    unittest.main()
