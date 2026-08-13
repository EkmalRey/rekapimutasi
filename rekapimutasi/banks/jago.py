import re

from ..errors import EmptyPDFError, InvalidFormatError
from ..model import BankCode, PocketGroup, Statement, Transaction
from ..parser import Parser
from ..utils import _MONTH_NAMES, compact_line, parse_idr, parse_jago_date

_SKIP_CONTAINS = [
    # English
    "Monthly Statements",
    "PT Bank Jago Tbk",
    "licensed and supervised",
    "Financial Services Authority",
    "Bank Indonesia",
    "Indonesia Deposit Insurance",
    "www.jago.com",
    "Date & Time",
    "Source/Destination",
    "Transaction Details",
    "Notes",
    "Amount",
    "Balance",
    "Currency In IDR",
    "Currency In EUR",
    "Rates against the Indonesian IDR",
    "BALANCE SUMMARY",
    "Total Personal Balance",
    "Total Shared Balance",
    "Ending balance",
    "HIGHLIGHTS",
    "MONEY IN",
    "MONEY OUT",
    "PERSONAL POCKETS",
    "SHARED POCKETS",
    "Pocket Name",
    "Currency",
    "From last month",
    "Page ",
    "Showing IDR transaction from",
    # Indonesian
    "Laporan Keuangan Bulanan",
    "Halaman",
    "RINGKASAN SALDO",
    "SOROTAN",
    "UANG MASUK",
    "UANG KELUAR",
    "KANTONG PERSONAL",
    "KANTONG BERSAMA",
    "Nama Kantong",
    "Saldo Sebelumnya",
    "Total Pemasukan",
    "Total Pengeluaran",
    "Saldo Akhir",
    "Saldo akhir pada",
    "Dibanding bulan kemarin",
    "Tanggal & Waktu",
    "Sumber/Tujuan",
    "Rincian Transaksi",
    "Catatan",
    "Jumlah",
    # "ID Kantong" must stay: is_pocket_header_at reads the line after the
    # pocket name to detect pocket sections.
    "Akun Aktif, mulai",
    "Mata Uang Dalam IDR",
    "Total Saldo Personal",
    "Total Saldo Bersama",
]
_REMOVE_NOISE_EXACT = {
    "Pocket ID",
    "Pocket is created on",
    "Previous Balance",
    "Total Incoming",
    "Total Outgoing",
    "Closing Balance",
}
_INTEREST_LIKE = {"Interest", "Tax on Interest"}


