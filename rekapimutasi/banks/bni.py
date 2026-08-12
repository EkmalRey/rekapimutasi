import re
from datetime import datetime

from ..errors import EmptyPDFError
from ..model import BankCode, Money, PocketGroup, Statement, Transaction
from ..parser import Parser
from ..utils import (
    compact_line,
    is_bca_money,
    parse_bca_money,
    parse_jago_date,
    split_lines,
)

_DATE_RE = re.compile(r"^\d{2}-[A-Za-z]{3}-\d{2,4}$")
_MARKER_RE = re.compile(r"^(Db\.|Cr\.)$")
_MONTH_NUM = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def _format_date(s):
    """'DD-Mon-YY' or 'DD-Mon-YYYY' -> 'YYYY-MM-DD'; input unchanged on failure."""
    parts = s.split("-")
    if len(parts) != 3:
        return s
    year = parts[2]
    if len(year) == 2:
        year = "20" + year
    month = _MONTH_NUM.get(parts[1])
    if month is None:
        return s
    try:
        return datetime(int(year), month, int(parts[0])).strftime("%Y-%m-%d")
    except ValueError:
        return s


class BNIParser(Parser):
    """BNI savings statement PDFs.

    BNI prints a 'Db.'/'Cr.' marker column next to the amount:

        01-Jan-21
        TRSF E-BANKING
        Db.
        1,234,567.00
    """

    bank = BankCode.BNI

    def can_parse(self, text):
        lower = text.lower()
        return "histori transaksi" in lower or "transactions list" in lower

    def parse(self, text):
        lines = [compact_line(l) for l in split_lines(text) if compact_line(l)]
        if not lines:
            raise EmptyPDFError("empty pdf text")

        stmt = Statement(bank=self.bank, currency="IDR")
        transactions = []
        block = []
        marker = ""

        def flush():
            nonlocal block, marker
            if block and marker:
                tx = self._parse_block(block, marker)
                if tx.date:
                    transactions.append(tx)
            block = []
            marker = ""

        for line in lines:
            if _DATE_RE.match(line):
                flush()
                block = [line]
                continue
            m = _MARKER_RE.match(line)
            if m:
                marker = m.group(1)[:-1].upper()
                continue
            if block:
                block.append(line)
        flush()

        if transactions:
            stmt.pockets = [PocketGroup(name="Savings", transactions=transactions)]
        return stmt

    def _parse_block(self, block, mutation_type):
        tx = Transaction(
            date=_format_date(block[0]),
            mutation_type=mutation_type,
            notes="-",
            source_destination="-",
        )
        desc_parts = []
        for line in block[1:]:
            if is_bca_money(line):
                tx.amount = parse_bca_money(line, mutation_type == "CR")
                continue
            desc_parts.append(line)
        tx.transaction_detail = compact_line(" ".join(desc_parts))
        tx.raw = compact_line(" ".join(block))

        if not tx.transaction_detail:
            return Transaction()
        return tx


# --- BNI new-format parsers ---------------------------------------------

_BNI_DATE_RE = re.compile(r"^\d{1,2} [A-Za-z]{3} \d{4}$")
_BNI_TIME_RE = re.compile(r"^(\d{2}:\d{2}:\d{2}) WIB")
_BNI_SIGNED_RE = re.compile(r"([+-][\d,]+)(?:\s+(\d[\d,]*))?")
# "Rp. 2,351,519 Rp. 1,000,000 - Rp. 1,351,519 (TELLER) (Empty)"
# the zeroed column is a bare "-" with no "Rp." prefix
_BNI_ROW_RE = re.compile(
    r"Rp\.?\s*([\d,]+)\s+(?:Rp\.?\s*)?([\d,-]+)\s+(?:Rp\.?\s*)?([\d,-]+)\s+Rp\.?\s*([\d,]+)"
)
_BNI_NAME_RE = re.compile(r"^[A-Z][A-Z .]{3,}$")


def _bni_idn_whole(s):
    s = s.replace(",", "")
    return int(s) if s.isdigit() else 0


