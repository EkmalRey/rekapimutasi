"""Regression tests for real bank fixtures dropped into banks/*/testdata.

Each test skips when its sample PDF is absent (the PDFs stay out of git, so a
clean checkout only runs the synthetic tests unless a sample is supplied).
"""
import os
import re
import unittest

import rekapimutasi

BASE = {b: f"banks/{b}/testdata" for b in ("bca", "jago", "mandiri", "bni", "jenius", "bri")}


def path(bank, name):
    p = os.path.join(BASE[bank], name)
    return p if os.path.exists(p) else None


def requires(bank, name):
    sample = path(bank, name)
    return unittest.skipUnless(sample, f"{bank}/{name} fixture not present")(lambda f: f)


def _sums(stmt):
    cr = db = 0
    for p in stmt.pockets:
        for t in p.transactions:
            if t.mutation_type == "CR":
                cr += t.amount.value
            else:
                db += -t.amount.value
    return cr, db


def _first_summary(text, key):
    m = re.search(rf"{key} : ([\d.,]+)", text)
    return int(m.group(1).replace(",", "").split(".")[0]) if m else None


def _reconciles(stmt, text, tol=60):
    op = _first_summary(text, "SALDO AWAL")
    cl = _first_summary(text, "SALDO AKHIR")
    if op is None or cl is None:
        return True
    cr, db = _sums(stmt)
    return abs(op + cr - db - cl) <= tol


class BCAFixtures(unittest.TestCase):
    @requires("bca", "5771045236_JUL_2026.pdf")
    def test_jul_2026(self):
        sample = path("bca", "5771045236_JUL_2026.pdf")
        text = rekapimutasi.extractor.extract_pdf_text(sample)
        stmt = rekapimutasi.parse_file(sample)
        self.assertEqual(stmt.bank, "BCA")
        self.assertEqual(stmt.account_no, "5771045236")
        txs = stmt.pockets[0].transactions
        self.assertEqual(len(txs), 17)
        self.assertEqual(txs[0].date, "2026-07-01")
        self.assertEqual(txs[0].mutation_type, "DB")
        self.assertEqual(txs[0].amount.value, -23000)
        self.assertEqual(txs[-1].balance.value, 2085794)
        self.assertTrue(_reconciles(stmt, text))

    @requires("bca", "5771045236_JUN_2026.pdf")
    def test_jun_2026(self):
        text = rekapimutasi.extractor.extract_pdf_text(path("bca", "5771045236_JUN_2026.pdf"))
        stmt = rekapimutasi.parse_file(path("bca", "5771045236_JUN_2026.pdf"))
        self.assertEqual(len(stmt.pockets[0].transactions), 30)
        self.assertTrue(_reconciles(stmt, text))

    @requires("bca", "5771045236_MAY_2026.pdf")
    def test_may_2026(self):
        text = rekapimutasi.extractor.extract_pdf_text(path("bca", "5771045236_MAY_2026.pdf"))
        stmt = rekapimutasi.parse_file(path("bca", "5771045236_MAY_2026.pdf"))
        self.assertEqual(len(stmt.pockets[0].transactions), 11)
        self.assertTrue(_reconciles(stmt, text))

    @requires("bca", "867191975-6043181055-FEB-2025.pdf")
    def test_inline_markerless_variant(self):
        text = rekapimutasi.extractor.extract_pdf_text(path("bca", "867191975-6043181055-FEB-2025.pdf"))
        stmt = rekapimutasi.parse_file(path("bca", "867191975-6043181055-FEB-2025.pdf"))
        self.assertEqual(stmt.account_no, "6043181055")
        self.assertEqual(len(stmt.pockets[0].transactions), 26)
        self.assertTrue(_reconciles(stmt, text, tol=3000))

    @requires("bca", "942800978-7641564358Aug2025-2-1-1-1.pdf")
    def test_large_statement(self):
        text = rekapimutasi.extractor.extract_pdf_text(path("bca", "942800978-7641564358Aug2025-2-1-1-1.pdf"))
        stmt = rekapimutasi.parse_file(path("bca", "942800978-7641564358Aug2025-2-1-1-1.pdf"))
        self.assertEqual(stmt.account_name, "TRIYANA NUGRAHA")
        self.assertEqual(len(stmt.pockets[0].transactions), 154)
        self.assertTrue(_reconciles(stmt, text))

    @requires("bca", "964360461-Imam-Apryadi.pdf")
    def test_concatenated_three_months(self):
        stmt = rekapimutasi.parse_file(path("bca", "964360461-Imam-Apryadi.pdf"))
        self.assertEqual(stmt.account_no, "7745325118")
        # three consecutive months squeezed into one PDF
        self.assertEqual(len(stmt.pockets[0].transactions), 27)
        self.assertEqual(stmt.pockets[0].transactions[0].date[:7], "2023-10")

    @requires("bca", "986438530-7435064540-Sep-2025.pdf")
    def test_spaced_letter_header(self):
        text = rekapimutasi.extractor.extract_pdf_text(path("bca", "986438530-7435064540-Sep-2025.pdf"))
        stmt = rekapimutasi.parse_file(path("bca", "986438530-7435064540-Sep-2025.pdf"))
        self.assertEqual(stmt.account_name, "LINAWATI S.PDI")
        self.assertEqual(stmt.account_no, "7435064540")
        self.assertEqual(len(stmt.pockets[0].transactions), 32)
        self.assertTrue(_reconciles(stmt, text))


