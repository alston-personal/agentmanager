#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import venv
from datetime import datetime, timezone
from pathlib import Path

MCP_PACKAGE = "mcp>=2,<3"
CONFIG_START = "# AGENTOS_ONE_MCP_START"
CONFIG_END = "# AGENTOS_ONE_MCP_END"
AGENTS_START = "<!-- AGENTOS_ONE_CODEX_BOOTSTRAP_START -->"
AGENTS_END = "<!-- AGENTOS_ONE_CODEX_BOOTSTRAP_END -->"

AGENTS_BLOCK = f"""{AGENTS_START}
## AgentOS ONE bootstrap for Codex

This Codex local harness participates in AgentOS ONE through the `agentos-one` MCP server.

For a fresh thread, when the user's instruction is relative continuation such as `continue` or `繼續` and there is no newer explicit task, resolve the current work from ONE before inspecting workspace-local TODOs, status files, open editors, vendor history, or uncommitted changes.

Required startup action:
1. call `agentos-one.one_resolve_active`;
2. treat `selector.project_id + selector.index_id + selector.ir_id` and the returned Canonical IR as the authoritative continuation generation;
3. continue from that IR's goal, constraints, decisions, pending tasks, continuation, and next action;
4. report provenance `source=ONE_ACTIVE_CONTINUATION` plus project/index/IR identifiers when beginning a relative continuation;
5. newer explicit user intent still wins over hydrated state.

Do not infer the current project from the IDE workspace. Do not reconstruct continuation from Pulse, PM2, local memory, git diff, STATUS files, or previous Codex/Gemini conversation history when ONE is available.

If `one_resolve_active` is unavailable, missing, stale, or fails, report `ONE_ACTIVE_CONTINUATION_UNRESOLVED` and do not fabricate the continuation.

Never request, print, copy, or expose Realm/node credentials. The MCP process owns only the trusted local read-only projection.
{AGENTS_END}
"""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _data_root() -> Path:
    return Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data")).expanduser()


def _codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()


def _venv_python(root: Path) -> Path:
    return root / "bin" / "python"


def ensure_venv(root: Path) -> Path:
    python = _venv_python(root)
    if not python.is_file():
        root.parent.mkdir(parents=True, exist_ok=True)
        venv.EnvBuilder(with_pip=True, clear=False).create(root)
    check = subprocess.run(
        [str(python), "-c", "from mcp.server.mcpserver import MCPServer"],
        text=True,
        capture_output=True,
        check=False,
    )
    if check.returncode != 0:
        install = subprocess.run(
            [str(python), "-m", "pip", "install", "--disable-pip-version-check", MCP_PACKAGE],
            text=True,
            capture_output=True,
            check=False,
        )
        if install.returncode != 0:
            raise RuntimeError("failed to install MCP SDK: " + (install.stderr or install.stdout)[-4000:])
    return python


def _backup(path: Path) -> None:
    if not path.exists():
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    shutil.copy2(path, path.with_name(path.name + f".agentos-backup-{stamp}"))


def _replace_block(existing: str, start: str, end: str, block: str) -> str:
    if start in existing or end in existing:
        if start not in existing or end not in existing:
            raise ValueError(f"partial managed block found: {start}")
        before, rest = existing.split(start, 1)
        _, after = rest.split(end, 1)
        return before.rstrip() + "\n\n" + block.strip() + "\n" + after.lstrip()
    prefix = existing.rstrip()
    return (prefix + "\n\n" if prefix else "") + block.strip() + "\n"


