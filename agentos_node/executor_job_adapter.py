"""Node-local adapter for registered ONE executor jobs.

The adapter separates the generic ONE job transport from workload ownership.
Core owns validation/routing semantics; issue-specific providers register a fixed
callable under a known job type.  No caller-supplied command, argv, path, module,
or executable can influence provider selection.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from agent_core.executor_job_contract import (
    ExecutorJobContractError,
    JobTypeSpec,
    project_executor_job_receipt,
    validate_executor_job,
)


Provider = Callable[[Mapping[str, Any]], Mapping[str, Any]]


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


def _failure_receipt(
    *,
    job_id: str,
    request: Mapping[str, Any],
    spec: JobTypeSpec,
    executor_available: bool,
    routable: bool,
    authorized: bool,
    classification: str,
) -> dict[str, Any]:
    return project_executor_job_receipt(
        job_id=job_id,
        request=request,
        executor_available=executor_available,
        routable=routable,
        authorized=authorized,
        successful=False,
        result={"classification": classification},
    )


def execute_registered_executor_job(
    *,
    job_id: str,
    request: Mapping[str, Any],
    registry: ExecutorJobProviderRegistry = DEFAULT_PROVIDERS,
) -> dict[str, Any]:
    """Execute exactly one registered provider and return a sanitized receipt.

    Availability, routability, authorization, and success remain independent.
    A missing provider is a normal bounded failure, never a shell fallback.
    """
    spec = validate_executor_job(request)
    binding = registry.get(spec.job_type)
    if binding is None:
        return _failure_receipt(
            job_id=job_id,
            request=request,
            spec=spec,
            executor_available=False,
            routable=False,
            authorized=False,
            classification="JOB_IMPLEMENTATION_UNAVAILABLE",
        )
    if binding.executor_class != spec.executor_class:
        return _failure_receipt(
            job_id=job_id,
            request=request,
            spec=spec,
            executor_available=True,
            routable=False,
            authorized=False,
            classification="EXECUTOR_CLASS_MISMATCH",
        )

    try:
        raw = binding.handler(request)
    except Exception as exc:
        # Do not project exception text: it may include provider-local paths,
        # model/session details, or other implementation-private material.
        return _failure_receipt(
            job_id=job_id,
            request=request,
            spec=spec,
            executor_available=True,
            routable=True,
            authorized=True,
            classification=f"PROVIDER_ERROR_{type(exc).__name__.upper()}",
        )
    if not isinstance(raw, Mapping):
        return _failure_receipt(
            job_id=job_id,
            request=request,
            spec=spec,
            executor_available=True,
            routable=True,
            authorized=True,
            classification="PROVIDER_RESULT_INVALID",
        )

    successful = raw.get("verdict") == "PASS" and raw.get("credential_exposed") is not True
    return project_executor_job_receipt(
        job_id=job_id,
        request=request,
        executor_available=True,
        routable=True,
        authorized=True,
        successful=successful,
        result=raw,
    )
