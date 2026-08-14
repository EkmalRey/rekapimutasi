import re

from ..errors import EmptyPDFError
from ..model import BankCode, Money, PocketGroup, Statement, Transaction
from ..parser import Parser
from ..utils import compact_line, parse_jago_date, whole_number

_DATE_RE = re.compile(r"^\d{1,2} [A-Za-z]{3} \d{4}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")
# "+20,000" (older Jenius), "+ 50,000", or "+110.703.716" (dot thousands):
# optional space after the sign, digits with , or . separators
_AMOUNT_RE = re.compile(r"^[+-] ?[\d.,]+$")
# A sub-card / savings running balance is a plain number with no sign
# ("3.005.000", "1.803.129"); it only appears after the signed amount.
_BALANCE_RE = re.compile(r"^\d{1,3}(?:[.,]\d{3})*$")
# Jenius transaction IDs: "202305010001@DCB20198" / "201911180001@@AT63606" /
# "202305040001GTWO3477" / "202008289021@@CI58767". Always exactly 12 digits
# followed by an @-code or an uppercase suffix; the trailing (?!\d) excludes
# DANA merchant references ("DANA2023050452073526MAULANASAYYIDIA").
_TX_ID_RE = re.compile(r"(?<!\d)\d{12}(?:@@?[A-Z][A-Z0-9]*|[A-Z]{2,}[A-Z0-9]*)(?!\d)")
# Card numbers print masked: "**** **** **** 3659"
_CARD_RE = re.compile(r"^\*{4}(?: \*{4})* (\d{4})$")
_COLUMN_HEADER_RE = re.compile(r"^TANGGAL & JAM$")
# Every page opens and closes with "E-STATEMENT <Month> <Year>"; it is never
# part of a transaction description.
_PAGE_MARKER_RE = re.compile(r"^E-STATEMENT ")
# Pocket/section headers that start a new transaction group.
_SECTION_RE = re.compile(r"^(?:Saldo Aktif IDR|m-Card|e-Card|x-Card|Flexi Saver(?:\s+-.*)?)$")
# The transaction-type legend repeats on every page ("Transfer Masuk",
# "Transfer Keluar", "Top up Kartu", ...); these tokens only ever appear as
# whole lines in the legend/footer noise, never inside a real description.
_LEGEND_TOKENS = (
    "Transfer Masuk",
    "Transfer Keluar",
    "Pembayaran Tarif",
    "Pembayaran Tagihan Rintis",
    "Fee Pembayaran Rintis",
    "Pembayaran dengan Kartu",
    "Penarikan Tunai",
    "Penarikan dari Saldo Tabungan",
    "Top up Kartu",
    "Top up Saldo Tabungan",
    "Db Bifast Outgoing",
    "Cr Bifast Incoming",
    "Db Fee Bifast Outgoing",
    "Transfer to VAM",
    "Isi Ulang Pulsa",
    "FEE TRF ALTO IB MB",
    "TRF ALTO IB MB",
    "TRF PRIMA IB MB",
    "Bunga",
    "Pajak Bunga",
    "Refund Kartu",
    "Tarik Tunai di ATM",
    "Biaya ATM",
    "Biaya Transfer",
    "Kategori",
    "CATATAN",
    "Tipe transaksi",
    "JUMLAH",
    "RINCIAN",
    "ID Transaksi | Kategori",
    "Feesible",
    "Active Balance",
    "Nomor Kartu",
    "Transaksi masuk :",
    "Transaksi keluar :",
)

# Section headers that carry a card number (their transactions get a balance).
_CARD_SECTIONS = ("m-Card", "e-Card", "x-Card")


