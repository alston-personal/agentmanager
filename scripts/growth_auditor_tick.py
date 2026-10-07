#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from agent_core.growth_auditor import GrowthAuditor


def _load_jsonl(path: Path):
    if not path.exists():
        return []
    rows = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Capture reusable-experience evidence into the AgentOS Growth Proof ledger.")
    ap.add_argument("--input", required=True, help="JSONL observations emitted by runtimes/receipts.")
    ap.add_argument("--data-root", default=os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
    ap.add_argument("--receipt-out")
    args = ap.parse_args()

    auditor = GrowthAuditor(Path(args.data_root))
    results = auditor.observe_many(_load_jsonl(Path(args.input)))
    receipt = {
        "schema": "agentos.growth-auditor-receipt/v1",
        "ok": True,
        "input": args.input,
        "observed": len(results),
        "qualified": sum(1 for item in results if item.get("qualified")),
        "g3_or_above": sum(
            1
            for item in results
            if item.get("qualified") and item.get("proof", {}).get("verdict") in {"G3", "G4", "G5"}
        ),
        "proof_ids": [
            item["proof"]["proof_id"]
            for item in results
            if item.get("qualified") and item.get("proof")
        ],
    }
    if args.receipt_out:
        out = Path(args.receipt_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
