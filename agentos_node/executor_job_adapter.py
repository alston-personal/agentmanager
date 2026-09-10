"""Node-local adapter for registered ONE executor jobs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from agent_core.executor_job_contract import project_executor_job_receipt, validate_executor_job
from agent_core.experience_attribution_contract import sanitize_attribution_evidence_json

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
_PROVIDER_STATE_FIELDS = ("executor_available", "routable", "authorized", "successful")


@dataclass(frozen=True)
class ProviderBinding:
    job_type: str
    provider_id: str
    executor_class: str
    handler: Provider


class ExecutorJobProviderRegistry:
    def __init__(self) -> None:
        self._bindings: dict[str, ProviderBinding] = {}

    def register(self, *, job_type: str, provider_id: str, executor_class: str, handler: Provider) -> None:
        job_type = str(job_type or "").strip()
        provider_id = str(provider_id or "").strip()
        executor_class = str(executor_class or "").strip()
        if not job_type or not provider_id or not executor_class or not callable(handler):
            raise ValueError("complete trusted provider binding is required")
        if job_type in self._bindings:
            raise ValueError(f"provider already registered for job type: {job_type}")
        self._bindings[job_type] = ProviderBinding(job_type, provider_id, executor_class, handler)

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
    """Bound provider output before Action Relay persistence.

    No arbitrary nested provider data crosses this boundary. #117's one structured
    evidence object is carried only as canonical JSON after strict schema validation.
    """
    safe: dict[str, Any] = {}
    for key in _SAFE_PROVIDER_RESULT_FIELDS:
        value = raw.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
    if "attribution_evidence_json" in raw:
        safe["attribution_evidence_json"] = sanitize_attribution_evidence_json(
            raw.get("attribution_evidence_json")
        )
    return safe


def _trusted_provider_state(raw: Mapping[str, Any], key: str, default: bool) -> bool:
    if key not in raw:
        return bool(default)
    value = raw.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"trusted provider state must be boolean: {key}")
    return value


def run_registered_executor_job(*, request: Mapping[str, Any], registry: ExecutorJobProviderRegistry = DEFAULT_PROVIDERS) -> dict[str, Any]:
    spec = validate_executor_job(request)
    binding = registry.get(spec.job_type)
    if binding is None:
        return _semantic_failure("JOB_IMPLEMENTATION_UNAVAILABLE", executor_available=False, routable=False, authorized=False)
    if binding.executor_class != spec.executor_class:
        return _semantic_failure("EXECUTOR_CLASS_MISMATCH", executor_available=True, routable=False, authorized=False)
    try:
        raw = binding.handler(request)
    except Exception as exc:
        return _semantic_failure(f"PROVIDER_ERROR_{type(exc).__name__.upper()}", executor_available=True, routable=True, authorized=True)
    if not isinstance(raw, Mapping):
        return _semantic_failure("PROVIDER_RESULT_INVALID", executor_available=True, routable=True, authorized=True)
    try:
        result = _sanitize_provider_result(raw)
        executor_available = _trusted_provider_state(raw, "executor_available", True)
        routable = _trusted_provider_state(raw, "routable", True)
        authorized = _trusted_provider_state(raw, "authorized", True)
        default_success = result.get("verdict") == "PASS" and raw.get("credential_exposed") is not True
        successful = _trusted_provider_state(raw, "successful", default_success)
    except (ValueError, TypeError):
        return _semantic_failure("PROVIDER_STATE_INVALID", executor_available=True, routable=True, authorized=True)

    if raw.get("credential_exposed") is True:
        successful = False
        result["classification"] = "PROVIDER_CREDENTIAL_BOUNDARY_VIOLATION"

    result.update({
        "executor_available": executor_available,
        "routable": routable,
        "authorized": authorized,
        "successful": successful,
        "credential_exposed": False,
        "ok": bool(successful),
    })
    return result


def execute_registered_executor_job(*, job_id: str, request: Mapping[str, Any], registry: ExecutorJobProviderRegistry = DEFAULT_PROVIDERS) -> dict[str, Any]:
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
