class RekapimutasiError(Exception):
    """Base class for all parse errors."""


class UnsupportedBankError(RekapimutasiError):
    """No registered parser recognized the statement text."""


class EmptyPDFError(RekapimutasiError):
    """The file had no extractable text."""


class InvalidFormatError(RekapimutasiError):
    """The text was recognized but structurally invalid."""
