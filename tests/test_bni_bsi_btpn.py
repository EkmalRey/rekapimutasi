import unittest

from rekapimutasi import BankCode
from rekapimutasi.banks.bni import BNIParser
from rekapimutasi.banks.bsi import BSIParser
from rekapimutasi.banks.btpn import BTPNParser

BNI_INPUT = """HISTORI TRANSAKSI
01-Jan-21
TRSF E-BANKING
Db.
1,234,567.00
02-Jan-21
Transfer Masuk
Cr.
500,000.00
"""

BSI_INPUT = """MUTASI REKENING
Rekening : 1234567890
Periode : 01/01/2021 - 31/01/2021
01/01
Transfer Masuk
500,000.00
02/01
Beli Pulsa
- 100,000.00
"""

BTPN_INPUT = """BTPN Jenius
1 Jan 2021
Transfer GRAB
- 50,000
2 Jan 2021
Incoming Transfer
+ 1,000,000
"""


class BNITest(unittest.TestCase):
    def test_parser(self):
        p = BNIParser()
        self.assertTrue(p.can_parse(BNI_INPUT))
        stmt = p.parse(BNI_INPUT)
        self.assertEqual(stmt.bank, BankCode.BNI)
        txs = stmt.pockets[0].transactions
        self.assertEqual(len(txs), 2)
        self.assertEqual((txs[0].date, txs[0].mutation_type, txs[0].amount.value), ("2021-01-01", "DB", -1234567))
        self.assertEqual((txs[1].date, txs[1].mutation_type, txs[1].amount.value), ("2021-01-02", "CR", 500000))


class BSITest(unittest.TestCase):
    def test_parser(self):
        p = BSIParser()
        self.assertTrue(p.can_parse(BSI_INPUT))
        stmt = p.parse(BSI_INPUT)
        self.assertEqual(stmt.bank, BankCode.BSI)
        txs = stmt.pockets[0].transactions
        self.assertEqual(len(txs), 2)
        self.assertEqual((txs[0].date, txs[0].mutation_type, txs[0].amount.value), ("2021-01-01", "CR", 500000))
        self.assertEqual((txs[1].date, txs[1].mutation_type, txs[1].amount.value), ("2021-01-02", "DB", -100000))


class BTPNTest(unittest.TestCase):
    def test_parser(self):
        p = BTPNParser()
        self.assertTrue(p.can_parse(BTPN_INPUT))
        stmt = p.parse(BTPN_INPUT)
        self.assertEqual(stmt.bank, BankCode.JENIUS)
        txs = stmt.pockets[0].transactions
        self.assertEqual(len(txs), 2)
        self.assertEqual((txs[0].date, txs[0].mutation_type, txs[0].amount.value), ("2021-01-01", "DB", -50000))
        self.assertEqual((txs[1].date, txs[1].mutation_type, txs[1].amount.value), ("2021-01-02", "CR", 1000000))


if __name__ == "__main__":
    unittest.main()
