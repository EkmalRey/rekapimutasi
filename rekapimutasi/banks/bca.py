import csv
import re

from ..errors import EmptyPDFError
from ..model import BankCode, PocketGroup, Statement, Transaction
from ..parser import Parser
from ..utils import (
    compact_line,
    parse_bca_balance,
    parse_bca_date,
    parse_bca_money,
    split_lines,
)

# --- shared CSV helpers -------------------------------------------------


def _extract_meta_value(line):
    parts = line.split(",=,", 1)
    return parts[1].strip() if len(parts) == 2 else ""


def _clean_quote(value):
    value = value.strip()
    return value.removeprefix("'")


def _format_bca_date(value):
    return parse_bca_date(_clean_quote(value))


def _parse_personal_row(line):
    fields = next(csv.reader([line]))
    if len(fields) < 6:
        return Transaction()
    balance = fields[-1].strip()
    crdb = fields[-2].strip()
    amount = fields[-3].strip()
    date = _clean_quote(fields[0])

    description = compact_line(",".join(fields[1:-4]))
    is_credit = crdb.upper() == "CR"
    mutation = "CR" if is_credit else "DB"

    return Transaction(
        date=_format_bca_date(date),
        source_destination="-",
        transaction_detail=description,
        mutation_type=mutation,
        notes="-",
        amount=parse_bca_money(amount, is_credit),
        balance=parse_bca_balance(balance),
        raw=line,
    )


def _parse_bisnis_row(line):
    fields = next(csv.reader([line]))
    if len(fields) < 5:
        return Transaction()
    date = fields[0]
    description = compact_line(fields[1])
    amount = fields[3]
    balance = fields[4]

    mutation = "CR" if amount.strip().endswith("CR") else "DB"
    return Transaction(
        date=_format_bca_date(date),
        source_destination="-",
        transaction_detail=description,
        mutation_type=mutation,
        notes="-",
        amount=parse_bca_money(amount, mutation == "CR"),
        balance=parse_bca_balance(balance),
        raw=line,
    )


class PersonalParser(Parser):
    """KlikBCA Individual e-statement CSVs ('Account No.,=,', row CR/DB column)."""

    bank = BankCode.BCA

    def can_parse(self, text):
        return "Account No.,=," in text and "Starting Balance" in text

    def parse(self, text):
        statement = Statement(bank=self.bank, currency="IDR")
        transactions = []
        in_data = False

        for raw in split_lines(text):
            line = raw.strip()
            if not line:
                continue

            if line.startswith("Account No.,=,"):
                statement.account_no = _clean_quote(_extract_meta_value(line))
                continue
            if line.startswith("Name,=,"):
                statement.account_name = _extract_meta_value(line)
                continue
            if line.startswith("Date,Description,"):
                in_data = True
                continue
            if line.startswith(("Starting Balance", "Credit,", "Debet,", "Ending Balance")):
                in_data = False
                continue
            if not in_data:
                continue

            tx = _parse_personal_row(line)
            if tx.date:
                transactions.append(tx)

        if transactions:
            statement.pockets = [PocketGroup(name="Personal", transactions=transactions)]
        return statement


class BisnisParser(Parser):
    """BCA Bisnis (corporate) e-statement CSVs, fully quoted fields."""

    bank = BankCode.BCA_BISNIS

    def can_parse(self, text):
        return "No. rekening :" in text and (
            "Saldo Awal" in text or "Tanggal Transaksi" in text
        )

    def parse(self, text):
        statement = Statement(bank=self.bank, currency="IDR")
        transactions = []
        in_data = False

        for raw in split_lines(text):
            line = raw.strip()
            if not line:
                continue

            unquoted = line.strip('"')
            if unquoted.startswith("No. rekening :"):
                statement.account_no = unquoted[len("No. rekening :"):].strip()
                continue
            if unquoted.startswith("Nama :"):
                statement.account_name = unquoted[len("Nama :"):].strip()
                continue
            if unquoted.startswith("Periode :"):
                statement.period = unquoted[len("Periode :"):].strip()
                continue
            if unquoted.startswith(("Informasi Rekening", "Kode Mata Uang")):
                continue
            if "Tanggal Transaksi" in line:
                in_data = True
                continue
            if unquoted.startswith(("Saldo Awal", "Mutasi Debet", "Mutasi Kredit", "Saldo Akhir")):
                in_data = False
                continue
            if not in_data:
                continue

            tx = _parse_bisnis_row(line)
            if tx.date:
                transactions.append(tx)

        if transactions:
            statement.pockets = [PocketGroup(name="Business", transactions=transactions)]
        return statement


# --- BCA PDF parser -----------------------------------------------------
#
# BCA e-statements ship in many near-identical layouts that pypdf renders
# slightly differently. Across all observed variants a transaction is:
#
#   DD/MM <description> <amount> [DB|CR] [running balance]
#
# where the cells may be separate lines, one inline row, or even glued to the
# date line ("06/07 BIAYA ADM 0998 10,000.00 DB 2,003,917.13"). The only
# reliable money pattern is "amount [marker] [balance]" matching the regular
# expression below. Page breaks are announced either by an explicit
# "Bersambung ke halaman berikut" line or by a repeated account header
# ("NO. REKENING ..."). Parsing stops at the first summary line.

