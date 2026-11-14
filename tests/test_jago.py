import os
import unittest

from rekapimutasi import BankCode, EmptyPDFError
from rekapimutasi.banks.jago import JagoParser
from rekapimutasi.extractor import extract_pdf_text

MONTHLY_INPUT = """
Monthly Statements April 2026 Page 2 of 3
PT Bank Jago Tbk is licensed and supervised by Financial Services Authority (OJK), Bank Indonesia,
and also a member of Indonesia Deposit Insurance Corporation (LPS) deposit insurance program. www.jago.com

JOHN DOE / 100000000001

Main Pocket
Pocket ID 100000000001
Pocket is created on 17 Dec 2023
Previous Balance
Total Incoming
Total Outgoing
Closing Balance
23.349,76
+221.876,48
-245.003,10
223,15
Date & Time Source/Destination Transaction Details Notes Amount Balance
13 Apr 2026
11:33
JOHN
DOE
Jago 100000000002
RDN Disbursement
ID# 260413-ABCD-EFGH01
WD jago
+221.861
245.210
13 Apr 2026
11:55
JOHN
DOE
Mandiri 1390000000001
Outgoing Transfer
ID# 260413-WXYZ-123456
-245.000
210
28 Apr 2026
06:41
Interest
Main Pocket
Interest
ID# 260428-INTX-000001
+15
226
28 Apr 2026
06:41
Tax on Interest
Main Pocket
Tax on Interest
ID# 260428-TAXR-000001
-3
223

Stockbit Sekuritas RDN
Pocket ID 100000000002
Pocket is created on22 Dec 2025
Previous Balance
Total Incoming
Total Outgoing
Closing Balance
221.861,60
+359.949,58
-221.951,12
359.860,06
Date & Time Source/Destination Transaction Details Notes Amount Balance
13 Apr 2026
11:33
RDN Withdrawal
RDN Withdrawal
ID# 3500000001
WD jago
-221.861
0
15 Apr 2026
10:34
Incoming Fund
Incoming Fund
ID# 3500000002
{botd} P-000001
Payment to: john
doe
+359.498
359.499
28 Apr 2026
01:04
Interest
Stockbit Sekuritas RDN
Interest
ID# 3500000003
+450
359.950
28 Apr 2026
01:04
Tax on Interest
Stockbit Sekuritas RDN
Tax on Interest
ID# 3500000004
-90
359.860

GoPay Tabungan
Pocket ID 100000000003
Previous Balance
Total Incoming
Total Outgoing
Closing Balance
0,00
+0,00
-0,00
0,00
"""

HISTORY_INPUT = """
PT Bank Jago Tbk is licensed and supervised by Financial Services Authority (OJK), Bank Indonesia, and
also a member of Indonesia Deposit Insurance Corporation (LPS) deposit insurance program.
www.jago.com
Pockets Transactions
History
Page 1 of 47
JANE SMITH
savings / 100000000099
Showing IDR transaction from
Latest Balance per 14 May 2026
28 Mar 2022 - 14 May 2026
IDR 16
Date & Time
Source/Destination
Transaction Details
Notes
Amount
Balance
March 2022
28 Mar 2022
13:29
Main Pocket
Movement between Pockets
Pocket Money In
ID# 42000001
+200.000
200.000
28 Mar 2022
13:32
acme
Movement between Pockets
Movement between Pockets
ID# 42000002
+930.602
1.130.602
"""


class JagoMonthlyTest(unittest.TestCase):
    def setUp(self):
        self.parser = JagoParser()

    def test_monthly_statement(self):
        stmt = self.parser.parse(MONTHLY_INPUT)
        self.assertEqual(stmt.bank, BankCode.JAGO)
        self.assertEqual(stmt.account_name, "JOHN DOE")
        self.assertEqual(stmt.account_no, "100000000001")

        self.assertEqual(len(stmt.pockets), 2)
        main = stmt.pockets[0]
        self.assertEqual(main.name, "Main Pocket")
        self.assertEqual(len(main.transactions), 4)

        stockbit = stmt.pockets[1]
        self.assertEqual(stockbit.name, "Stockbit Sekuritas RDN")
        self.assertEqual(len(stockbit.transactions), 4)

    def test_history_pdf(self):
        stmt = self.parser.parse(HISTORY_INPUT)
        self.assertEqual(stmt.bank, BankCode.JAGO)
        self.assertEqual(stmt.account_name, "JANE SMITH")

        self.assertEqual(len(stmt.pockets), 1)
        pocket = stmt.pockets[0]
        self.assertEqual(pocket.name, "savings")
        self.assertEqual(len(pocket.transactions), 2)

        first = pocket.transactions[0]
        self.assertEqual(first.date, "2022-03-28")
        self.assertEqual(first.time, "13:29")
        self.assertEqual(first.source_destination, "Main Pocket")
        self.assertEqual(first.amount.value, 200000)

        second = pocket.transactions[1]
        self.assertEqual(second.date, "2022-03-28")
        self.assertEqual(second.time, "13:32")
        self.assertEqual(second.source_destination, "acme")
        self.assertEqual(second.amount.value, 930602)

    def test_can_parse(self):
        self.assertTrue(self.parser.can_parse("something PT Bank Jago Tbk something"))
        self.assertTrue(self.parser.can_parse("something www.jago.com something"))
        self.assertFalse(self.parser.can_parse("random text without bank identifiers"))

    def test_empty_input(self):
        with self.assertRaises(EmptyPDFError):
            self.parser.parse("")


