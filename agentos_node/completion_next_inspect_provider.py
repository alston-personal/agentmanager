"""Read-only Completion Controller queue-head provider.

Exposes only the identity/state of the next durable work item selected by the
installed Completion Runtime. The caller cannot choose a work item, state path,
owner, command, argv, or filesystem location.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from typing import Any, Mapping

from agent_core.executor_job_contract import validate_executor_job
from agentos_node.executor_job_adapter import DEFAULT_PROVIDERS, ExecutorJobProviderRegistry

JOB_TYPE = "completion.next.inspect"
EXECUTOR_CLASS = "completion-controller"
PROVIDER_ID = "completion-next-inspect-v1"

DATA_ROOT = Path("/home/ubuntu/agent-data")
STATE = DATA_ROOT / "governance" / "work-items.json"
COMPLETION_RUNTIME = DATA_ROOT / "runtime" / "agentos-lobster" / "current"
WORK_COMPLETION = COMPLETION_RUNTIME / "scripts" / "work_completion.py"


def _failure(classification: str) -> dict[str, Any]:
    return {
        "verdict": "FAIL",
        "classification": classification,
        "executor_available": True,
        "routable": True,
        "authorized": True,
        "successful": False,
        "credential_exposed": False,
    }


def inspect_next_completion_work(request: Mapping[str, Any]) -> dict[str, Any]:
    spec = validate_executor_job(request)
    if spec.job_type != JOB_TYPE or spec.executor_class != EXECUTOR_CLASS:
        return {
            **_failure("COMPLETION_INSPECT_CONTRACT_MISMATCH"),
            "authorized": False,
            "routable": False,
        }

    if not WORK_COMPLETION.is_file() or not STATE.is_file():
        return {
            **_failure("COMPLETION_RUNTIME_UNAVAILABLE"),
            "authorized": False,
            "routable": False,
        }

    try:
        proc = subprocess.run(
            [
                "/usr/bin/python3",
                str(WORK_COMPLETION),
                "--state",
                str(STATE),
                "next",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
            check=False,
            env={
                "HOME": "/home/ubuntu",
                "USER": "ubuntu",
                "AGENT_DATA_ROOT": str(DATA_ROOT),
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
    except subprocess.TimeoutExpired:
        return _failure("COMPLETION_INSPECT_TIMEOUT")
    except OSError:
        return _failure("COMPLETION_INSPECT_LAUNCH_ERROR")

    if proc.returncode != 0:
        return _failure("COMPLETION_INSPECT_FAILED")

    try:
        item = json.loads(proc.stdout)
    except Exception:
        return _failure("COMPLETION_INSPECT_RESULT_INVALID")

    if item is None:
        return {
            "verdict": "PASS",
            "classification": "COMPLETION_QUEUE_EMPTY",
            "executor_available": True,
            "routable": True,
            "authorized": True,
            "successful": True,
            "credential_exposed": False,
            "work_id": "",
            "completion_status": "empty",
            "completion_owner": "",
            "completion_owner_generation": 0,
        }

    if not isinstance(item, dict):
        return _failure("COMPLETION_INSPECT_RESULT_INVALID")

    work_id = str(item.get("work_id") or "").strip()
    status = str(item.get("status") or "").strip()
    owner = str(item.get("owner") or "").strip()
    generation = int(item.get("owner_generation") or 0)
    if not work_id or status not in {"accepted", "in_progress", "blocked", "verifying"}:
        return _failure("COMPLETION_INSPECT_RESULT_INVALID")

    return {
        "verdict": "PASS",
        "classification": "COMPLETION_NEXT_WORK",
        "executor_available": True,
        "routable": True,
        "authorized": True,
        "successful": True,
        "credential_exposed": False,
        "work_id": work_id,
        "completion_status": status,
        "completion_owner": owner,
        "completion_owner_generation": generation,
    }


def register_completion_next_inspect_provider(
    registry: ExecutorJobProviderRegistry = DEFAULT_PROVIDERS,
) -> bool:
    existing = registry.get(JOB_TYPE)
    if existing is not None:
        if existing.provider_id == PROVIDER_ID and existing.executor_class == EXECUTOR_CLASS:
            return True
        raise RuntimeError("Completion next inspect provider already registered differently")
    registry.register(
        job_type=JOB_TYPE,
        provider_id=PROVIDER_ID,
        executor_class=EXECUTOR_CLASS,
        handler=inspect_next_completion_work,
    )
    return True