class JagoFixtures(unittest.TestCase):
    @requires("jago", "1033192008-Jago-monthly-statement-January-2025-1741950967813.pdf")
    def test_january_2025(self):
        stmt = rekapimutasi.parse_file(path("jago", "1033192008-Jago-monthly-statement-January-2025-1741950967813.pdf"))
        self.assertEqual(stmt.account_name, "MUKTI PAMUNGKARI")
        self.assertEqual(stmt.account_no, "101558770131")
        self.assertEqual(sum(len(p.transactions) for p in stmt.pockets), 67)

    @requires("jago", "884784371-Jago-Monthly-Statement-June-2025-1751429724825.pdf")
    def test_june_2025_english(self):
        stmt = rekapimutasi.parse_file(path("jago", "884784371-Jago-Monthly-Statement-June-2025-1751429724825.pdf"))
        self.assertEqual(stmt.account_name, "ZAINI MAHDI")
        self.assertEqual(stmt.account_no, "107781526840")
        self.assertEqual(sum(len(p.transactions) for p in stmt.pockets), 73)


class MandiriFixtures(unittest.TestCase):
    @requires("mandiri", "799491100-E-Statement-XXXXXXXXX6547-01-Sep-2024-30-Sep-2024.pdf")
    def test_e_statement_sep_2024(self):
        stmt = rekapimutasi.parse_file(path("mandiri", "799491100-E-Statement-XXXXXXXXX6547-01-Sep-2024-30-Sep-2024.pdf"))
        self.assertEqual(stmt.bank, "MANDIRI")
        self.assertEqual(stmt.account_name, "ANDY PANGERAN")
        self.assertEqual(stmt.account_no, "1310018826547")
        self.assertEqual(len(stmt.pockets[0].transactions), 37)

    @requires("mandiri", "758460586-E-Statement-XXXXXXXXX2476-01-Feb-2024-29-Feb-2024-5-compressed.pdf")
    def test_e_statement_feb_2024(self):
        stmt = rekapimutasi.parse_file(path("mandiri", "758460586-E-Statement-XXXXXXXXX2476-01-Feb-2024-29-Feb-2024-5-compressed.pdf"))
        self.assertEqual(stmt.account_name, "RUDI ISMAWAN")
        self.assertEqual(len(stmt.pockets[0].transactions), 377)

    @requires("mandiri", "743763303-Mandiri-Acc-Statement-Agustus-2023.pdf")
    def test_koran_report(self):
        stmt = rekapimutasi.parse_file(path("mandiri", "743763303-Mandiri-Acc-Statement-Agustus-2023.pdf"))
        self.assertEqual(stmt.account_no, "1330015618499")
        self.assertEqual(len(stmt.pockets[0].transactions), 36)

    @requires("mandiri", "743763303-Mandiri-Acc-Statement-Agustus-2023.pdf")
    def test_koran_report_v1_time_and_fees(self):
        stmt = rekapimutasi.parse_file(path("mandiri", "743763303-Mandiri-Acc-Statement-Agustus-2023.pdf"))
        txs = stmt.pockets[0].transactions
        self.assertEqual(txs[0].time, "08:04:05")
        self.assertNotIn(":", txs[0].transaction_detail)
        # Biaya administrasi rows carry their label in the detail.
        self.assertTrue(any(t.transaction_detail.startswith("Biaya Adm") for t in txs))
        self.assertTrue(any(t.transaction_detail.startswith("Bunga") for t in txs))
        self.assertEqual(txs[-1].balance.value, 588537)  # Closing Balance
        self.assertFalse(any("Total Amount" in t.transaction_detail for t in txs))

    @requires("mandiri", "593522975-September-2019.pdf")
    def test_koran_2019_time_and_first_row(self):
        stmt = rekapimutasi.parse_file(path("mandiri", "593522975-September-2019.pdf"))
        txs = stmt.pockets[0].transactions
        # First transaction (VAP) must not be skipped or merged into the next.
        self.assertEqual(txs[0].date, "2019-09-01")
        self.assertEqual(txs[0].time, "19:51:49")
        self.assertEqual(txs[0].amount.value, -609800)
        self.assertIn("72174990", txs[0].transaction_detail)
        # Second transaction carries its own time, not the first's.
        self.assertEqual(txs[1].time, "11:04:58")
        self.assertFalse(any("Total Amount" in t.transaction_detail for t in txs))


    @requires("mandiri", "537548916-Account-Statement-PDF-1320022271077-10-September-2019-2.pdf")
    def test_koran_account_statement_large(self):
        stmt = rekapimutasi.parse_file(path("mandiri", "537548916-Account-Statement-PDF-1320022271077-10-September-2019-2.pdf"))
        self.assertEqual(stmt.account_no, "1330016554388")
        txs = stmt.pockets[0].transactions
        # The old parser dropped page-break-split rows; every money row must
        # be captured (balance of the last row equals the report's Closing
        # Balance 302,571,011.57).
        self.assertGreaterEqual(len(txs), 2000)
        self.assertEqual(txs[-1].balance.value, 302571011)
        # No report summary may leak into transaction details.
        self.assertFalse(any(
            "Total Amount" in t.transaction_detail or "Closing Balance" in t.transaction_detail
            for t in txs
        ))


