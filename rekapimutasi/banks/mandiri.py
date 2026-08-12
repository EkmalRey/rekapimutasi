import re

from ..errors import EmptyPDFError
from ..model import BankCode, PocketGroup, Statement, Transaction
from ..parser import Parser
from ..utils import (
    compact_line,
    is_bca_money,
    is_bca_money_signed,
    parse_bca_balance,
    parse_bca_date,
    parse_bca_money,
    parse_idr,
    parse_jago_date,
    split_lines,
)

_DATE_RE = re.compile(r"^\d{2}/\d{2}$")
_YEAR_RE = re.compile(r"(\d{2})/(\d{2})/(\d{2})")
_STOP_WORDS = (
    "saldo awal /",
    "mutasi kredit /",
    "mutasi debit /",
    "saldo akhir /",
    "previous balance",
    "total of credit transactions",
    "total of debit transactions",
    "current balance",
)


class MandiriParser(Parser):
    """Mandiri savings statement PDFs.

    A transaction row is date, posting-date, description, amount[ D], balance,
    with the description possibly continuing onto following lines:

        05/09
        05/09
        -MONTHLY CARD CHARGE 987654321
        5,500.00 D
        653,970.00
    """

    bank = BankCode.MANDIRI

    def can_parse(self, text):
        lower = text.lower()
        return (
            "periode /" in lower
            and "mutasi kredit" in lower
            and "rekening tahapan" not in lower
        )

    def parse(self, text):
        lines = [compact_line(l) for l in split_lines(text) if compact_line(l)]
        if not lines:
            raise EmptyPDFError("empty pdf text")

        year = self._extract_year(lines)
        stmt = Statement(bank=self.bank, currency="IDR", period=self._extract_period(lines))

        transactions = []
        block = []
        block_has_amount = False
        in_table = False
        header_seen = False

        def flush():
            nonlocal block, block_has_amount
            if not block:
                return
            tx = self._parse_block(block, year)
            if tx.date:
                transactions.append(tx)
            block = []
            block_has_amount = False

        for line in lines:
            if not in_table:
                if header_seen:
                    if line == "Balance":
                        in_table = True
                    continue
                if self._is_column_header(line):
                    header_seen = True
                continue

            if self._is_stop_word(line):
                flush()
                break

            if _DATE_RE.match(line):
                if block_has_amount:
                    flush()
                block.append(line)
            else:
                block.append(line)
                if is_bca_money_signed(line):
                    block_has_amount = True
        flush()

        if transactions:
            stmt.pockets = [PocketGroup(name="Savings", transactions=transactions)]
        return stmt

    def _is_column_header(self, line):
        lower = line.lower()
        return any(
            k in lower
            for k in (
                "transaction date",
                "reference number",
                "debit / credit",
                "debit / kredit",
            )
        ) or ("saldo" in lower and "balance" in lower)

    def _is_stop_word(self, line):
        lower = line.lower()
        return any(k in lower for k in _STOP_WORDS)

    def _parse_block(self, block, year):
        tx = Transaction(
            date=self._format_date(block[0], year),
            notes="-",
            source_destination="-",
        )

        amount_str = ""
        is_debit = False
        balance_str = ""
        desc_parts = []

        for line in block[1:]:
            if line.endswith(" D") and is_bca_money(line[:-2].strip()):
                amount_str = line[:-2].strip()
                is_debit = True
            elif is_bca_money(line):
                if amount_str == "":
                    amount_str = line
                else:
                    balance_str = line
            elif _DATE_RE.match(line):
                # posting date
                continue
            else:
                desc_parts.append(line)

        mutation_type = "DB" if is_debit else "CR"
        tx.mutation_type = mutation_type
        tx.transaction_detail = compact_line(" ".join(desc_parts))
        tx.raw = compact_line(" ".join(block))

        if tx.transaction_detail == "" or tx.transaction_detail.lower() == "saldo awal":
            return Transaction()

        if amount_str:
            tx.amount = parse_bca_money(amount_str, mutation_type == "CR")
        if balance_str:
            tx.balance = parse_bca_balance(balance_str)
        return tx

    def _extract_year(self, lines):
        for i, line in enumerate(lines):
            if "periode /" in line.lower():
                for nxt in lines[i + 1:]:
                    m = _YEAR_RE.search(nxt)
                    if m:
                        return "20" + m.group(3)
        return ""

    def _extract_period(self, lines):
        for i, line in enumerate(lines):
            if "periode /" in line.lower():
                for nxt in lines[i + 1:]:
                    if "s/d" in nxt:
                        return compact_line(nxt)
        return ""

    def _format_date(self, ddmm, year):
        if not year:
            return ddmm
        return parse_bca_date(ddmm + "/" + year)


