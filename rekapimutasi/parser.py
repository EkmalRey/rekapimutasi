from .errors import UnsupportedBankError


class Parser:
    """Interface for a bank-specific parser.

    Subclasses must define ``bank``, ``can_parse(text)`` and ``parse(text)``.
    """

    bank = "UNKNOWN"

    def can_parse(self, text):
        raise NotImplementedError

    def parse(self, text):
        raise NotImplementedError


class Registry:
    def __init__(self, parsers=None):
        self.parsers = list(parsers) if parsers else []

    def parse(self, text):
        for parser in self.parsers:
            if parser.can_parse(text):
                return parser.parse(text)
        raise UnsupportedBankError("unsupported bank statement")
