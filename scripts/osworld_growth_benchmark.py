#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_core.osworld_growth_benchmark import (
    build_run_record,
    compare_growth,
    load_release,
    parse_osworld_results,
)


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize and compare OSWorld AgentOS Growth Proof runs")
    sub = parser.add_subparsers(dest="cmd", required=True)

    norm = sub.add_parser("normalize")
    norm.add_argument("--release", required=True)
    norm.add_argument("--arm", choices=["raw", "cold", "experienced"], required=True)
    norm.add_argument("--results", required=True, help="OSWorld summary/results.json")
    norm.add_argument("--model", required=True, help="JSON file")
    norm.add_argument("--runtime", required=True, help="JSON file")
    norm.add_argument("--cognition", default="")
    norm.add_argument("--contamination", default="")
    norm.add_argument("--out", required=True)

    cmp = sub.add_parser("compare")
    cmp.add_argument("--cold", required=True)
    cmp.add_argument("--experienced", required=True)
    cmp.add_argument("--out", required=True)

    args = parser.parse_args()

    if args.cmd == "normalize":
        release = load_release(Path(args.release))
        record = build_run_record(
            release=release,
            arm=args.arm,
            results=parse_osworld_results(Path(args.results)),
            model=_load(args.model),
            runtime=_load(args.runtime),
            cognitive_snapshot=_load(args.cognition) if args.cognition else None,
            contamination=_load(args.contamination) if args.contamination else None,
        )
        Path(args.out).write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(record["metrics"], ensure_ascii=False))
        return 0

    result = compare_growth(cold=_load(args.cold), experienced=_load(args.experienced))
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result["metrics"], ensure_ascii=False))
    return 0 if result["verdict"] == "G3_CANDIDATE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
