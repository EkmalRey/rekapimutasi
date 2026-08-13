import re
from datetime import datetime

from .model import Money

# Month name -> number. Indonesian (mei/agu/okt/des) plus English, both
# abbreviated and full forms.
_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "mei": 5,
    "jun": 6, "jul": 7, "aug": 8, "agu": 8, "agt": 8, "sep": 9,
    "oct": 10, "okt": 10, "nov": 11, "dec": 12, "des": 12,
    "january": 1, "januari": 1, "february": 2, "februari": 2,
    "march": 3, "maret": 3, "april": 4,
    "june": 6, "juni": 6, "july": 7, "juli": 7,
    "august": 8, "agustus": 8, "september": 9,
    "october": 10, "oktober": 10, "november": 11, "december": 12, "desember": 12,
}

# Full month names, for "does this line look like a period" checks.
_MONTH_NAMES = (
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
    "januari", "februari", "maret", "mei", "juni", "juli",
    "agustus", "oktober", "desember",
)

_BCA_MONEY = re.compile(r"^\d{1,3}(,\d{3})*\.\d{2}$")
_BCA_MONEY_SIGNED = re.compile(r"^\d{1,3}(,\d{3})*\.\d{2}(\s+[Dd][Bb])?$")


def compact_line(s):
    """Collapse runs of any whitespace to a single space and strip."""
    return " ".join(s.split())


def month_number(month_str):
    return _MONTH_MAP.get(month_str.lower())


def parse_jago_date(value):
    """'d MMM YYYY' -> 'YYYY-MM-DD'; returns input unchanged if it cannot parse."""
    parts = compact_line(value).split()
    if len(parts) != 3:
        return value
    month = month_number(parts[1])
    if month is None:
        return value
    try:
        return datetime(int(parts[2]), month, int(parts[0])).strftime("%Y-%m-%d")
    except ValueError:
        return value


def parse_bca_date(value):
    """'DD/MM/YYYY' -> 'YYYY-MM-DD'; returns input unchanged if it cannot parse."""
    value = compact_line(value)
    try:
        return datetime.strptime(value, "%d/%m/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return value


def _format_idr(value):
    value = compact_line(value)
    if not value:
        return value
    if value.startswith("+Rp") or value.startswith("-Rp") or value.startswith("Rp"):
        return value
    if value.startswith("+"):
        return "+Rp" + value[1:]
    if value.startswith("-"):
        return "-Rp" + value[1:]
    return "Rp" + value


def _strip_bca_suffix(value):
    """Strips a trailing ' CR'/' DB', returning (clean_value, is_credit or None)."""
    value = compact_line(value)
    if value.endswith(" CR"):
        return value[:-3].strip(), True
    if value.endswith(" DB"):
        return value[:-3].strip(), False
    return value, None


def _whole_rupiah(value):
    """Parse '1,234.56' / '108400.00' to whole rupiah (1234) without float math.

    Cents are truncated, matching the original extractor's int() behaviour.
    """
    value = value.strip()
    if not value:
        raise ValueError("empty value")
    if "." in value:
        value = value.split(".", 1)[0]
    value = value.replace(",", "")
    if not value.isdigit():
        raise ValueError(f"not an amount: {value!r}")
    return int(value)


def whole_number(s):
    """Strip thousand separators ('.' and ',') and return int, or 0."""
    s = s.replace(".", "").replace(",", "")
    return int(s) if s.isdigit() else 0


def parse_idr(value):
    """Parse an Indonesian IDR string ('61.832,04', '+221.861', '-30.000')."""
    value = compact_line(value)
    display = _format_idr(value)
    s = value.replace("Rp", "")
    if "," in s:
        s = s.split(",", 1)[0]
    s = s.replace(".", "")
    sign = 1
    if s.startswith("+"):
        s = s[1:]
    elif s.startswith("-"):
        sign = -1
        s = s[1:]
    if not s.isdigit():
        return Money(currency="IDR", display=display, value=0)
    return Money(currency="IDR", display=display, value=int(s) * sign)


def parse_bca_money(value, is_credit):
    """Parse BCA money ('3,528,964.00 CR', '108400.00') with explicit sign."""
    value, suffix = _strip_bca_suffix(value)
    if suffix is not None:
        is_credit = suffix
    if not value:
        return Money(currency="IDR")
    try:
        ival = _whole_rupiah(value)
    except ValueError:
        return Money(currency="IDR")
    if not is_credit:
        ival = -ival
    return Money(currency="IDR", display=_format_idr(str(ival)), value=ival)


def parse_bca_balance(value):
    value = compact_line(value)
    try:
        ival = _whole_rupiah(value)
    except ValueError:
        return Money(currency="IDR")
    return Money(currency="IDR", display="Rp" + value, value=ival)


# Shared amount recognizers, kept here so every bank parser reuses the same
# definitions instead of re-declaring its own.
def is_bca_money(value):
    return bool(_BCA_MONEY.match(value))


def is_bca_money_signed(value):
    return bool(_BCA_MONEY_SIGNED.match(value))
