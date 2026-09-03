from __future__ import annotations

import copy
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_core.active_continuation import resolve_active_continuation
from agent_core.historical_ir import discover_historical_irs
from agentos_node.one_mcp import OracleLocalGateway

SURFACE = "codex-local"
EXECUTOR_CLASS = "openai-codex-local"
RECEIPT_SCHEMA = "agentos.codex-one-active-resolve-receipt/v1"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _runtime_source_commit() -> str | None:
    explicit = str(os.environ.get("AGENTOS_RUNTIME_SOURCE_COMMIT") or "").strip()
    if explicit:
        return explicit
    candidate = Path(__file__).resolve().parents[1].name
    return candidate if len(candidate) >= 12 else None


def _receipt_path(data_root: Path) -> Path:
    explicit = str(os.environ.get("AGENTOS_CODEX_ONE_RECEIPT_PATH") or "").strip()
    if explicit:
        return Path(explicit).expanduser()
    return data_root / "runtime" / "codex-one-active-resolve-last.json"


def _write_resolve_receipt(data_root: Path, selector: dict[str, Any]) -> None:
    path = _receipt_path(data_root)
    if path.is_symlink():
        raise ValueError("Codex ONE receipt path may not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schema": RECEIPT_SCHEMA,
        "recorded_at": _now(),
        "runtime_source_commit": _runtime_source_commit(),
        "surface": SURFACE,
        "executor_class": EXECUTOR_CLASS,
        "executor_identity_bound": True,
        "executor_identity_source": "codex-mcp-config",
        "source": "ONE_ACTIVE_CONTINUATION",
        "selection_source": "ONE_ACTIVE_CONTINUATION",
        "project_id": selector.get("project_id"),
        "index_id": selector.get("index_id"),
        "ir_id": selector.get("ir_id"),
        "credential_exposed": False,
    }
    fd, raw = tempfile.mkstemp(prefix=".codex-one-resolve-", suffix=".tmp", dir=str(path.parent))
    tmp = Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o640)
            json.dump(record, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        tmp = None
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def _project_codex_client(value: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(value)
    result["surface"] = SURFACE
    result["executor_class"] = EXECUTOR_CLASS
    result["executor_identity_bound"] = True
    result["executor_identity_source"] = "codex-mcp-config"
    result["credential_exposed"] = False
    return result


def _active_projection(one: OracleLocalGateway, *, write_receipt: bool = False) -> dict[str, Any]:
    active = resolve_active_continuation(data_root=one.data_root)
    selector = active["selector"]
    resolution = active["resolution"]
    if write_receipt:
        _write_resolve_receipt(Path(one.data_root), selector)
    return _project_codex_client(
        {
            "schema": "agentos.one-active-resolve/v1",
            "source": "ONE_ACTIVE_CONTINUATION",
            "selection_source": "ONE_ACTIVE_CONTINUATION",
            "selector": {
                "project_id": selector.get("project_id"),
                "index_id": selector.get("index_id"),
                "ir_id": selector.get("ir_id"),
            },
            "resolution": resolution,
            "credential_exposed": False,
        }
    )


def create_server(gateway: OracleLocalGateway | None = None):
    from mcp.server.mcpserver import MCPServer

    one = gateway or OracleLocalGateway()
    server = MCPServer("AgentOS ONE for Codex", version="0.1.0")

    @server.tool()
    def one_status() -> dict[str, Any]:
        """Verify the Codex local harness can reach the trusted Oracle-local ONE projection."""
        return _project_codex_client(one.status())

    @server.tool()
    def one_capabilities() -> dict[str, Any]:
        """Return bounded ONE capabilities available to the Codex local harness."""
        return _project_codex_client(one.capabilities())

    @server.tool()
    def one_resolve_active() -> dict[str, Any]:
        """Resolve the ONE-selected active Canonical IR; never infer current work from IDE workspace state."""
        return _active_projection(one, write_receipt=True)

    @server.tool()
    def one_resolve(project: str) -> dict[str, Any]:
        """Explicitly resolve a named canonical project through ONE."""
        return _project_codex_client(one.resolve(project))

    @server.tool()
    def one_historical_ir_discover(project_id: str, limit: int = 50) -> dict[str, Any]:
        """List bounded Historical IR metadata for review; it never changes active continuation."""
        return _project_codex_client({
            "schema": "agentos.historical-ir-discovery/v1",
            "source": "ONE_HISTORICAL_IR",
            "project_id": project_id,
            "items": discover_historical_irs(project_id, data_root=Path(one.data_root), limit=limit),
            "active_ir_mutated": False,
            "credential_exposed": False,
        })

    return server


def main() -> int:
    create_server().run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