_HEADER_RE = re.compile(r"^\s*TANGGAL\s+KETERANGAN\s+CBG\s+MUTASI\s+SALDO\s*$")
_DATE_START_RE = re.compile(r"^(\d{2}/\d{2})(?:\s|$)")
# amount [DB|CR] [balance]: "23,000.00 DB 535,419.13", "100,000.00 135,794.13",
# "85,000.00", "0998 10,000.00 DB 525,419.13" (leading CBG branch code)
_MONEY_LINE_RE = re.compile(
    r"^(?:\d{3,4}\s+)?(\d{1,3}(?:,\d{3})*\.\d{2})\s*(DB|CR)?(?:\s+(\d{1,3}(?:,\d{3})*\.\d{2}))?\s*$"
)
# inline amount within a row: "06/07 ... 25,000.00 DB", or the row cells run
# together "300,000.00 3,016,333.59". Marker optional, so the third group is
# only a balance when the row actually carries one.
_MONEY_EMBED_RE = re.compile(
    r"(\d{1,3}(?:,\d{3})*\.\d{2})\s*(DB|CR)?\s*(\d{1,3}(?:,\d{3})*\.\d{2})?"
)
# duplicate amount without thousands separators in the description area, e.g.
# "85000.00"; dropped to keep TransactionDetail clean.
_DUP_AMT_RE = re.compile(r"^\d{4,}\.\d{2}$")
_YEAR_RE = re.compile(r"\d{4}")

_SUMMARY_PREFIXES = ("SALDO AWAL", "MUTASI CR", "MUTASI DB", "SALDO AKHIR")
_MONTH_NAMES = (
    "JANUARI", "FEBRUARI", "MARET", "APRIL", "MEI", "JUNI",
    "JULI", "AGUSTUS", "SEPTEMBER", "OKTOBER", "NOVEMBER", "DESEMBER",
    "JANUARY", "FEBRUARY", "MARCH", "MAY", "JUNE", "JULY",
    "AUGUST", "SEPT", "OCT", "OCTOBER", "NOV", "DEC",
)
# a repeated account header marks a page break in statements that never print
# "Bersambung ke halaman berikut" (e.g. the "KCU KUBU RAYA" variant).
_PAGE_HEADER_PREFIXES = ("NO. REKENING", "HALAMAN", "PERIODE", "MATA UANG", "CATATAN")
_BRANCH_PREFIXES = ("KCP", "KCU")

# running balances are cent-truncated, so adjacent amounts may disagree with
# the balance direction by a few rupiah.
_BALANCE_TOL = 20