class BNIFixtures(unittest.TestCase):
    @requires("bni", "1020546352-BNI-Oktober.pdf")
    def test_oktober(self):
        stmt = rekapimutasi.parse_file(path("bni", "1020546352-BNI-Oktober.pdf"))
        self.assertEqual(stmt.bank, "BNI")
        txs = stmt.pockets[0].transactions
        self.assertEqual(txs[0].date, "2025-10-26")
        self.assertEqual(txs[0].mutation_type, "CR")
        self.assertEqual(txs[0].amount.value, 3497000)

    @requires("bni", "994533524-mutasi-transaksi-September.pdf")
    def test_mutasi_transaksi(self):
        stmt = rekapimutasi.parse_file(path("bni", "994533524-mutasi-transaksi-September.pdf"))
        self.assertEqual(stmt.bank, "BNI")
        txs = stmt.pockets[0].transactions
        self.assertEqual(len(txs), 92)
        self.assertEqual(txs[0].date, "2022-09-30")
        self.assertEqual(txs[0].mutation_type, "DB")


class JeniusFixtures(unittest.TestCase):
    @requires("jenius", "442665252-Jenius-eStatement-NOV-2019-pdf.pdf")
    def test_nov_2019(self):
        stmt = rekapimutasi.parse_file(path("jenius", "442665252-Jenius-eStatement-NOV-2019-pdf.pdf"))
        self.assertEqual(stmt.bank, "JENIUS")
        txs = stmt.pockets[0].transactions
        self.assertFalse(any("SALDO" in t.transaction_detail for t in txs))
        self.assertFalse(any("TANGGAL" in t.transaction_detail for t in txs))
        self.assertFalse(any("E-STATEMENT" in t.transaction_detail for t in txs))
        self.assertFalse(any("DISCLAIMER" in t.transaction_detail for t in txs))

    @requires("jenius", "561195771-Jenius-eStatement-AUG-2020.pdf")
    def test_aug_2020(self):
        stmt = rekapimutasi.parse_file(path("jenius", "561195771-Jenius-eStatement-AUG-2020.pdf"))
        txs = stmt.pockets[0].transactions
        cr = sum(t.amount.value for t in txs if t.mutation_type == "CR")
        db = sum(-t.amount.value for t in txs if t.mutation_type == "DB")
        self.assertEqual(len(txs), 159)
        self.assertEqual(cr, 110703716)
        self.assertEqual(db, 108082579)
        # The user-reported leak: statement summary (SALDO AKHIR, TANGGAL & JAM,
        # legend, DISCLAIMER) must never appear in a transaction detail.
        self.assertFalse(any("SALDO" in t.transaction_detail for t in txs))
        self.assertFalse(any("TANGGAL & JAM" in t.transaction_detail for t in txs))
        self.assertFalse(any("DISCLAIMER" in t.transaction_detail for t in txs))
        self.assertFalse(any("www.jenius" in t.transaction_detail for t in txs))

    @requires("jenius", "659711381-Jenius-eStatement-MAY-2023-1.pdf")
    def test_may_2023_metadata_and_pockets(self):
        stmt = rekapimutasi.parse_file(path("jenius", "659711381-Jenius-eStatement-MAY-2023-1.pdf"))
        self.assertEqual(stmt.bank, "JENIUS")
        self.assertEqual(stmt.account_name, "MARINA MARYANTI")
        self.assertEqual(stmt.account_no, "90370212491")
        self.assertEqual(stmt.period, "Mei 2023")
        names = [p.name for p in stmt.pockets]
        self.assertIn("Saldo Aktif", names)
        self.assertIn("e-Card *3890", names)
        self.assertIn("x-Card *1184", names)
        self.assertIn("x-Card *3659", names)
        self.assertIn("x-Card *3667", names)
        self.assertIn("Flexi Saver - BISMILAH BELI MOBIL", names)
        # card-pocket transactions carry the card as source and a balance
        x3659 = next(p for p in stmt.pockets if p.name == "x-Card *3659")
        self.assertTrue(all(t.source_destination == "x-Card *3659" for t in x3659.transactions))
        self.assertTrue(any(t.balance.currency for t in x3659.transactions))
        flexi = next(p for p in stmt.pockets if p.name.startswith("Flexi Saver"))
        self.assertTrue(all(t.source_destination.startswith("Flexi Saver") for t in flexi.transactions))
        self.assertTrue(any(t.balance.currency for t in flexi.transactions))
        # transaction IDs are captured from the Rincian column and removed
        # from the detail; the category after "|" becomes notes
        all_txs = [t for p in stmt.pockets for t in p.transactions]
        with_id = [t for t in all_txs if t.transaction_id]
        self.assertTrue(len(with_id) > 150)
        self.assertTrue(all(
            re.fullmatch(r"\d{12}(?:@@?[A-Z][A-Z0-9]*|[A-Z]{2,}[A-Z0-9]*)", t.transaction_id)
            for t in with_id
        ))
        self.assertTrue(all(t.transaction_id not in t.transaction_detail for t in with_id))
        self.assertTrue(any(t.notes not in ("", "-") for t in all_txs))
        # main pocket has no balance (per statement layout)
        main = next(p for p in stmt.pockets if p.name == "Saldo Aktif")
        self.assertFalse(any(t.balance.currency for t in main.transactions))


