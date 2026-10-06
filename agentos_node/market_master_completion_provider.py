"""Bounded Completion Controller intake provider for Market Master #1200.

This is intentionally a fixed semantic proving workload. The caller cannot
supply work text, paths, shell, owner, acceptance criteria, or workspace.
The provider delegates the actual ledger mutation to the installed immutable
Completion Runtime.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Mapping

from agent_core.executor_job_contract import validate_executor_job
from agentos_node.executor_job_adapter import DEFAULT_PROVIDERS, ExecutorJobProviderRegistry

JOB_TYPE = "completion.market-master-1200.register"
EXECUTOR_CLASS = "completion-controller"
PROVIDER_ID = "completion-market-master-1200-intake-v1"

DATA_ROOT = Path("/home/ubuntu/agent-data")
STATE = DATA_ROOT / "governance" / "work-items.json"
COMPLETION_RUNTIME = DATA_ROOT / "runtime" / "agentos-lobster" / "current"
WORK_COMPLETION = COMPLETION_RUNTIME / "scripts" / "work_completion.py"
WORKSPACE = Path("/home/ubuntu/agent-workspaces/agentmanager")
WORK_ID = "market-master-1200-mvp"

INTAKE = {
    "schema": "agentos.work-intake/v1",
    "work_id": WORK_ID,
    "project_id": "market-master-evolution",
    "title": "Finish Market Master MVP v0.1",
    "next_action": (
        "Backfill recent-years 2454 TWSE STOCK_DAY + T86 data for 2022-2026, "
        "run replay using Discovery=2022-2024, Validation=2025, LockedHoldout=2026, "
        "compare Flow/Momentum/Reversal/Neutral on identical cutoffs, and produce "
        "an evidence-backed report before proposing any scope expansion."
    ),
    "acceptance": [
        "2022-2026 recent-years dataset is archived with immutable raw source evidence",
        "Discovery 2022-2024 replay is completed without future leakage",
        "Validation 2025 replay is completed without tuning on validation outcomes",
        "Locked holdout 2026 replay is evaluated only after strategy freeze",
        "Flow Momentum Reversal Neutral are compared on identical cutoffs",
        "Result report includes sample count accuracy Brier abstention MFE MAE and limitations",
        "Terminal completion has verification evidence and no unsupported alpha claim",
    ],
    "source": "https://github.com/alston-personal/agentmanager/issues/1200",
    "workspace": str(WORKSPACE),
    "lease_seconds": 1800,
}


def _failure(classification: str, *, authorized: bool = True, routable: bool = True) -> dict[str, Any]:
    return {
        "verdict": "FAIL",
        "classification": classification,
        "executor_available": True,
        "routable": routable,
        "authorized": authorized,
        "successful": False,
        "credential_exposed": False,
        "work_id": WORK_ID,
    }


def _existing_item() -> dict[str, Any] | None:
    if not STATE.is_file():
        return None
    try:
        payload = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return None
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, dict):
        return None
    item = items.get(WORK_ID)
    return item if isinstance(item, dict) else None


def _success(item: Mapping[str, Any], classification: str) -> dict[str, Any]:
    return {
        "verdict": "PASS",
        "classification": classification,
        "executor_available": True,
        "routable": True,
        "authorized": True,
        "successful": True,
        "credential_exposed": False,
        "work_id": WORK_ID,
        "completion_status": str(item.get("status") or ""),
        "completion_owner": str(item.get("owner") or ""),
        "completion_owner_generation": int(item.get("owner_generation") or 0),
    }


def register_market_master_completion_work(request: Mapping[str, Any]) -> dict[str, Any]:
    spec = validate_executor_job(request)
    if spec.job_type != JOB_TYPE or spec.executor_class != EXECUTOR_CLASS:
        return _failure("COMPLETION_INTAKE_CONTRACT_MISMATCH", authorized=False, routable=False)

    existing = _existing_item()
    if existing is not None:
        return _success(existing, "COMPLETION_WORK_ALREADY_REGISTERED")

    if not WORK_COMPLETION.is_file():
        return _failure("COMPLETION_RUNTIME_UNAVAILABLE", authorized=False, routable=False)
    if not WORKSPACE.is_dir():
        return _failure("COMPLETION_WORKSPACE_UNAVAILABLE", authorized=False, routable=False)

    temp_path: Path | None = None
    try:
        fd, raw_path = tempfile.mkstemp(prefix="market-master-intake-", suffix=".json", dir="/tmp")
        temp_path = Path(raw_path)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(INTAKE, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, 0o600)

        proc = subprocess.run(
            [
                "/usr/bin/python3",
                str(WORK_COMPLETION),
                "--state",
                str(STATE),
                "register-intake",
                "--input",
                str(temp_path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
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
        return _failure("COMPLETION_INTAKE_TIMEOUT")
    except OSError:
        return _failure("COMPLETION_INTAKE_LAUNCH_ERROR")
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    if proc.returncode != 0:
        return _failure("COMPLETION_INTAKE_FAILED")

    item = _existing_item()
    if item is None:
        return _failure("COMPLETION_INTAKE_RECEIPT_MISSING")
    if item.get("owner") != "role://completion.controller":
        return _failure("COMPLETION_INTAKE_OWNER_MISMATCH")

    return _success(item, "COMPLETION_WORK_REGISTERED")


def register_market_master_completion_provider(
    registry: ExecutorJobProviderRegistry = DEFAULT_PROVIDERS,
) -> bool:
    existing = registry.get(JOB_TYPE)
    if existing is not None:
        if existing.provider_id == PROVIDER_ID and existing.executor_class == EXECUTOR_CLASS:
            return True
        raise RuntimeError("Market Master completion provider already registered differently")
    registry.register(
        job_type=JOB_TYPE,
        provider_id=PROVIDER_ID,
        executor_class=EXECUTOR_CLASS,
        handler=register_market_master_completion_work,
    )
    return True