class PDFParser(Parser):
    """BCA Personal (Rekening Tahapan) e-statement PDFs.

    The transaction sign is resolved from arithmetic first: when the running
    balance matches ``prev ± amount`` that decides credit/debit, which fixes
    statements that print a misleading "DB" marker on every row. Otherwise the
    explicit marker, then a DB/CR/DEBIT/KREDIT token in the description, are
    used, defaulting to credit for deposit rows.
    """

    bank = BankCode.BCA

    def can_parse(self, text):
        # "REKENING TAHAPAN" may be split across lines ("REKENING" /
        # "TAHAPANKCP CIREBON"), so the column banner is the reliable marker.
        return (
            ("TANGGAL KETERANGAN" in text or "REKENING TAHAPAN" in text)
            and "MUTASI" in text
            and "Account No.,=," not in text
        )

    def parse(self, text):
        lines = [compact_line(l) for l in split_lines(text) if compact_line(l)]
        if not lines:
            raise EmptyPDFError("empty pdf text")

        stmt = Statement(
            bank=self.bank,
            currency="IDR",
            account_name=self._extract_account_name(lines),
            account_no=self._extract_after_colon(lines, "NO. REKENING"),
            period=self._extract_after_colon(lines, "PERIODE"),
        )
        year = _YEAR_RE.search(stmt.period).group(0) if _YEAR_RE.search(stmt.period) else ""

        transactions = []
        prev_balance = None
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
            if not in_table:
                if _HEADER_RE.match(line) or _DATE_START_RE.match(line):
                    in_table = True
                else:
                    continue
                # fall through: the line that opened the table is processed

            if line.startswith(_SUMMARY_PREFIXES):
                # end of a month/period block; keep going so concatenated
                # multi-month statements are all captured.
                flush()
                gap = True
                continue

            if line == "Bersambung ke halaman berikut" or line.startswith(_PAGE_HEADER_PREFIXES):
                gap = True
            if line.startswith("MATA UANG") and ":" in line and "IDR" not in line.split(":", 1)[1].upper():
                # a foreign-currency (e.g. "Poket Valas" CNY) sub-statement:
                # never mix it into the IDR statement. A bare "MATA UANG" key
                # line (value on a separate line) is not a currency change.
                flush()
                break

            if gap:
                # skip the repeated header / summary block; the open block
                # (if any) is kept and flushed by the next date line.
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
            stmt.pockets = [PocketGroup(name="Personal", transactions=transactions)]
        return stmt

    def _parse_block(self, block, year, prev_balance):
        first = block[0]
        date = _DATE_START_RE.match(first).group(1)
        rest = first[len(date):].strip()

        tx = Transaction(date=parse_bca_date(date + "/" + year), notes="-", source_destination="-")

        amount_line = None
        for line in block:
            mm = _MONEY_LINE_RE.match(line)
            if mm:
                amount_line = mm
                break
        if amount_line is None:
            # amount embedded in a row (pypdf keeps the cells together, e.g.
            # "06/07 ... 25,000.00 DB"). The date row is tried first because
            # it carries the real amount; later lines may hold noise like
            # "0000.00CW Coffee" whose bare "00.00" would otherwise win.
            for line in [first] + block[1:]:
                if _DUP_AMT_RE.match(line):
                    continue
                matches = list(_MONEY_EMBED_RE.finditer(line))
                if matches:
                    amount_line = matches[-1]
                    break

        desc_lines = [rest] if rest else []
        for line in block[1:]:
            if _DUP_AMT_RE.match(line):
                continue
            if amount_line is not None and _MONEY_LINE_RE.match(line):
                continue
            cleaned = _MONEY_EMBED_RE.sub("", line)
            if cleaned.strip():
                desc_lines.append(cleaned.strip())

        description = compact_line(" ".join(desc_lines))

        if description.startswith("SALDO AWAL"):
            # opening balance row: seed the running balance, emit no transaction
            if amount_line is not None:
                tx.balance = parse_bca_balance(amount_line.group(1))
                tx.date = ""
            return tx

        if amount_line is None:
            # no amount anywhere in the block: it is not a real transaction
            # (e.g. a stray "11/10" date fragment between two rows).
            return Transaction()

        marker = amount_line.group(2) or ""
        raw_amount = parse_bca_balance(amount_line.group(1)).value
        balance = parse_bca_balance(amount_line.group(3)) if amount_line.group(3) else None
        mutation = self._resolve_sign(raw_amount, marker, balance, prev_balance, description)

        tx.mutation_type = mutation
        tx.transaction_detail = description
        tx.raw = compact_line(" ".join(block))
        tx.amount = parse_bca_money(amount_line.group(1), mutation == "CR")
        if balance is not None:
            tx.balance = balance
        return tx

    def _resolve_sign(self, amount, marker, balance, prev_balance, description):
        if balance is not None and prev_balance is not None:
            delta = balance.value - prev_balance
            if abs(delta - amount) <= _BALANCE_TOL:
                return "CR"
            if abs(delta + amount) <= _BALANCE_TOL:
                return "DB"
        words = set(re.findall(r"[A-Za-z]{2,}", description.upper()))
        if "BUNGA" in words:
            # interest is credited, tax on interest is debited
            return "DB" if "PAJAK" in words else "CR"
        if "DB" in words or "DEBIT" in words:
            return "DB"
        if "CR" in words or "KREDIT" in words:
            return "CR"
        if marker:
            return marker
        return "CR"

    def _extract_account_name(self, lines):
        for i, line in enumerate(lines):
            if not line.startswith("REKENING TAHAPAN"):
                continue
            for nxt in lines[i + 1:]:
                if not nxt:
                    continue
                if nxt.replace(" ", "").startswith(_BRANCH_PREFIXES):
                    continue
                if _DATE_START_RE.match(nxt) or nxt.startswith(("SALDO", "MUTASI")):
                    # no customer name is printed on this statement
                    return ""
                return nxt
        return ""

    def _extract_after_colon(self, lines, key):
        valid = {
            "NO. REKENING": lambda v: bool(re.fullmatch(r"\d{7,13}", v)),
            "PERIODE": lambda v: any(m in v.upper() for m in _MONTH_NAMES) or "-" in v or "s/d" in v,
            "MATA UANG": lambda v: bool(re.fullmatch(r"[A-Z]{3}", v)),
        }
        idx = None
        for i, line in enumerate(lines):
            if not line.startswith(key):
                continue
            value = line.split(":", 1)
            if len(value) == 2 and value[1].strip():
                return value[1].strip()
            if idx is None:
                idx = i
        if idx is None:
            return ""
        # Some statements print "KEY" far from its ": value" line, so fall
        # back to the nearest ":" value line that looks like what the key
        # wants (digit account no, month-named period, 3-letter currency).
        check = valid.get(key, lambda v: True)
        best, best_d = "", len(lines)
        for j, line in enumerate(lines):
            if line.startswith(":") and line.strip(": ") and check(line.split(":", 1)[1].strip()):
                d = abs(j - idx)
                if d < best_d:
                    best_d, best = d, line.split(":", 1)[1].strip()
        return best