class BRIFixtures(unittest.TestCase):
    @requires("bri", "502177382-Welcome-to-BRI-Internet-Banking.pdf")
    def test_anton_heni(self):
        stmt = rekapimutasi.parse_file(path("bri", "502177382-Welcome-to-BRI-Internet-Banking.pdf"))
        self.assertEqual(stmt.bank, "BRI")
        self.assertEqual(stmt.account_name, "ANTON HENI WIBOWO")
        self.assertEqual(stmt.account_no, "141901002581501")
        self.assertEqual(len(stmt.pockets[0].transactions), 153)

    @requires("bri", "588513110-R-K-BRI-Per-1-Mai-Sd-24-Mai-2021.pdf")
    def test_glued_variant(self):
        stmt = rekapimutasi.parse_file(path("bri", "588513110-R-K-BRI-Per-1-Mai-Sd-24-Mai-2021.pdf"))
        self.assertEqual(stmt.account_name, "ASOSIASI ASURANSI UM")
        self.assertEqual(len(stmt.pockets[0].transactions), 13)
        last = stmt.pockets[0].transactions[-1]
        self.assertEqual(last.balance.value, 71447187)  # Saldo Akhir, not Total Mutasi totals
        self.assertNotIn("Total Mutasi", last.transaction_detail)
        self.assertNotIn("Saldo Akhir", last.transaction_detail)

    @requires("bri", "502177382-Welcome-to-BRI-Internet-Banking.pdf")
    def test_anton_heni_summary_not_leaked(self):
        stmt = rekapimutasi.parse_file(path("bri", "502177382-Welcome-to-BRI-Internet-Banking.pdf"))
        last = stmt.pockets[0].transactions[-1]
        self.assertEqual(last.balance.value, 2791424)  # Saldo Akhir 2.791.424,72
        self.assertNotIn("Total Mutasi", last.transaction_detail)
        self.assertNotIn("Saldo Akhir", last.transaction_detail)
        self.assertNotIn("Catatan", last.transaction_detail)

    @requires("bri", "611319327-Welcome-to-BRI-Internet-Banking.pdf")
    def test_reni(self):
        stmt = rekapimutasi.parse_file(path("bri", "611319327-Welcome-to-BRI-Internet-Banking.pdf"))
        self.assertEqual(len(stmt.pockets[0].transactions), 49)


if __name__ == "__main__":
    unittest.main()