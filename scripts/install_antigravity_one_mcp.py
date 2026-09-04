#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import venv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MCP_PACKAGE = "mcp>=2,<3"
SERVER_NAME = "agentos-one"
HOOK_NAME = "agentos-one-preinvocation"
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

This enrolled client participates in AgentOS ONE through a credential-isolated `PreInvocation` hook plus the `agentos-one` MCP server.

On the first invocation of a fresh Antigravity conversation, the hook resolves ONE's active continuation before the model is called and injects the exact current Canonical IR generation. The workspace is environment metadata, not continuation authority. For explicit live checks, use `one_status`, `one_resolve_active`, or `one_resolve(project)`.

If the hook reports `ONE_IR_HEAD_UNRESOLVED`, do not reconstruct AgentOS state from workspace files, Pulse, PM2, local memory, or vendor history. Never expose Realm/node credentials. The local adapter owns the trust boundary. `agy`, standalone `gemini`, Claude, and Codex are distinct executors and are not substitutes for the active Antigravity executor.
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


def antigravity_hooks_config_path() -> Path:
    explicit = os.environ.get("AGENTOS_ANTIGRAVITY_HOOKS_CONFIG")
    if explicit:
        return Path(explicit).expanduser()
    return Path.home() / ".gemini" / "config" / "hooks.json"


def _windows_hook_command(launcher: Path) -> str:
    command_processor = os.environ.get("COMSPEC", "cmd.exe")
    return f'{command_processor} /d /c call "{launcher}"'


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
    raw = path.read_text(encoding="utf-8-sig")
    if not raw.strip():
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"MCP config must be a JSON object: {path}")
    return data


def _backup(path: Path) -> None:
    if not path.exists():
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    shutil.copy2(path, path.with_name(path.name + f".agentos-backup-{stamp}"))


