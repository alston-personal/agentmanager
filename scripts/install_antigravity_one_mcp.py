#!/usr/bin/env python3
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
        candidates.append(Path(local_app_data) / "AgentOS" / "state" / "client.json")
    if os.name == "nt":
        candidates.append(Path.home() / "AppData" / "Local" / "AgentOS" / "state" / "client.json")
    candidates.append(Path.home() / ".agentos" / "client.json")
    return candidates


def discover_client_config() -> Path:
    for path in _client_config_candidates():
        if path.is_file():
            return path
    raise FileNotFoundError(
        "AgentOS client.json not found; enroll/start the AgentOS client first"
    )


def antigravity_mcp_config_path() -> Path:
    explicit = os.environ.get("AGENTOS_ANTIGRAVITY_MCP_CONFIG")
    if explicit:
        return Path(explicit).expanduser()
    current = Path.home() / ".gemini" / "config" / "mcp_config.json"
    legacy = Path.home() / ".gemini" / "antigravity" / "mcp_config.json"
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
        [str(python), "-c", "from mcp.server import MCPServer"],
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
) -> dict[str, Any]:
    config = _load_json(path)
    servers = config.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError("mcpServers must be an object")
    servers[SERVER_NAME] = {
        "command": str(python),
        "args": ["-m", "agentos_node.one_mcp"],
        "cwd": str(repo_root),
        "env": {"PYTHONPATH": str(repo_root)},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        shutil.copy2(path, path.with_name(path.name + f".agentos-backup-{stamp}"))
    tmp = path.with_suffix(path.suffix + ".agentos.tmp")
    tmp.write_text(
        json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)
    return servers[SERVER_NAME]


def probe(python: Path, repo_root: Path) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    result = subprocess.run(
        [str(python), "-m", "agentos_node.one_mcp", "--probe"],
        cwd=str(repo_root),
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "ONE MCP probe failed: " + (result.stderr or result.stdout)[-5000:]
        )
    payload = json.loads(result.stdout)
    if payload.get("probe") != "PASS":
        raise RuntimeError(f"ONE MCP probe did not pass: {payload}")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install AgentOS ONE MCP for the real Antigravity IDE agent"
    )
    parser.add_argument("--repo", type=Path, default=_repo_root())
    parser.add_argument("--no-probe", action="store_true")
    args = parser.parse_args(argv)

    repo_root = args.repo.expanduser().resolve()
    if not (repo_root / "agentos_node" / "one_mcp.py").is_file():
        raise FileNotFoundError(
            f"AgentOS ONE MCP module missing under repo: {repo_root}"
        )
    client_config = discover_client_config()
    state_root = client_config.parent
    venv_root = state_root / "mcp" / "venv"
    python = ensure_mcp_venv(venv_root)
    evidence = None if args.no_probe else probe(python, repo_root)
    mcp_config = antigravity_mcp_config_path()
    server = write_antigravity_config(
        mcp_config,
        python=python,
        repo_root=repo_root,
    )
    print(
        json.dumps(
            {
                "schema": "agentos.antigravity-one-mcp-install/v0.1",
                "ok": True,
                "server": SERVER_NAME,
                "mcp_config": str(mcp_config),
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
