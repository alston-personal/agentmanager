#!/usr/bin/env python3
"""Create reviewable Experience candidates from bounded historical summaries."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agentos_node.conversation_backfill import backfill_conversation_candidates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--projects-root", required=True)
    parser.add_argument("--candidate-root", required=True)
    parser.add_argument("--historical-ir-root", help="output root for immutable Historical IR records")
    parser.add_argument("--max-conversations", type=int, default=100)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = backfill_conversation_candidates(
        projects_root=Path(args.projects_root),
        candidate_root=Path(args.candidate_root),
        historical_ir_root=Path(args.historical_ir_root) if args.historical_ir_root else None,
        max_conversations=args.max_conversations,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