def write_agents(path: Path) -> Path:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    updated = _replace_block(existing, AGENTS_START, AGENTS_END, AGENTS_BLOCK)
    path.parent.mkdir(parents=True, exist_ok=True)
    _backup(path)
    tmp = path.with_suffix(path.suffix + ".agentos.tmp")
    tmp.write_text(updated, encoding="utf-8")
    tmp.replace(path)
    return path


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def config_block(*, python: Path, repo_root: Path) -> str:
    return "\n".join(
        [
            CONFIG_START,
            '[mcp_servers."agentos-one"]',
            f"command = {_toml_string(str(python))}",
            'args = ["-m", "agentos_node.codex_one_mcp_stdio"]',
            f"cwd = {_toml_string(str(repo_root))}",
            "enabled = true",
            "",
            '[mcp_servers."agentos-one".env]',
            f"PYTHONPATH = {_toml_string(str(repo_root))}",
            f"AGENT_DATA_ROOT = {_toml_string(str(_data_root()))}",
            'AGENTOS_ONE_MCP_MODE = "oracle-local"',
            f"AGENTOS_CORE_NODE_ID = {_toml_string(str(os.environ.get('AGENTOS_CORE_NODE_ID', 'oracle-core-node')))}",
            CONFIG_END,
        ]
    )


def write_config(path: Path, *, python: Path, repo_root: Path) -> Path:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    unmanaged = existing
    if CONFIG_START in existing and CONFIG_END in existing:
        before, rest = existing.split(CONFIG_START, 1)
        _, after = rest.split(CONFIG_END, 1)
        unmanaged = before + after
    if '[mcp_servers."agentos-one"]' in unmanaged or "[mcp_servers.agentos-one]" in unmanaged:
        raise ValueError("unmanaged Codex agentos-one MCP entry already exists; refusing to overwrite")
    updated = _replace_block(existing, CONFIG_START, CONFIG_END, config_block(python=python, repo_root=repo_root))
    path.parent.mkdir(parents=True, exist_ok=True)
    _backup(path)
    tmp = path.with_suffix(path.suffix + ".agentos.tmp")
    tmp.write_text(updated, encoding="utf-8")
    tmp.replace(path)
    return path


def probe(python: Path, repo_root: Path) -> dict[str, object]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    env["AGENT_DATA_ROOT"] = str(_data_root())
    code = """
import json
from agentos_node.codex_one_mcp_stdio import _active_projection
from agentos_node.one_mcp import OracleLocalGateway
r = _active_projection(OracleLocalGateway())
s = r.get('selector') or {}
print(json.dumps({
  'ok': True,
  'schema': r.get('schema'),
  'source': r.get('source'),
  'selection_source': r.get('selection_source'),
  'surface': r.get('surface'),
  'executor_class': r.get('executor_class'),
  'project_id': s.get('project_id'),
  'index_id': s.get('index_id'),
  'ir_id': s.get('ir_id'),
  'credential_exposed': r.get('credential_exposed'),
}, ensure_ascii=False))
"""
    result = subprocess.run(
        [str(python), "-c", code],
        cwd=str(repo_root),
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("Codex ONE probe failed: " + (result.stderr or result.stdout)[-4000:])
    payload = json.loads(result.stdout)
    if payload.get("source") != "ONE_ACTIVE_CONTINUATION":
        raise RuntimeError(f"Codex ONE active selector probe failed: {payload}")
    if payload.get("credential_exposed") is not False:
        raise RuntimeError("Codex ONE credential isolation not proven")
    return payload


def main() -> int:
    if os.name == "nt":
        raise RuntimeError("Oracle-local Codex installer must run on Oracle/Linux")
    repo_root = _repo_root()
    required = repo_root / "agentos_node" / "codex_one_mcp_stdio.py"
    if not required.is_file():
        raise FileNotFoundError(f"required Codex ONE MCP module missing: {required}")
    if not (_data_root() / "runtime" / "active-continuation.json").is_file():
        raise FileNotFoundError("ONE active continuation selector is missing")

    state_root = Path.home() / ".local" / "share" / "agentos" / "one-mcp"
    python = ensure_venv(state_root / "venv")
    evidence = probe(python, repo_root)
    codex_home = _codex_home()
    agents = write_agents(codex_home / "AGENTS.md")
    config = write_config(codex_home / "config.toml", python=python, repo_root=repo_root)

    print(json.dumps({
        "schema": "agentos.codex-one-oracle-install/v0.1",
        "ok": True,
        "mode": "oracle-local",
        "probe": evidence,
        "codex_home": str(codex_home),
        "agents_path": str(agents),
        "config_path": str(config),
        "mcp_server": "agentos-one",
        "credential_in_config": False,
        "reload_required": True,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
