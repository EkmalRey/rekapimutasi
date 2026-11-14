import csv
import io
import re
import zipfile

from openpyxl import Workbook
from openpyxl.styles import Font

from .utils import format_period

_HEADERS = ["Date", "Time", "Type", "Amount", "Balance", "Source/Destination", "Details", "Notes", "Transaction ID"]

_AMOUNT_FMT = "+Rp#,##0;-Rp#,##0;Rp0"
_BALANCE_FMT = "Rp#,##0;-Rp#,##0;Rp0"


def _format_money(money):
    return "" if not money.currency else str(money.value)


def _tx_sort_key(tx):
    d = tx.date or ""
    t = (tx.time or "").replace(".", ":")
    return (d, t)


def _stmt_sort_key(s):
    first_dt = ""
    for p in s.pockets:
        for tx in p.transactions:
            dt = (tx.date or "") + " " + (tx.time or "").replace(".", ":")
            if dt.strip() and (not first_dt or dt < first_dt):
                first_dt = dt
    return (first_dt or s.period or s.bank, s.bank, s.account_no)


def statement_csv_rows(stmt):
    rows = [_HEADERS]
    for pocket in stmt.pockets:
        sorted_txs = sorted(pocket.transactions, key=_tx_sort_key)
        for tx in sorted_txs:
            rows.append(
                [
                    tx.date,
                    tx.time,
                    tx.mutation_type,
                    _format_money(tx.amount),
                    _format_money(tx.balance),
                    tx.source_destination,
                    tx.transaction_detail,
                    tx.notes,
                    tx.transaction_id,
                ]
            )
    return rows


def write_csv(stmt, out):
    writer = csv.writer(out)
    writer.writerows(statement_csv_rows(stmt))


def csv_bytes(stmt):
    buf = io.StringIO()
    write_csv(stmt, buf)
    return buf.getvalue().encode("utf-8")


def write_xlsx(stmt, out):
    wb = Workbook()
    ws = wb.active
    ws.title = "Transactions"
    ws.append(_HEADERS)

    for pocket in stmt.pockets:
        if len(stmt.pockets) > 1 and pocket.name:
            cell = ws.cell(row=ws.max_row + 1, column=1, value=f"— {pocket.name} —")
            cell.font = Font(bold=True)
        sorted_txs = sorted(pocket.transactions, key=_tx_sort_key)
        for tx in sorted_txs:
            ws.append(
                [
                    tx.date,
                    tx.time,
                    tx.mutation_type,
                    tx.amount.value,
                    tx.balance.value,
                    tx.source_destination,
                    tx.transaction_detail,
                    tx.notes,
                    tx.transaction_id,
                ]
            )

    for col, width in zip("ABCDEFGHI", [12, 8, 8, 18, 18, 40, 50, 30, 24]):
        ws.column_dimensions[col].width = width

    # Amount and Balance stay real numbers; Excel formats them as IDR via a
    # custom number format.
    for row in range(2, ws.max_row + 1):
        ws.cell(row=row, column=4).number_format = _AMOUNT_FMT
        ws.cell(row=row, column=5).number_format = _BALANCE_FMT

    wb.save(out)


def xlsx_bytes(stmt):
    buf = io.BytesIO()
    write_xlsx(stmt, buf)
    return buf.getvalue()


def write_multi_xlsx(statements, out, mode="multi_sheet"):
    """Write multiple statements to an Excel workbook.

    mode:
      - 'multi_sheet': 1 worksheet per file/period with original balance format.
      - 'single_sheet': 1 consolidated sheet with [Bank], [No. Rekening], [Nama Rekening], [Periode], [Kantong].
    """
    if not statements:
        wb = Workbook()
        wb.save(out)
        return

    wb = Workbook()

    if mode == "single_sheet":
        ws = wb.active
        ws.title = "Semua Transaksi"
        headers = ["Bank", "No. Rekening", "Nama Rekening", "Periode", "Kantong"] + _HEADERS
        ws.append(headers)

        all_txs = []
        for stmt in statements:
            for pocket in stmt.pockets:
                p_name = pocket.name or ""
                for tx in pocket.transactions:
                    all_txs.append((stmt, p_name, tx))

        # Default sort by Date and Time from oldest to newest
        all_txs.sort(key=lambda item: _tx_sort_key(item[2]))

        for stmt, p_name, tx in all_txs:
            ws.append(
                [
                    stmt.bank,
                    stmt.account_no,
                    stmt.account_name,
                    format_period(stmt.period),
                    p_name,
                    tx.date,
                    tx.time,
                    tx.mutation_type,
                    tx.amount.value,
                    tx.balance.value,
                    tx.source_destination,
                    tx.transaction_detail,
                    tx.notes,
                    tx.transaction_id,
                ]
            )

        widths = [14, 18, 26, 18, 16, 12, 8, 8, 18, 18, 36, 48, 30, 24]
        for col, width in zip("ABCDEFGHIJKLMN", widths):
            ws.column_dimensions[col].width = width

        for row in range(2, ws.max_row + 1):
            ws.cell(row=row, column=9).number_format = _AMOUNT_FMT
            ws.cell(row=row, column=10).number_format = _BALANCE_FMT

    else:  # multi_sheet
        used_titles = set()
        sorted_stmts = sorted(statements, key=_stmt_sort_key)
        for idx, stmt in enumerate(sorted_stmts):
            if idx == 0:
                ws = wb.active
            else:
                ws = wb.create_sheet()

            raw_title = f"{stmt.bank}_{stmt.period or f'File_{idx + 1}'}"
            safe_title = re.sub(r"[\\/*?:\[\]]", "_", raw_title).strip()[:26] or f"Sheet_{idx + 1}"
            title = safe_title
            counter = 2
            while title.lower() in used_titles:
                title = f"{safe_title[:24]}_{counter}"[:31]
                counter += 1
            used_titles.add(title.lower())
            ws.title = title

            ws.append(_HEADERS)
            for pocket in stmt.pockets:
                if len(stmt.pockets) > 1 and pocket.name:
                    cell = ws.cell(row=ws.max_row + 1, column=1, value=f"— {pocket.name} —")
                    cell.font = Font(bold=True)
                sorted_txs = sorted(pocket.transactions, key=_tx_sort_key)
                for tx in sorted_txs:
                    ws.append(
                        [
                            tx.date,
                            tx.time,
                            tx.mutation_type,
                            tx.amount.value,
                            tx.balance.value,
                            tx.source_destination,
                            tx.transaction_detail,
                            tx.notes,
                            tx.transaction_id,
                        ]
                    )

            for col, width in zip("ABCDEFGHI", [12, 8, 8, 18, 18, 40, 50, 30, 24]):
                ws.column_dimensions[col].width = width

            for row in range(2, ws.max_row + 1):
                ws.cell(row=row, column=4).number_format = _AMOUNT_FMT
                ws.cell(row=row, column=5).number_format = _BALANCE_FMT

    wb.save(out)


