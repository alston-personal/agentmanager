"""Bounded engineering Subagent providers for Main Agent work items.

These providers delegate fixed engineering work items and a read-only control
smoke to the existing Antigravity relay. Relay completion never self-authorizes
mutating task success; the
provider returns a terminal PENDING_VERIFICATION classification and #889/Main
Agent must verify branch/CI evidence before closure.
"""
from __future__ import annotations

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
    "engineering.control.smoke": {
        "workload_ref": "control://engineering-smoke",
        "mode": "read-only-smoke",
        "goal": "Prove the governed engineering Subagent can execute a bounded read-only task.",
        "acceptance": "Return the exact marker AGENTOS_ENGINEERING_SUBAGENT_SMOKE=PASS without modifying the repository.",
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


def _failure(classification: str, *, executor_available: bool = True, routable: bool = True, authorized: bool = True, **safe_fields: Any) -> dict[str, Any]:
    result = {
        "verdict": "FAIL",
        "classification": classification,
        "executor_available": executor_available,
        "routable": routable,
        "authorized": authorized,
        "successful": False,
        "credential_exposed": False,
    }
    result.update(safe_fields)
    return result


def _relay_failure(receipt: Mapping[str, Any]) -> dict[str, Any]:
    provider = str(receipt.get("provider") or "").strip().lower()
    safe: dict[str, Any] = {}
    if provider in {"claude", "agy"}:
        safe["executor_provider"] = provider
    returncode = receipt.get("returncode")
    if isinstance(returncode, int):
        safe["executor_returncode"] = returncode
    timed_out = receipt.get("timed_out") is True
    safe["executor_timed_out"] = timed_out
    if timed_out:
        return _failure("ENGINEERING_EXECUTOR_TIMEOUT", **safe)
    if isinstance(returncode, int) and returncode != 0:
        return _failure("ENGINEERING_EXECUTOR_NONZERO", **safe)
    if receipt.get("error"):
        return _failure("ENGINEERING_EXECUTOR_INTERNAL_ERROR", **safe)
    return _failure("ENGINEERING_EXECUTOR_FAILED", **safe)


def _instruction(job_type: str) -> str:
    item = JOBS[job_type]
    if item.get("mode") == "read-only-smoke":
        return (
            "Execute the bounded AgentOS engineering control smoke. "
            "Read only enough repository state to confirm the workspace is usable. "
            "Do not edit files, create or switch branches, commit, push, deploy, or open a PR. "
            "If the workspace is usable, return exactly this marker on its own line: "
            "AGENTOS_ENGINEERING_SUBAGENT_SMOKE=PASS"
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

    client = AntigravityRelayClient(relay_root)
    try:
        capsule = client.submit(
            project_id="agentos-core",
            canonical_ir={
                "schema": "agentos.engineering-subagent-ir/v1",
                "goal": JOBS[spec.job_type]["goal"],
                "constraints": (
                    [
                        f"workload_ref={JOBS[spec.job_type]['workload_ref']}",
                        "read_only=true",
                        "production_mutation=false",
                    ]
                    if JOBS[spec.job_type].get("mode") == "read-only-smoke"
                    else [
                        f"workload_ref={JOBS[spec.job_type]['workload_ref']}",
                        f"branch={JOBS[spec.job_type]['branch']}",
                        "base_ref=core/integration",
                        "production_mutation=false",
                        "main_agent_verification_required=true",
                    ]
                ),
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
        return _relay_failure(receipt)

    provider = str(receipt.get("provider") or "").strip().lower()
    safe_provider = provider if provider in {"claude", "agy"} else None
    if spec.job_type == "engineering.control.smoke":
        stdout = str(receipt.get("stdout") or "")
        if "AGENTOS_ENGINEERING_SUBAGENT_SMOKE=PASS" not in stdout.splitlines():
            return _failure(
                "ENGINEERING_SMOKE_MARKER_MISSING",
                executor_provider=safe_provider,
                executor_returncode=int(receipt.get("returncode") or 0),
                executor_timed_out=False,
            )
        return {
            "verdict": "PASS",
            "classification": "ENGINEERING_SMOKE_PASS",
            "executor_available": True,
            "routable": True,
            "authorized": True,
            "successful": True,
            "credential_exposed": False,
            "executor_provider": safe_provider,
            "executor_returncode": int(receipt.get("returncode") or 0),
            "executor_timed_out": False,
        }

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