def _atomic_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _backup(path)
    tmp = path.with_suffix(path.suffix + ".agentos.tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)
    return path


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
    if mode == CLIENT_MODE:
        env["AGENTOS_CLIENT_CONFIG"] = str(discover_client_config())
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


def write_hook_launcher(
    state_root: Path,
    *,
    python: Path,
    repo_root: Path,
    client_config: Path,
    audit_path: Path,
) -> Path:
    values = (python, repo_root, client_config, audit_path)
    if any("\n" in str(value) or "\r" in str(value) for value in values):
        raise ValueError("hook launcher paths must not contain newlines")
    if os.name == "nt":
        path = state_root / "agentos-one-preinvocation.cmd"
        content = (
            "@echo off\r\n"
            f'set "PYTHONPATH={repo_root}"\r\n'
            'set "AGENTOS_ONE_MCP_MODE=client"\r\n'
            f'set "AGENTOS_CLIENT_CONFIG={client_config}"\r\n'
            f'set "AGENTOS_PREINVOCATION_AUDIT_PATH={audit_path}"\r\n'
            f'"{python}" -m agentos_node.antigravity_one_hook\r\n'
        )
    else:
        path = state_root / "agentos-one-preinvocation.sh"
        assignments = {
            "PYTHONPATH": str(repo_root),
            "AGENTOS_ONE_MCP_MODE": CLIENT_MODE,
            "AGENTOS_CLIENT_CONFIG": str(client_config),
            "AGENTOS_PREINVOCATION_AUDIT_PATH": str(audit_path),
        }
        exports = "\n".join(
            f"export {key}={shlex.quote(value)}" for key, value in assignments.items()
        )
        content = (
            "#!/usr/bin/env sh\nset -eu\n"
            + exports
            + "\nexec "
            + shlex.quote(str(python))
            + " -m agentos_node.antigravity_one_hook\n"
        )
    _atomic_text(path, content)
    if os.name != "nt":
        path.chmod(0o700)
    return path


def write_hooks_config(path: Path, *, launcher: Path) -> dict[str, Any]:
    config = _load_json(path)
    command = (
        _windows_hook_command(launcher)
        if os.name == "nt"
        else shlex.quote(str(launcher))
    )
    hook = {
        "enabled": True,
        "PreInvocation": [
            {
                "type": "command",
                "command": command,
                "timeout": 12,
            }
        ],
    }
    config[HOOK_NAME] = hook
    content = (
        json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8-sig") == content:
        return hook
    _backup(path)
    tmp = path.with_suffix(path.suffix + ".agentos.tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)
    return hook


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


def probe_preinvocation_hook(
    python: Path,
    repo_root: Path,
    *,
    client_config: Path,
    audit_path: Path,
    launcher: Path | None = None,
) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    env["AGENTOS_ONE_MCP_MODE"] = CLIENT_MODE
    env["AGENTOS_CLIENT_CONFIG"] = str(client_config)
    env["AGENTOS_PREINVOCATION_AUDIT_PATH"] = str(audit_path)
    hook_input = {
        "invocationNum": 0,
        "initialNumSteps": 1,
        "conversationId": "agentos-vopc-client-installer-probe",
        "workspacePaths": [str(repo_root)],
        "transcriptPath": "",
        "artifactDirectoryPath": "",
        "modelName": "gemini-client-installer-probe",
    }
    if launcher is None:
        command = [str(python), "-m", "agentos_node.antigravity_one_hook"]
        execution = "python-module"
    elif os.name == "nt":
        command = _windows_hook_command(launcher)
        execution = "windows-cmd-launcher"
    else:
        command = ["/bin/sh", str(launcher)]
        execution = "posix-shell-launcher"
    result = subprocess.run(
        command,
        cwd=str(repo_root),
        env=env,
        input=json.dumps(hook_input),
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
        shell=os.name == "nt" and launcher is not None,
        executable=(
            os.environ.get("COMSPEC", "cmd.exe")
            if os.name == "nt" and launcher is not None
            else None
        ),
    )
    if result.returncode != 0:
        raise RuntimeError(
            "PreInvocation hook probe failed: "
            + (result.stderr or result.stdout)[-5000:]
        )
    output = json.loads(result.stdout or "{}")
    steps = output.get("injectSteps") if isinstance(output, dict) else None
    if not isinstance(steps, list) or not steps:
        raise RuntimeError("PreInvocation hook produced no hydration")
    message = str((steps[0] or {}).get("ephemeralMessage") or "")
    if "ONE_IR_HEAD_UNRESOLVED" in message:
        raise RuntimeError("PreInvocation hook failed closed")
    if "ONE_PREINVOCATION_IR" not in message:
        raise RuntimeError("PreInvocation hook lacks canonical provenance")
    envelope = json.loads(message.rsplit("\n", 1)[-1])
    selector = envelope.get("active_selector") or {}
    canonical_ir = envelope.get("canonical_ir") or {}
    if envelope.get("selection_source") != "ONE_ACTIVE_CONTINUATION":
        raise RuntimeError("PreInvocation hook did not use active continuation")
    if envelope.get("executor_class") != "antigravity-gemini":
        raise RuntimeError("PreInvocation hook did not bind Gemini executor")
    if envelope.get("executor_identity_bound") is not True:
        raise RuntimeError("PreInvocation hook executor identity is unbound")
    if canonical_ir.get("index_id") != selector.get("index_id"):
        raise RuntimeError("PreInvocation hook index generation mismatch")
    if canonical_ir.get("ir_id") != selector.get("ir_id"):
        raise RuntimeError("PreInvocation hook IR generation mismatch")
    if envelope.get("credential_exposed") is not False:
        raise RuntimeError("PreInvocation hook credential isolation failed")
    return {
        "schema": "agentos.antigravity-one-client-preinvocation-probe/v1",
        "ok": True,
        "source": "ONE_PREINVOCATION_IR",
        "selection_source": "ONE_ACTIVE_CONTINUATION",
        "project_id": selector.get("project_id"),
        "index_id": selector.get("index_id"),
        "ir_id": selector.get("ir_id"),
        "executor_class": envelope.get("executor_class"),
        "credential_exposed": False,
        "execution": execution,
    }


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
    client_config = discover_client_config() if mode == CLIENT_MODE else None
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
    hook_probe = None
    hooks_config = None
    hook = None
    hook_launcher = None
    if mode == CLIENT_MODE:
        assert client_config is not None
        lifecycle_audit_path = (
            state_root / "antigravity-preinvocation-last.json"
        )
        probe_audit_path = (
            state_root / "antigravity-preinvocation-installer-probe.json"
        )
        probe_launcher = write_hook_launcher(
            state_root / "installer-probe",
            python=python,
            repo_root=repo_root,
            client_config=client_config,
            audit_path=probe_audit_path,
        )
        hook_probe = probe_preinvocation_hook(
            python,
            repo_root,
            client_config=client_config,
            audit_path=probe_audit_path,
            launcher=probe_launcher,
        )
        hook_launcher = write_hook_launcher(
            state_root,
            python=python,
            repo_root=repo_root,
            client_config=client_config,
            audit_path=lifecycle_audit_path,
        )
        hooks_config = antigravity_hooks_config_path()
        hook = write_hooks_config(hooks_config, launcher=hook_launcher)
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
                "preinvocation_hook_probe": hook_probe,
                "credential_in_mcp_config": False,
                "credential_in_hook_config": False,
                "hooks_config": str(hooks_config) if hooks_config else None,
                "hook_launcher": str(hook_launcher) if hook_launcher else None,
                "hook": hook,
                "reload_required": True,
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
