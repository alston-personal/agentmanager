from __future__ import annotations

import argparse
import fcntl
import json
import os
import uuid
from contextlib import contextmanager
from pathlib import Path
from threading import Event
from typing import Iterator

from agent_core.controller_service import ControllerService
from agent_core.core_supervisor_delivery import (
    SupervisorWakeAuthorityResolver,
    SupervisorWakeCoordinator,
)
from agent_core.core_supervisor_service import CoreSupervisorService
from agent_core.employee_lifecycle import EmployeeLifecycle
from agent_core.employee_presence import EmployeePresenceRegistry
from agent_core.employee_runtime import EmployeeRuntime
from agent_core.employee_wake_delivery import EmployeeWakeDelivery
from agent_core.node_registry import NodeRegistry
from agent_core.realm_fabric import RealmFabricStore


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = str(os.environ.get(name) or default).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"invalid_{name.lower()}") from exc
    if value < minimum or value > maximum:
        raise ValueError(f"invalid_{name.lower()}")
    return value


def _runtime_root(value: str | None = None) -> Path:
    raw = str(value or os.environ.get("AGENTOS_EMPLOYEE_RUNTIME_ROOT") or "").strip()
    if not raw:
        data_root = str(os.environ.get("AGENTOS_DATA_ROOT") or "").strip()
        if data_root:
            raw = str(Path(data_root) / "employee-runtime")
    if not raw:
        raise ValueError("employee_runtime_root_required")
    root = Path(raw).expanduser()
    if not root.is_absolute():
        raise ValueError("employee_runtime_root_must_be_absolute")
    return root.resolve()


def _service_id(value: str | None = None) -> str:
    text = str(value or os.environ.get("AGENTOS_SUPERVISOR_SERVICE_ID") or "agentos-core-supervisor").strip()
    if not text or len(text) > 120 or any(ch in text for ch in "/\\\0"):
        raise ValueError("invalid_supervisor_service_id")
    return text


def _delivery_mode(value: str | None = None) -> str:
    mode = str(value or os.environ.get("AGENTOS_SUPERVISOR_DELIVERY_MODE") or "disabled").strip().lower()
    if mode not in {"disabled", "one_direct"}:
        raise ValueError("invalid_supervisor_delivery_mode")
    return mode


def _one_data_root(value: str | None = None) -> Path:
    raw = str(
        value
        or os.environ.get("AGENTOS_SUPERVISOR_ONE_DATA_ROOT")
        or os.environ.get("AGENTOS_DATA_ROOT")
        or os.environ.get("AGENT_DATA_ROOT")
        or ""
    ).strip()
    if not raw:
        raise ValueError("supervisor_one_data_root_required")
    root = Path(raw).expanduser()
    if not root.is_absolute():
        raise ValueError("supervisor_one_data_root_must_be_absolute")
    return root.resolve()