class JagoParser(Parser):
    bank = BankCode.JAGO

    def __init__(self):
        self.date_re = re.compile(r"^\d{1,2} [A-Za-z]{3} \d{4}$")
        self.time_re = re.compile(r"^\d{2}[:.]\d{2}$")
        self.id_re = re.compile(r"ID#\s*([A-Za-z0-9\-]+)")
        self.money_re = re.compile(r"^[+-]?\d{1,3}(\.\d{3})*(,\d{1,2})?$")
        self.account_re = re.compile(
            r"(?i)(jago|mandiri|bca|bni|bri|cimb|permata|danamon|ocbc|seabank|blu|line bank|bank|wallet|\d{6,})"
        )
        self.account_id_re = re.compile(r"^(.+)\s*/\s*(\d+)$")
        self.month_year_re = re.compile(r"^[A-Za-z]+ \d{4}$")
        self.period_dash_re = re.compile(r"\d{4}.*\-.*\d{4}")
        self.period_year_re = re.compile(r"\d{4}")

    def can_parse(self, text):
        lower = text.lower()
        return (
            "pt bank jago tbk" in lower
            or "www.jago.com" in lower
            or "main pocket" in lower
        )

    def parse(self, text):
        lines = self._normalize_lines(text)
        if not lines:
            raise EmptyPDFError("empty pdf text")

        start = self._find_transaction_start(lines)
        if start == -1:
            raise InvalidFormatError("invalid statement format")

        statement = Statement(bank=self.bank, currency="IDR")
        is_history, global_pocket = self._extract_metadata(lines[:start], statement)
        if not statement.account_no:
            self._extract_account_from(lines, statement)
        lines = lines[start:]

        current_pocket = global_pocket if is_history else ""
        groups = {}
        ordered = []

        i = 0
        while i < len(lines):
            line = lines[i]
            if not is_history and self._is_pocket_header_at(lines, i):
                current_pocket = line
                i += 1
                continue

            if not self.date_re.match(line):
                i += 1
                continue

            # A transaction date is always followed by a time line; this skips
            # non-transaction dates such as the pocket activation date and the
            # summary highlights.
            if i + 1 >= len(lines) or not self.time_re.match(lines[i + 1]):
                i += 1
                continue

            if current_pocket == "":
                # monthly statements that never print a "… / ID Kantong"
                # pocket header (the first pocket's header is missing from the
                # extraction) fall back to a generic main pocket.
                current_pocket = "Main Pocket"

            tx, next_i = self._parse_transaction_block(lines, i, current_pocket)
            if tx.date and tx.time and tx.transaction_detail:
                if current_pocket not in groups:
                    groups[current_pocket] = PocketGroup(name=current_pocket)
                    ordered.append(current_pocket)
                groups[current_pocket].transactions.append(tx)
            i = next_i

        statement.pockets = [groups[name] for name in ordered]
        return statement

    # -- helpers ---------------------------------------------------------

    def _extract_metadata(self, header_lines, stmt):
        is_history = False
        global_pocket = ""
        for i, line in enumerate(header_lines):
            if "Pockets Transactions" in line or "History" in line:
                is_history = True

            match = self.account_id_re.match(line)
            if match:
                if is_history:
                    global_pocket = match.group(1).strip()
                    if i > 0:
                        stmt.account_name = header_lines[i - 1]
                else:
                    stmt.account_name = match.group(1).strip()
                    stmt.account_no = match.group(2).strip()
                continue

            if self._looks_like_period(line):
                stmt.period = line

        if is_history and global_pocket == "":
            global_pocket = "Unknown Pocket"
        return is_history, global_pocket

    def _looks_like_period(self, line):
        if "-" in line and self.period_dash_re.search(line):
            return True
        for m in _MONTH_NAMES:
            if m in line.lower() and self.period_year_re.search(line):
                return True
        return False

    def _parse_transaction_block(self, lines, date_index, pocket):
        tx = Transaction(date=parse_jago_date(lines[date_index]), notes="-")
        i = date_index + 1
        if i < len(lines) and self.time_re.match(lines[i]):
            tx.time = lines[i]
            i += 1

        block = []
        seen_money = False
        while i < len(lines):
            line = lines[i]
            if self.date_re.match(line) or self._is_hard_stop(line):
                i -= 1
                break
            if self.month_year_re.match(line):
                i += 1
                continue
            if seen_money and self._is_pocket_header_at(lines, i):
                i -= 1
                break
            if self.money_re.match(line):
                seen_money = True
            block.append(line)
            i += 1

        self._fill_transaction(tx, pocket, block)
        return tx, i

    def _fill_transaction(self, tx, pocket, block):
        block = self._remove_noise(block)

        amount_candidates = []
        text_parts = []
        raw_parts = []

        for part in block:
            part = compact_line(part)
            if not part:
                continue
            raw_parts.append(part)

            if self.money_re.match(part):
                amount_candidates.append(part)
                continue

            match = self.id_re.search(part)
            if match:
                tx.transaction_id = match.group(1)
                cleaned = compact_line(self.id_re.sub("", part))
                if cleaned:
                    text_parts.append(cleaned)
                continue

            text_parts.append(part)

        tx.raw = " ".join(raw_parts)

        if len(amount_candidates) >= 2:
            tx.amount = parse_idr(amount_candidates[-2])
            tx.balance = parse_idr(amount_candidates[-1])
        elif len(amount_candidates) == 1:
            tx.amount = parse_idr(amount_candidates[0])

        tx.mutation_type = "CR" if tx.amount.value >= 0 else "DB"
        self._parse_text_parts(tx, pocket, text_parts)

    def _parse_text_parts(self, tx, pocket, parts):
        if not parts:
            return
        if pocket in ("Main Pocket", "Kantong Utama"):
            self._parse_main_pocket_parts(tx, parts)
        elif pocket == "Stockbit Sekuritas RDN":
            self._parse_stockbit_parts(tx, parts)
        else:
            self._parse_generic_parts(tx, parts)

    def _parse_main_pocket_parts(self, tx, parts):
        account_index = None
        for i, part in enumerate(parts):
            if self.account_re.search(part):
                account_index = i
                break

        if account_index is not None and account_index > 0:
            name = " ".join(parts[:account_index])
            account = parts[account_index]
            tx.source_destination = f"{name} — {account}"
            if account_index + 1 < len(parts):
                tx.transaction_detail = parts[account_index + 1]
            if account_index + 2 < len(parts):
                tx.notes = " ".join(parts[account_index + 2:])
            return

        if len(parts) >= 3 and parts[0] in _INTEREST_LIKE:
            tx.source_destination = f"{parts[0]} — {parts[1]}"
            tx.transaction_detail = parts[2]
            if len(parts) > 3:
                tx.notes = " ".join(parts[3:])
            return

        self._parse_generic_parts(tx, parts)

    def _parse_stockbit_parts(self, tx, parts):
        if len(parts) >= 3 and parts[0] in _INTEREST_LIKE:
            tx.source_destination = f"{parts[0]} — {parts[1]}"
            tx.transaction_detail = parts[2]
            if len(parts) > 3:
                tx.notes = " ".join(parts[3:])
            return

        tx.source_destination = parts[0]
        if len(parts) >= 2:
            tx.transaction_detail = parts[1]
        if len(parts) >= 3:
            tx.notes = " ".join(parts[2:])

    def _parse_generic_parts(self, tx, parts):
        tx.source_destination = parts[0]
        if len(parts) >= 2:
            tx.transaction_detail = parts[1]
        if len(parts) >= 3:
            tx.notes = " ".join(parts[2:])

    def _normalize_lines(self, text):
        lines = []
        for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            line = compact_line(raw)
            if not line or self._should_skip_line(line):
                continue
            lines.append(line)
        return lines

    def _should_skip_line(self, line):
        return any(k in line for k in _SKIP_CONTAINS)

    def _remove_noise(self, parts):
        clean = []
        for part in parts:
            part = compact_line(part)
            if not part or self._should_skip_line(part):
                continue
            if part in _REMOVE_NOISE_EXACT:
                continue
            if part.startswith("Latest Balance per"):
                continue
            clean.append(part)
        return clean

    def _find_transaction_start(self, lines):
        # the table starts at the first "date followed by a time" pair (a real
        # transaction) or the first pocket header, whichever comes first. The
        # date+time guard skips summary dates such as "31 Dec 2024"/"0,00".
        for i in range(len(lines) - 1):
            if self._is_pocket_header_at(lines, i) or (
                self.date_re.match(lines[i]) and self.time_re.match(lines[i + 1])
            ):
                return i
        return -1

    def _extract_account_from(self, lines, stmt):
        for line in lines:
            match = self.account_id_re.match(line)
            if match:
                # fill only what was missed; _extract_metadata may have already
                # set the name (history statements keep a separate owner line).
                if not stmt.account_no:
                    stmt.account_no = match.group(2).strip()
                if not stmt.account_name:
                    stmt.account_name = match.group(1).strip()
                return
            if not stmt.period and self._looks_like_period(line):
                stmt.period = line

    def _is_pocket_header_at(self, lines, i):
        if i + 1 >= len(lines):
            return False
        nxt = lines[i + 1]
        return nxt.startswith("Pocket ID") or nxt.startswith("ID Kantong")

    def _is_hard_stop(self, line):
        return line.startswith("CURRENCY EXCHANGE RATE") or line.startswith("DISCLAIMER")
