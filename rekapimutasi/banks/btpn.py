import re

from ..errors import EmptyPDFError
from ..model import BankCode, Money, PocketGroup, Statement, Transaction
from ..parser import Parser
from ..utils import compact_line, parse_jago_date, split_lines

_DATE_RE = re.compile(r"^\d{1,2} [A-Za-z]{3} \d{4}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")
# "+20,000" (older Jenius), "+ 50,000", or "+110.703.716" (dot thousands):
# optional space after the sign, digits with , or . separators
_AMOUNT_RE = re.compile(r"^[+-] ?[\d.,]+$")


def _idn_whole(s):
    """'20,000' or '110.703.716' -> 20000 / 110703716 (whole rupiah;
    Jenius statements never carry cents)."""
    s = s.replace(".", "").replace(",", "")
    return int(s) if s.isdigit() else 0


class BTPNParser(Parser):
    """BTPN Jenius statement PDFs.

    Rows carry a '+ ' (credit) or '- ' (debit) amount:

        18 Nov 2019
        12:11
        LAUKHIM MAHFUD
        BANK MANDIRI
        +20,000
    """

    bank = BankCode.BTPN

    def can_parse(self, text):
        lower = text.lower()
        return "jenius" in lower or "btpn" in lower

    def parse(self, text):
        lines = [compact_line(l) for l in split_lines(text) if compact_line(l)]
        if not lines:
            raise EmptyPDFError("empty pdf text")

        stmt = Statement(bank=self.bank, currency="IDR")
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
            if _DATE_RE.match(line):
                flush()
                block = [line]
                continue
            if block:
                block.append(line)
        flush()

        if transactions:
            stmt.pockets = [PocketGroup(name="Jenius", transactions=transactions)]
        return stmt

    def _parse_block(self, block):
        tx = Transaction(
            date=parse_jago_date(block[0]),
            notes="-",
            source_destination="-",
        )
        desc_parts = []
        for i, line in enumerate(block[1:], 1):
            if i == 1 and _TIME_RE.match(line):
                tx.time = line
                continue
            if _AMOUNT_RE.match(line):
                is_credit = line.startswith("+")
                ival = _idn_whole(line[1:].strip())
                if not is_credit:
                    ival = -ival
                tx.amount = Money(currency="IDR", display=f"{'+' if is_credit else '-'}Rp{line[1:].strip()}", value=ival)
                tx.mutation_type = "CR" if is_credit else "DB"
                continue
            desc_parts.append(line)

        tx.transaction_detail = compact_line(" ".join(desc_parts))
        tx.raw = compact_line(" ".join(block))

        if not tx.transaction_detail:
            return Transaction()
        return tx