# --- Mandiri e-Statement -------------------------------------------------
#
#   e-Statement
#   Nama/Name ... :ANDY PANGERAN
#   Periode/Period : 01 Sep 2024 - 30 Sep 2024
#   Date
#   02 Sep 2024
#   Pembayaran Telkomsel Postpaid
#   08111929636 14.249.465,013 -350.760,0022:34:49 WIB
#
# Each transaction ends with a row that glues running balance, a sequence
# number, a signed amount and the time: "BALANCE<seq> AMOUNT HH:MM:SS WIB".

_ESTMT_DATE_RE = re.compile(r"^\d{1,2} [A-Za-z]{3} \d{4}$")
_ESTMT_ROW_RE = re.compile(
    r"(\d{1,3}(?:\.\d{3})*,\d{2})\d*\s+([+-]\d{1,3}(?:\.\d{3})*,\d{2})\s*(\d{2}:\d{2}:\d{2} WIB)"
)
_ESTMT_NAME_RE = re.compile(r"^:\s*([A-Z][A-Z .]{3,})$")
_ESTMT_ACCT_RE = re.compile(r"\d{10,16}")
_ESTMT_PERIOD_RE = re.compile(r"\d{1,2} [A-Za-z]{3} \d{4} - \d{1,2} [A-Za-z]{3} \d{4}")


class MandiriEStatementParser(Parser):
    """Mandiri 'e-Statement' PDFs (the two-column Date/Amount layout)."""

    bank = BankCode.MANDIRI

    def can_parse(self, text):
        return "e-Statement" in text and "Nama/Name" in text

    def parse(self, text):
        lines = [compact_line(l) for l in split_lines(text) if compact_line(l)]
        if not lines:
            raise EmptyPDFError("empty pdf text")

        stmt = Statement(bank=self.bank, currency="IDR")
        for line in lines:
            m = _ESTMT_NAME_RE.match(line)
            if m:
                stmt.account_name = m.group(1)
                break
        for line in lines:
            if "Nomor Rekening" in line or "Account Number" in line:
                n = _ESTMT_ACCT_RE.search(line)
                if n:
                    stmt.account_no = n.group(0)
                    break
        if not stmt.account_no:
            for line in lines:
                m = _ESTMT_ACCT_RE.search(line.rstrip(":"))
                if m and line.strip().rstrip(":").endswith(m.group(0)):
                    stmt.account_no = m.group(0)
                    break
        mp = _ESTMT_PERIOD_RE.search(text)
        if mp:
            stmt.period = mp.group(0)

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
            if _ESTMT_DATE_RE.match(line):
                flush()
                block = [line]
            elif block:
                block.append(line)
        flush()

        if transactions:
            stmt.pockets = [PocketGroup(name="Savings", transactions=transactions)]
        return stmt

    def _parse_block(self, block):
        tx = Transaction(
            date=parse_jago_date(block[0]),
            notes="-",
            source_destination="-",
        )
        desc_parts = []
        for line in block[1:]:
            m = _ESTMT_ROW_RE.search(line)
            if m:
                tx.balance = parse_idr(m.group(1))
                tx.amount = parse_idr(m.group(2))
                tx.mutation_type = "CR" if tx.amount.value >= 0 else "DB"
                tx.time = m.group(3)[:5]
                continue
            desc_parts.append(line)

        tx.transaction_detail = compact_line(" ".join(desc_parts))
        tx.raw = compact_line(" ".join(block))
        return tx


