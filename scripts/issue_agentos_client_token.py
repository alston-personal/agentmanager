#!/usr/bin/env python3
"""Issue a scoped AgentOS client token locally on the Core host.

This is an administrative bootstrap utility. The plaintext token is printed
once; only its SHA-256 digest is persisted in the Core SQLite store.
"""

from __future__ import annotations

import argparse
import json

from agent_core.client_auth import ClientTokenStore, DEFAULT_IDE_PERMISSIONS
from agent_core.distributed_control_plane import DistributedControlPlane


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db")
    parser.add_argument("--subject", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--ttl-days", type=int, default=1)
    parser.add_argument("--permission", action="append", dest="permissions")
    args = parser.parse_args()

    store = DistributedControlPlane(args.db) if args.db else DistributedControlPlane()
    token_store = ClientTokenStore(store)
    issued = token_store.issue(
        args.subject,
        label=args.label,
        permissions=args.permissions or DEFAULT_IDE_PERMISSIONS,
        ttl_days=args.ttl_days,
    )
    print(json.dumps(issued, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
