from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import time
import uuid
from pathlib import Path
from typing import Any

from agent_core.employee_presence import EmployeePresenceRegistry, WAKE_CAPABILITY
from agent_core.employee_runtime import EmployeeRuntime
from agent_core.node_registry import NodeRegistry
from agent_core.realm_fabric import RealmFabricStore
from agentos_node.employee_wake_inbox import deliver_employee_wake
from agentos_node.thin_client_transport import ClientConfig, ThinClientTransport

NODE_ID = "oracle-employee-wake-node"
EMPLOYEE_IDS = ("zeus-writer", "youtube-ai-manager")
NODE_RECEIPT_SCHEMA = "agentos.node-receipt/v0.1"


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class EmployeeWakeOnlyClient:
    """Least-privilege ONE client: authenticated wake delivery and nothing else."""

    def __init__(self, realm_id: str, node_id: str, wake_root: Path) -> None:
        if node_id != NODE_ID:
            raise ValueError("employee_wake_node_id_not_allowed")
        self.realm_id = str(realm_id or "").strip()
        self.node_id = node_id
        self.wake_root = Path(wake_root).expanduser().resolve()
        if not self.realm_id:
            raise ValueError("employee_wake_realm_id_required")

    def capability_manifest(self) -> dict[str, Any]:
        return {
            "schema": "agentos.node-manifest/v0.1",
            "realm_id": self.realm_id,
            "node_id": self.node_id,
            "role": "client",
            "hostname": socket.gethostname(),
            "platform": platform.system(),
            "platform_release": platform.release(),
            "observed_at": _utc_now(),
            "capabilities": [WAKE_CAPABILITY],
            "tool_presence": {},
            "surface_inventory": {"surfaces": []},
            "workspace_roots": {"readable": [], "writable": []},
        }

    def heartbeat(self) -> dict[str, Any]:
        manifest = self.capability_manifest()
        return {
            "schema": "agentos.node-heartbeat/v0.1",
            "realm_id": self.realm_id,
            "node_id": self.node_id,
            "role": "client",
            "status": "online",
            "observed_at": _utc_now(),
            "capability_count": 1,
            "surface_count": 0,
            "manifest": manifest,
        }

    def execute(self, task: dict[str, Any]) -> dict[str, Any]:
        started = _utc_now()
        receipt: dict[str, Any] = {
            "schema": NODE_RECEIPT_SCHEMA,
            "realm_id": self.realm_id,
            "node_id": self.node_id,
            "task_id": task.get("task_id"),
            "action": task.get("action"),
            "started_at": started,
            "completed_at": None,
            "ok": False,
            "cognition_ids_used": [],
        }
        try:
            if task.get("schema") != "agentos.node-task/v0.1":
                raise ValueError("invalid task schema")
            if task.get("action") != WAKE_CAPABILITY:
                raise PermissionError("employee_wake_node_action_not_allowed")
            receipt.update(deliver_employee_wake(task, self.wake_root, expected_node_id=self.node_id))
            receipt["ok"] = True
        except Exception as exc:
            receipt["error"] = f"{type(exc).__name__}: {exc}"
        receipt["completed_at"] = _utc_now()
        receipt["credential_exposed"] = False
        receipt["executor_invoked"] = False
        return receipt


def _build_transport(config: ClientConfig, wake_root: Path) -> ThinClientTransport:
    return ThinClientTransport(EmployeeWakeOnlyClient(config.realm_id, config.node_id, wake_root), config)


