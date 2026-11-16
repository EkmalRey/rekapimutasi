from dataclasses import dataclass, field
from decimal import Decimal


class BankCode:
    UNKNOWN = "UNKNOWN"
    JAGO = "JAGO"
    BCA = "BCA"
    BCA_BISNIS = "BCA_BISNIS"
    MANDIRI = "MANDIRI"
    BNI = "BNI"
    BSI = "BSI"
    BRI = "BRI"
    BTPN = "BTPN"
    JENIUS = "JENIUS"


@dataclass
class Money:
    currency: str = ""
    display: str = ""
    # whole rupiah as int; a two-place Decimal when the amount has cents
    value: int | Decimal = 0


@dataclass
class Transaction:
    date: str = ""
    time: str = ""
    source_destination: str = ""
    transaction_detail: str = ""
    transaction_id: str = ""
    mutation_type: str = ""
    notes: str = ""
    amount: Money = field(default_factory=Money)
    balance: Money = field(default_factory=Money)
    raw: str = ""


@dataclass
class PocketGroup:
    name: str = ""
    transactions: list = field(default_factory=list)


@dataclass
class Statement:
    bank: str = ""
    account_name: str = ""
    account_no: str = ""
    period: str = ""
    currency: str = ""
    pockets: list = field(default_factory=list)