class BNIMutasiParser(Parser):
    """BNI 'Laporan Mutasi Rekening' PDFs (the simplified Oct 2025 layout):

    Saldo Awal 0
    26 Oct 2025
    08:14:47 WIB
    Lainnya
    TRANSFER DARI +3,497,000
    ...
    -5,000 3,492,206
    Saldo Akhir 47,000
    """

    bank = BankCode.BNI

    def can_parse(self, text):
        return "Laporan Mutasi Rekening" in text and "Saldo Awal" in text

    def parse(self, text):
        lines = [compact_line(l) for l in split_lines(text) if compact_line(l)]
        if not lines:
            raise EmptyPDFError("empty pdf text")

        stmt = Statement(bank=self.bank, currency="IDR")
        for line in lines:
            if _BNI_NAME_RE.match(line):
                stmt.account_name = line
                break
        for line in lines:
            m = re.search(r"\d{10}", line)
            if m and "TAPLUS" in line.upper():
                stmt.account_no = m.group(0)
                break
        for line in lines:
            if "Periode:" in line:
                stmt.period = line.split(":", 1)[-1].strip()
                break

        transactions = []
        block = []

        def flush():
            nonlocal block
            if not block:
                return
            tx = self._parse_block(block)
            if tx.date:
                transactions.append(tx)
            block = []

        for line in lines:
            if _BNI_DATE_RE.match(line):
                flush()
                block = [line]
            elif block:
                block.append(line)
        flush()

        if transactions:
            stmt.pockets = [PocketGroup(name="Rekening", transactions=transactions)]
        return stmt

    def _parse_block(self, block):
        tx = Transaction(date=parse_jago_date(block[0]), notes="-", source_destination="-")
        desc_parts = []
        for i, line in enumerate(block[1:], 1):
            m = _BNI_TIME_RE.match(line)
            if i == 1 and m:
                tx.time = m.group(1)[:5]
                continue
            if line.startswith(("Saldo Awal", "Saldo Akhir")):
                continue
            desc_parts.append(line)

        joined = " ".join(desc_parts)
        money = None
        for m in _BNI_SIGNED_RE.finditer(joined):
            money = m
        if money is not None:
            amount_s, balance_s = money.group(1), money.group(2)
            is_credit = amount_s.startswith("+")
            amount_v = _bni_idn_whole(amount_s[1:])
            tx.amount = Money(currency="IDR", display=f"{amount_s.strip()}Rp", value=amount_v if is_credit else -amount_v)
            tx.mutation_type = "CR" if is_credit else "DB"
            if balance_s:
                tx.balance = Money(currency="IDR", display="Rp" + balance_s, value=_bni_idn_whole(balance_s))
            joined = joined[:money.start()] + " " + joined[money.end():]

        tx.transaction_detail = compact_line(joined)
        tx.raw = compact_line(" ".join(block))
        return tx


class BNITransaksiParser(Parser):
    """BNI 'Mutasi Transaksi' PDFs (government/corporate, date split over
    lines): "2022-" / "09-30", then rows:

        Rp. 2,351,519 Rp. 1,000,000 - Rp. 1,351,519 (TELLER) (Empty)
    """

    bank = BankCode.BNI

    def can_parse(self, text):
        return "Mutasi Transaksi" in text and "Saldo Akhir" in text

    def parse(self, text):
        lines = [compact_line(l) for l in split_lines(text) if compact_line(l)]
        if not lines:
            raise EmptyPDFError("empty pdf text")

        stmt = Statement(bank=self.bank, currency="IDR")
        m = re.search(r"Mutasi Transaksi \((\d{2}/\d{2}/\d{4}) - (\d{2}/\d{2}/\d{4})\)", text)
        if m:
            stmt.period = f"{m.group(1)} - {m.group(2)}"

        transactions = []
        block = []
        date = ""

        def flush():
            nonlocal date
            if not block or not date:
                block.clear()
                return
            tx = self._parse_block(block, date)
            if tx.date:
                transactions.append(tx)
            block.clear()

        i = 0
        while i < len(lines):
            line = lines[i]
            # date split over two lines: "2022-" + "09-30"
            if re.match(r"^\d{4}-$", line) and i + 1 < len(lines):
                nxt = lines[i + 1]
                if re.match(r"^\d{2}-\d{2}$", nxt):
                    flush()
                    date = f"{line[:-1]}-{nxt}"
                    i += 2
                    continue
            if re.match(r"^\d{4}-\d{2}-\d{2}$", line):
                flush()
                date = line
                i += 1
                continue
            if date:
                block.append(line)
            i += 1
        flush()

        if transactions:
            stmt.pockets = [PocketGroup(name="Rekening", transactions=transactions)]
        return stmt

    def _parse_block(self, block, date):
        tx = Transaction(date=date, notes="-", source_destination="-")
        desc_parts = []
        for line in block:
            values = _BNI_ROW_RE.search(line)
            if values:
                _, debit, kredit, akhir = (v.strip() for v in values.groups())
                closing = _bni_idn_whole(akhir)
                if debit == "-" or not debit:
                    tx.mutation_type = "CR"
                    tx.amount = Money(currency="IDR", value=_bni_idn_whole(kredit))
                else:
                    tx.mutation_type = "DB"
                    tx.amount = Money(currency="IDR", value=-_bni_idn_whole(debit))
                tx.balance = Money(currency="IDR", value=closing)
                continue
            desc_parts.append(line)
        tx.transaction_detail = compact_line(" ".join(desc_parts))
        tx.raw = compact_line(" ".join(block))
        if tx.amount.currency == "" and not tx.transaction_detail:
            return Transaction()
        return tx
