#!/usr/bin/env python3
"""Run bounded Experience recovery for an already enrolled Node."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentos_node.executor_experience_recovery import run_post_join_experience_recovery


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("/home/ubuntu/agent-data"))
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--projects-root", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--historical-ir-root", type=Path, required=True)
    parser.add_argument("--max-conversations", type=int, default=100)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    nodes = json.loads((args.data_root / "realm" / "nodes.json").read_text(encoding="utf-8"))
    manifest = (nodes.get("nodes") or {}).get(args.node_id)
    if not isinstance(manifest, dict):
        raise ValueError("registered node manifest not found")
    result = run_post_join_experience_recovery(
        manifest,
        projects_root=str(args.projects_root),
        candidate_root=str(args.candidate_root),
        historical_ir_root=str(args.historical_ir_root),
        max_conversations=args.max_conversations,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
