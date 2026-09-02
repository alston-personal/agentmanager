from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agentos_node.governed_spec_steward_worker import GovernedSpecStewardWakeWorker


def _absolute_path(value: str, field: str) -> str:
    path = Path(str(value or "").strip()).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError(f"{field}_must_be_absolute")
    return str(path.resolve())


def _runtime_root(value: str) -> str:
    return _absolute_path(value, "runtime_root")


def _wake_root(value: str) -> str:
    return _absolute_path(value, "wake_root")


def _worker_state_root(value: str) -> str:
    return _absolute_path(value, "worker_state_root")


def _presence_generation(value: str) -> int:
    try:
        generation = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("presence_generation_must_be_integer") from exc
    if generation < 1:
        raise argparse.ArgumentTypeError("presence_generation_must_be_positive")
    return generation


def _safe_output(state: Any) -> dict[str, Any]:
    if state is None:
        return {
            "schema": "agentos.spec-steward-o3-worker-cli-result/v1",
            "status": "idle",
            "work_performed": False,
            "credential_exposed": False,
            "session_identity_exposed": False,
            "verified_marker_emitted": False,
        }
    return {
        "schema": "agentos.spec-steward-o3-worker-cli-result/v1",
        "status": state.status,
        "work_performed": state.status in {"checkpointed", "completed", "unknown"},
        "employee_id": state.employee_id,
        "assignment_id": state.assignment_id,
        "wake_id": getattr(state, "wake_id", None),
        "presence_generation": getattr(state, "presence_generation", None),
        "lease_generation": state.lease_generation,
        "thread_head": state.thread_head,
        "error_code": state.error_code,
        "executor_provider": state.executor_provider,
        "executor_model": state.executor_model,
        "credential_exposed": False,
        "session_identity_exposed": False,
        "verified_marker_emitted": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentos-spec-steward-worker",
        description="Run one governed Spec Steward O3 Employee wake. This does not bootstrap state or emit VERIFIED.",
    )
    parser.add_argument("--runtime-root", required=True, type=_runtime_root)
    parser.add_argument("--wake-root", required=True, type=_wake_root)
    parser.add_argument("--worker-state-root", required=True, type=_worker_state_root)
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--lease-seconds", type=int, default=60)
    parser.add_argument("--wake-id", help="Optional exact persisted wake selector; must be paired with --presence-generation.")
    parser.add_argument("--presence-generation", type=_presence_generation)
    parser.add_argument(
        "--once",
        action="store_true",
        required=True,
        help="Required O3 mode: process at most one governed wake, then exit so a later process can prove resume continuity.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    exact_requested = bool(args.wake_id) or args.presence_generation is not None
    if exact_requested and (not args.wake_id or args.presence_generation is None):
        raise SystemExit("--wake-id and --presence-generation must be provided together")

    worker = GovernedSpecStewardWakeWorker(
        runtime_root=args.runtime_root,
        wake_root=args.wake_root,
        worker_state_root=args.worker_state_root,
        node_id=args.node_id,
        lease_seconds=args.lease_seconds,
    )
    if exact_requested:
        state = worker.process_exact(
            wake_id=args.wake_id,
            presence_generation=args.presence_generation,
        )
    else:
        state = worker.process_one()
    print(json.dumps(_safe_output(state), ensure_ascii=False, sort_keys=True))
    if state is None or state.status in {"checkpointed", "completed"}:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
