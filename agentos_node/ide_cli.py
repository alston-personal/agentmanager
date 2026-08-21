"""Cross-IDE command line adapter for Distributed AgentOS."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

from runtime_core.canonical_ir import CanonicalIR

from .control_plane_client import ControlPlaneClient, ControlPlaneClientError
from .ide_adapter import (
    DEFAULT_CAPABILITY,
    build_ide_ir,
    capture_workspace,
    derive_ide_continuation,
    infer_project_id,
    resolve_workspace,
    write_project_marker,
)


TERMINAL_TASK_STATES = {"succeeded", "failed", "cancelled", "expired"}


def _emit(payload: Any, as_json: bool = False) -> None:
    if as_json or not isinstance(payload, str):
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(payload)


def _client(args: argparse.Namespace) -> ControlPlaneClient:
    gateway = args.gateway or os.environ.get("AGENTOS_CONTROL_PLANE_URL")
    if not gateway:
        raise ValueError("Control Plane URL is required via --gateway or AGENTOS_CONTROL_PLANE_URL")
    return ControlPlaneClient(
        gateway,
        token=os.environ.get("AGENTOS_CONTROL_PLANE_TOKEN"),
        timeout=args.http_timeout,
        allow_insecure_http=args.allow_insecure_http,
    )


def _project(args: argparse.Namespace) -> str:
    root = resolve_workspace(getattr(args, "workspace", None))
    return infer_project_id(root, getattr(args, "project", None))


def _wait(client: ControlPlaneClient, task_id: str, timeout: float, interval: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        response = client.get_task(task_id)
        task = response["task"]
        if task.get("status") in TERMINAL_TASK_STATES:
            return response
        if time.monotonic() >= deadline:
            return {"task": task, "waitTimedOut": True}
        time.sleep(interval)


def _submit_and_maybe_wait(
    client: ControlPlaneClient,
    ir: CanonicalIR,
    args: argparse.Namespace,
) -> dict[str, Any]:
    response = client.submit_ir(ir, target_node_id=getattr(args, "target", None))
    if getattr(args, "wait", False):
        task_id = response["task"]["taskId"]
        response["final"] = _wait(client, task_id, args.timeout, args.interval)
    return response


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Distributed AgentOS IDE Adapter CLI")
    parser.add_argument("--gateway", help="Control Plane URL (or AGENTOS_CONTROL_PLANE_URL)")
    parser.add_argument("--allow-insecure-http", action="store_true")
    parser.add_argument("--http-timeout", type=float, default=30.0)
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON error output")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create a stable .agentos/project.json marker for this workspace")
    init.add_argument("project_id", nargs="?")
    init.add_argument("--workspace")
    init.add_argument("--force", action="store_true")

    status = sub.add_parser("status", help="Show Control Plane, workspace, and project continuity state")
    status.add_argument("--project")
    status.add_argument("--workspace")

    ask = sub.add_parser("ask", help="Submit a new Canonical IR task")
    ask.add_argument("instruction")
    ask.add_argument("--project")
    ask.add_argument("--workspace")
    ask.add_argument("--capability", default=os.environ.get("AGENTOS_DEFAULT_CAPABILITY", DEFAULT_CAPABILITY))
    ask.add_argument("--provider")
    ask.add_argument("--target")
    ask.add_argument("--include-diff", action="store_true")
    ask.add_argument("--wait", action="store_true")
    ask.add_argument("--timeout", type=float, default=300.0)
    ask.add_argument("--interval", type=float, default=2.0)

    cont = sub.add_parser("continue", help="Continue from the project's current Canonical IR")
    cont.add_argument("instruction", nargs="?")
    cont.add_argument("--project")
    cont.add_argument("--workspace")
    cont.add_argument("--capability")
    cont.add_argument("--provider")
    cont.add_argument("--target")
    cont.add_argument("--include-diff", action="store_true")
    cont.add_argument("--wait", action="store_true")
    cont.add_argument("--timeout", type=float, default=300.0)
    cont.add_argument("--interval", type=float, default=2.0)

    delegate = sub.add_parser("delegate", help="Submit work preferring a named Provider Bridge provider")
    delegate.add_argument("provider")
    delegate.add_argument("instruction")
    delegate.add_argument("--project")
    delegate.add_argument("--workspace")
    delegate.add_argument("--capability", default=os.environ.get("AGENTOS_DEFAULT_CAPABILITY", DEFAULT_CAPABILITY))
    delegate.add_argument("--target")
    delegate.add_argument("--include-diff", action="store_true")
    delegate.add_argument("--wait", action="store_true")
    delegate.add_argument("--timeout", type=float, default=300.0)
    delegate.add_argument("--interval", type=float, default=2.0)

    wait = sub.add_parser("wait", help="Wait for one task to reach a terminal state")
    wait.add_argument("task_id")
    wait.add_argument("--timeout", type=float, default=300.0)
    wait.add_argument("--interval", type=float, default=2.0)

    result = sub.add_parser("result", help="Read a task result; defaults to latest project task")
    result.add_argument("task_id", nargs="?")
    result.add_argument("--project")
    result.add_argument("--workspace")

    ir_cmd = sub.add_parser("ir", help="Print the project's current Canonical IR")
    ir_cmd.add_argument("--project")
    ir_cmd.add_argument("--workspace")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            _emit(
                write_project_marker(
                    args.project_id,
                    workspace=args.workspace,
                    force=args.force,
                ),
                True,
            )
            return 0

        client = _client(args)

        if args.command == "status":
            project_id = _project(args)
            payload = {
                "health": client.health(),
                "project": client.get_project_state(project_id),
                "workspace": capture_workspace(args.workspace),
            }
            _emit(payload, True)
            return 0

        if args.command in {"ask", "delegate"}:
            provider = args.provider if args.command == "delegate" else getattr(args, "provider", None)
            ir = build_ide_ir(
                args.instruction,
                workspace=args.workspace,
                project_id=args.project,
                capability=args.capability,
                provider=provider,
                include_diff=args.include_diff,
            )
            _emit(_submit_and_maybe_wait(client, ir, args), True)
            return 0

        if args.command == "continue":
            state = client.get_project_state(_project(args))
            latest = state.get("latestTask")
            if latest and latest.get("status") in {"submitted", "leased", "running"}:
                payload: dict[str, Any] = {
                    "status": "already_in_progress",
                    "task": latest,
                    "currentIR": state.get("currentIR"),
                }
                if args.wait:
                    payload["final"] = _wait(client, latest["taskId"], args.timeout, args.interval)
                _emit(payload, True)
                return 0

            raw_current = state.get("currentIR")
            if not isinstance(raw_current, dict):
                if not args.instruction:
                    raise ValueError("project has no Canonical IR yet; provide an instruction or use `agentos ask`")
                ir = build_ide_ir(
                    args.instruction,
                    workspace=args.workspace,
                    project_id=args.project,
                    capability=args.capability or os.environ.get("AGENTOS_DEFAULT_CAPABILITY", DEFAULT_CAPABILITY),
                    provider=args.provider,
                    include_diff=args.include_diff,
                )
            else:
                current = CanonicalIR.from_dict(raw_current)
                if state.get("currentSource") == "task_continuation" and not args.instruction and not args.capability and not args.provider:
                    ir = current
                else:
                    ir = derive_ide_continuation(
                        current,
                        instruction=args.instruction,
                        workspace=args.workspace,
                        capability=args.capability,
                        provider=args.provider,
                        include_diff=args.include_diff,
                    )
            _emit(_submit_and_maybe_wait(client, ir, args), True)
            return 0

        if args.command == "wait":
            _emit(_wait(client, args.task_id, args.timeout, args.interval), True)
            return 0

        if args.command == "result":
            task_id = args.task_id
            if not task_id:
                state = client.get_project_state(_project(args))
                latest = state.get("latestTask")
                if not latest:
                    raise ValueError("project has no tasks")
                task_id = latest["taskId"]
            _emit(client.get_task(task_id), True)
            return 0

        if args.command == "ir":
            state = client.get_project_state(_project(args))
            current = state.get("currentIR")
            if current is None:
                raise ValueError("project has no Canonical IR")
            _emit(current, True)
            return 0

        parser.error("unknown command")
        return 2
    except (ValueError, ControlPlaneClientError) as exc:
        if args.json:
            _emit({"error": type(exc).__name__, "message": str(exc)}, True)
        else:
            print(f"agentos: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
