from . import model  # noqa: F401  (re-exported names below)
from .banks import default_registry
from .errors import (
    EmptyPDFError,
    InvalidFormatError,
    RekapimutasiError,
    UnsupportedBankError,
)
from .export import (
    compact_statement,
    csv_bytes,
    flatten_statement,
    statement_csv_rows,
    write_csv,
    write_xlsx,
    xlsx_bytes,
)
from .extractor import extract_pdf_text
from .model import BankCode, Money, PocketGroup, Statement, Transaction

__all__ = [
    "BankCode",
    "EmptyPDFError",
    "InvalidFormatError",
    "Money",
    "PocketGroup",
    "RekapimutasiError",
    "Statement",
    "Transaction",
    "UnsupportedBankError",
    "compact_statement",
    "csv_bytes",
    "default_registry",
    "extract_pdf_text",
    "flatten_statement",
    "parse_csv_file",
    "parse_file",
    "parse_text",
    "statement_csv_rows",
    "write_csv",
    "write_xlsx",
    "xlsx_bytes",
]


def parse_text(text):
    return default_registry().parse(text)


def parse_file(path):
    if path.lower().endswith(".csv"):
        return parse_csv_file(path)
    return parse_text(extract_pdf_text(path))


def parse_csv_file(path):
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        data = f.read()
    if not data.strip():
        raise EmptyPDFError("empty csv file")
    return parse_text(data)