JAGO_DIR = "banks/jago/testdata"
JAGO_JULY = (
    os.path.join(JAGO_DIR, "Jago_monthly_statement_July_2026_1786446004518 (OLD, WORKS WELL).pdf")
    if os.path.exists(os.path.join(JAGO_DIR, "Jago_monthly_statement_July_2026_1786446004518 (OLD, WORKS WELL).pdf"))
    else os.path.join(JAGO_DIR, "Jago_monthly_statement_July_2026_1786446004518.pdf")
)
JAGO_AUG = os.path.join(JAGO_DIR, "Jago_monthly_statement_August_2026.pdf")
JAGO_SEP = os.path.join(JAGO_DIR, "Jago_monthly_statement_September_2026.pdf")
JAGO_OCT = os.path.join(JAGO_DIR, "Jago_monthly_statement_October_2026.pdf")


class JagoRealSampleTest(unittest.TestCase):
    @unittest.skipUnless(os.path.exists(JAGO_JULY), "real Jago July fixture not present")
    def test_real_indonesian_sample(self):
        text = extract_pdf_text(JAGO_JULY)
        stmt = JagoParser().parse(text)

        self.assertEqual(stmt.account_name, "EKMAL REYHAN TARIHORAN")
        self.assertEqual(stmt.account_no, "101018375551")
        self.assertEqual(stmt.period, "Juli 2026")
        self.assertEqual(len(stmt.pockets), 8)

        main = stmt.pockets[0]
        self.assertEqual(main.name, "Kantong Utama")
        self.assertEqual(len(main.transactions), 61)

        first = main.transactions[0]
        self.assertEqual(first.date, "2026-07-01")
        self.assertEqual(first.mutation_type, "DB")
        self.assertEqual(first.amount.value, -30000)
        self.assertEqual(first.balance.value, 61832)

        total_txs = sum(len(p.transactions) for p in stmt.pockets)
        self.assertEqual(total_txs, 114)

        for pocket in stmt.pockets:
            for tx in pocket.transactions:
                self.assertNotEqual(tx.date, "", f"pocket {pocket.name!r} has empty date")
                self.assertNotEqual(tx.transaction_id, "", f"pocket {pocket.name!r} has empty transaction id")

    @unittest.skipUnless(os.path.exists(JAGO_AUG), "real Jago August fixture not present")
    def test_august_sample(self):
        text = extract_pdf_text(JAGO_AUG)
        stmt = JagoParser().parse(text)

        self.assertEqual(stmt.account_name, "EKMAL REYHAN TARIHORAN")
        self.assertEqual(stmt.account_no, "101018375551")
        self.assertEqual(stmt.period, "Agustus 2026")
        self.assertEqual(len(stmt.pockets), 8)

        main = stmt.pockets[0]
        self.assertEqual(main.name, "Kantong Utama")
        first = main.transactions[0]
        self.assertEqual(first.date, "2026-08-02")
        self.assertEqual(first.transaction_id, "260802-UT2Q-MYP43E")
        self.assertEqual(first.mutation_type, "CR")
        self.assertEqual(first.amount.value, 1300000)
        self.assertEqual(first.balance.value, 1306096)

        total_txs = sum(len(p.transactions) for p in stmt.pockets)
        self.assertEqual(total_txs, 74)

    @unittest.skipUnless(os.path.exists(JAGO_SEP), "real Jago September fixture not present")
    def test_september_sample(self):
        text = extract_pdf_text(JAGO_SEP)
        stmt = JagoParser().parse(text)

        self.assertEqual(stmt.account_name, "EKMAL REYHAN TARIHORAN")
        self.assertEqual(stmt.account_no, "101018375551")
        self.assertEqual(stmt.period, "September 2026")
        self.assertEqual(len(stmt.pockets), 7)

        main = stmt.pockets[0]
        self.assertEqual(main.name, "Kantong Utama")
        first = main.transactions[0]
        self.assertEqual(first.date, "2026-09-01")
        self.assertEqual(first.transaction_id, "260901-KRJ9-BH7WW4")
        self.assertEqual(first.mutation_type, "DB")
        self.assertEqual(first.amount.value, -16500)
        self.assertEqual(first.balance.value, 55571)

        total_txs = sum(len(p.transactions) for p in stmt.pockets)
        self.assertEqual(total_txs, 56)

    @unittest.skipUnless(os.path.exists(JAGO_OCT), "real Jago October fixture not present")
    def test_october_sample(self):
        text = extract_pdf_text(JAGO_OCT)
        stmt = JagoParser().parse(text)

        self.assertEqual(stmt.account_name, "EKMAL REYHAN TARIHORAN")
        self.assertEqual(stmt.account_no, "101018375551")
        self.assertEqual(stmt.period, "Oktober 2026")
        self.assertEqual(len(stmt.pockets), 7)

        main = stmt.pockets[0]
        self.assertEqual(main.name, "Kantong Utama")
        first = main.transactions[0]
        self.assertEqual(first.date, "2026-10-01")
        self.assertEqual(first.transaction_id, "261001-WZY3-WFL4KM")
        self.assertEqual(first.mutation_type, "CR")
        self.assertEqual(first.amount.value, 1500000)
        self.assertEqual(first.balance.value, 1561738)

        total_txs = sum(len(p.transactions) for p in stmt.pockets)
        self.assertEqual(total_txs, 54)


if __name__ == "__main__":
    unittest.main()
