from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping

from agentos_node.antigravity_relay import AntigravityRelayClient
from agentos_node.antigravity_relay_worker import discover_executor

INVOKE_SCHEMA = "agentos.executor-provider-invoke/v0.1"
RELAY_ROOT = Path("/home/ubuntu/agent-data/runtime/antigravity-relay")
WORKSPACES = {
    "agentos-core": Path("/home/ubuntu/agentmanager"),
}
_OPAQUE_ID = re.compile(r"^relay-[A-Za-z0-9._-]{8,120}$")


def _auth_required(text: str) -> bool:
    lowered = str(text or "").casefold()
    return any(token in lowered for token in (
        "login", "sign in", "auth required", "not authenticated", "unauthorized"
    ))


def _provider_command(provider: str, workspace: Path, instruction: str) -> list[str] | None:
    selected, executable = discover_executor(provider)
    if not executable:
        return None
    if selected == "agy":
        return [*executable, "run", "--task", instruction, "--workspace", str(workspace)]
    if selected == "gemini":
        return [*executable, "--skip-trust", "--approval-mode", "plan", "--output-format", "text", "-p", instruction]
    return [
        *executable,
        "--safe-mode",
        "--tools", "",
        "--disallowedTools", "mcp__*",
        "--max-turns", "1",
        "--disable-slash-commands",
        instruction,
    ]


