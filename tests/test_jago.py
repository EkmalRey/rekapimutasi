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


JAGO_REAL = "banks/jago/testdata/Jago_monthly_statement_July_2026_1786446004518.pdf"


@unittest.skipUnless(os.path.exists(JAGO_REAL), "real Jago fixture not present")
class JagoRealSampleTest(unittest.TestCase):
    def test_real_indonesian_sample(self):
        text = extract_pdf_text(JAGO_REAL)
        stmt = JagoParser().parse(text)

        self.assertEqual(stmt.account_name, "EKMAL REYHAN TARIHORAN")
        self.assertEqual(stmt.account_no, "101018375551")
        self.assertGreaterEqual(len(stmt.pockets), 3)

        main = stmt.pockets[0]
        self.assertEqual(main.name, "Kantong Utama")
        self.assertGreaterEqual(len(main.transactions), 50)

        first = main.transactions[0]
        self.assertEqual(first.date, "2026-07-01")
        self.assertEqual(first.mutation_type, "DB")
        self.assertEqual(first.amount.value, -30000)
        self.assertEqual(first.balance.value, 61832)

        for pocket in stmt.pockets:
            for tx in pocket.transactions:
                self.assertNotEqual(tx.date, "", f"pocket {pocket.name!r} has empty date")


if __name__ == "__main__":
    unittest.main()
