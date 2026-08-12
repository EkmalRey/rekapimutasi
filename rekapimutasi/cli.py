import argparse
import sys

from . import compact_statement, parse_file, write_csv, write_xlsx


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="rekapimutasi",
        description="Parse Indonesian bank statement PDFs and CSVs into clean tabular data.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="",
        help="output file (.xlsx or .csv); default prints to stdout",
    )
    parser.add_argument("file", help="statement PDF or CSV")
    args = parser.parse_args(argv)

    try:
        stmt = parse_file(args.file)
    except Exception as e:  # noqa: BLE001 - report the failure, exit non-zero
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    out = args.output.lower()
    if not out:
        print(compact_statement(stmt))
        for pocket in stmt.pockets:
            for tx in pocket.transactions:
                print(f"{tx.date}  {tx.mutation_type:<2}  {tx.amount.display:>12}  {tx.transaction_detail}")
    elif out.endswith(".xlsx"):
        write_xlsx(stmt, args.output)
        print("wrote", args.output)
    elif out.endswith(".csv"):
        with open(args.output, "w", newline="", encoding="utf-8") as f:
            write_csv(stmt, f)
        print("wrote", args.output)
    else:
        print(f"unsupported output format: {args.output}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
