#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import venv

MCP_PACKAGE = "mcp>=2,<3"
CONFIG_START = "# AGENTOS_EXPERIENCE_MCP_START"
CONFIG_END = "# AGENTOS_EXPERIENCE_MCP_END"
SERVER = "agentos-experience"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def data_root() -> Path:
    return Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data")).expanduser()


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()


def ensure_python() -> Path:
    shared = Path.home() / ".local" / "share" / "agentos" / "one-mcp" / "venv" / "bin" / "python"
    if shared.is_file():
        probe = subprocess.run([str(shared), "-c", "from mcp.server.mcpserver import MCPServer"], capture_output=True)
        if probe.returncode == 0:
            return shared
    root = Path.home() / ".local" / "share" / "agentos" / "experience-mcp" / "venv"
    python = root / "bin" / "python"
    if not python.is_file():
        root.parent.mkdir(parents=True, exist_ok=True)
        venv.EnvBuilder(with_pip=True, clear=False).create(root)
    probe = subprocess.run([str(python), "-c", "from mcp.server.mcpserver import MCPServer"], capture_output=True)
    if probe.returncode != 0:
        install = subprocess.run(
            [str(python), "-m", "pip", "install", "--disable-pip-version-check", MCP_PACKAGE],
            text=True,
            capture_output=True,
            check=False,
        )
        if install.returncode != 0:
            raise RuntimeError("failed to install MCP SDK: " + (install.stderr or install.stdout)[-3000:])
    return python


def _toml(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def block(python: Path) -> str:
    root = repo_root()
    return "\n".join([
        CONFIG_START,
        f'[mcp_servers."{SERVER}"]',
        f"command = {_toml(str(python))}",
        'args = ["-m", "agentos_node.experience_mcp_stdio"]',
        f"cwd = {_toml(str(root))}",
        "enabled = true",
        "",
        f'[mcp_servers."{SERVER}".env]',
        f"PYTHONPATH = {_toml(str(root))}",
        f"AGENT_DATA_ROOT = {_toml(str(data_root()))}",
        CONFIG_END,
    ])


def replace_block(existing: str, new_block: str) -> str:
    if CONFIG_START in existing or CONFIG_END in existing:
        if CONFIG_START not in existing or CONFIG_END not in existing:
            raise ValueError("partial managed Experience MCP block found")
        before, rest = existing.split(CONFIG_START, 1)
        _, after = rest.split(CONFIG_END, 1)
        return before.rstrip() + "\n\n" + new_block.strip() + "\n" + after.lstrip()
    unmanaged_keys = (f'[mcp_servers."{SERVER}"]', f"[mcp_servers.{SERVER}]")
    if any(key in existing for key in unmanaged_keys):
        raise ValueError("unmanaged agentos-experience MCP entry exists; refusing overwrite")
    return (existing.rstrip() + "\n\n" if existing.strip() else "") + new_block.strip() + "\n"


def main() -> int:
    if os.name == "nt":
        raise RuntimeError("Oracle-local Experience MCP installer requires Linux")
    required = data_root() / "experience" / "agentos-core" / "accepted.json"
    if not required.is_file():
        raise FileNotFoundError(f"ONE Experience store missing: {required}")
    python = ensure_python()
    home = codex_home()
    config = home / "config.toml"
    existing = config.read_text(encoding="utf-8") if config.exists() else ""
    updated = replace_block(existing, block(python))
    home.mkdir(parents=True, exist_ok=True)
    tmp = config.with_suffix(".toml.agentos-experience.tmp")
    tmp.write_text(updated, encoding="utf-8")
    tmp.replace(config)
    print(json.dumps({
        "schema": "agentos.codex-experience-mcp-install/v1",
        "ok": True,
        "server": SERVER,
        "config_path": str(config),
        "experience_path": str(required),
        "canonical_ir_copied": False,
        "experience_body_copied_to_config": False,
        "credential_in_config": False,
        "reload_required": False,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