def _require_existing_one_root(root: Path) -> str:
    """Fail closed unless root already contains one coherent ONE Realm."""
    fabric_path = root / "realm" / "fabric.json"
    nodes_path = root / "realm" / "nodes.json"
    if not fabric_path.is_file() or not nodes_path.is_file():
        raise RuntimeError("supervisor_one_control_plane_state_missing")
    try:
        fabric = json.loads(fabric_path.read_text(encoding="utf-8"))
        nodes = json.loads(nodes_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("supervisor_one_control_plane_state_invalid") from exc
    if not isinstance(fabric, dict) or fabric.get("schema") != "agentos.realm-fabric/v0.1":
        raise RuntimeError("supervisor_one_fabric_schema_invalid")
    if not isinstance(nodes, dict) or nodes.get("schema") != "agentos.node-registry/v0.1":
        raise RuntimeError("supervisor_one_node_registry_schema_invalid")
    fabric_realm = str(fabric.get("realm_id") or "").strip()
    node_realm = str(nodes.get("realm_id") or "").strip()
    if not fabric_realm or not node_realm or fabric_realm != node_realm:
        raise RuntimeError("supervisor_one_control_plane_realm_mismatch")
    return fabric_realm


def _instance_owner(service_id: str) -> str:
    return f"{service_id}.{uuid.uuid4().hex[:12]}"


def _heartbeat_step(remaining_seconds: int, leader_lease_seconds: int) -> int:
    """Return a wait chunk short enough that idle backoff never outlives leadership."""
    if remaining_seconds <= 0:
        return 0
    safe = max(1, int(leader_lease_seconds) // 2)
    return min(int(remaining_seconds), safe)


@contextmanager
def _process_singleton_lock(root: Path) -> Iterator[None]:
    """Hold an OS lock for this runtime root for the lifetime of one daemon process."""
    path = root / "supervisor" / "process.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("supervisor_process_already_active") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def build_service(
    *,
    runtime_root: Path,
    service_id: str,
    base_poll_seconds: int,
    max_poll_seconds: int,
    delivery_mode: str = "disabled",
    one_data_root: Path | None = None,
) -> CoreSupervisorService:
    runtime = EmployeeRuntime(runtime_root)
    lifecycle = EmployeeLifecycle(runtime)
    service = CoreSupervisorService(
        lifecycle,
        owner_id=_instance_owner(service_id),
        base_poll_seconds=base_poll_seconds,
        max_poll_seconds=max_poll_seconds,
    )
    mode = _delivery_mode(delivery_mode)
    if mode == "disabled":
        return service

    root = _one_data_root(str(one_data_root) if one_data_root is not None else None)
    _require_existing_one_root(root)
    node_registry = NodeRegistry(path=root / "realm" / "nodes.json")
    fabric = RealmFabricStore(path=root / "realm" / "fabric.json", node_registry=node_registry)
    controller = ControllerService(fabric)
    presence = EmployeePresenceRegistry(runtime, node_registry)
    wake_delivery = EmployeeWakeDelivery(presence, controller)
    authority = SupervisorWakeAuthorityResolver(requested_transport="one_direct")
    coordinator = SupervisorWakeCoordinator(
        service,
        wake_delivery,
        authority,
        available_transports={"one_direct": True},
    )
    service.attach_delivery_driver(coordinator)
    return service


def run_persistent(
    service: CoreSupervisorService,
    *,
    stop_event: Event | None = None,
    leader_lease_seconds: int = 30,
) -> None:
    """Run persistent reconcile cycles and any explicitly attached governed S4 driver."""
    stopper = stop_event or Event()
    retry_seconds = max(1, min(5, leader_lease_seconds // 2))

    while not stopper.is_set():
        try:
            leader = service.claim_leader(lease_seconds=leader_lease_seconds)
            break
        except RuntimeError as exc:
            if str(exc) != "supervisor_leader_already_active":
                raise
            stopper.wait(retry_seconds)
    else:
        return

    while not stopper.is_set():
        receipt = service.run_cycle(leader.generation)
        remaining = int(receipt.next_poll_seconds)
        while remaining > 0 and not stopper.is_set():
            step = _heartbeat_step(remaining, leader_lease_seconds)
            if stopper.wait(step):
                return
            remaining -= step
            leader = service.heartbeat_leader(
                leader.generation,
                lease_seconds=leader_lease_seconds,
            )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgentOS Core Supervisor (S3 observe/plan; S4 governed delivery opt-in)")
    parser.add_argument("--runtime-root")
    parser.add_argument("--service-id")
    parser.add_argument("--once", action="store_true", help="Run one reconcile cycle and exit")
    parser.add_argument("--health", action="store_true", help="Print durable Supervisor health and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.once and args.health:
        raise ValueError("choose_once_or_health")

    root = _runtime_root(args.runtime_root)
    service_id = _service_id(args.service_id)
    base_poll = _env_int("AGENTOS_SUPERVISOR_BASE_POLL_SECONDS", 5, minimum=1, maximum=300)
    max_poll = _env_int("AGENTOS_SUPERVISOR_MAX_POLL_SECONDS", 60, minimum=base_poll, maximum=3600)
    leader_lease = _env_int("AGENTOS_SUPERVISOR_LEADER_LEASE_SECONDS", 30, minimum=5, maximum=300)
    delivery_mode = _delivery_mode()
    one_root = _one_data_root() if delivery_mode == "one_direct" else None

    service = build_service(
        runtime_root=root,
        service_id=service_id,
        base_poll_seconds=base_poll,
        max_poll_seconds=max_poll,
        delivery_mode=delivery_mode,
        one_data_root=one_root,
    )

    if args.health:
        payload = service.health()
        if service.delivery_driver is not None:
            payload["delivery"] = service.delivery_driver.health()
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0

    with _process_singleton_lock(root):
        if args.once:
            leader = service.claim_leader(lease_seconds=leader_lease)
            receipt = service.run_cycle(leader.generation)
            print(json.dumps(receipt.__dict__ if hasattr(receipt, "__dict__") else {
                name: getattr(receipt, name) for name in receipt.__dataclass_fields__
            }, ensure_ascii=False, sort_keys=True))
            return 0
        run_persistent(service, leader_lease_seconds=leader_lease)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
