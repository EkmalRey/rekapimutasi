# rekapimutasi

Parse Indonesian bank statement PDFs and CSVs into clean tabular data. A
drag-and-drop web app plus a CLI, all in a small Python package.

*rekapitulasi mutasi* — statement recap.

## Run

```bash
docker compose up --build
# → http://localhost:8092
```

Or without Docker:

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m rekapimutasi.web --addr :8092      # web UI
.venv/bin/python -m rekapimutasi -o out.xlsx statement.pdf   # CLI
```

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Tests run on synthetic fixtures that ship with the repo. When a real sample
statement PDF is dropped into the matching `banks/<bank>/testdata/` directory,
an extra regression test for it runs automatically; without the PDF the test
is skipped (the PDFs are kept out of git because they contain personal data).

## Supported banks

| Bank | Format | Status |
|---|---|---|
| Bank Jago | Monthly statement PDF (ID & EN, incl. 2025 layouts) | ✅ |
| Bank Jago | Pockets history PDF | ✅ |
| BCA Personal | PDF e-statement (AES-256 encrypted, several layouts) | ✅ |
| BCA Personal / Bisnis | CSV e-statement (KlikBCA) | ✅ |
| Mandiri | Savings PDF (3 layouts: classic, e-Statement, Rekening Koran) | ✅ |
| BNI | Savings PDF (3 layouts) | ✅ |
| BSI | Savings PDF | ✅ |
| BTPN Jenius | e-Statement PDF | ✅ |
| BRI | Rekening Koran PDF | ✅ |

BCA PDFs are AES-256 encrypted with an empty password; they are decrypted
in-memory with pypdf (which needs `cryptography`) before parsing.

## Usage (library)

```python
import rekapimutasi

stmt = rekapimutasi.parse_file("statement.pdf")
for pocket in stmt.pockets:
    for tx in pocket.transactions:
        print(tx.date, tx.mutation_type, tx.amount.value, tx.transaction_detail)
```

## Export

- **xlsx** — `Amount`/`Balance` are real numbers; Excel formats them as
  `+Rp104000` / `-Rp104000` (balance shows plain `Rp` when positive).
- **csv** — plain signed integers, e.g. `104000` / `-104000`.

## Structure

```
rekapimutasi/            — package
  __init__.py            — facade API (parse_file, parse_text)
  extractor.py           — PDF text extraction (+ AES-256 decrypt, pypdf)
  export.py              — xlsx/csv/JSON export
  model.py               — Statement / Transaction / Money dataclasses
  parser.py              — Parser protocol + registry
  utils.py               — money/date parsing (integer math, no floats)
  banks/                 — per-bank parsers (jago, bca, mandiri, bni, bsi, btpn)
  cli.py                 — CLI (python -m rekapimutasi.cli)
  web.py                 — web app (python -m rekapimutasi.web, stdlib server)
  web/index.html         — embedded frontend
tests/                   — regression tests
```

## Adding a bank

A bank is one class implementing `rekapimutasi.parser.Parser` (`bank`,
`can_parse`, `parse`), registered in `rekapimutasi.banks.default_registry()`.
Drop a sample statement into `banks/<bank>/testdata/` to verify.

## License

MIT
