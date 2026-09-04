from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agentos_node.product_employee_worker import GovernedProductEmployeeWorker, SUPPORTED_PRODUCT_RUNNERS

RESULT_SCHEMAS = {
    "zeus_writer_v1": "agentos.zeus-writer-worker-cli-result/v1",
    "youtube_ai_manager_scan_v1": "agentos.youtube-ai-manager-scan-worker-cli-result/v1",
}


def _absolute_path(value: str, field: str) -> str:
    path = Path(str(value or "").strip()).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError(f"{field}_must_be_absolute")
    return str(path.resolve())


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("positive_integer_required") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("positive_integer_required")
    return number


def _safe_output(runner_kind: str, state: Any) -> dict[str, Any]:
    schema = RESULT_SCHEMAS[runner_kind]
    if state is None:
        return {
            "schema": schema,
            "status": "idle",
            "work_performed": False,
            "credential_exposed": False,
            "session_identity_exposed": False,
            "verified_marker_emitted": False,
        }
    return {
        "schema": schema,
        "status": state.status,
        "work_performed": state.status in {"checkpointed", "completed", "unknown"},
        "employee_id": state.employee_id,
        "assignment_id": state.assignment_id,
        "wake_id": state.wake_id,
        "presence_generation": state.presence_generation,
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
        prog="agentos-product-employee-worker",
        description="Run one fixed governed product Employee dry-run checkpoint. No product mutation authority is granted.",
    )
    parser.add_argument("--runner-kind", required=True, choices=sorted(SUPPORTED_PRODUCT_RUNNERS))
    parser.add_argument("--runtime-root", required=True, type=lambda value: _absolute_path(value, "runtime_root"))
    parser.add_argument("--wake-root", required=True, type=lambda value: _absolute_path(value, "wake_root"))
    parser.add_argument("--worker-state-root", required=True, type=lambda value: _absolute_path(value, "worker_state_root"))
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--lease-seconds", type=int, default=60)
    parser.add_argument("--wake-id", required=True)
    parser.add_argument("--presence-generation", required=True, type=_positive_int)
    parser.add_argument("--once", action="store_true", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    worker = GovernedProductEmployeeWorker(
        runtime_root=args.runtime_root,
        wake_root=args.wake_root,
        worker_state_root=args.worker_state_root,
        node_id=args.node_id,
        runner_kind=args.runner_kind,
        lease_seconds=args.lease_seconds,
    )
    state = worker.process_exact(
        wake_id=args.wake_id,
        presence_generation=args.presence_generation,
    )
    print(json.dumps(_safe_output(args.runner_kind, state), ensure_ascii=False, sort_keys=True))
    if state is None or state.status in {"checkpointed", "completed"}:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
