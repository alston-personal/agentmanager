#!/usr/bin/env python3
"""Export/consume the Web Agent Adapter wire envelope."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentos_node.web_agent_adapter import WebAgentAdapter
from runtime_core.canonical_ir import CanonicalIR


def _load_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} JSON root must be an object")
    return value


def _write(value: dict, output: Path | None) -> None:
    raw = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(raw, encoding="utf-8")
    else:
        print(raw, end="")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--input", type=Path, required=True)
    export_parser.add_argument("--runtime-id", required=True)
    export_parser.add_argument("--output", type=Path)

    complete_parser = subparsers.add_parser("complete")
    complete_parser.add_argument("--input", type=Path, required=True)
    complete_parser.add_argument("--response", type=Path, required=True)
    complete_parser.add_argument("--runtime-id", required=True)
    complete_parser.add_argument("--output", type=Path)

    args = parser.parse_args()
    ir = CanonicalIR.from_dict(_load_object(args.input))
    adapter = WebAgentAdapter(args.runtime_id)

    if args.command == "export":
        _write(adapter.build_request(ir), args.output)
        return 0

    result = adapter.consume_response(ir, _load_object(args.response))
    _write(result.to_dict(), args.output)
    return 0 if result.status == "succeeded" else 2


if __name__ == "__main__":
    raise SystemExit(main())
