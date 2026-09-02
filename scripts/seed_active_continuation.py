#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

from agent_core.active_continuation import (
    activate_continuation,
    read_active_continuation,
    resolve_active_continuation,
    selector_path,
)
from agent_core.resolve_facade import resolve_continuation

PROJECT_ID = "agentos-core"


def _data_root() -> Path:
    return Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))


def main() -> int:
    root = _data_root()
    path = selector_path(root)
    if path.exists():
        try:
            current = resolve_active_continuation(data_root=root)
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "schema": "agentos.active-continuation-seed/v1",
                        "ok": False,
                        "seeded": False,
                        "reason": f"existing selector is invalid/stale: {type(exc).__name__}: {exc}",
                        "path": str(path),
                        "credential_exposed": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
            return 3
        selector = current["selector"]
        print(
            json.dumps(
                {
                    "schema": "agentos.active-continuation-seed/v1",
                    "ok": True,
                    "seeded": False,
                    "reason": "existing selector is current",
                    "path": str(path),
                    "project_id": selector["project_id"],
                    "index_id": selector["index_id"],
                    "ir_id": selector["ir_id"],
                    "credential_exposed": False,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    resolved = resolve_continuation(PROJECT_ID, data_root=root)
    head = resolved.get("execution_head") if isinstance(resolved.get("execution_head"), dict) else {}
    continuation = resolved.get("continuation") if isinstance(resolved.get("continuation"), dict) else {}
    ir = continuation.get("canonical_ir") if isinstance(continuation.get("canonical_ir"), dict) else {}
    index_id = str(head.get("index_id") or "").strip()
    ir_id = str(ir.get("ir_id") or "").strip()
    if not index_id or not ir_id or str(ir.get("index_id") or "").strip() != index_id:
        raise RuntimeError("agentos-core has no valid canonical generation to seed as active")

    receipt = activate_continuation(
        PROJECT_ID,
        index_id=index_id,
        ir_id=ir_id,
        reason="initial ONE active continuation selector; only canonical publisher currently supported is agentos-core",
        data_root=root,
    )
    print(
        json.dumps(
            {
                "schema": "agentos.active-continuation-seed/v1",
                "ok": True,
                "seeded": True,
                "path": str(path),
                "project_id": PROJECT_ID,
                "index_id": index_id,
                "ir_id": ir_id,
                "credential_exposed": False,
                "activation_receipt": receipt,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
