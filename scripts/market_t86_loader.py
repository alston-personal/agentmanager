#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from market_learning.data_loader import ImmutableRawArchive, TwseInstitutionalFlowLoader


def trading_dates_from_bars(path: Path, instrument: str) -> list[str]:
    dates: list[str] = []
    seen = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        row = json.loads(raw)
        if str(row.get("instrument")) != instrument:
            continue
        value = str(row.get("date") or "")
        if value and value not in seen:
            seen.add(value)
            dates.append(value)
    return sorted(dates)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill TWSE T86 institutional flow for trading dates already present in normalized bars.")
    parser.add_argument("--bars", required=True, help="Normalized market-bar JSONL")
    parser.add_argument("--stock", required=True)
    parser.add_argument("--root", default="market-data")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    dates = trading_dates_from_bars(Path(args.bars), args.stock)
    if not dates:
        raise SystemExit("no trading dates found for requested stock")

    loader = TwseInstitutionalFlowLoader()
    archive = ImmutableRawArchive(Path(args.root))
    output = Path(args.output) if args.output else Path(args.root) / "normalized" / "twse-t86" / f"{args.stock}.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)

    existing = set()
    if output.exists():
        for raw in output.read_text(encoding="utf-8").splitlines():
            if raw.strip():
                item = json.loads(raw)
                existing.add(str(item.get("date") or ""))

    with output.open("a", encoding="utf-8") as handle:
        for trading_date in dates:
            if trading_date in existing:
                continue
            payload = loader.fetch_day(trading_date)
            receipt, row = loader.archive_day(archive, args.stock, trading_date, payload)
            if row is not None:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            print(json.dumps(receipt.to_dict(), ensure_ascii=False, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