def multi_xlsx_bytes(statements, mode="multi_sheet"):
    buf = io.BytesIO()
    write_multi_xlsx(statements, buf, mode=mode)
    return buf.getvalue()


def multi_csv_bytes(statements):
    buf = io.StringIO()
    writer = csv.writer(buf)
    headers = ["Bank", "No. Rekening", "Nama Rekening", "Periode", "Kantong"] + _HEADERS
    writer.writerow(headers)

    all_txs = []
    for stmt in statements:
        for pocket in stmt.pockets:
            p_name = pocket.name or ""
            for tx in pocket.transactions:
                all_txs.append((stmt, p_name, tx))

    # Default sort by Date and Time from oldest to newest
    all_txs.sort(key=lambda item: _tx_sort_key(item[2]))

    for stmt, p_name, tx in all_txs:
        writer.writerow(
            [
                stmt.bank,
                stmt.account_no,
                stmt.account_name,
                format_period(stmt.period),
                p_name,
                tx.date,
                tx.time,
                tx.mutation_type,
                _format_money(tx.amount),
                _format_money(tx.balance),
                tx.source_destination,
                tx.transaction_detail,
                tx.notes,
                tx.transaction_id,
            ]
        )
    return buf.getvalue().encode("utf-8")


def multi_csv_zip_bytes(statements):
    buf = io.BytesIO()
    used_names = set()
    sorted_stmts = sorted(statements, key=_stmt_sort_key)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for idx, stmt in enumerate(sorted_stmts):
            raw_name = f"{idx + 1}_{stmt.bank}_{stmt.period or 'statement'}.csv"
            safe_name = re.sub(r'[\\/*?:\[\]"]', "_", raw_name)
            counter = 2
            while safe_name.lower() in used_names:
                safe_name = f"{idx + 1}_{stmt.bank}_{stmt.period or 'statement'}_{counter}.csv"
                counter += 1
            used_names.add(safe_name.lower())
            zf.writestr(safe_name, csv_bytes(stmt))
    return buf.getvalue()


def compact_statement(stmt):
    parts = [f"{stmt.bank} account {stmt.account_no} ({stmt.account_name})"]
    for pocket in stmt.pockets:
        parts.append(f"  {pocket.name}: {len(pocket.transactions)} transactions")
    return "\n".join(parts)


def flatten_statement(stmt):
    """JSON shape consumed by the web frontend (rows flattened across pockets)."""
    rows = []
    row_pockets = []
    for pocket in stmt.pockets:
        p_name = pocket.name or ""
        sorted_txs = sorted(pocket.transactions, key=_tx_sort_key)
        for tx in sorted_txs:
            rows.append(
                [
                    tx.date,
                    tx.time,
                    tx.mutation_type,
                    _format_money(tx.amount),
                    _format_money(tx.balance),
                    tx.source_destination,
                    tx.transaction_detail,
                    tx.notes,
                    tx.transaction_id,
                ]
            )
            row_pockets.append(p_name)
    return {
        "bank": stmt.bank,
        "account_name": stmt.account_name,
        "account_no": stmt.account_no,
        "period": format_period(stmt.period),
        "currency": stmt.currency,
        "columns": _HEADERS,
        "rows": rows,
        "row_pockets": row_pockets,
        "pockets": [p.name for p in stmt.pockets],
    }
