#!/usr/bin/env python3
"""Read-only Core IR preflight. Same validator runs inside the publisher lock."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_core.ir_validation import validate_ir_change


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--parent", type=Path)
    parser.add_argument("--writer", choices=("explicit", "ir_stop_sync"), default="explicit")
    args = parser.parse_args()
    try:
        candidate = json.loads(args.candidate.read_text())
        parent = json.loads(args.parent.read_text()) if args.parent else None
        result = validate_ir_change(candidate, parent=parent, writer=args.writer)
    except (ValueError, OSError) as exc:
        # Do not echo input files or potentially sensitive parser diagnostics.
        code = str(exc) if str(exc).startswith("IR_VALIDATION_FAILED:") else "INPUT_UNREADABLE_OR_INVALID"
        print(json.dumps({"verdict": "FAIL", "error": code}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
