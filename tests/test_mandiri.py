import unittest

from rekapimutasi import BankCode
from rekapimutasi.banks.mandiri import MandiriParser

MANDIRI_INPUT = """Periode /
Period
:
1/09/23 s/d 30/09/23
Tabungan /
Savings
No. Rekening
Account Number
Nama Produk
Product Name
Cabang
Branch
Periode
Period
Valuta
Currency
Saldo
Balance
111-00-98765432-1
Mandiri Tabungan
101010 - KCP Jl Sesama
1/09/23 s/d
30/09/23
Indonesian
Rupiah
(IDR)
605,764.00
Tanggal
Transaksi
Transaction
Date
Tanggal
Valuta
Valuta
Date
Rincian Transaksi / Nomor Referensi
Transaction Details / Reference Number
Debit / Kredit
Debit / Credit
Saldo
Balance
01/09
Saldo Awal
659,470.00
05/09
05/09
-MONTHLY CARD CHARGE 987654321
5,500.00 D
653,970.00
07/09
07/09
Tarif Link -123 /001122/ATB-001122
500,000.00 D
153,970.00
987654321
AFMT SESAMA
07/09
07/09
Tarif Link -001122 /001122/ATB-001122
7,500.00 D
146,470.00
987654321
AFMT SESAMA
10/09
10/09
-UBP987654321
20,000.00 D
126,470.00
16/09
16/09
-20230916CENAIDJA987654321
1,000,000.00
1,126,470.00
CENAIDJA/JOHN DOE
987654321
-
16/09
16/09
-987654321
508,206.00 D
618,264.00
987654321=
30/09
30/09
Biaya Adm -
12,500.00 D
605,764.00
Saldo Awal /
Previous Balance
:
659,470.00
Mutasi Kredit /
Total of Credit Transactions
:
1,000,000.00
Mutasi Debit /
Total of Debit Transactions
:
1,053,706.00
Saldo Akhir /
Current Balance
:
605,764.00
"""

EXPECTED = [
    ("2023-09-05", "DB", "-MONTHLY CARD CHARGE 987654321", -5500, 653970),
    ("2023-09-07", "DB", "Tarif Link -123 /001122/ATB-001122 987654321 AFMT SESAMA", -500000, 153970),
    ("2023-09-07", "DB", "Tarif Link -001122 /001122/ATB-001122 987654321 AFMT SESAMA", -7500, 146470),
    ("2023-09-10", "DB", "-UBP987654321", -20000, 126470),
    ("2023-09-16", "CR", "-20230916CENAIDJA987654321 CENAIDJA/JOHN DOE 987654321 -", 1000000, 1126470),
    ("2023-09-16", "DB", "-987654321 987654321=", -508206, 618264),
    ("2023-09-30", "DB", "Biaya Adm -", -12500, 605764),
]


class MandiriTest(unittest.TestCase):
    def test_parser(self):
        parser = MandiriParser()
        self.assertTrue(parser.can_parse(MANDIRI_INPUT))

        stmt = parser.parse(MANDIRI_INPUT)
        self.assertEqual(stmt.bank, BankCode.MANDIRI)
        self.assertEqual(stmt.period, "1/09/23 s/d 30/09/23")

        self.assertEqual(len(stmt.pockets), 1)
        txs = stmt.pockets[0].transactions
        self.assertEqual(len(txs), 7)

        for i, (date, typ, detail, amt, bal) in enumerate(EXPECTED):
            tx = txs[i]
            self.assertEqual(tx.date, date, f"tx[{i}] date")
            self.assertEqual(tx.mutation_type, typ, f"tx[{i}] type")
            self.assertEqual(tx.transaction_detail, detail, f"tx[{i}] detail")
            self.assertEqual(tx.amount.value, amt, f"tx[{i}] amount")
            self.assertEqual(tx.balance.value, bal, f"tx[{i}] balance")

    def test_can_parse_negative(self):
        parser = MandiriParser()
        self.assertFalse(parser.can_parse("random text without bank identifiers"))
        self.assertFalse(parser.can_parse("REKENING TAHAPAN\nMUTASI\nSARAH SAUSAN"))


if __name__ == "__main__":
    unittest.main()
