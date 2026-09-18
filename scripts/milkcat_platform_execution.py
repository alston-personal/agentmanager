#!/usr/bin/env python3
"""CLI for governed Milkcat Platform execution accounting.

This adapter is intentionally thin so workflows and other hosts share the same
Python transaction semantics rather than duplicating shell accounting logic.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_core.platform_execution import PlatformExecutionStore
from agent_core.studio_capability_adapter import sync_studio_release_capabilities


def _json_metadata(raw: str | None) -> dict:
    if not raw:
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("metadata must decode to a JSON object")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt-root")
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare")
    prepare.add_argument("--execution-id", required=True)
    prepare.add_argument("--account-id", required=True)
    prepare.add_argument("--credit-cost", required=True, type=int)
    prepare.add_argument("--capability", action="append", required=True)
    prepare.add_argument("--allow-build-when-missing", action="store_true")
    prepare.add_argument("--force-build", action="store_true")
    prepare.add_argument("--override-reason")
    prepare.add_argument("--metadata-json")
    prepare.add_argument(
        "--sync-studio-capabilities",
        action="store_true",
        help="Mirror canonical Studio release capability contracts before resolution.",
    )

    settle = sub.add_parser("settle")
    settle.add_argument("--execution-id", required=True)
    outcome = settle.add_mutually_exclusive_group(required=True)
    outcome.add_argument("--success", action="store_true")
    outcome.add_argument("--failure", action="store_true")
    settle.add_argument("--actual-cost", type=int)
    settle.add_argument("--metadata-json")

    show = sub.add_parser("show")
    show.add_argument("--execution-id", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    store = PlatformExecutionStore(
        receipt_root=Path(args.receipt_root) if args.receipt_root else None
    )

    if args.command == "prepare":
        if args.sync_studio_capabilities:
            sync_studio_release_capabilities()
        receipt = store.prepare(
            execution_id=args.execution_id,
            account_id=args.account_id,
            required_capabilities=args.capability,
            credit_cost=args.credit_cost,
            allow_build_when_missing=args.allow_build_when_missing,
            force_build=args.force_build,
            override_reason=args.override_reason,
            metadata=_json_metadata(args.metadata_json),
        )
    elif args.command == "settle":
        receipt = store.settle(
            args.execution_id,
            succeeded=bool(args.success),
            actual_cost=args.actual_cost,
            metadata=_json_metadata(args.metadata_json),
        )
    else:
        receipt = store.get(args.execution_id)

    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
