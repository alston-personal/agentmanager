"""Node-local adapter for registered ONE executor jobs.

The adapter separates the generic ONE job transport from workload ownership.
Core owns validation/routing semantics; issue-specific providers register a fixed
callable under a known job type. No caller-supplied command, argv, path, module,
or executable can influence provider selection.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from agent_core.executor_job_contract import (
    project_executor_job_receipt,
    validate_executor_job,
)


Provider = Callable[[Mapping[str, Any]], Mapping[str, Any]]
_SAFE_PROVIDER_RESULT_FIELDS = (
    "experiment_id",
    "verdict",
    "baseline_score",
    "hydrated_score",
    "uplift",
    "hydration_receipt_ok",
    "classification",
)


@dataclass(frozen=True)
class ProviderBinding:
    job_type: str
    provider_id: str
    executor_class: str
    handler: Provider


class ExecutorJobProviderRegistry:
    """Trusted-process provider registry; registrations are not model input."""

    def __init__(self) -> None:
        self._bindings: dict[str, ProviderBinding] = {}

    def register(
        self,
        *,
        job_type: str,
        provider_id: str,
        executor_class: str,
        handler: Provider,
    ) -> None:
        job_type = str(job_type or "").strip()
        provider_id = str(provider_id or "").strip()
        executor_class = str(executor_class or "").strip()
        if not job_type or not provider_id or not executor_class or not callable(handler):
            raise ValueError("complete trusted provider binding is required")
        if job_type in self._bindings:
            raise ValueError(f"provider already registered for job type: {job_type}")
        self._bindings[job_type] = ProviderBinding(
            job_type=job_type,
            provider_id=provider_id,
            executor_class=executor_class,
            handler=handler,
        )

    def get(self, job_type: str) -> ProviderBinding | None:
        return self._bindings.get(str(job_type or ""))


DEFAULT_PROVIDERS = ExecutorJobProviderRegistry()


def _semantic_failure(classification: str, *, executor_available: bool, routable: bool, authorized: bool) -> dict[str, Any]:
    return {
        "ok": False,
        "executor_available": bool(executor_available),
        "routable": bool(routable),
        "authorized": bool(authorized),
        "successful": False,
        "classification": classification,
        "credential_exposed": False,
    }


def _sanitize_provider_result(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Bound provider output before it is persisted by Action Relay.

    Final model-visible projection is also bounded by the Core receipt contract,
    but persistence must be safe on its own. In particular stdout/stderr, paths,
    prompts, session data and credentials never enter the relay receipt.
    """
    safe: dict[str, Any] = {}
    for key in _SAFE_PROVIDER_RESULT_FIELDS:
        value = raw.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
    return safe


def run_registered_executor_job(
    *,
    request: Mapping[str, Any],
    registry: ExecutorJobProviderRegistry = DEFAULT_PROVIDERS,
) -> dict[str, Any]:
    """Run one trusted semantic provider without knowing the transport job ID.

    This is the Action Relay boundary: providers receive only the validated
    semantic request. They never receive capsule IDs, spool paths, commands,
    credentials, or other transport authority.
    """
    spec = validate_executor_job(request)
    binding = registry.get(spec.job_type)
    if binding is None:
        return _semantic_failure(
            "JOB_IMPLEMENTATION_UNAVAILABLE",
            executor_available=False,
            routable=False,
            authorized=False,
        )
    if binding.executor_class != spec.executor_class:
        return _semantic_failure(
            "EXECUTOR_CLASS_MISMATCH",
            executor_available=True,
            routable=False,
            authorized=False,
        )
    try:
        raw = binding.handler(request)
    except Exception as exc:
        return _semantic_failure(
            f"PROVIDER_ERROR_{type(exc).__name__.upper()}",
            executor_available=True,
            routable=True,
            authorized=True,
        )
    if not isinstance(raw, Mapping):
        return _semantic_failure(
            "PROVIDER_RESULT_INVALID",
            executor_available=True,
            routable=True,
            authorized=True,
        )

    result = _sanitize_provider_result(raw)
    result["executor_available"] = True
    result["routable"] = True
    result["authorized"] = True
    result["successful"] = result.get("verdict") == "PASS" and raw.get("credential_exposed") is not True
    result["credential_exposed"] = False
    result["ok"] = bool(result["successful"])
    return result


def execute_registered_executor_job(
    *,
    job_id: str,
    request: Mapping[str, Any],
    registry: ExecutorJobProviderRegistry = DEFAULT_PROVIDERS,
) -> dict[str, Any]:
    """Compatibility wrapper that projects a formal transport receipt."""
    semantic = run_registered_executor_job(request=request, registry=registry)
    return project_executor_job_receipt(
        job_id=job_id,
        request=request,
        executor_available=bool(semantic.get("executor_available")),
        routable=bool(semantic.get("routable")),
        authorized=bool(semantic.get("authorized")),
        successful=bool(semantic.get("successful")),
        result=semantic,
    )
