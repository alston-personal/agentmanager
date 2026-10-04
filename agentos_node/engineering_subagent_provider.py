"""Bounded engineering Subagent providers for Main Agent work items.

These providers delegate only three fixed engineering work items to the existing
Antigravity relay. Relay completion never self-authorizes task success; the
provider returns a terminal PENDING_VERIFICATION classification and #889/Main
Agent must verify branch/CI evidence before closure.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from agent_core.executor_job_contract import validate_executor_job
from agentos_node.antigravity_relay import AntigravityRelayClient
from agentos_node.antigravity_relay_worker import discover_executor
from agentos_node.executor_job_adapter import DEFAULT_PROVIDERS, ExecutorJobProviderRegistry

EXECUTOR_CLASS = "antigravity-engineering"
PROVIDER_ID = "agentos-engineering-subagent-v1"
RELAY_ROOT = Path("/home/ubuntu/agent-data/runtime/antigravity-relay")
WORKSPACE = Path("/home/ubuntu/agentmanager")
POLL_SECONDS = 1.0
TIMEOUT_SECONDS = 240.0
HEALTH_SNAPSHOT_MAX_AGE_SECONDS = 420.0

JOBS: dict[str, dict[str, str]] = {
    "engineering.subagent.smoke": {
        "workload_ref": "surface://engineering-subagent",
        "branch": "",
        "goal": "Prove the governed engineering Subagent can inspect the canonical AgentOS repository without mutation.",
        "acceptance": "Inspect current HEAD and repository status, make no changes, and return a concrete bounded result.",
    },
    "engineering.executor.health": {
        "workload_ref": "surface://engineering-executors",
        "branch": "",
        "goal": "Probe fixed local engineering model providers without mutation.",
        "acceptance": "Classify Claude and agy as READY, AUTH_REQUIRED, TIMEOUT, ERROR, or UNAVAILABLE and select the first READY provider.",
    },
    "engineering.model.smoke": {
        "workload_ref": "surface://engineering-model-subagent",
        "branch": "",
        "goal": "Prove a health-selected real model executor can complete a bounded read-only AgentOS task through the relay.",
        "acceptance": "Return a concrete read-only result through the selected healthy provider without modifying the repository.",
    },
    "engineering.windows-thin-client.fix": {
        "workload_ref": "issue://892",
        "branch": "fix/subagent-892-windows-thin-client",
        "goal": "Fix Windows Thin Client isolated installed-package verification regression.",
        "acceptance": "Thin Client Windows workflow passes without weakening bootstrap, health, or verify checks.",
    },
    "engineering.realm-device-flow.fix": {
        "workload_ref": "issue://893",
        "branch": "fix/subagent-893-realm-device-flow",
        "goal": "Fix Realm Device Flow request -> approve -> claim -> heartbeat regression.",
        "acceptance": "Realm Device Flow workflow passes without weakening enrollment, challenge, approval, claim, or heartbeat checks.",
    },
    "engineering.realm-node-fabric.fix": {
        "workload_ref": "issue://894",
        "branch": "fix/subagent-894-realm-node-fabric",
        "goal": "Fix Realm Node Fabric regression introduced around executor inventory/onboarding compatibility.",
        "acceptance": "Realm Node Fabric tests and package entry-point validation pass without vendor hard-coding or weaker assertions.",
    },
}


def _failure(classification: str, *, executor_available: bool = True, routable: bool = True, authorized: bool = True) -> dict[str, Any]:
    return {
        "verdict": "FAIL",
        "classification": classification,
        "executor_available": executor_available,
        "routable": routable,
        "authorized": authorized,
        "successful": False,
        "credential_exposed": False,
    }


def _instruction(job_type: str) -> str:
    item = JOBS[job_type]
    if job_type in {"engineering.subagent.smoke", "engineering.model.smoke"}:
        return (
            f"Execute bounded AgentOS engineering probe {item['workload_ref']}. "
            f"Goal: {item['goal']} "
            f"Acceptance: {item['acceptance']} "
            "Do not create or switch branches, do not modify files, do not commit, do not push, "
            "do not deploy, and do not expose credentials. Report the observed repository HEAD "
            "and whether the worktree is clean. If inspection is unavailable, report BLOCKED."
        )
    return (
        f"Execute bounded AgentOS engineering work {item['workload_ref']}. "
        f"Goal: {item['goal']} "
        f"Acceptance: {item['acceptance']} "
        f"Use dedicated branch {item['branch']} based on current core/integration. "
        "Inspect the current failing CI evidence before editing. Make the minimal safe fix, "
        "run the relevant tests, commit changes, and open or update a PR targeting core/integration. "
        "Do not deploy production, do not weaken tests, do not expose credentials, and do not "
        "modify unrelated projects. If the repository/worktree is unsafe or evidence is insufficient, "
        "stop and report BLOCKED rather than guessing."
    )


def _relay_failure_classification(receipt: Mapping[str, Any]) -> str:
    if str(receipt.get("classification") or "") == "UNKNOWN_SIDE_EFFECT":
        return "ENGINEERING_EXECUTOR_UNKNOWN_SIDE_EFFECT"
    error = str(receipt.get("error") or "")
    if "StrandedProcessingCapsule" in error:
        return "ENGINEERING_EXECUTOR_UNKNOWN_SIDE_EFFECT"
    if receipt.get("timed_out") is True or int(receipt.get("returncode") or 0) == 124:
        return "ENGINEERING_EXECUTOR_TIMEOUT"
    error = str(receipt.get("error") or "")
    if "no authorized local Antigravity executor discovered" in error:
        return "ENGINEERING_EXECUTOR_UNAVAILABLE"
    returncode = receipt.get("returncode")
    if isinstance(returncode, int) and returncode != 0:
        return "ENGINEERING_EXECUTOR_NONZERO"
    if error:
        return "ENGINEERING_EXECUTOR_RUNTIME_ERROR"
    return "ENGINEERING_EXECUTOR_FAILED"


def _run_read_only_smoke(workspace_path: Path) -> dict[str, Any]:
    try:
        head = subprocess.run(
            ["git", "-C", str(workspace_path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(workspace_path), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return _failure("ENGINEERING_SUBAGENT_SMOKE_PROBE_FAILED")
    if len(head) != 40 or any(ch not in "0123456789abcdef" for ch in head):
        return _failure("ENGINEERING_SUBAGENT_SMOKE_INVALID_HEAD")
    return {
        "verdict": "PASS",
        "classification": "ENGINEERING_SUBAGENT_SMOKE_COMPLETED_PENDING_VERIFICATION",
        "executor_available": True,
        "routable": True,
        "authorized": True,
        "successful": False,
        "credential_exposed": False,
        "executor_provider": "deterministic-git-probe",
        "executor_returncode": 0,
        "executor_timed_out": False,
        "worktree_clean": status == "",
        "observed_head": head,
    }


def _classify_probe_output(returncode: int, text: str, *, timed_out: bool) -> str:
    lowered = text.casefold()
    if any(token in lowered for token in ("login", "sign in", "auth required", "not authenticated", "unauthorized")):
        return "AUTH_REQUIRED"
    if timed_out:
        return "TIMEOUT"
    if returncode == 0:
        return "READY"
    return "ERROR"


def _classify_probe_diagnostic(returncode: int, text: str, *, timed_out: bool) -> str:
    lowered = text.casefold()
    if any(token in lowered for token in ("login", "sign in", "auth required", "not authenticated", "unauthorized")):
        return "AUTH_REQUIRED"
    if timed_out:
        return "TIMEOUT"
    if returncode == 0:
        return "READY"
    if any(token in lowered for token in (
        "unknown command", "unrecognized argument", "unrecognized option",
        "no such option", "invalid option", "usage:",
    )):
        return "CLI_CONTRACT"
    if any(token in lowered for token in (
        "rate limit", "rate_limit", "quota", "too many requests", "resource exhausted",
    )):
        return "RATE_LIMITED"
    if any(token in lowered for token in (
        "connection refused", "connection reset", "network is unreachable",
        "temporary failure", "timed out connecting", "dns",
    )):
        return "NETWORK"
    return "NONZERO"


def _probe_binary_liveness(provider: str) -> str:
    try:
        selected, executable = discover_executor(provider)
    except Exception:
        return "ERROR"
    if not executable:
        return "UNAVAILABLE"
    binary = str(executable[0])
    argv = [binary, "--version"] if selected == "claude" else [binary, "--help"]
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "TIMEOUT"
    except OSError:
        return "UNAVAILABLE"
    return "READY" if completed.returncode == 0 else "ERROR"


def _probe_model_provider(provider: str, workspace_path: Path, *, timeout_seconds: float = 20.0) -> dict[str, Any]:
    try:
        selected, executable = discover_executor(provider)
    except Exception:
        return {"state": "ERROR", "returncode": None, "timed_out": False}
    if not executable:
        return {"state": "UNAVAILABLE", "returncode": None, "timed_out": False}

    prompt = (
        "AgentOS bounded executor health probe. Do not modify files, do not create branches, "
        "do not commit, push, deploy, or expose credentials. Reply exactly READY."
    )
    if selected == "agy":
        argv = [*executable, "run", "--task", prompt, "--workspace", str(workspace_path)]
    else:
        # Health probing must isolate model/auth/network readiness from project
        # customizations. Safe mode preserves authentication/model selection but
        # disables CLAUDE.md, skills, plugins, hooks, MCP, and other local
        # customization sources. Also remove all tools and cap the agent loop.
        argv = [
            *executable,
            "--safe-mode",
            "--tools", "",
            "--disallowedTools", "mcp__*",
            "--max-turns", "1",
            "--disable-slash-commands",
            prompt,
        ]

    try:
        completed = subprocess.run(
            argv,
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            timeout=max(1.0, float(timeout_seconds)),
            check=False,
        )
        text = (completed.stdout or "")[-4000:] + "\n" + (completed.stderr or "")[-4000:]
        return {
            "state": _classify_probe_output(int(completed.returncode), text, timed_out=False),
            "classification": _classify_probe_diagnostic(int(completed.returncode), text, timed_out=False),
            "returncode": int(completed.returncode),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else str(exc.stdout or "")
        err = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else str(exc.stderr or "")
        probe_text = out[-4000:] + "\n" + err[-4000:]
        return {
            "state": _classify_probe_output(124, probe_text, timed_out=True),
            "classification": _classify_probe_diagnostic(124, probe_text, timed_out=True),
            "returncode": 124,
            "timed_out": True,
        }
    except OSError:
        return {"state": "UNAVAILABLE", "classification": "SPAWN_ERROR", "returncode": None, "timed_out": False}


def _probe_provider_stability(
    provider: str,
    workspace_path: Path,
    *,
    attempts: int = 2,
) -> dict[str, Any]:
    results = [_probe_model_provider(provider, workspace_path) for _ in range(max(1, int(attempts)))]
    ready_count = sum(1 for item in results if item.get("state") == "READY")
    total = len(results)
    if ready_count == total:
        state = "READY"
    elif ready_count > 0:
        state = "FLAKY"
    else:
        states = [str(item.get("state") or "ERROR") for item in results]
        if "AUTH_REQUIRED" in states:
            state = "AUTH_REQUIRED"
        elif all(item == "TIMEOUT" for item in states):
            state = "TIMEOUT"
        elif all(item == "UNAVAILABLE" for item in states):
            state = "UNAVAILABLE"
        else:
            state = "ERROR"
    last = results[-1]
    classifications = [str(item.get("classification") or "") for item in results]
    classification = next((value for value in classifications if value and value != "READY"), "READY" if state == "READY" else state)
    return {
        "state": state,
        "classification": classification,
        "returncode": last.get("returncode"),
        "timed_out": any(item.get("timed_out") is True for item in results),
        "ready_count": ready_count,
        "attempts": total,
    }


def _snapshot_path() -> Path:
    root = Path(os.environ.get("AGENTOS_CLIENT_HOME") or (Path.home() / ".agentos"))
    return root / "executor-adoption.json"


def _parse_utc(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _load_executor_snapshot(*, max_age_seconds: float = HEALTH_SNAPSHOT_MAX_AGE_SECONDS) -> dict[str, Any] | None:
    path = _snapshot_path()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if payload.get("schema") != "agentos.executor-adoption/v0.2":
        return None
    observed = _parse_utc(str(payload.get("observed_at") or ""))
    if observed is None:
        return None
    age = (datetime.now(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds()
    if age < 0 or age > max(1.0, float(max_age_seconds)):
        return None
    return payload


def _snapshot_entry(snapshot: Mapping[str, Any] | None, executor_id: str) -> dict[str, Any]:
    if not isinstance(snapshot, Mapping):
        return {}
    for item in snapshot.get("executors") or []:
        if isinstance(item, dict) and str(item.get("executor_id") or "") == executor_id:
            return item
    return {}


def _snapshot_health_classification(item: Mapping[str, Any]) -> str:
    health = item.get("provider_health") or {}
    value = str(health.get("classification") or "").strip()
    if value:
        return value
    provider_error = str(item.get("provider_error") or "").strip()
    if provider_error:
        return "PROVIDER_EXCEPTION_" + provider_error.upper()
    state = str(item.get("state") or "").strip()
    if state == "AUTH_REQUIRED":
        return "AUTH_REQUIRED"
    if state == "TIMEOUT":
        return "TIMEOUT"
    if state in {"UNHEALTHY", "ERROR"}:
        return "HEALTH_CONTRACT_INCOMPLETE"
    return ""


def _snapshot_state(item: Mapping[str, Any]) -> str:
    if not item:
        return "UNAVAILABLE"
    if item.get("stable_routable") is True:
        return "READY"
    state = str(item.get("state") or "ERROR")
    classification = _snapshot_health_classification(item)
    if state == "AUTH_REQUIRED":
        return "AUTH_REQUIRED"
    if classification == "TIMEOUT":
        return "TIMEOUT"
    if state == "READY":
        return "FLAKY"
    if state in {"INSTALL_REQUIRED", "REGISTRATION_REQUIRED"}:
        return "UNAVAILABLE"
    return "ERROR"


def _health_from_snapshot(snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
    claude = _snapshot_entry(snapshot, "claude-code")
    agy = _snapshot_entry(snapshot, "antigravity")
    claude_state = _snapshot_state(claude)
    agy_state = _snapshot_state(agy)
    selected_provider = ""
    for provider, item in (("claude", claude), ("agy", agy)):
        if item.get("stable_routable") is True:
            selected_provider = provider
            break
    ok = bool(selected_provider)

    def ready_count(item: Mapping[str, Any]) -> int:
        return min(2, max(0, int(item.get("ready_streak") or 0)))

    return {
        "verdict": "PASS" if ok else "FAIL",
        "runtime_source_commit": str(os.environ.get("AGENTOS_ACTION_RUNTIME_SOURCE_COMMIT") or ""),
        "classification": "ENGINEERING_EXECUTOR_HEALTH_READY" if ok else "ENGINEERING_EXECUTOR_NO_HEALTHY_PROVIDER",
        "executor_available": bool(claude or agy),
        "routable": ok,
        "authorized": ok,
        "successful": ok,
        "credential_exposed": False,
        "claude_liveness": "READY" if claude.get("discovered") else "UNAVAILABLE",
        "claude_state": claude_state,
        "claude_returncode": 124 if claude_state == "TIMEOUT" else (0 if claude_state == "READY" else None),
        "claude_timed_out": claude_state == "TIMEOUT",
        "claude_ready_count": ready_count(claude),
        "claude_probe_attempts": 2,
        "claude_health_classification": _snapshot_health_classification(claude),
        "agy_liveness": "READY" if agy.get("discovered") else "UNAVAILABLE",
        "agy_state": agy_state,
        "agy_returncode": 124 if agy_state == "TIMEOUT" else (0 if agy_state == "READY" else None),
        "agy_timed_out": agy_state == "TIMEOUT",
        "agy_ready_count": ready_count(agy),
        "agy_probe_attempts": 2,
        "agy_health_classification": _snapshot_health_classification(agy),
        "selected_provider": selected_provider,
    }


def _run_executor_health(workspace_path: Path) -> dict[str, Any]:
    # Keep the durable adoption snapshot current for subsequent model routing,
    # but use independent bounded two-sample probes for this health receipt.
    try:
        from agentos_node.executor_reconcile import reconcile_executor_adoption
        reconcile_executor_adoption(node_id="oracle-core-node")
    except Exception:
        return _failure(
            "ENGINEERING_EXECUTOR_HEALTH_REFRESH_FAILED",
            executor_available=False,
            routable=False,
            authorized=False,
        )

    claude = _probe_provider_stability("claude", workspace_path, attempts=2)
    agy = _probe_provider_stability("agy", workspace_path, attempts=2)
    selected_provider = ""
    for provider, result in (("claude", claude), ("agy", agy)):
        if result.get("state") == "READY":
            selected_provider = provider
            break
    ok = bool(selected_provider)
    return {
        "verdict": "PASS" if ok else "FAIL",
        "classification": "ENGINEERING_EXECUTOR_HEALTH_READY" if ok else "ENGINEERING_EXECUTOR_NO_HEALTHY_PROVIDER",
        "executor_available": any(result.get("state") != "UNAVAILABLE" for result in (claude, agy)),
        "routable": ok,
        "authorized": ok,
        "successful": ok,
        "credential_exposed": False,
        "claude_liveness": _probe_binary_liveness("claude"),
        "claude_state": str(claude.get("state") or "ERROR"),
        "claude_returncode": claude.get("returncode"),
        "claude_timed_out": bool(claude.get("timed_out")),
        "claude_ready_count": int(claude.get("ready_count") or 0),
        "claude_probe_attempts": int(claude.get("attempts") or 0),
        "claude_health_classification": str(claude.get("classification") or ""),
        "agy_liveness": _probe_binary_liveness("agy"),
        "agy_state": str(agy.get("state") or "ERROR"),
        "agy_returncode": agy.get("returncode"),
        "agy_timed_out": bool(agy.get("timed_out")),
        "agy_ready_count": int(agy.get("ready_count") or 0),
        "agy_probe_attempts": int(agy.get("attempts") or 0),
        "agy_health_classification": str(agy.get("classification") or ""),
        "selected_provider": selected_provider,
    }


def _read_executor_health() -> dict[str, Any]:
    snapshot = _load_executor_snapshot()
    if snapshot is None:
        return _failure(
            "ENGINEERING_EXECUTOR_HEALTH_SNAPSHOT_STALE",
            executor_available=False,
            routable=False,
            authorized=False,
        )
    return _health_from_snapshot(snapshot)


def run_engineering_subagent(
    request: Mapping[str, Any],
    *,
    relay_root: str | Path = RELAY_ROOT,
    workspace: str | Path = WORKSPACE,
    timeout_seconds: float = TIMEOUT_SECONDS,
) -> dict[str, Any]:
    spec = validate_executor_job(request)
    if spec.job_type not in JOBS or spec.executor_class != EXECUTOR_CLASS:
        return _failure(
            "ENGINEERING_SUBAGENT_CONTRACT_MISMATCH",
            executor_available=False,
            routable=False,
            authorized=False,
        )
    workspace_path = Path(workspace)
    if not workspace_path.is_dir() or not (workspace_path / ".git").exists():
        return _failure(
            "ENGINEERING_WORKSPACE_UNAVAILABLE",
            executor_available=False,
            routable=False,
            authorized=False,
        )

    if spec.job_type == "engineering.subagent.smoke":
        return _run_read_only_smoke(workspace_path)
    if spec.job_type == "engineering.executor.health":
        return _run_executor_health(workspace_path)

    health = _read_executor_health()
    selected_provider = str(health.get("selected_provider") or "")
    if not selected_provider:
        return health

    client = AntigravityRelayClient(relay_root)
    if spec.job_type == "engineering.model.smoke":
        canonical_ir = {"schema": "agentos.engineering-subagent-ir/v1"}
        instruction = "AgentOS routed model smoke. Do not modify files. Reply exactly READY."
    else:
        canonical_ir = {
            "schema": "agentos.engineering-subagent-ir/v1",
            "goal": JOBS[spec.job_type]["goal"],
            "constraints": [
                f"workload_ref={JOBS[spec.job_type]['workload_ref']}",
                f"branch={JOBS[spec.job_type]['branch'] or 'none'}",
                "base_ref=core/integration",
                "production_mutation=false",
                "main_agent_verification_required=true",
            ],
        }
        instruction = _instruction(spec.job_type)
    try:
        capsule = client.submit(
            project_id="agentos-core",
            canonical_ir=canonical_ir,
            instruction=instruction,
            workspace=str(workspace_path),
            executor_hint=f"provider:{selected_provider}",
        )
    except Exception:
        return _failure("ENGINEERING_RELAY_SUBMIT_FAILED")

    capsule_id = str(capsule.get("capsule_id") or "")
    deadline = time.monotonic() + max(1.0, float(timeout_seconds))
    receipt = None
    while time.monotonic() < deadline:
        try:
            receipt = client.receipt(capsule_id)
        except Exception:
            return _failure("ENGINEERING_RELAY_RECEIPT_INVALID")
        if receipt is not None:
            break
        time.sleep(POLL_SECONDS)

    if receipt is None:
        result = _failure("ENGINEERING_RELAY_TIMEOUT")
        result["selected_provider"] = selected_provider
        result["executor_provider"] = selected_provider
        result["executor_timed_out"] = True
        return result
    if receipt.get("ok") is not True:
        classification = _relay_failure_classification(receipt)
        result = _failure(
            classification,
            executor_available=classification != "ENGINEERING_EXECUTOR_UNAVAILABLE",
        )
        provider = str(receipt.get("provider") or "").strip().lower()
        if provider in {"claude", "agy"}:
            result["executor_provider"] = provider
        else:
            result["executor_provider"] = selected_provider
        result["selected_provider"] = selected_provider
        returncode = receipt.get("returncode")
        if isinstance(returncode, int):
            result["executor_returncode"] = returncode
        result["executor_timed_out"] = receipt.get("timed_out") is True
        return result

    # A successful relay process only proves that the delegated worker returned.
    # It deliberately does not prove code correctness or acceptance. Main Agent
    # must inspect the resulting branch/PR and CI before closing the work item.
    return {
        "verdict": "PASS",
        "classification": (
            "ENGINEERING_MODEL_SMOKE_COMPLETED_PENDING_VERIFICATION"
            if spec.job_type == "engineering.model.smoke"
            else "ENGINEERING_EXECUTOR_COMPLETED_PENDING_VERIFICATION"
        ),
        "executor_available": True,
        "routable": True,
        "authorized": True,
        "successful": False,
        "credential_exposed": False,
        "executor_provider": selected_provider,
        "selected_provider": selected_provider,
        "executor_returncode": int(receipt.get("returncode") or 0),
        "executor_timed_out": receipt.get("timed_out") is True,
    }


def register_engineering_subagent_providers(
    *,
    registry: ExecutorJobProviderRegistry = DEFAULT_PROVIDERS,
    relay_root: str | Path = RELAY_ROOT,
    workspace: str | Path = WORKSPACE,
) -> bool:
    for job_type in JOBS:
        existing = registry.get(job_type)
        if existing is not None:
            if existing.provider_id != PROVIDER_ID or existing.executor_class != EXECUTOR_CLASS:
                raise RuntimeError(f"engineering provider already registered differently: {job_type}")
            continue

        def handler(request: Mapping[str, Any], _job_type: str = job_type) -> Mapping[str, Any]:
            spec = validate_executor_job(request)
            if spec.job_type != _job_type:
                return _failure("ENGINEERING_SUBAGENT_JOB_TYPE_MISMATCH")
            return run_engineering_subagent(
                request,
                relay_root=relay_root,
                workspace=workspace,
            )

        registry.register(
            job_type=job_type,
            provider_id=PROVIDER_ID,
            executor_class=EXECUTOR_CLASS,
            handler=handler,
        )
    return True
