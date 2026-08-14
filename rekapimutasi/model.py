from dataclasses import dataclass, field


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
    value: int = 0


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
