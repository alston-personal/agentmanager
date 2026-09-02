from __future__ import annotations

import argparse
import json
import os
from contextlib import contextmanager
from pathlib import Path
from threading import Event
from typing import Iterator

from agentos_node.employee_worker_host_runtime import ExactEmployeeWorkerHost


def _absolute_env(name: str, fallback: str | None = None) -> Path:
    raw = str(os.environ.get(name) or fallback or "").strip()
    if not raw:
        raise ValueError(f"{name.lower()}_required")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{name.lower()}_must_be_absolute")
    return path.resolve()


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = str(os.environ.get(name) or default).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"invalid_{name.lower()}") from exc
    if value < minimum or value > maximum:
        raise ValueError(f"invalid_{name.lower()}")
    return value


def _node_id() -> str:
    value = str(os.environ.get("AGENTOS_EMPLOYEE_WORKER_NODE_ID") or "").strip()
    if not value or len(value) > 256 or any(ch in value for ch in "/\\\0"):
        raise ValueError("invalid_agentos_employee_worker_node_id")
    return value


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _require_separate_roots(*roots: Path) -> None:
    resolved = [root.resolve() for root in roots]
    if len(set(resolved)) != len(resolved):
        raise ValueError("employee_worker_host_roots_must_be_distinct")
    for index, left in enumerate(resolved):
        for right in resolved[index + 1 :]:
            if _inside(left, right) or _inside(right, left):
                raise ValueError("employee_worker_host_roots_must_not_overlap")


@contextmanager
def _singleton_lock(root: Path) -> Iterator[None]:
    """Hold one OS-level lock per shared Employee Worker Host state root."""
    root.mkdir(parents=True, exist_ok=True)
    path = root / "process.lock"
    handle = path.open("a+", encoding="utf-8")
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            handle.write("0")
            handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError("employee_worker_host_process_already_active") from exc
        else:
            import fcntl

            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("employee_worker_host_process_already_active") from exc
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def build_host() -> ExactEmployeeWorkerHost:
    data_root_raw = str(os.environ.get("AGENTOS_DATA_ROOT") or os.environ.get("AGENT_DATA_ROOT") or "").strip()
    data_root = Path(data_root_raw).expanduser().resolve() if data_root_raw else None
    runtime_root = _absolute_env(
        "AGENTOS_EMPLOYEE_RUNTIME_ROOT",
        str(data_root / "employee-runtime") if data_root else None,
    )
    wake_root = _absolute_env("AGENTOS_EMPLOYEE_WAKE_ROOT")
    host_state_root = _absolute_env(
        "AGENTOS_EMPLOYEE_WORKER_HOST_STATE_ROOT",
        str(data_root / "employee-worker-host") if data_root else None,
    )
    worker_state_root = _absolute_env(
        "AGENTOS_EMPLOYEE_WORKER_STATE_ROOT",
        str(data_root / "employee-worker-state") if data_root else None,
    )
    _require_separate_roots(runtime_root, wake_root, host_state_root, worker_state_root)
    return ExactEmployeeWorkerHost(
        runtime_root=runtime_root,
        wake_root=wake_root,
        host_state_root=host_state_root,
        worker_state_root=worker_state_root,
        node_id=_node_id(),
        child_timeout_seconds=_env_int(
            "AGENTOS_EMPLOYEE_WORKER_CHILD_TIMEOUT_SECONDS", 180, minimum=5, maximum=1800
        ),
        lease_seconds=_env_int("AGENTOS_EMPLOYEE_WORKER_LEASE_SECONDS", 60, minimum=30, maximum=3600),
    )


def run_forever(host: ExactEmployeeWorkerHost, *, stop_event: Event | None = None) -> None:
    stopper = stop_event or Event()
    poll_seconds = _env_int("AGENTOS_EMPLOYEE_WORKER_POLL_SECONDS", 2, minimum=1, maximum=60)
    with _singleton_lock(host.host_state_root):
        while not stopper.is_set():
            result = host.process_one()
            if result is None:
                stopper.wait(poll_seconds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentos-employee-worker-host")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Process at most one source-registered wake.")
    mode.add_argument("--status", action="store_true", help="Print sanitized host status and exit.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    host = build_host()
    if args.status:
        print(json.dumps(host.status(), ensure_ascii=False, sort_keys=True))
        return 0
    if args.once:
        with _singleton_lock(host.host_state_root):
            result = host.process_one()
        print(
            json.dumps(
                {
                    "schema": "agentos.employee-worker-host-once/v1",
                    "status": "idle" if result is None else result.get("status"),
                    "work_observed": result is not None,
                    "credential_exposed": False,
                    "session_identity_exposed": False,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0 if result is None or result.get("status") in {"checkpointed", "completed"} else 2
    run_forever(host)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
