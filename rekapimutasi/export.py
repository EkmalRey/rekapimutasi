import csv
import io
import re

from openpyxl import Workbook
from openpyxl.styles import Font

_HEADERS = ["Date", "Time", "Type", "Amount", "Balance", "Source/Destination", "Details", "Notes", "Transaction ID"]

_AMOUNT_FMT = "+Rp#,##0;-Rp#,##0;Rp0"
_BALANCE_FMT = "Rp#,##0;-Rp#,##0;Rp0"


def _format_money(money):
    return "" if not money.currency else str(money.value)


def statement_csv_rows(stmt):
    rows = [_HEADERS]
    for pocket in stmt.pockets:
        for tx in pocket.transactions:
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
        for tx in pocket.transactions:
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

        for stmt in statements:
            for pocket in stmt.pockets:
                p_name = pocket.name or ""
                for tx in pocket.transactions:
                    ws.append(
                        [
                            stmt.bank,
                            stmt.account_no,
                            stmt.account_name,
                            stmt.period,
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
        for idx, stmt in enumerate(statements):
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
                for tx in pocket.transactions:
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
    for stmt in statements:
        for pocket in stmt.pockets:
            p_name = pocket.name or ""
            for tx in pocket.transactions:
                writer.writerow(
                    [
                        stmt.bank,
                        stmt.account_no,
                        stmt.account_name,
                        stmt.period,
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


def compact_statement(stmt):
    parts = [f"{stmt.bank} account {stmt.account_no} ({stmt.account_name})"]
    for pocket in stmt.pockets:
        parts.append(f"  {pocket.name}: {len(pocket.transactions)} transactions")
    return "\n".join(parts)


def flatten_statement(stmt):
    """JSON shape consumed by the web frontend (rows flattened across pockets)."""
    return {
        "bank": stmt.bank,
        "account_name": stmt.account_name,
        "account_no": stmt.account_no,
        "period": stmt.period,
        "currency": stmt.currency,
        "columns": _HEADERS,
        "rows": statement_csv_rows(stmt)[1:],
        "pockets": [p.name for p in stmt.pockets],
    }
