"""Bounded engineering Subagent providers for Main Agent work items.

These providers delegate only three fixed engineering work items to the existing
Antigravity relay. Relay completion never self-authorizes task success; the
provider returns a terminal PENDING_VERIFICATION classification and #889/Main
Agent must verify branch/CI evidence before closure.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any, Mapping

from agent_core.executor_job_contract import validate_executor_job
from agentos_node.antigravity_relay import AntigravityRelayClient
from agentos_node.executor_job_adapter import DEFAULT_PROVIDERS, ExecutorJobProviderRegistry

EXECUTOR_CLASS = "antigravity-engineering"
PROVIDER_ID = "agentos-engineering-subagent-v1"
RELAY_ROOT = Path("/home/ubuntu/agent-data/runtime/antigravity-relay")
WORKSPACE = Path("/home/ubuntu/agentmanager")
POLL_SECONDS = 1.0
TIMEOUT_SECONDS = 240.0

JOBS: dict[str, dict[str, str]] = {
    "engineering.subagent.smoke": {
        "workload_ref": "surface://engineering-subagent",
        "branch": "",
        "goal": "Prove the governed engineering Subagent can inspect the canonical AgentOS repository without mutation.",
        "acceptance": "Inspect current HEAD and repository status, make no changes, and return a concrete bounded result.",
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
    if job_type == "engineering.subagent.smoke":
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

    client = AntigravityRelayClient(relay_root)
    try:
        capsule = client.submit(
            project_id="agentos-core",
            canonical_ir={
                "schema": "agentos.engineering-subagent-ir/v1",
                "goal": JOBS[spec.job_type]["goal"],
                "constraints": [
                    f"workload_ref={JOBS[spec.job_type]['workload_ref']}",
                    f"branch={JOBS[spec.job_type]['branch'] or 'none'}",
                    "base_ref=core/integration",
                    "production_mutation=false",
                    "main_agent_verification_required=true",
                ],
            },
            instruction=_instruction(spec.job_type),
            workspace=str(workspace_path),
            executor_hint="engineering-subagent",
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
        return _failure("ENGINEERING_RELAY_TIMEOUT")
    if receipt.get("ok") is not True:
        classification = _relay_failure_classification(receipt)
        result = _failure(
            classification,
            executor_available=classification != "ENGINEERING_EXECUTOR_UNAVAILABLE",
        )
        provider = str(receipt.get("provider") or "").strip().lower()
        if provider in {"claude", "agy"}:
            result["executor_provider"] = provider
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
        "classification": "ENGINEERING_EXECUTOR_COMPLETED_PENDING_VERIFICATION",
        "executor_available": True,
        "routable": True,
        "authorized": True,
        "successful": False,
        "credential_exposed": False,
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
