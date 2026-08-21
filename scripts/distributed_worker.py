#!/usr/bin/env python3
"""GitHub Actions/local entrypoint for the Distributed AgentOS MVP worker."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from runtime_core.canonical_ir import CanonicalIR
from runtime_core.remote_runtime import RemoteRuntimeWorker


def _validate(ir: CanonicalIR) -> dict:
    return {
        "validated": True,
        "project_id": ir.project_id,
        "goal": ir.goal,
        "payload_keys": sorted(ir.payload),
    }


def build_worker(runtime_id: str) -> RemoteRuntimeWorker:
    worker = RemoteRuntimeWorker(runtime_id)
    worker.register("agentos.ir.validate", _validate)
    return worker


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, help="Path to Canonical IR JSON")
    parser.add_argument("--input-json", help="Canonical IR JSON string")
    parser.add_argument("--output", type=Path, default=Path("distributed-runtime-result.json"))
    parser.add_argument("--runtime-id", default=os.getenv("AGENTOS_RUNTIME_ID", "github-actions-worker"))
    args = parser.parse_args()

    if bool(args.input) == bool(args.input_json):
        parser.error("provide exactly one of --input or --input-json")

    raw = args.input.read_text(encoding="utf-8") if args.input else args.input_json
    ir = CanonicalIR.from_json(raw)
    result = build_worker(args.runtime_id).execute(ir)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": result.status, "output": str(args.output), "input_ir_id": ir.ir_id}))
    return 0 if result.status == "succeeded" else 2


if __name__ == "__main__":
    raise SystemExit(main())
