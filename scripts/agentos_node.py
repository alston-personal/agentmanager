#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_core import governance_directory as governance  # noqa: E402
from agent_core import resource_registry as resources  # noqa: E402

NODE_VERSION = "0.1"

CAPABILITIES = [
    {"id": "governance.resolve", "mode": "read", "description": "Resolve capability responsibility/provider."},
    {"id": "governance.get", "mode": "read", "description": "Read one governance entity."},
    {"id": "governance.list", "mode": "read", "description": "List governance entities."},
    {"id": "resource.query", "mode": "read", "description": "Read/list registered world resources."},
    {"id": "resource.register", "mode": "write", "description": "Register declared resource state."},
    {"id": "resource.verify.site", "mode": "observe", "description": "Targeted site verification."},
]


def emit(value, pretty: bool = True) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2 if pretty else None))


def harvest() -> dict:
    governance.seed_core()
    return {
        "node_contract": "agentos-node/0.1",
        "version": NODE_VERSION,
        "identity": os.environ.get("AGENTOS_NODE_ID") or os.uname().nodename,
        "capabilities": CAPABILITIES,
        "authorities": {
            "governance_roles": ".agent/roles/registry.yaml",
            "governance_directory": str(governance.REGISTRY_PATH),
            "resource_registry": str(resources.REGISTRY_PATH),
            "port_manager": "manager://port",
        },
        "invariant": "Node query/dispatch does not grant execution authority.",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="agentos-node", description="AgentOS node-local canonical query/dispatch surface")
    sub = parser.add_subparsers(dest="domain", required=True)

    sub.add_parser("harvest", help="Advertise node capabilities and canonical authorities")

    g = sub.add_parser("governance", help="Responsibility and provider resolution")
    gs = g.add_subparsers(dest="command", required=True)
    gr = gs.add_parser("resolve"); gr.add_argument("capability")
    gg = gs.add_parser("get"); gg.add_argument("entity_id")
    gl = gs.add_parser("list"); gl.add_argument("--kind")

    r = sub.add_parser("resource", help="Query or verify the Resource Registry")
    rs = r.add_subparsers(dest="command", required=True)
    rl = rs.add_parser("list"); rl.add_argument("--kind")
    rg = rs.add_parser("get"); rg.add_argument("resource_id")
    rr = rs.add_parser("register")
    rr.add_argument("resource_id"); rr.add_argument("--kind", required=True)
    rr.add_argument("--declared-json", required=True); rr.add_argument("--ttl", type=int, default=86400); rr.add_argument("--replace", action="store_true")
    rv = rs.add_parser("verify-site"); rv.add_argument("resource_id")

    args = parser.parse_args(argv)
    governance.seed_core()

    if args.domain == "harvest":
        emit(harvest()); return 0

    if args.domain == "governance":
        if args.command == "resolve":
            result = governance.resolve(args.capability); emit(result); return 0 if result else 4
        if args.command == "get":
            result = governance.get(args.entity_id); emit(result); return 0 if result else 4
        if args.command == "list":
            emit(governance.list_entities(args.kind)); return 0

    if args.domain == "resource":
        if args.command == "list":
            emit(resources.list_resources(args.kind)); return 0
        if args.command == "get":
            result = resources.get(args.resource_id); emit(result); return 0 if result else 4
        if args.command == "register":
            try:
                declared = json.loads(args.declared_json)
                if not isinstance(declared, dict):
                    raise ValueError("--declared-json must be a JSON object")
                emit(resources.register(args.resource_id, args.kind, declared, args.ttl, replace=args.replace)); return 0
            except Exception as exc:
                print(f"error: {exc}", file=sys.stderr); return 2
        if args.command == "verify-site":
            try:
                emit(resources.verify_site(args.resource_id)); return 0
            except Exception as exc:
                print(f"error: {exc}", file=sys.stderr); return 2

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