# --- Mandiri Rekening Koran family ---------------------------------------
# "Laporan Rekening Koran (Account Statement Report)" and
# "Rekening Koran (Account Statement)". Rows carry three BCA-style amounts
# (debit, credit, balance):
#
#   - 0.00 200,000,000.00 201,363,630.49          (separate money row)
#   609,800.00 0.00 335,148,829.7401/09/2019      (glued to value date)
#   09/06/2019 09/06/2019 50,000,000.00 0.00 278,553,757.37   (inline row)

_KORAN_DATE_RE = re.compile(r"^(\d{2}/\d{2}/\d{4})")
_KORAN_MONEY_RE = re.compile(r"\d{1,3}(?:,\d{3})*\.\d{2}")


class MandiriKoranParser(Parser):
    bank = BankCode.MANDIRI

    def can_parse(self, text):
        return (
            "Account Statement" in text
            and "Opening Balance" in text
            and "e-Statement" not in text
        )

    def parse(self, text):
        lines = [compact_line(l) for l in split_lines(text) if compact_line(l)]
        if not lines:
            raise EmptyPDFError("empty pdf text")

        stmt = Statement(bank=self.bank, currency="IDR")
        stmt.period = self._extract_period(lines)
        stmt.account_no = self._extract_account_no(lines)

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
            if _KORAN_DATE_RE.match(line):
                flush()
                block = [line]
            elif block:
                block.append(line)
        flush()

        if transactions:
            stmt.pockets = [PocketGroup(name="Savings", transactions=transactions)]
        return stmt

    def _parse_block(self, block):
        first = block[0]
        date = _KORAN_DATE_RE.match(first).group(1)
        rest = first[len(date):].strip()

        money_line = None
        for line in block:
            if len(_KORAN_MONEY_RE.findall(line)) >= 3:
                money_line = line
                break

        tx = Transaction(date=parse_bca_date(date), notes="-", source_destination="-")
        desc_lines = [rest] if rest else []
        for line in block[1:]:
            if line is money_line:
                continue
            desc_lines.append(line)
        tx.transaction_detail = compact_line(" ".join(desc_lines))
        tx.raw = compact_line(" ".join(block))

        if money_line is None:
            return tx if rest else Transaction()

        values = _KORAN_MONEY_RE.findall(money_line)[:3]
        debit = parse_bca_balance(values[0]).value
        credit = parse_bca_balance(values[1]).value

        if debit > 0:
            tx.mutation_type = "DB"
            tx.amount = parse_bca_money(values[0], False)
        elif credit > 0:
            tx.mutation_type = "CR"
            tx.amount = parse_bca_money(values[1], True)
        else:
            tx.mutation_type = "CR"
            tx.amount = parse_bca_money("0.00", True)
        tx.balance = parse_bca_balance(values[2])
        return tx

    def _extract_period(self, lines):
        date_re = re.compile(r"\d{1,2} [A-Za-z]+ \d{4}")
        for i, line in enumerate(lines):
            if "Perio" not in line and not line.startswith(("From", "To")):
                continue
            dates = []
            for nxt in lines[max(0, i - 1):i + 8]:
                m = date_re.search(nxt)
                if m and m.group(0) not in dates:
                    dates.append(m.group(0))
            if len(dates) >= 2:
                return f"{dates[0]} - {dates[1]}"
            if dates:
                return dates[0]
        return ""

    def _extract_account_no(self, lines):
        for i, line in enumerate(lines):
            if "Account No" not in line:
                continue
            for nxt in lines[i:i + 5]:
                m = _ESTMT_ACCT_RE.search(nxt)
                if m:
                    return m.group(0)
        return ""
