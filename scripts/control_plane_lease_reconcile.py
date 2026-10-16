#!/usr/bin/env python3
"""One-shot bounded lease reconciliation adapter for existing AgentOS Supervisor.

Not a scheduler or authority grant. Never replays external effects.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_core.control_plane import ControlPlaneStore


def reconcile(db_path: Path | str | None = None) -> dict:
    store = ControlPlaneStore(db_path)
    expired = store.expire_overdue_leases()
    return {
        "schema": "agentos.control-plane-lease-reconcile/v1",
        "expired_count": len(expired),
        "tasks": [
            {
                "task_id": item["taskId"],
                "status": item["status"],
                "side_effect_state": (item["result"] or {}).get("sideEffectState"),
                "recovery_required": (item["result"] or {}).get("recoveryRequired"),
            }
            for item in expired
        ],
        "auto_replayed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=None)
    args = parser.parse_args()
    print(json.dumps(reconcile(args.db_path), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
