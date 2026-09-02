"""Governed bounded executor-job contract for AgentOS ONE.

This is deliberately not a remote shell contract. A caller selects only a
registered job type plus its bounded semantic inputs. Node-local adapters own
the executable mapping and credentials. Long-running executor work is submitted
as an asynchronous job and observed later through an opaque job identifier.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping


EXECUTOR_JOB_SCHEMA = "agentos.executor-job/v1"
EXECUTOR_JOB_SUBMISSION_SCHEMA = "agentos.executor-job-submission/v1"
EXECUTOR_JOB_RECEIPT_SCHEMA = "agentos.executor-job-receipt/v1"

FORBIDDEN_REQUEST_KEYS = {
    "command",
    "cmd",
    "shell",
    "script",
    "argv",
    "executable",
    "binary",
    "cwd",
    "path",
    "paths",
    "env",
    "environment",
    "token",
    "credential",
    "credentials",
    "secret",
    "password",
}

# Opaque identifiers may cross the control plane, but path-like or URL-like
# values may not. The format is intentionally transport-neutral; Oracle's
# Action Relay currently produces ``action-<uuidhex>`` while another Node may
# use a different safe prefix.
_OPAQUE_JOB_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{7,127}\Z")


class ExecutorJobContractError(ValueError):
    """Raised when a caller attempts to escape a bounded executor-job contract."""


@dataclass(frozen=True)
class JobTypeSpec:
    job_type: str
    capability: str
    authority: str
    executor_class: str
    project_id: str
    workload_ref: str
    read_only: bool


JOB_TYPES: dict[str, JobTypeSpec] = {
    "experience.regression": JobTypeSpec(
        job_type="experience.regression",
        capability="agentos.experience.regression",
        authority="read-only-regression",
        executor_class="openai-codex-local",
        project_id="agentos-core",
        workload_ref="issue://117",
        read_only=True,
    ),
}


def _reject_forbidden_keys(value: Any, *, prefix: str = "request") -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key).strip().casefold()
            if key in FORBIDDEN_REQUEST_KEYS:
                raise ExecutorJobContractError(f"forbidden generic-execution field: {prefix}.{raw_key}")
            _reject_forbidden_keys(child, prefix=f"{prefix}.{raw_key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_keys(child, prefix=f"{prefix}[{index}]")


def validate_executor_job(request: Mapping[str, Any]) -> JobTypeSpec:
    """Validate a declarative executor job without granting execution authority."""
    if not isinstance(request, Mapping):
        raise ExecutorJobContractError("executor job must be an object")
    _reject_forbidden_keys(request)

    allowed = {
        "schema",
        "job_type",
        "project_id",
        "executor_class",
        "workload_ref",
        "authority",
    }
    unexpected = set(request) - allowed
    if unexpected:
        raise ExecutorJobContractError(f"unexpected executor-job fields: {sorted(unexpected)}")
    if request.get("schema") != EXECUTOR_JOB_SCHEMA:
        raise ExecutorJobContractError("unsupported executor-job schema")

    job_type = str(request.get("job_type") or "").strip()
    spec = JOB_TYPES.get(job_type)
    if spec is None:
        raise ExecutorJobContractError("unsupported executor job type")

    exact = {
        "project_id": spec.project_id,
        "executor_class": spec.executor_class,
        "workload_ref": spec.workload_ref,
        "authority": spec.authority,
    }
    for field, expected in exact.items():
        if request.get(field) != expected:
            raise ExecutorJobContractError(f"{field} must equal the registered job contract")
    return spec


def validate_executor_job_id(job_id: str) -> str:
    """Validate an opaque durable identifier without accepting filesystem input."""
    value = str(job_id or "").strip()
    if not _OPAQUE_JOB_ID.fullmatch(value):
        raise ExecutorJobContractError("job_id must be an opaque non-path identifier")
    return value


def canonical_experience_regression_request() -> dict[str, str]:
    spec = JOB_TYPES["experience.regression"]
    return {
        "schema": EXECUTOR_JOB_SCHEMA,
        "job_type": spec.job_type,
        "project_id": spec.project_id,
        "executor_class": spec.executor_class,
        "workload_ref": spec.workload_ref,
        "authority": spec.authority,
    }


def project_executor_job_submission(
    *,
    job_id: str,
    node_id: str,
    request: Mapping[str, Any],
    reused: bool = False,
) -> dict[str, Any]:
    """Project the asynchronous acknowledgement returned before execution ends."""
    spec = validate_executor_job(request)
    job_id = validate_executor_job_id(job_id)
    node_id = str(node_id or "").strip()
    if not node_id:
        raise ExecutorJobContractError("node_id is required")
    return {
        "schema": EXECUTOR_JOB_SUBMISSION_SCHEMA,
        "ok": True,
        "state": "queued",
        "job_id": job_id,
        "node_id": node_id,
        "job_type": spec.job_type,
        "project_id": spec.project_id,
        "executor_class": spec.executor_class,
        "capability": spec.capability,
        "reused": bool(reused),
        "credential_exposed": False,
    }


def project_executor_job_receipt(
    *,
    job_id: str,
    request: Mapping[str, Any],
    executor_available: bool,
    routable: bool,
    authorized: bool,
    successful: bool,
    result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create the bounded model-visible result; never infer one state from another."""
    spec = validate_executor_job(request)
    job_id = validate_executor_job_id(job_id)
    summary: dict[str, Any] = {
        "schema": EXECUTOR_JOB_RECEIPT_SCHEMA,
        "job_id": job_id,
        "job_type": spec.job_type,
        "project_id": spec.project_id,
        "executor_class": spec.executor_class,
        "capability": spec.capability,
        "executor_available": bool(executor_available),
        "routable": bool(routable),
        "authorized": bool(authorized),
        "successful": bool(successful),
        "credential_exposed": False,
    }
    if result is not None:
        # Only explicitly safe scalar regression fields cross the boundary.
        for key in (
            "experiment_id",
            "verdict",
            "baseline_score",
            "hydrated_score",
            "uplift",
            "hydration_receipt_ok",
            "classification",
        ):
            value = result.get(key)
            if isinstance(value, (str, int, float, bool)) or value is None:
                summary[key] = value
    return summary
