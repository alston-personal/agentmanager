from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_core.employee_presence import EmployeePresenceRegistry
from agent_core.employee_runtime import EmployeeRuntime
from agent_core.node_registry import NodeRegistry


SPEC_STEWARD_EMPLOYEE_ID = "agentos-spec-steward"


def _absolute_path(value: str, field: str) -> Path:
    path = Path(str(value or "").strip()).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError(f"{field}_must_be_absolute")
    return path.resolve()


def _runtime_root(value: str) -> Path:
    return _absolute_path(value, "runtime_root")


def _one_root(value: str) -> Path:
    return _absolute_path(value, "one_data_root")


def _existing_node_registry(one_root: Path) -> NodeRegistry:
    fabric_path = one_root / "realm" / "fabric.json"
    nodes_path = one_root / "realm" / "nodes.json"
    if not fabric_path.is_file() or not nodes_path.is_file():
        raise RuntimeError("spec_steward_presence_one_control_plane_state_missing")
    fabric = json.loads(fabric_path.read_text(encoding="utf-8"))
    nodes = json.loads(nodes_path.read_text(encoding="utf-8"))
    if not isinstance(fabric, dict) or fabric.get("schema") != "agentos.realm-fabric/v0.1":
        raise RuntimeError("spec_steward_presence_fabric_schema_invalid")
    if not isinstance(nodes, dict) or nodes.get("schema") != "agentos.node-registry/v0.1":
        raise RuntimeError("spec_steward_presence_node_registry_schema_invalid")
    fabric_realm = str(fabric.get("realm_id") or "").strip()
    nodes_realm = str(nodes.get("realm_id") or "").strip()
    if not fabric_realm or fabric_realm != nodes_realm:
        raise RuntimeError("spec_steward_presence_realm_mismatch")
    return NodeRegistry(path=nodes_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentos-spec-steward-presence",
        description="Bounded #197 O3 Employee presence acceptance utility. Never creates Realm/Node/Employee state.",
    )
    parser.add_argument("--runtime-root", required=True, type=_runtime_root)
    parser.add_argument("--one-data-root", required=True, type=_one_root)
    parser.add_argument("--node-id", required=True)
    sub = parser.add_subparsers(dest="command", required=True)

    bind = sub.add_parser("bind")
    bind.add_argument("--presence-id", required=True)
    bind.add_argument("--ttl-seconds", type=int, default=300)
    bind.add_argument("--supersede-presence-id")

    heartbeat = sub.add_parser("heartbeat")
    heartbeat.add_argument("--presence-id", required=True)
    heartbeat.add_argument("--ttl-seconds", type=int, default=300)

    sub.add_parser("inspect")
    return parser


def _safe_presence(presence) -> dict:
    if presence is None:
        return {
            "schema": "agentos.spec-steward-o3-presence-cli-result/v1",
            "status": "absent",
            "employee_id": SPEC_STEWARD_EMPLOYEE_ID,
            "credential_exposed": False,
            "executor_identity_bound": False,
        }
    return {
        "schema": "agentos.spec-steward-o3-presence-cli-result/v1",
        "status": "present",
        "employee_id": presence.employee_id,
        "node_id": presence.node_id,
        "presence_id": presence.presence_id,
        "generation": presence.generation,
        "bound_at": presence.bound_at,
        "heartbeat_at": presence.heartbeat_at,
        "expires_at": presence.expires_at,
        "required_capability": presence.required_capability,
        "executor_identity_bound": False,
        "credential_exposed": False,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runtime = EmployeeRuntime(args.runtime_root)
    runtime.get_employee(SPEC_STEWARD_EMPLOYEE_ID)
    registry = _existing_node_registry(args.one_data_root)
    presence = EmployeePresenceRegistry(runtime, registry)

    if args.command == "bind":
        result = presence.bind(
            SPEC_STEWARD_EMPLOYEE_ID,
            args.node_id,
            args.presence_id,
            ttl_seconds=args.ttl_seconds,
            supersede_presence_id=args.supersede_presence_id,
        )
    elif args.command == "heartbeat":
        current = presence.get(SPEC_STEWARD_EMPLOYEE_ID)
        if current is None or current.node_id != args.node_id:
            raise PermissionError("spec_steward_presence_node_not_owner")
        result = presence.heartbeat(
            SPEC_STEWARD_EMPLOYEE_ID,
            args.presence_id,
            ttl_seconds=args.ttl_seconds,
        )
    elif args.command == "inspect":
        result = presence.get(SPEC_STEWARD_EMPLOYEE_ID)
    else:
        raise RuntimeError("unsupported_spec_steward_presence_command")

    print(json.dumps(_safe_presence(result), ensure_ascii=False, sort_keys=True))
    return 0 if result is not None else 3


if __name__ == "__main__":
    raise SystemExit(main())
