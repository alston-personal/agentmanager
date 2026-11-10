#!/usr/bin/env python3
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

BOOTSTRAP_START = "<!-- AGENTOS_ONE_CLAUDE_BOOTSTRAP_START -->"
BOOTSTRAP_END = "<!-- AGENTOS_ONE_CLAUDE_BOOTSTRAP_END -->"
SERVER_NAME = "agentos-one"

BOOTSTRAP_BLOCK = f"""{BOOTSTRAP_START}
## AgentOS ONE bootstrap for Claude Code

This Claude Code extension surface participates in AgentOS ONE through the `{SERVER_NAME}` MCP server.

For a completely fresh thread, when the user's instruction is relative continuation such as `continue` or `繼續` and there is no newer explicit task, resolve current work from ONE before inspecting workspace-local TODOs, status files, open editors, local conversation history, or git state.

Required startup action:
1. call `{SERVER_NAME}.one_resolve_active`;
2. treat `selector.project_id + selector.index_id + selector.ir_id` and the returned Canonical IR as the authoritative continuation generation;
3. continue from that IR's goal, constraints, decisions, pending tasks, continuation, and next action;
4. report provenance `source=ONE_ACTIVE_CONTINUATION` plus project/index/IR identifiers when beginning a relative continuation;
5. newer explicit user intent always wins over hydrated state.

Do not infer backend/model identity from the Claude Code extension surface. Surface identity, executor adapter identity, backend/model identity, and session identity are separate dimensions. If the trusted ONE projection reports backend identity as unbound/unknown, preserve that uncertainty.

Do not infer the current project from the IDE workspace. Do not reconstruct continuation from local memory, git diff, STATUS files, or previous Claude/Codex/Gemini conversation history when ONE is available.

If `one_resolve_active` is unavailable, missing, stale, or fails, report `ONE_ACTIVE_CONTINUATION_UNRESOLVED` and do not fabricate continuation.

Never request, print, copy, or expose Realm/node credentials. The MCP process exposes only the trusted local read-only ONE projection.
{BOOTSTRAP_END}
"""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _data_root() -> Path:
    return Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data")).expanduser()


def _claude_home() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))).expanduser()


def _venv_python() -> Path:
    candidate = Path.home() / ".local" / "share" / "agentos" / "one-mcp" / "venv" / "bin" / "python"
    if not candidate.is_file():
        raise FileNotFoundError(
            "shared AgentOS ONE MCP venv is missing; install the existing ONE MCP runtime before Claude bootstrap"
        )
    return candidate


def _discover_claude() -> Path:
    explicit = str(os.environ.get("AGENTOS_CLAUDE_EXECUTABLE") or "").strip()
    if explicit:
        candidate = Path(explicit).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
        raise FileNotFoundError(f"configured Claude executable is not executable: {candidate}")

    patterns = [
        str(Path.home() / ".antigravity-ide-server/extensions/anthropic.claude-code-*-linux-arm64/resources/native-binary/claude"),
        str(Path.home() / ".antigravity-ide-server/extensions/anthropic.claude-code-*/resources/native-binary/claude"),
    ]
    matches: list[str] = []
    for pattern in patterns:
        matches.extend(glob.glob(pattern))
    for item in sorted(set(matches), reverse=True):
        candidate = Path(item)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate

    from_path = shutil.which("claude")
    if from_path:
        return Path(from_path)
    raise FileNotFoundError("Anthropic Claude Code executable not found")


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


def write_bootstrap(path: Path) -> Path:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    updated = _replace_block(existing, BOOTSTRAP_START, BOOTSTRAP_END, BOOTSTRAP_BLOCK)
    path.parent.mkdir(parents=True, exist_ok=True)
    _backup(path)
    tmp = path.with_suffix(path.suffix + ".agentos.tmp")
    tmp.write_text(updated, encoding="utf-8")
    tmp.replace(path)
    return path


def _mcp_payload(*, python: Path, repo_root: Path) -> dict[str, object]:
    env: dict[str, str] = {
        "PYTHONPATH": str(repo_root),
        "AGENT_DATA_ROOT": str(_data_root()),
        "AGENTOS_ONE_MCP_MODE": "oracle-local",
        "AGENTOS_CORE_NODE_ID": str(os.environ.get("AGENTOS_CORE_NODE_ID", "oracle-core-node")),
    }
    backend_class = str(os.environ.get("AGENTOS_CLAUDE_BACKEND_CLASS") or "").strip()
    backend_id = str(os.environ.get("AGENTOS_CLAUDE_BACKEND_ID") or "").strip()
    if backend_class:
        env["AGENTOS_CLAUDE_BACKEND_CLASS"] = backend_class
    if backend_id:
        env["AGENTOS_CLAUDE_BACKEND_ID"] = backend_id
    return {
        "type": "stdio",
        "command": str(python),
        "args": ["-m", "agentos_node.claude_one_mcp_stdio"],
        "env": env,
    }