def _health(provider: str, *, workspace: Path | None = None, timeout_seconds: float = 30.0) -> dict[str, Any]:
    workspace = workspace or WORKSPACES["agentos-core"]
    command = _provider_command(
        provider,
        workspace,
        "AgentOS provider health probe. Do not modify files. Reply exactly READY.",
    )
    if not command:
        return {
            "installed": False,
            "reachable": False,
            "authorized": False,
            "routable": False,
            "healthy": False,
            "state": "INSTALL_REQUIRED",
        }
    health_cwd = workspace
    temp_health_root: tempfile.TemporaryDirectory[str] | None = None
    run_env = None
    if provider == "gemini":
        temp_health_root = tempfile.TemporaryDirectory(prefix="agentos-gemini-health-")
        temp_root = Path(temp_health_root.name)
        health_cwd = temp_root / "workspace"
        health_cwd.mkdir()
        cli_home = temp_root / "cli-home"
        settings_dir = cli_home / ".gemini"
        settings_dir.mkdir(parents=True, exist_ok=True)
        (settings_dir / "settings.json").write_text(
            json.dumps({
                "security": {"auth": {"selectedType": "oauth-personal"}},
                "hooksConfig": {"enabled": False},
                "skills": {"enabled": False},
            }, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        source_settings = Path("/home/ubuntu/.gemini")
        for credential_name in ("oauth_creds.json", "google_accounts.json"):
            source = source_settings / credential_name
            if source.exists():
                (settings_dir / credential_name).symlink_to(source)
        run_env = {
            **os.environ,
            "HOME": "/home/ubuntu",
            "USER": "ubuntu",
            "GEMINI_CLI_HOME": str(cli_home),
            "CI": "1",
        }
    try:
        completed = subprocess.run(
            command,
            cwd=str(health_cwd),
            capture_output=True,
            text=True,
            timeout=max(1.0, float(timeout_seconds)),
            check=False,
            env=run_env,
        )
    except subprocess.TimeoutExpired:
        return {
            "installed": True,
            "reachable": True,
            "authorized": False,
            "routable": False,
            "healthy": False,
            "state": "UNHEALTHY",
            "classification": "TIMEOUT",
        }
    except OSError:
        return {
            "installed": True,
            "reachable": False,
            "authorized": False,
            "routable": False,
            "healthy": False,
            "state": "UNHEALTHY",
            "classification": "SPAWN_ERROR",
        }
    finally:
        if temp_health_root is not None:
            temp_health_root.cleanup()

    combined = (completed.stdout or "")[-4000:] + "\n" + (completed.stderr or "")[-4000:]
    if completed.returncode == 0:
        return {
            "installed": True,
            "reachable": True,
            "authorized": True,
            "routable": True,
            "healthy": True,
            "state": "READY",
        }
    if _auth_required(combined):
        return {
            "installed": True,
            "reachable": True,
            "authorized": False,
            "routable": False,
            "healthy": False,
            "state": "AUTH_REQUIRED",
            "classification": "AUTH_REQUIRED",
        }
    lowered = combined.casefold()
    if any(token in lowered for token in (
        "unknown command", "unrecognized argument", "unrecognized option",
        "no such option", "invalid option", "usage:",
    )):
        classification = "CLI_CONTRACT"
    elif any(token in lowered for token in (
        "rate limit", "rate_limit", "quota", "too many requests", "resource exhausted",
    )):
        classification = "RATE_LIMITED"
    elif any(token in lowered for token in (
        "connection refused", "connection reset", "network is unreachable",
        "temporary failure", "timed out connecting", "dns",
    )):
        classification = "NETWORK"
    else:
        classification = "NONZERO"
    return {
        "installed": True,
        "reachable": True,
        "authorized": False,
        "routable": False,
        "healthy": False,
        "state": "UNHEALTHY",
        "classification": classification,
    }


class _RelayProvider:
    executor_id = ""
    provider_id = ""
    executor_class = ""
    relay_provider = ""

    def __init__(self, root: str | Path = RELAY_ROOT) -> None:
        self.root = Path(root)

    def discover(self) -> dict[str, Any]:
        _selected, executable = discover_executor(self.relay_provider)
        return {
            "executor_id": self.executor_id,
            "provider_id": self.provider_id,
            "executor_class": self.executor_class,
            "installed": bool(executable),
            "credential_access": False,
        }

    def capabilities(self) -> list[str]:
        return ["agent.chat", "code.edit"]

    def health(self) -> dict[str, Any]:
        return _health(self.relay_provider)

    def invoke(self, request: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(request, dict) or request.get("schema") != INVOKE_SCHEMA:
            raise ValueError("unsupported provider invocation schema")
        operation = str(request.get("operation") or "").strip()
        if operation not in set(self.capabilities()):
            raise ValueError("unsupported provider operation")
        project_id = str(request.get("project_id") or "").strip()
        workspace_ref = str(request.get("workspace_ref") or "").strip()
        instruction = str(request.get("instruction") or "").strip()
        if project_id != "agentos-core" or workspace_ref not in WORKSPACES:
            raise ValueError("provider invocation scope is not allowlisted")
        if not instruction or len(instruction) > 8000:
            raise ValueError("bounded semantic instruction is required")
        workspace = WORKSPACES[workspace_ref]
        if not workspace.is_dir():
            raise RuntimeError("allowlisted provider workspace is unavailable")

        client = AntigravityRelayClient(self.root)
        capsule = client.submit(
            project_id=project_id,
            canonical_ir={
                "schema": "agentos.executor-provider-ir/v0.1",
                "operation": operation,
                "provider_id": self.provider_id,
                "constraints": [
                    "caller_supplied_executable=false",
                    "caller_supplied_argv=false",
                    "caller_supplied_env=false",
                    "credential_access=false",
                ],
            },
            instruction=instruction,
            workspace=str(workspace),
            executor_hint=f"provider:{self.relay_provider}",
        )
        return {
            "ok": True,
            "state": "queued",
            "invocation_id": str(capsule["capsule_id"]),
            "executor_id": self.executor_id,
            "credential_exposed": False,
        }

    def cancel(self, invocation_id: str) -> dict[str, Any]:
        self._validate_invocation_id(invocation_id)
        return {
            "ok": False,
            "classification": "CANCEL_UNSUPPORTED",
            "invocation_id": invocation_id,
        }

    def receipt(self, invocation_id: str) -> dict[str, Any]:
        invocation_id = self._validate_invocation_id(invocation_id)
        raw = AntigravityRelayClient(self.root).receipt(invocation_id)
        if raw is None:
            return {"ok": True, "state": "pending", "invocation_id": invocation_id}
        timed_out = raw.get("timed_out") is True or int(raw.get("returncode") or 0) == 124
        returncode = raw.get("returncode")
        result = {
            "ok": raw.get("ok") is True,
            "state": "completed",
            "invocation_id": invocation_id,
            "provider": str(raw.get("provider") or self.relay_provider),
            "timed_out": timed_out,
            "credential_exposed": False,
        }
        if isinstance(returncode, int):
            result["returncode"] = returncode
        if timed_out:
            result["classification"] = "TIMEOUT"
        elif raw.get("ok") is not True:
            result["classification"] = "NONZERO"
        else:
            result["classification"] = "COMPLETED"
        return result

    @staticmethod
    def _validate_invocation_id(value: str) -> str:
        value = str(value or "").strip()
        if not _OPAQUE_ID.fullmatch(value):
            raise ValueError("invalid provider invocation id")
        return value


class ClaudeCodeProvider(_RelayProvider):
    executor_id = "claude-code"
    provider_id = "anthropic"
    executor_class = "claude-code"
    relay_provider = "claude"


class AntigravityProvider(_RelayProvider):
    executor_id = "antigravity"
    provider_id = "google-antigravity"
    executor_class = "antigravity"
    relay_provider = "agy"


class GeminiCliProvider(_RelayProvider):
    executor_id = "gemini"
    provider_id = "google"
    executor_class = "gemini"
    relay_provider = "gemini"

    def health(self) -> dict[str, Any]:
        return _health(self.relay_provider, timeout_seconds=60.0)
