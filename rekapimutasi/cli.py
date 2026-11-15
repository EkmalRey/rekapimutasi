import argparse
import sys

from . import (
    compact_statement,
    multi_csv_bytes,
    parse_file,
    write_csv,
    write_multi_xlsx,
    write_xlsx,
)


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
    parser.add_argument(
        "--mode",
        choices=["multi_sheet", "single_sheet"],
        default="multi_sheet",
        help="excel multi-file export mode: multi_sheet (default) or single_sheet",
    )
    parser.add_argument(
        "-p",
        "--password",
        default="",
        help="password for encrypted/protected PDF files",
    )
    parser.add_argument("file", nargs="+", help="statement PDF or CSV file(s)")
    args = parser.parse_args(argv)

    try:
        stmts = [parse_file(f, password=args.password or None) for f in args.file]
    except Exception as e:  # noqa: BLE001 - report the failure, exit non-zero
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    out = args.output.lower()
    if not out:
        for stmt in stmts:
            print(compact_statement(stmt))
            for pocket in stmt.pockets:
                for tx in pocket.transactions:
                    print(f"{tx.date}  {tx.mutation_type:<2}  {tx.amount.display:>12}  {tx.transaction_detail}")
    elif out.endswith(".xlsx"):
        if len(stmts) == 1:
            write_xlsx(stmts[0], args.output)
        else:
            write_multi_xlsx(stmts, args.output, mode=args.mode)
        print("wrote", args.output)
    elif out.endswith(".csv"):
        if len(stmts) == 1:
            with open(args.output, "w", newline="", encoding="utf-8") as f:
                write_csv(stmts[0], f)
        else:
            with open(args.output, "wb") as f:
                f.write(multi_csv_bytes(stmts))
        print("wrote", args.output)
    else:
        print(f"unsupported output format: {args.output}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
