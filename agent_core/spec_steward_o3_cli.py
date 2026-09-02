from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_core.employee_runtime import EmployeeRuntime
from agent_core.spec_steward_acceptance import inspect_spec_steward_acceptance
from agent_core.spec_steward_bootstrap import ensure_spec_steward


def _absolute_runtime_root(value: str) -> str:
    path = Path(str(value or "").strip()).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("runtime_root_must_be_absolute")
    return str(path.resolve())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentos-spec-steward-o3",
        description="Explicit Core-side bootstrap/inspection for #197 O3. No ONE dispatch or VERIFIED emission.",
    )
    parser.add_argument("--runtime-root", required=True, type=_absolute_runtime_root)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser(
        "bootstrap",
        help="Idempotently materialize the canonical Spec Steward Employee/WorkItem/assignment only.",
    )
    sub.add_parser(
        "inspect",
        help="Read persisted O3 evidence without mutating Employee/Supervisor/ONE state.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runtime = EmployeeRuntime(args.runtime_root)
    if args.command == "bootstrap":
        result = ensure_spec_steward(runtime)
        payload = result.as_dict()
        payload["verified_marker_emitted"] = False
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "inspect":
        report = inspect_spec_steward_acceptance(runtime)
        print(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True))
        return 0 if report.ready_for_live_marker else 3
    raise RuntimeError("unsupported_spec_steward_o3_command")


if __name__ == "__main__":
    raise SystemExit(main())
