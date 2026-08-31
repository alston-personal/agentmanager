#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import venv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SERVER_NAME = "agentos-one"
MCP_PACKAGE = "mcp>=2,<3"
GLOBAL_RULE_START = "<!-- AGENTOS_ONE_BOOTSTRAP_START -->"
GLOBAL_RULE_END = "<!-- AGENTOS_ONE_BOOTSTRAP_END -->"
GLOBAL_RULE = """<!-- AGENTOS_ONE_BOOTSTRAP_START -->
## AgentOS ONE bootstrap

When the `agentos-one` MCP tools are available and the current workspace is governed by AgentOS, use ONE before reconstructing state from vendor conversation history.

For a fresh or relative request such as `continue` / `繼續` in an AgentOS-governed workspace:
1. call `one_status`;
2. identify the current project from workspace/repository context without guessing;
3. call `one_resolve(project)` before continuing substantial work;
4. treat canonical goal/continuation/authority returned by ONE as durable state, while newer explicit user intent always wins.

Never expose Realm/node credentials. The MCP adapter owns the trust boundary. `agy`, standalone `gemini`, Claude, and Codex are distinct executors and are not substitutes for the active Antigravity executor.
<!-- AGENTOS_ONE_BOOTSTRAP_END -->
"""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _data_root() -> Path:
    return Path(
        os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data")
    ).expanduser()


def _venv_python(root: Path) -> Path:
    return root / "bin" / "python"


def ensure_venv(root: Path) -> Path:
    python = _venv_python(root)
    if not python.is_file():
        root.parent.mkdir(parents=True, exist_ok=True)
        venv.EnvBuilder(with_pip=True, clear=False).create(root)
    check = subprocess.run(
        [
            str(python),
            "-c",
            "from mcp.server.mcpserver import MCPServer",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if check.returncode != 0:
        install = subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                MCP_PACKAGE,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if install.returncode != 0:
            raise RuntimeError(
                "failed to install MCP SDK: "
                + (install.stderr or install.stdout)[-4000:]
            )
    return python


def _backup(path: Path) -> None:
    if not path.exists():
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    shutil.copy2(
        path,
        path.with_name(path.name + f".agentos-backup-{stamp}"),
    )


def write_global_rule() -> Path:
    path = Path.home() / ".gemini" / "GEMINI.md"
    existing = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    if GLOBAL_RULE_START in existing and GLOBAL_RULE_END in existing:
        before, remainder = existing.split(GLOBAL_RULE_START, 1)
        _, after = remainder.split(GLOBAL_RULE_END, 1)
        updated = before.rstrip() + "\n\n" + GLOBAL_RULE.strip() + after
    else:
        prefix = existing.rstrip()
        updated = (prefix + "\n\n" if prefix else "") + GLOBAL_RULE.strip() + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    _backup(path)
    tmp = path.with_suffix(path.suffix + ".agentos.tmp")
    tmp.write_text(updated, encoding="utf-8")
    tmp.replace(path)
    return path


def mcp_config_path() -> Path:
    explicit = os.environ.get("AGENTOS_ANTIGRAVITY_MCP_CONFIG")
    if explicit:
        return Path(explicit).expanduser()
    return Path.home() / ".gemini" / "config" / "mcp_config.json"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"MCP config must be a JSON object: {path}")
    return payload


def write_mcp_config(path: Path, *, python: Path, repo_root: Path) -> dict[str, Any]:
    config = _load_json(path)
    servers = config.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError("mcpServers must be an object")
    server = {
        "command": str(python),
        "args": ["-m", "agentos_node.one_mcp_stdio"],
        "cwd": str(repo_root),
        "env": {
            "PYTHONPATH": str(repo_root),
            "AGENTOS_ONE_MCP_MODE": "oracle-local",
            "AGENT_DATA_ROOT": str(_data_root()),
            "AGENTOS_CORE_NODE_ID": str(
                os.environ.get("AGENTOS_CORE_NODE_ID", "oracle-core-node")
            ),
        },
    }
    servers[SERVER_NAME] = server
    path.parent.mkdir(parents=True, exist_ok=True)
    _backup(path)
    tmp = path.with_suffix(path.suffix + ".agentos.tmp")
    tmp.write_text(
        json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)
    return server


def probe(python: Path, repo_root: Path) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    env["AGENTOS_ONE_MCP_MODE"] = "oracle-local"
    env["AGENT_DATA_ROOT"] = str(_data_root())
    result = subprocess.run(
        [
            str(python),
            "-m",
            "agentos_node.one_mcp",
            "--mode",
            "oracle-local",
            "--probe",
        ],
        cwd=str(repo_root),
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Oracle ONE probe failed: "
            + (result.stderr or result.stdout)[-5000:]
        )
    payload = json.loads(result.stdout)
    if payload.get("probe") != "PASS":
        raise RuntimeError(f"Oracle ONE probe did not pass: {payload}")
    if payload.get("mode") != "oracle-local":
        raise RuntimeError(f"unexpected ONE MCP mode: {payload}")
    if payload.get("credential_exposed") is not False:
        raise RuntimeError("credential isolation not proven")
    return payload


def main() -> int:
    if os.name == "nt":
        raise RuntimeError("Oracle-local installer must run on Oracle/Linux")
    if os.environ.get("USER") not in (None, "", "ubuntu"):
        raise PermissionError("Oracle-local installer must run as ubuntu")

    repo_root = _repo_root()
    if not (repo_root / "agentos_node" / "one_mcp.py").is_file():
        raise FileNotFoundError("one_mcp.py missing")
    if not (repo_root / "agentos_node" / "one_mcp_stdio.py").is_file():
        raise FileNotFoundError("one_mcp_stdio.py missing")
    if not (_data_root() / "realm" / "nodes.json").is_file():
        raise FileNotFoundError("Oracle ONE Node Registry missing")

    state_root = Path.home() / ".local" / "share" / "agentos" / "one-mcp"
    python = ensure_venv(state_root / "venv")
    evidence = probe(python, repo_root)
    rule = write_global_rule()
    config_path = mcp_config_path()
    server = write_mcp_config(config_path, python=python, repo_root=repo_root)

    print(
        json.dumps(
            {
                "schema": "agentos.antigravity-one-oracle-install/v0.1",
                "ok": True,
                "mode": "oracle-local",
                "probe": evidence,
                "global_rule": str(rule),
                "mcp_config": str(config_path),
                "server": server,
                "credential_in_mcp_config": False,
                "reload_required": True,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
