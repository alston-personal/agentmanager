#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from market_learning.data_loader import ImmutableRawArchive, TwseMonthlyStockLoader


def _months(start: str, end: str):
    sy, sm = (int(x) for x in start.split("-", 1))
    ey, em = (int(x) for x in end.split("-", 1))
    y, m = sy, sm
    while (y, m) <= (ey, em):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill TWSE monthly stock history into an immutable raw archive.")
    parser.add_argument("--stock", action="append", required=True, help="TWSE stock number; repeat for multiple stocks")
    parser.add_argument("--from-month", required=True, help="YYYY-MM")
    parser.add_argument("--to-month", required=True, help="YYYY-MM")
    parser.add_argument("--root", default="market-data")
    args = parser.parse_args()

    loader = TwseMonthlyStockLoader()
    archive = ImmutableRawArchive(Path(args.root))
    normalized_root = Path(args.root) / "normalized" / "twse-stock-day"
    normalized_root.mkdir(parents=True, exist_ok=True)

    for stock in args.stock:
        out = normalized_root / f"{stock}.jsonl"
        with out.open("a", encoding="utf-8") as handle:
            for year, month in _months(args.from_month, args.to_month):
                payload = loader.fetch_month(stock, year, month)
                receipt, rows = loader.archive_month(archive, stock, year, month, payload)
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                print(json.dumps(receipt.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
