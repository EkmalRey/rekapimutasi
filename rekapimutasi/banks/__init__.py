from ..parser import Registry
from .bca import BisnisParser, PDFParser, PersonalParser
from .bni import BNIMutasiParser, BNIParser, BNITransaksiParser
from .bri import BRIParser
from .bsi import BSIParser
from .btpn import BTPNParser
from .jago import JagoParser
from .mandiri import MandiriEStatementParser, MandiriKoranParser, MandiriParser


def default_registry():
    # Order matters: the first parser whose can_parse() agrees wins. The
    # specific parsers come first; BSI/BTPN's loose phrase checks last.
    return Registry(
        [
            JagoParser(),
            PersonalParser(),
            BisnisParser(),
            PDFParser(),
            MandiriParser(),
            MandiriEStatementParser(),
            MandiriKoranParser(),
            BNIParser(),
            BNIMutasiParser(),
            BNITransaksiParser(),
            BRIParser(),
            BSIParser(),
            BTPNParser(),
        ]
    )