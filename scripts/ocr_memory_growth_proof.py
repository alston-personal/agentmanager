#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from agent_core.ocr_growth_proof import run_ocr_growth_proof


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run AgentOS OCR-memory counterfactual Growth Proof benchmark."
    )
    parser.add_argument("--manifest", required=True, help="Benchmark manifest JSON")
    parser.add_argument("--out", default="", help="Optional receipt output path")
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="agentos-growth-proof-") as tmp:
        receipt = run_ocr_growth_proof(manifest, workdir=Path(tmp))

    payload = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True)
    print(payload)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload + "\n", encoding="utf-8")
    return 0 if receipt["verdict"] == "G3" else 2


if __name__ == "__main__":
    raise SystemExit(main())