def bootstrap_local_enrollment(*, data_root: Path, config_path: Path, wake_root: Path) -> ClientConfig:
    data_root = Path(data_root).expanduser().resolve()
    config_path = Path(config_path).expanduser().resolve()
    wake_root = Path(wake_root).expanduser().resolve()
    registry = NodeRegistry(data_root / "realm" / "nodes.json")
    fabric = RealmFabricStore(data_root / "realm" / "fabric.json", node_registry=registry)
    realm = fabric.load()
    realm_id = str(realm.get("realm_id") or "").strip()
    if not realm_id:
        raise RuntimeError("employee_wake_realm_not_initialized")

    if config_path.exists():
        config = ClientConfig.load(config_path)
        if config.realm_id != realm_id or config.node_id != NODE_ID or config.one_url.rstrip("/") != "http://127.0.0.1:8780":
            raise RuntimeError("employee_wake_existing_config_mismatch")
        fabric.authenticate(config.node_id, config.node_token)
        return config

    existing = (realm.get("nodes") or {}).get(NODE_ID)
    if existing and not existing.get("revoked_at"):
        raise RuntimeError("employee_wake_node_enrolled_without_local_config")

    client = EmployeeWakeOnlyClient(realm_id, NODE_ID, wake_root)
    invite = fabric.create_invite(expires_minutes=5, label="core-238-product-employee-wake-node")
    result = fabric.enroll(invite_id=str(invite["invite_id"]), code=str(invite["code"]), manifest=client.capability_manifest())
    config = ClientConfig(
        one_url="http://127.0.0.1:8780",
        realm_id=realm_id,
        node_id=NODE_ID,
        node_token=str(result["node_token"]),
        poll_seconds=2.0,
    )
    config.save(config_path)
    return config


def _bind_presences(*, runtime: EmployeeRuntime, registry: NodeRegistry, node_id: str, presence_id: str) -> EmployeePresenceRegistry:
    presence = EmployeePresenceRegistry(runtime, registry)
    for employee_id in EMPLOYEE_IDS:
        existing = presence.get(employee_id)
        presence.bind(
            employee_id,
            node_id,
            presence_id,
            ttl_seconds=120,
            supersede_presence_id=existing.presence_id if existing else None,
        )
    return presence


def run_daemon(*, data_root: Path, config_path: Path, wake_root: Path, runtime_root: Path, once: bool = False) -> int:
    data_root = Path(data_root).expanduser().resolve()
    config = ClientConfig.load(config_path)
    if config.node_id != NODE_ID:
        raise RuntimeError("employee_wake_node_config_identity_mismatch")
    wake_root.mkdir(parents=True, exist_ok=True)
    runtime = EmployeeRuntime(Path(runtime_root).expanduser().resolve())
    for employee_id in EMPLOYEE_IDS:
        runtime.get_employee(employee_id)
    registry = NodeRegistry(data_root / "realm" / "nodes.json")
    transport = _build_transport(config, wake_root)
    presence_id = "presence-" + uuid.uuid4().hex

    # Heartbeat Node first so presence eligibility is independently observable.
    transport.heartbeat()
    presences = _bind_presences(runtime=runtime, registry=registry, node_id=NODE_ID, presence_id=presence_id)

    while True:
        transport.run_once()
        for employee_id in EMPLOYEE_IDS:
            presences.heartbeat(employee_id, presence_id, ttl_seconds=120)
        if once:
            return 0
        time.sleep(max(1.0, float(config.poll_seconds)))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentos-employee-wake-node")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--wake-root", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("bootstrap")
    p_run = sub.add_parser("run")
    p_run.add_argument("--once", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "bootstrap":
        args.wake_root.expanduser().resolve().mkdir(parents=True, exist_ok=True)
        config = bootstrap_local_enrollment(data_root=args.data_root, config_path=args.config, wake_root=args.wake_root)
        print(json.dumps({
            "schema": "agentos.employee-wake-node-bootstrap/v1",
            "ok": True,
            "node_id": config.node_id,
            "realm_id": config.realm_id,
            "capabilities": [WAKE_CAPABILITY],
            "credential_exposed": False,
        }, sort_keys=True))
        return 0
    return run_daemon(
        data_root=args.data_root,
        config_path=args.config,
        wake_root=args.wake_root,
        runtime_root=args.runtime_root,
        once=args.once,
    )


if __name__ == "__main__":
    raise SystemExit(main())
