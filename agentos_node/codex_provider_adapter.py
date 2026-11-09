from __future__ import annotations

import os
import secrets
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INVOKE_SCHEMA = "agentos.executor-provider-invoke/v0.1"
def _default_core_workspace() -> Path:
    explicit = os.environ.get("AGENTOS_CORE_WORKSPACE")
    if explicit:
        return Path(explicit).expanduser()
    legacy = Path("/home/ubuntu/agentmanager")
    return legacy if legacy.is_dir() else Path.cwd()


WORKSPACES = {"agentos-core": _default_core_workspace()}
RECEIPT_ROOT = Path.home() / ".agentos" / "provider-receipts" / "codex"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _discover_codex() -> str | None:
    candidates = [
        Path.home() / ".local/bin/codex",
        Path.home() / ".npm-global/bin/codex",
        Path("/usr/local/bin/codex"),
        Path("/usr/bin/codex"),
    ]
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    found = shutil.which("codex")
    return str(Path(found).resolve()) if found else None


def _classify(text: str, returncode: int, *, timed_out: bool = False) -> str:
    lowered = str(text or "").casefold()
    if timed_out:
        return "TIMEOUT"
    if any(token in lowered for token in ("rate limit", "rate_limit", "quota", "too many requests", "resource exhausted")):
        return "RATE_LIMITED"
    if any(token in lowered for token in ("401 unauthorized", "incorrect api key", "token_invalidated", "app_session_terminated")):
        return "AUTH_RUNTIME_REJECTED"
    if any(token in lowered for token in ("not logged in", "login required", "please login", "authentication required")):
        return "AUTH_REQUIRED"
    if any(token in lowered for token in ("connection refused", "network is unreachable", "dns", "stream disconnected")):
        return "NETWORK"
    return "READY" if returncode == 0 else "NONZERO"


def _run(executable: str, argv: list[str], *, cwd: Path, timeout: float) -> tuple[int, str, bool]:
    try:
        completed = subprocess.run(
            [executable, *argv],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=max(1.0, float(timeout)),
            check=False,
        )
        text = (completed.stdout or "")[-4000:] + "\n" + (completed.stderr or "")[-4000:]
        return int(completed.returncode), text, False
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else str(exc.stdout or "")
        err = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else str(exc.stderr or "")
        return 124, out[-4000:] + "\n" + err[-4000:], True


class CodexProvider:
    executor_id = "codex"
    provider_id = "openai"
    executor_class = "codex"

    def discover(self) -> dict[str, Any]:
        executable = _discover_codex()
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
        executable = _discover_codex()
        if not executable:
            return {
                "installed": False,
                "reachable": False,
                "authorized": False,
                "routable": False,
                "healthy": False,
                "state": "INSTALL_REQUIRED",
                "classification": "INSTALL_REQUIRED",
            }

        login_rc, login_text, login_timeout = _run(
            executable, ["login", "status"], cwd=Path.home(), timeout=10.0
        )
        login_classification = _classify(login_text, login_rc, timed_out=login_timeout)
        if login_rc != 0:
            return {
                "installed": True,
                "reachable": True,
                "authorized": False,
                "routable": False,
                "healthy": False,
                "state": "AUTH_REQUIRED" if login_classification == "AUTH_REQUIRED" else "UNHEALTHY",
                "classification": login_classification,
            }

        workspace = WORKSPACES["agentos-core"]
        if not workspace.is_dir():
            return {
                "installed": True,
                "reachable": True,
                "authorized": True,
                "routable": False,
                "healthy": False,
                "state": "UNHEALTHY",
                "classification": "WORKSPACE_UNAVAILABLE",
            }

        rc, output, timed_out = _run(
            executable,
            [
                "-a", "never",
                "exec",
                "--skip-git-repo-check",
                "--sandbox", "read-only",
                "--color", "never",
                "--ephemeral",
                "-C", str(workspace),
                "AgentOS Codex health probe. Do not modify files. Reply exactly READY.",
            ],
            cwd=workspace,
            timeout=60.0,
        )
        classification = _classify(output, rc, timed_out=timed_out)
        ready = rc == 0 and classification == "READY"
        return {
            "installed": True,
            "reachable": classification not in {"NETWORK"},
            "authorized": classification not in {"AUTH_REQUIRED", "AUTH_RUNTIME_REJECTED"},
            "routable": ready,
            "healthy": ready,
            "state": "READY" if ready else ("AUTH_REQUIRED" if classification in {"AUTH_REQUIRED", "AUTH_RUNTIME_REJECTED"} else "UNHEALTHY"),
            "classification": classification,
            "timed_out": timed_out,
            "rate_limited": classification == "RATE_LIMITED",
        }

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

        executable = _discover_codex()
        if not executable:
            raise RuntimeError("Codex executable unavailable")
        workspace = WORKSPACES[workspace_ref]
        invocation_id = "codex-" + secrets.token_hex(12)
        started = _utc_now()
        sandbox = "read-only" if operation == "agent.chat" else "workspace-write"
        rc, output, timed_out = _run(
            executable,
            [
                "-a", "never",
                "exec",
                "--skip-git-repo-check",
                "--sandbox", sandbox,
                "--color", "never",
                "--ephemeral",
                "-C", str(workspace),
                instruction,
            ],
            cwd=workspace,
            timeout=180.0,
        )
        classification = _classify(output, rc, timed_out=timed_out)
        RECEIPT_ROOT.mkdir(parents=True, exist_ok=True)
        receipt = {
            "executor_id": self.executor_id,
            "provider_id": self.provider_id,
            "invocation_id": invocation_id,
            "started_at": started,
            "completed_at": _utc_now(),
            "successful": rc == 0 and not timed_out,
            "classification": classification,
            "returncode": rc,
            "timed_out": timed_out,
            "credential_exposed": False,
        }
        (RECEIPT_ROOT / f"{invocation_id}.json").write_text(
            __import__("json").dumps(receipt, sort_keys=True) + "\n", encoding="utf-8"
        )
        return {
            "ok": True,
            "state": "completed",
            "invocation_id": invocation_id,
            "executor_id": self.executor_id,
            "credential_exposed": False,
        }

    def cancel(self, invocation_id: str) -> dict[str, Any]:
        return {"ok": False, "classification": "CANCEL_UNSUPPORTED", "invocation_id": str(invocation_id)}

    def receipt(self, invocation_id: str) -> dict[str, Any]:
        value = str(invocation_id or "").strip()
        if not value.startswith("codex-") or len(value) > 80:
            raise ValueError("invalid provider invocation id")
        path = RECEIPT_ROOT / f"{value}.json"
        if not path.exists():
            return {"ok": True, "state": "pending", "invocation_id": value}
        data = __import__("json").loads(path.read_text(encoding="utf-8"))
        return {"ok": True, "state": "completed", **data}
