#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from agent_core.growth_auditor import GrowthAuditor


def _read_new_jsonl(path: Path, cursor_path: Path):
    if not path.exists():
        return [], 0
    try:
        offset = int(cursor_path.read_text(encoding="utf-8").strip()) if cursor_path.exists() else 0
    except Exception:
        offset = 0
    size = path.stat().st_size
    if offset < 0 or offset > size:
        offset = 0

    rows = []
    with path.open("rb") as fh:
        fh.seek(offset)
        for raw in fh:
            try:
                value = json.loads(raw.decode("utf-8"))
            except Exception:
                continue
            if isinstance(value, dict):
                rows.append(value)
        new_offset = fh.tell()
    return rows, new_offset


def main() -> int:
    ap = argparse.ArgumentParser(description="Capture reusable-experience evidence into the AgentOS Growth Proof ledger.")
    ap.add_argument("--input", help="JSONL observation inbox. Defaults under AGENT_DATA_ROOT/growth-proof/")
    ap.add_argument("--data-root", default=os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
    ap.add_argument("--cursor")
    ap.add_argument("--receipt-out")
    args = ap.parse_args()

    data_root = Path(args.data_root)
    input_path = Path(args.input) if args.input else data_root / "growth-proof" / "inbox.jsonl"
    cursor_path = Path(args.cursor) if args.cursor else data_root / "growth-proof" / "inbox.cursor"
    input_path.parent.mkdir(parents=True, exist_ok=True)

    observations, new_offset = _read_new_jsonl(input_path, cursor_path)
    auditor = GrowthAuditor(data_root)
    results = auditor.observe_many(observations)

    cursor_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cursor_path.with_suffix(cursor_path.suffix + ".tmp")
    tmp.write_text(str(new_offset) + "\n", encoding="utf-8")
    tmp.replace(cursor_path)

    receipt = {
        "schema": "agentos.growth-auditor-receipt/v1",
        "ok": True,
        "input": str(input_path),
        "cursor": str(cursor_path),
        "observed": len(results),
        "qualified": sum(1 for item in results if item.get("qualified")),
        "g3_or_above": sum(
            1 for item in results
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
