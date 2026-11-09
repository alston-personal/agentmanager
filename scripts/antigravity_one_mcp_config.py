"""Safe Antigravity CLI MCP configuration merge for the existing ONE server.

Never installs packages, rewrites legacy Gemini settings, or changes auth.
Only produces a candidate; runtime activation requires immutable convergence.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

SERVER_NAME = "agentos-one"
GLOBAL_CONFIG = Path("/home/ubuntu/.gemini/config/mcp_config.json")


def merge_config(existing: Mapping[str, Any], *, python: Path, repo: Path,
                 data_root: Path = Path("/home/ubuntu/agent-data")) -> dict[str, Any]:
    # Preserve unrelated servers/settings and fail closed on malformed configuration.
    result = dict(existing)
    servers = result.get("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError("antigravity_mcp_servers_invalid")
    servers = dict(servers)
    expected = {
        "command": str(python),
        "args": ["-m", "agentos_node.one_mcp", "--mode", "oracle-local"],
        "cwd": str(repo),
        "env": {
            "PYTHONPATH": str(repo),
            "AGENT_DATA_ROOT": str(data_root),
            "AGENTOS_CORE_NODE_ID": "oracle-core-node",
        },
    }
    if not python.is_absolute() or not repo.is_absolute() or not data_root.is_absolute():
        raise ValueError("antigravity_mcp_paths_must_be_absolute")
    current = servers.get(SERVER_NAME)
    if current is not None and current != expected:
        raise ValueError("antigravity_one_server_conflict")
    servers[SERVER_NAME] = expected
    result["mcpServers"] = servers
    return result


def load_config(path: Path = GLOBAL_CONFIG) -> dict[str, Any]:
    if not path.exists():
        return {}
    if path.is_symlink():
        raise ValueError("antigravity_mcp_symlink_rejected")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("antigravity_mcp_config_not_object")
    return value


def candidate_json(path: Path, *, python: Path, repo: Path) -> str:
    return json.dumps(merge_config(load_config(path), python=python, repo=repo),
                      ensure_ascii=False, indent=2, sort_keys=True) + "\n"