def _run(args: list[str], *, timeout: float = 20.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)


def install_user_mcp(claude: Path, *, python: Path, repo_root: Path) -> dict[str, object]:
    marker_root = Path.home() / ".local" / "share" / "agentos" / "claude-one"
    marker_root.mkdir(parents=True, exist_ok=True)
    marker_path = marker_root / "managed-mcp.json"
    payload = _mcp_payload(python=python, repo_root=repo_root)
    expected = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    probe = _run([str(claude), "mcp", "get", SERVER_NAME])
    exists = probe.returncode == 0
    owned = False
    if marker_path.is_file():
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            owned = marker.get("server") == SERVER_NAME and marker.get("payload") == payload
        except (OSError, json.JSONDecodeError):
            owned = False

    if exists and not owned:
        raise ValueError(f"unmanaged Claude MCP server {SERVER_NAME!r} already exists; refusing to overwrite")

    if not exists:
        add = _run(
            [str(claude), "mcp", "add-json", "--scope", "user", SERVER_NAME, json.dumps(payload, ensure_ascii=False)]
        )
        if add.returncode != 0:
            raise RuntimeError("Claude MCP add-json failed: " + (add.stderr or add.stdout)[-4000:])

    marker_path.write_text(
        json.dumps({"schema": "agentos.claude-one-managed-mcp/v1", "server": SERVER_NAME, "payload": payload}, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(marker_path, 0o600)
    return {"server": SERVER_NAME, "already_present": exists, "managed": True, "payload": payload}


def probe_projection(python: Path, repo_root: Path) -> dict[str, object]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    env["AGENT_DATA_ROOT"] = str(_data_root())
    code = """
import json
from agentos_node.claude_one_mcp_stdio import _active_projection
from agentos_node.one_mcp import OracleLocalGateway
r = _active_projection(OracleLocalGateway())
s = r.get('selector') or {}
print(json.dumps({
  'ok': True,
  'schema': r.get('schema'),
  'source': r.get('source'),
  'selection_source': r.get('selection_source'),
  'surface': r.get('surface'),
  'executor_adapter': r.get('executor_adapter'),
  'executor_class': r.get('executor_class'),
  'backend_class': r.get('backend_class'),
  'backend_identity': r.get('backend_identity'),
  'backend_identity_bound': r.get('backend_identity_bound'),
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
        raise RuntimeError("Claude ONE projection probe failed: " + (result.stderr or result.stdout)[-4000:])
    payload = json.loads(result.stdout)
    if payload.get("source") != "ONE_ACTIVE_CONTINUATION":
        raise RuntimeError(f"Claude ONE active selector probe failed: {payload}")
    if payload.get("credential_exposed") is not False:
        raise RuntimeError("Claude ONE credential isolation not proven")
    return payload


def main() -> int:
    if os.name == "nt":
        raise RuntimeError("Oracle-local Claude installer must run on Oracle/Linux")
    repo_root = _repo_root()
    required = repo_root / "agentos_node" / "claude_one_mcp_stdio.py"
    if not required.is_file():
        raise FileNotFoundError(f"required Claude ONE MCP module missing: {required}")
    if not (_data_root() / "runtime" / "active-continuation.json").is_file():
        raise FileNotFoundError("ONE active continuation selector is missing")

    python = _venv_python()
    evidence = probe_projection(python, repo_root)
    claude = _discover_claude()
    bootstrap = write_bootstrap(_claude_home() / "CLAUDE.md")
    mcp = install_user_mcp(claude, python=python, repo_root=repo_root)

    print(json.dumps({
        "schema": "agentos.claude-one-oracle-install/v0.1",
        "ok": True,
        "mode": "oracle-local",
        "probe": evidence,
        "claude_executable_class": "anthropic-claude-code-extension",
        "claude_home": str(_claude_home()),
        "bootstrap_path": str(bootstrap),
        "mcp_server": mcp["server"],
        "mcp_managed": mcp["managed"],
        "canonical_ir_copied": False,
        "credential_in_config": False,
        "backend_identity_inferred_from_surface": False,
        "reload_required": True,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
