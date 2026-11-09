#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import venv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MCP_PACKAGE = "mcp>=2,<3"
SERVER_NAME = "agentos-one"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def settings_path() -> Path:
    explicit = os.environ.get("AGENTOS_GEMINI_CLI_SETTINGS")
    return Path(explicit).expanduser() if explicit else Path.home() / ".gemini" / "settings.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("gemini_settings_not_object")
    return value


def venv_python(root: Path) -> Path:
    return root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def ensure_mcp_venv(root: Path) -> Path:
    python = venv_python(root)
    if not python.exists():
        root.parent.mkdir(parents=True, exist_ok=True)
        venv.EnvBuilder(with_pip=True).create(root)
    check = subprocess.run([str(python), "-c", "from mcp.server import MCPServer"], capture_output=True, text=True)
    if check.returncode:
        install = subprocess.run(
            [str(python), "-m", "pip", "install", "--disable-pip-version-check", MCP_PACKAGE],
            capture_output=True,
            text=True,
        )
        if install.returncode:
            raise RuntimeError("mcp_sdk_install_failed")
    return python


def merge_settings(path: Path, *, python: Path, root: Path, mode: str) -> dict[str, Any]:
    settings = load_json(path)
    env = {
        "PYTHONPATH": str(root),
        "AGENTOS_ONE_MCP_MODE": mode,
    }
    if mode == "oracle-local":
        env["AGENT_DATA_ROOT"] = os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data")
        env["AGENTOS_CORE_NODE_ID"] = os.environ.get("AGENTOS_CORE_NODE_ID", "oracle-core-node")

    servers = settings.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError("mcpServers_not_object")
    servers[SERVER_NAME] = {
        "command": str(python),
        "args": ["-m", "agentos_node.one_mcp"],
        "cwd": str(root),
        "env": env,
        "trust": False,
    }

    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("hooks_not_object")
    hooks["SessionStart"] = [
        {
            "matcher": "startup",
            "sequential": True,
            "hooks": [
                {
                    "name": "agentos-one-sessionstart",
                    "type": "command",
                    "command": f'"{python}" -m agentos_node.gemini_cli_one_hook',
                    "timeout": 12000,
                    "description": "Hydrate AgentOS ONE canonical continuation at Gemini CLI session start",
                }
            ],
        },
        {
            "matcher": "resume",
            "sequential": True,
            "hooks": [
                {
                    "name": "agentos-one-sessionstart",
                    "type": "command",
                    "command": f'"{python}" -m agentos_node.gemini_cli_one_hook',
                    "timeout": 12000,
                }
            ],
        },
        {
            "matcher": "clear",
            "sequential": True,
            "hooks": [
                {
                    "name": "agentos-one-sessionstart",
                    "type": "command",
                    "command": f'"{python}" -m agentos_node.gemini_cli_one_hook',
                    "timeout": 12000,
                }
            ],
        },
    ]

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        shutil.copy2(path, path.with_name(path.name + f".agentos-backup-{stamp}"))
    tmp = path.with_suffix(".json.agentos.tmp")
    tmp.write_text(json.dumps(settings, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
    return settings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Install Gemini CLI -> AgentOS ONE adapter")
    parser.add_argument("--repo", type=Path, default=repo_root())
    parser.add_argument("--mode", choices=("client", "oracle-local"), default="oracle-local")
    args = parser.parse_args(argv)
    root = args.repo.expanduser().resolve()
    python = ensure_mcp_venv(Path.home() / ".local" / "share" / "agentos" / "gemini-cli-one" / "venv")
    path = settings_path()
    config = merge_settings(path, python=python, root=root, mode=args.mode)
    print(json.dumps({
        "schema": "agentos.gemini-cli-one-install/v0.1",
        "ok": True,
        "settings": str(path),
        "server": SERVER_NAME,
        "session_start_hook": True,
        "credential_in_settings": False,
        "restart_required": True,
        "configured_mcp": SERVER_NAME in config.get("mcpServers", {}),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
