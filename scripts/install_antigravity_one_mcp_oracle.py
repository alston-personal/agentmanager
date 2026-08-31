#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import venv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SERVER_NAME = "agentos-one"
HOOK_NAME = "agentos-one-preinvocation"
MCP_PACKAGE = "mcp>=2,<3"
GLOBAL_RULE_START = "<!-- AGENTOS_ONE_BOOTSTRAP_START -->"
GLOBAL_RULE_END = "<!-- AGENTOS_ONE_BOOTSTRAP_END -->"
GLOBAL_RULE = """<!-- AGENTOS_ONE_BOOTSTRAP_START -->
## AgentOS ONE bootstrap — pre-invocation hydration is authoritative

This machine participates in AgentOS ONE through a trusted Oracle-local pre-invocation hook plus the `agentos-one` MCP server.

On the first model invocation of a fresh Antigravity conversation, AgentOS injects canonical ONE state before the model is called when the active workspace resolves to an AgentOS project. Treat an injected `source=ONE_PREINVOCATION_HOOK` envelope as the primary continuity source. Newer explicit user intent always wins.

Do not reconstruct the current AgentOS goal from Pulse boards, PM2 listings, local memory files, vendor conversation history, or prior chat summaries before using the injected ONE state. Those sources may only be consulted later as supporting evidence.

The `agentos-one` MCP tools remain available for explicit live queries (`one_status`, `one_bootstrap`, `one_capabilities`, `one_resolve`). If no ONE pre-invocation hydration is present in an AgentOS-governed workspace, use the MCP tools and report `ONE_BOOTSTRAP_BLOCKED` if they are unavailable. Never claim ONE continuity merely because local AgentOS files are readable.

Never expose Realm/node credentials. `agy`, standalone `gemini`, Claude, and Codex are distinct executors and are not substitutes for the active Antigravity executor.
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
        [str(python), "-c", "from mcp.server.mcpserver import MCPServer"],
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
    shutil.copy2(path, path.with_name(path.name + f".agentos-backup-{stamp}"))


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _backup(path)
    tmp = path.with_suffix(path.suffix + ".agentos.tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


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


def hooks_config_path() -> Path:
    explicit = os.environ.get("AGENTOS_ANTIGRAVITY_HOOKS_CONFIG")
    if explicit:
        return Path(explicit).expanduser()
    return Path.home() / ".gemini" / "config" / "hooks.json"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"config must be a JSON object: {path}")
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
    _atomic_json(path, config)
    return server


def _hook_command(python: Path, repo_root: Path) -> str:
    assignments = {
        "PYTHONPATH": str(repo_root),
        "AGENT_DATA_ROOT": str(_data_root()),
        "AGENTOS_CORE_NODE_ID": str(
            os.environ.get("AGENTOS_CORE_NODE_ID", "oracle-core-node")
        ),
    }
    env_prefix = " ".join(
        f"{key}={shlex.quote(value)}" for key, value in assignments.items()
    )
    return (
        f"cd {shlex.quote(str(repo_root))} && {env_prefix} "
        f"{shlex.quote(str(python))} -m agentos_node.antigravity_one_hook"
    )


def write_hooks_config(path: Path, *, python: Path, repo_root: Path) -> dict[str, Any]:
    config = _load_json(path)
    hook = {
        "enabled": True,
        "PreInvocation": [
            {
                "type": "command",
                "command": _hook_command(python, repo_root),
                "timeout": 10,
            }
        ],
    }
    config[HOOK_NAME] = hook
    _atomic_json(path, config)
    return hook


def probe(python: Path, repo_root: Path) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    env["AGENTOS_ONE_MCP_MODE"] = "oracle-local"
    env["AGENT_DATA_ROOT"] = str(_data_root())
    result = subprocess.run(
        [str(python), "-m", "agentos_node.one_mcp", "--mode", "oracle-local", "--probe"],
        cwd=str(repo_root),
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Oracle ONE probe failed: " + (result.stderr or result.stdout)[-5000:]
        )
    payload = json.loads(result.stdout)
    if payload.get("probe") != "PASS":
        raise RuntimeError(f"Oracle ONE probe did not pass: {payload}")
    if payload.get("mode") != "oracle-local":
        raise RuntimeError(f"unexpected ONE MCP mode: {payload}")
    if payload.get("credential_exposed") is not False:
        raise RuntimeError("credential isolation not proven")
    return payload


def probe_preinvocation_hook(python: Path, repo_root: Path) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    env["AGENT_DATA_ROOT"] = str(_data_root())
    payload = {
        "invocationNum": 0,
        "initialNumSteps": 1,
        "conversationId": "agentos-installer-probe",
        "workspacePaths": [str(Path("/home/ubuntu/agentmanager"))],
        "transcriptPath": "",
        "artifactDirectoryPath": "",
        "modelName": "installer-probe",
    }
    result = subprocess.run(
        [str(python), "-m", "agentos_node.antigravity_one_hook"],
        cwd=str(repo_root),
        env=env,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "PreInvocation hook probe failed: "
            + (result.stderr or result.stdout)[-5000:]
        )
    output = json.loads(result.stdout or "{}")
    steps = output.get("injectSteps") if isinstance(output, dict) else None
    if not isinstance(steps, list) or not steps:
        raise RuntimeError(f"PreInvocation hook produced no hydration: {output}")
    message = str((steps[0] or {}).get("ephemeralMessage") or "")
    if "ONE_PREINVOCATION_HOOK" not in message:
        raise RuntimeError("PreInvocation hook hydration lacks ONE provenance")
    return {
        "ok": True,
        "schema": "agentos.antigravity-one-preinvocation-probe/v0.1",
        "source": "ONE_PREINVOCATION_HOOK",
        "credential_exposed": False,
    }


def main() -> int:
    if os.name == "nt":
        raise RuntimeError("Oracle-local installer must run on Oracle/Linux")
    if os.environ.get("USER") not in (None, "", "ubuntu"):
        raise PermissionError("Oracle-local installer must run as ubuntu")

    repo_root = _repo_root()
    for required in (
        repo_root / "agentos_node" / "one_mcp.py",
        repo_root / "agentos_node" / "one_mcp_stdio.py",
        repo_root / "agentos_node" / "antigravity_one_hook.py",
    ):
        if not required.is_file():
            raise FileNotFoundError(f"required AgentOS runtime file missing: {required}")
    if not (_data_root() / "realm" / "nodes.json").is_file():
        raise FileNotFoundError("Oracle ONE Node Registry missing")

    state_root = Path.home() / ".local" / "share" / "agentos" / "one-mcp"
    python = ensure_venv(state_root / "venv")
    evidence = probe(python, repo_root)
    hook_probe = probe_preinvocation_hook(python, repo_root)
    rule = write_global_rule()
    mcp_path = mcp_config_path()
    server = write_mcp_config(mcp_path, python=python, repo_root=repo_root)
    hooks_path = hooks_config_path()
    hook = write_hooks_config(hooks_path, python=python, repo_root=repo_root)

    print(
        json.dumps(
            {
                "schema": "agentos.antigravity-one-oracle-install/v0.2",
                "ok": True,
                "mode": "oracle-local",
                "probe": evidence,
                "preinvocation_hook_probe": hook_probe,
                "global_rule": str(rule),
                "mcp_config": str(mcp_path),
                "server": server,
                "hooks_config": str(hooks_path),
                "hook": hook,
                "credential_in_mcp_config": False,
                "credential_in_hook_config": False,
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
