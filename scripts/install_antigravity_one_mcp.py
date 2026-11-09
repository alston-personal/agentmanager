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
CLIENT_MODE = "client"
ORACLE_LOCAL_MODE = "oracle-local"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _client_config_candidates() -> list[Path]:
    candidates: list[Path] = []
    explicit = os.environ.get("AGENTOS_CLIENT_CONFIG")
    if explicit:
        candidates.append(Path(explicit).expanduser())
    client_home = os.environ.get("AGENTOS_CLIENT_HOME")
    if client_home:
        candidates.append(Path(client_home).expanduser() / "client.json")
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(
            Path(local_app_data) / "AgentOS" / "state" / "client.json"
        )
    if os.name == "nt":
        candidates.append(
            Path.home()
            / "AppData"
            / "Local"
            / "AgentOS"
            / "state"
            / "client.json"
        )
    candidates.append(Path.home() / ".agentos" / "client.json")
    return candidates


def discover_client_config() -> Path:
    for path in _client_config_candidates():
        if path.is_file():
            return path
    raise FileNotFoundError("AgentOS client.json not found")


def oracle_data_root() -> Path:
    return Path(
        os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data")
    ).expanduser()


def detect_mode(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    try:
        discover_client_config()
        return CLIENT_MODE
    except FileNotFoundError:
        pass
    root = oracle_data_root()
    if os.name != "nt" and (root / "realm" / "nodes.json").is_file():
        return ORACLE_LOCAL_MODE
    raise RuntimeError(
        "Cannot determine ONE MCP mode: no enrolled client config and no "
        "Oracle-local ONE Node Registry. Use --mode explicitly after "
        "verifying the intended runtime."
    )


GLOBAL_RULE_START = "<!-- AGENTOS_ONE_BOOTSTRAP_START -->"
GLOBAL_RULE_END = "<!-- AGENTOS_ONE_BOOTSTRAP_END -->"
GLOBAL_RULE = """<!-- AGENTOS_ONE_BOOTSTRAP_START -->
## AgentOS ONE bootstrap

When the `agentos-one` MCP tools are available and the current workspace is governed by AgentOS (for example its `AGENTS.md` identifies AgentOS, or the user asks about AgentOS/ONE), use ONE before reconstructing state from vendor conversation history.

For a fresh or relative request such as `continue` / `繼續` in an AgentOS-governed workspace:
1. call `one_status`;
2. identify the current project from workspace/repository context without guessing;
3. call `one_resolve(project)` before continuing substantial work;
4. treat canonical goal/continuation/authority returned by ONE as durable state, while newer explicit user intent always wins.

Never expose Realm/node credentials. The MCP adapter owns the trust boundary. `agy`, standalone `gemini`, Claude, and Codex are distinct executors and are not substitutes for the active Antigravity executor.
<!-- AGENTOS_ONE_BOOTSTRAP_END -->
"""


def global_rule_path() -> Path:
    return Path.home() / ".gemini" / "GEMINI.md"


def write_global_rule(path: Path) -> Path:
    existing = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    if GLOBAL_RULE_START in existing and GLOBAL_RULE_END in existing:
        before, remainder = existing.split(GLOBAL_RULE_START, 1)
        _, after = remainder.split(GLOBAL_RULE_END, 1)
        updated = before.rstrip() + "\n\n" + GLOBAL_RULE.strip() + after
    else:
        prefix = existing.rstrip()
        updated = (prefix + "\n\n" if prefix else "") + GLOBAL_RULE.strip() + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        shutil.copy2(path, path.with_name(path.name + f".agentos-backup-{stamp}"))
    tmp = path.with_suffix(path.suffix + ".agentos.tmp")
    tmp.write_text(updated, encoding="utf-8")
    tmp.replace(path)
    return path


def antigravity_mcp_config_path() -> Path:
    explicit = os.environ.get("AGENTOS_ANTIGRAVITY_MCP_CONFIG")
    if explicit:
        return Path(explicit).expanduser()
    current = Path.home() / ".gemini" / "config" / "mcp_config.json"
    legacy = (
        Path.home() / ".gemini" / "antigravity" / "mcp_config.json"
    )
    if current.exists() or current.parent.exists() or not legacy.exists():
        return current
    return legacy


def _venv_python(root: Path) -> Path:
    if os.name == "nt":
        return root / "Scripts" / "python.exe"
    return root / "bin" / "python"


def ensure_mcp_venv(venv_root: Path) -> Path:
    python = _venv_python(venv_root)
    if not python.is_file():
        venv_root.parent.mkdir(parents=True, exist_ok=True)
        venv.EnvBuilder(with_pip=True, clear=False).create(venv_root)
    check = subprocess.run(
        [
            str(python),
            "-c",
            "from mcp.server import MCPServer",
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


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"MCP config must be a JSON object: {path}")
    return data


def write_antigravity_config(
    path: Path,
    *,
    python: Path,
    repo_root: Path,
    mode: str,
) -> dict[str, Any]:
    config = _load_json(path)
    servers = config.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError("mcpServers must be an object")

    env = {
        "PYTHONPATH": str(repo_root),
        "AGENTOS_ONE_MCP_MODE": mode,
    }
    if mode == ORACLE_LOCAL_MODE:
        env["AGENT_DATA_ROOT"] = str(oracle_data_root())
        env["AGENTOS_CORE_NODE_ID"] = str(
            os.environ.get(
                "AGENTOS_CORE_NODE_ID",
                "oracle-core-node",
            )
        )

    servers[SERVER_NAME] = {
        "command": str(python),
        "args": ["-m", "agentos_node.one_mcp"],
        "cwd": str(repo_root),
        "env": env,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        shutil.copy2(
            path,
            path.with_name(
                path.name + f".agentos-backup-{stamp}"
            ),
        )
    tmp = path.with_suffix(path.suffix + ".agentos.tmp")
    tmp.write_text(
        json.dumps(
            config,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)
    return servers[SERVER_NAME]


def state_root_for_mode(mode: str) -> Path:
    if mode == CLIENT_MODE:
        return discover_client_config().parent / "mcp"
    return Path.home() / ".local" / "share" / "agentos" / "one-mcp"


def probe(
    python: Path,
    repo_root: Path,
    *,
    mode: str,
) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    env["AGENTOS_ONE_MCP_MODE"] = mode
    if mode == ORACLE_LOCAL_MODE:
        env["AGENT_DATA_ROOT"] = str(oracle_data_root())
    result = subprocess.run(
        [
            str(python),
            "-m",
            "agentos_node.one_mcp",
            "--mode",
            mode,
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
            "ONE MCP probe failed: "
            + (result.stderr or result.stdout)[-5000:]
        )
    payload = json.loads(result.stdout)
    if payload.get("probe") != "PASS":
        raise RuntimeError(
            f"ONE MCP probe did not pass: {payload}"
        )
    if payload.get("credential_exposed") is not False:
        raise RuntimeError(
            "ONE MCP probe did not prove credential isolation"
        )
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Install AgentOS ONE MCP for the real Antigravity IDE agent"
        )
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=_repo_root(),
    )
    parser.add_argument(
        "--mode",
        choices=(CLIENT_MODE, ORACLE_LOCAL_MODE),
        help=(
            "client uses an enrolled Thin Client credential; "
            "oracle-local uses trusted read-only Oracle state"
        ),
    )
    parser.add_argument("--no-probe", action="store_true")
    args = parser.parse_args(argv)

    repo_root = args.repo.expanduser().resolve()
    if not (
        repo_root / "agentos_node" / "one_mcp.py"
    ).is_file():
        raise FileNotFoundError(
            f"AgentOS ONE MCP module missing under repo: {repo_root}"
        )

    mode = detect_mode(args.mode)
    state_root = state_root_for_mode(mode)
    venv_root = state_root / "venv"
    python = ensure_mcp_venv(venv_root)
    evidence = (
        None
        if args.no_probe
        else probe(python, repo_root, mode=mode)
    )
    global_rule = write_global_rule(global_rule_path())
    mcp_config = antigravity_mcp_config_path()
    server = write_antigravity_config(
        mcp_config,
        python=python,
        repo_root=repo_root,
        mode=mode,
    )
    print(
        json.dumps(
            {
                "schema": (
                    "agentos.antigravity-one-mcp-install/v0.2"
                ),
                "ok": True,
                "mode": mode,
                "server": SERVER_NAME,
                "mcp_config": str(mcp_config),
                "global_rule": str(global_rule),
                "repo": str(repo_root),
                "probe": evidence,
                "credential_in_mcp_config": False,
                "refresh_required": True,
                "server_config": server,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