class BTPNParser(Parser):
    """BTPN Jenius e-statement PDFs.

    The statement is split into pocket sections, each introduced by a header
    ("Saldo Aktif IDR", "e-Card", "x-Card", "Flexi Saver"). Card sections carry
    a masked card number ("**** **** **** 3659") and each transaction ends with
    a running balance; the main "Saldo Aktif" section has neither. Transactions
    are rows of date / time / description / signed amount (+ balance):

        05 Mei 2023
        02:01
        Top up Kartu
        202305050001@DCB22068 | Top up kartu
        +3.000.000
        3.005.000
    """

    bank = BankCode.JENIUS

    def can_parse(self, text):
        lower = text.lower()
        return "jenius" in lower or "btpn" in lower

    def parse(self, text):
        lines = [compact_line(l) for l in text.splitlines() if compact_line(l)]
        if not lines:
            raise EmptyPDFError("empty pdf text")

        stmt = Statement(bank=self.bank, currency="IDR")
        self._extract_metadata(lines, stmt)

        block = []
        groups = {}
        ordered = []
        current_section = "Saldo Aktif"
        current_card = ""

        def section_name(section, card):
            # Flexi Saver sections carry an account name ("Flexi Saver -
            # BISMILAH BELI MOBIL"); keep it so multiple saver accounts stay
            # separate pockets.
            if section.startswith("Flexi Saver"):
                return section
            if section in _CARD_SECTIONS:
                return f"{section} *{card}" if card else section
            return "Saldo Aktif"

        def flush():
            nonlocal block
            if not block:
                return
            tx = self._parse_block(block, current_section, current_card)
            if tx.date:
                name = section_name(current_section, current_card)
                if name not in groups:
                    groups[name] = PocketGroup(name=name)
                    ordered.append(name)
                groups[name].transactions.append(tx)
            block = []

        i = 0
        n = len(lines)
        while i < n:
            line = lines[i]
            if _DATE_RE.match(line):
                flush()
                block = [line]
                i += 1
                continue
            if _COLUMN_HEADER_RE.match(line) or _PAGE_MARKER_RE.match(line):
                # end of a page or of the statement: close the block and skip
                # the header/legend run up to the next date row or section
                flush()
                block = []
                while i < n and not _DATE_RE.match(lines[i]) and not _SECTION_RE.match(lines[i]):
                    i += 1
                continue
            if line == "DISCLAIMER":
                # nothing after the disclaimer is a transaction
                flush()
                block = []
                break
            if _SECTION_RE.match(line):
                # a new pocket section starts
                flush()
                block = []
                current_section = line
                current_card = ""
                i += 1
                continue
            if _CARD_RE.match(line) and current_card == "":
                # the section's card number; only the first card line after the
                # section header is the section's own (later masked numbers are
                # counterparty cards inside descriptions)
                current_card = _CARD_RE.match(line).group(1)
                i += 1
                continue
            if block:
                block.append(line)
            i += 1
        flush()

        if ordered:
            stmt.pockets = [groups[name] for name in ordered]
        return stmt

    def _extract_metadata(self, lines, stmt):
        """Pemilik Rekening / Nomor Rekening / Periode each label the line
        directly below them."""
        for i, line in enumerate(lines):
            if line == "Pemilik Rekening" and i + 1 < len(lines):
                stmt.account_name = lines[i + 1]
            elif line == "Nomor Rekening" and i + 1 < len(lines):
                stmt.account_no = lines[i + 1]
            elif line == "Periode" and i + 1 < len(lines):
                stmt.period = lines[i + 1]

    def _parse_block(self, block, section, card):
        tx = Transaction(
            date=parse_jago_date(block[0]),
            notes="-",
        )
        desc_parts = []
        seen_amount = False
        for i, line in enumerate(block[1:], 1):
            if i == 1 and _TIME_RE.match(line):
                tx.time = line
                continue
            if _AMOUNT_RE.match(line):
                seen_amount = True
                is_credit = line.startswith("+")
                ival = whole_number(line[1:].strip())
                if not is_credit:
                    ival = -ival
                tx.amount = Money(currency="IDR", display=f"{'+' if is_credit else '-'}Rp{line[1:].strip()}", value=ival)
                tx.mutation_type = "CR" if is_credit else "DB"
                continue
            # Sub-card and savings sections print a running balance as a
            # plain number on the line after the amount.
            if seen_amount and _BALANCE_RE.match(line):
                tx.balance = Money(currency="IDR", display="Rp" + line, value=whole_number(line))
                continue
            # The "SALDO AKHIR" section summary starts the end-of-statement
            # tail; nothing after it belongs to this transaction.
            if seen_amount and (line.startswith("SALDO ") or line == "RINCIAN"):
                break
            # A bare number right after the amount is the running balance; a
            # following "SALDO AKHIR" summary confirms it is not description.
            if (
                seen_amount
                and _BALANCE_RE.match(line)
                and any(l.startswith("SALDO ") for l in block[i + 1:])
            ):
                break
            # Skip runs of transaction-type legend tokens (footer noise). Real
            # descriptions can legitimately start with these words ("Top up
            # Kartu", "Refund Kartu"), so only drop them after the amount,
            # where the repeated page-footer legend sits.
            if seen_amount and line in _LEGEND_TOKENS:
                continue

            # "RINCIAN" holds the transaction ID ("202305010001@DCB20198")
            m = _TX_ID_RE.search(line)
            if m:
                tx.transaction_id = m.group(0)
                before = line[: m.start()].strip()
                after = line[m.end():].lstrip("| ").strip()
                if after and not re.search(r"\d{5,}", after):
                    # "| Refund" / "| Uang keluar" / "| DNID FEBXXXXXX" is the
                    # category (Rincian sub-column) -> notes
                    tx.notes = after
                else:
                    # a long digit/hex tail is a RINTIS or CENAIDJA reference
                    # -> keep in the detail
                    after_full = line[m.end():].strip()
                    before = (before + " " + after_full).strip()
                if before:
                    desc_parts.append(before)
                continue

            desc_parts.append(line)

        tx.transaction_detail = compact_line(" ".join(desc_parts))
        tx.raw = compact_line(" ".join(block))

        # The pocket/card the transaction belongs to is the source of the
        # money (e.g. "x-Card *3659" or "Flexi Saver - BISMILAH BELI MOBIL").
        if section in _CARD_SECTIONS:
            tx.source_destination = f"{section} *{card}" if card else section
        elif section.startswith("Flexi Saver"):
            tx.source_destination = section
        else:
            tx.source_destination = "Saldo Aktif"

        if not tx.transaction_detail:
            return Transaction()
        return tx
