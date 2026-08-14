import re

from ..errors import EmptyPDFError
from ..model import BankCode, PocketGroup, Statement, Transaction
from ..parser import Parser
from ..utils import compact_line, parse_bca_date, parse_idr

# DD/MM/YY alone ("01/03/21") or glued to the description
# ("01/05/21IBNK ASOSIASI ASURA TO WINDA")
_DATE_START_RE = re.compile(r"^(\d{2}/\d{2}/\d{2})")
# an Indonesian amount row: "25.000,00" and "585.642,40" may be glued
# ("25.000,00585.642,40") or spaced ("50.000,00 590.642,40")
_MONEY_RE = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}")
_COLUMN_HEADER_RE = re.compile(r"^\s*(?:tanggal\b|debet\s+kredit\s+Saldo)", re.IGNORECASE)
# The statement summary ("Total Mutasi" / "Saldo Akhir") and the footer note
# ("Catatan : ...") end the table; every line after the last transaction row
# belongs to one of these blocks.
_SUMMARY_START_RE = re.compile(r"^\s*Total Mutasi\b", re.IGNORECASE)
_FOOTER_RE = re.compile(r"^\s*Catatan\s*:", re.IGNORECASE)
_BALANCE_TOL = 20


class BRIParser(Parser):
    """BRI 'Rincian Rekening Koran' statements.

    A transaction block starts at a DD/MM/YY line (the date is sometimes glued
    onto the first description line) and runs to the next date. The last line
    carries amount + running balance; the sign is resolved from the balance
    direction because the statement prints no DB/CR marker.
    """

    bank = BankCode.BRI

    def can_parse(self, text):
        return "Rincian Rekening Koran" in text and "Yth." in text

    def parse(self, text):
        lines = [compact_line(l) for l in text.splitlines() if compact_line(l)]
        if not lines:
            raise EmptyPDFError("empty pdf text")

        stmt = Statement(bank=self.bank, currency="IDR")
        stmt.account_name = self._extract_after(lines, "Yth. Bapak/Ibu") or self._extract_after(lines, "Yth. Ibu")
        stmt.account_no = self._extract_after(lines, "No. Rekening")
        stmt.period = self._extract_after(lines, "Periode")
        year = self._period_year(stmt.period)
        opening = None
        for line in lines:
            if line.startswith("Saldo Awal"):
                opening = parse_idr(line.split(None, 2)[-1]).value
                break

        transactions = []
        prev_balance = opening
        block = []
        in_table = False
        gap = False

        def flush():
            nonlocal prev_balance
            if not block:
                return
            tx = self._parse_block(block, year, prev_balance)
            if tx.balance.currency:
                prev_balance = tx.balance.value
            if tx.date:
                transactions.append(tx)
            block.clear()
        for line in lines:
            # Summary and footer blocks end the table: everything after the
            # last transaction row ("Total Mutasi" / "Saldo Akhir" / "Catatan")
            # must not leak into the final block.
            if in_table and (_SUMMARY_START_RE.match(line) or _FOOTER_RE.match(line)):
                break

            if not in_table:
                if _DATE_START_RE.match(line):
                    in_table = True
                else:
                    continue

            if _COLUMN_HEADER_RE.match(line):
                gap = True
                continue

            if gap:
                if _DATE_START_RE.match(line):
                    gap = False
                else:
                    continue

            if _DATE_START_RE.match(line):
                flush()
                block = [line]
            elif block:
                block.append(line)
        flush()

        if transactions:
            stmt.pockets = [PocketGroup(name="Rekening Koran", transactions=transactions)]
        return stmt

    def _parse_block(self, block, year, prev_balance):
        first = block[0]
        date = _DATE_START_RE.match(first).group(1)  # DD/MM/YY
        yyyy = year or ("20" + date[6:8])
        rest = first[len(date):].strip()

        tx = Transaction(date=parse_bca_date(date[:5] + "/" + yyyy), notes="-", source_destination="-")

        desc_lines = [rest] if rest else []
        amounts = []
        for line in block[1:]:
            found = _MONEY_RE.findall(line)
            if len(found) >= 2:
                amounts = found[-2:]
                continue
            if len(found) == 1 and not line.startswith("Saldo Awal") and _MONEY_RE.fullmatch(line):
                # bare amount with no balance; keep as the row only if it is
                # the whole line (a description fragment would be shorter)
                amounts = found
                continue
            desc_lines.append(line)

        description = compact_line(" ".join(desc_lines))

        if not amounts:
            return Transaction()

        amount_money = parse_idr(amounts[0])
        balance = parse_idr(amounts[-1]) if len(amounts) == 2 else None
        amount = amount_money.value

        mutation = "CR"
        if balance is not None and prev_balance is not None:
            delta = balance.value - prev_balance
            if abs(delta + amount) <= _BALANCE_TOL:
                mutation = "DB"
            elif abs(delta - amount) <= _BALANCE_TOL:
                mutation = "CR"
        if mutation == "DB":
            amount_money.value = -amount

        tx.mutation_type = mutation
        tx.transaction_detail = description
        tx.raw = compact_line(" ".join(block))
        tx.amount = amount_money
        if balance is not None:
            tx.balance = balance
        return tx

    def _extract_after(self, lines, prefix):
        for line in lines:
            if line.startswith(prefix):
                return line[len(prefix):].strip()
        return ""

    def _period_year(self, period):
        m = re.search(r"\d{4}", period or "")
        return m.group(0) if m else ""
