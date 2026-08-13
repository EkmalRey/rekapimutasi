import re

from ..errors import EmptyPDFError
from ..model import BankCode, PocketGroup, Statement, Transaction
from ..parser import Parser
from ..utils import compact_line, parse_bca_date, parse_bca_money

_DATE_RE = re.compile(r"^\d{2}/\d{2}$")
_MONEY_RE = re.compile(r"^-?\s?\d{1,3}(,\d{3})*(\.\d{2})?$")
_YEAR_RE = re.compile(r"\d{2}/\d{2}/(\d{4})")


def _extract_period(lines):
    for line in lines:
        if "Periode" in line and "/" in line:
            parts = line.split(":", 1)
            if len(parts) == 2:
                return parts[1].strip()
    return ""


def _year_from_period(period):
    m = _YEAR_RE.search(period)
    return m.group(1) if m else ""


class BSIParser(Parser):
    """Bank Syariah Indonesia statement PDFs.

    Rows carry Debit and Kredit columns; debits are printed with a leading '-':

        01/08
        TRSF E-BANKING
        1,234,567.00
        - 456,789.00
    """

    bank = BankCode.BSI

    def can_parse(self, text):
        lower = text.lower()
        return (
            "mutasi rekening" in lower
            or ("saldo riil" in lower and "no. referensi" in lower)
        )

    def parse(self, text):
        lines = [compact_line(l) for l in text.splitlines() if compact_line(l)]
        if not lines:
            raise EmptyPDFError("empty pdf text")

        period = _extract_period(lines)
        year = _year_from_period(period)
        stmt = Statement(bank=self.bank, currency="IDR", period=period)

        transactions = []
        block = []

        def flush():
            nonlocal block
            if not block:
                return
            tx = self._parse_block(block, year)
            if tx.date:
                transactions.append(tx)
            block = []

        for line in lines:
            if _DATE_RE.match(line):
                flush()
                block = [line]
                continue
            if block:
                block.append(line)
        flush()

        if transactions:
            stmt.pockets = [PocketGroup(name="Rekening", transactions=transactions)]
        return stmt

    def _parse_block(self, block, year):
        tx = Transaction(
            date=self._format_date(block[0], year),
            notes="-",
            source_destination="-",
        )
        is_debit = False
        desc_parts = []
        for line in block[1:]:
            if _MONEY_RE.match(line):
                if line.strip().startswith("-"):
                    is_debit = True
                    line = line.strip().lstrip("-").strip()
                tx.amount = parse_bca_money(line, not is_debit)
                continue
            desc_parts.append(line)

        tx.mutation_type = "DB" if is_debit else "CR"
        tx.transaction_detail = compact_line(" ".join(desc_parts))
        tx.raw = compact_line(" ".join(block))

        if not tx.transaction_detail:
            return Transaction()
        return tx

    def _format_date(self, ddmm, year):
        if not year:
            return ddmm
        return parse_bca_date(ddmm + "/" + year)
