from agent_core.executor_job_contract import canonical_experience_regression_request
from agentos_node.executor_job_adapter import (
    ExecutorJobProviderRegistry,
    execute_registered_executor_job,
)


def test_missing_provider_fails_without_fallback():
    receipt = execute_registered_executor_job(
        job_id="job-missing",
        request=canonical_experience_regression_request(),
        registry=ExecutorJobProviderRegistry(),
    )
    assert receipt["executor_available"] is False
    assert receipt["routable"] is False
    assert receipt["authorized"] is False
    assert receipt["successful"] is False
    assert receipt["classification"] == "JOB_IMPLEMENTATION_UNAVAILABLE"
    assert receipt["credential_exposed"] is False


def test_executor_class_mismatch_is_not_routable_or_authorized():
    registry = ExecutorJobProviderRegistry()
    registry.register(
        job_type="experience.regression",
        provider_id="test-provider",
        executor_class="wrong-executor",
        handler=lambda request: {"verdict": "PASS"},
    )
    receipt = execute_registered_executor_job(
        job_id="job-mismatch",
        request=canonical_experience_regression_request(),
        registry=registry,
    )
    assert receipt["executor_available"] is True
    assert receipt["routable"] is False
    assert receipt["authorized"] is False
    assert receipt["successful"] is False
    assert receipt["classification"] == "EXECUTOR_CLASS_MISMATCH"


def test_registered_provider_returns_only_sanitized_result_projection():
    registry = ExecutorJobProviderRegistry()
    registry.register(
        job_type="experience.regression",
        provider_id="issue117-v1",
        executor_class="openai-codex-local",
        handler=lambda request: {
            "experiment_id": "exp-1",
            "verdict": "PASS",
            "baseline_score": 0.14,
            "hydrated_score": 1.0,
            "uplift": 0.86,
            "hydration_receipt_ok": True,
            "credential_exposed": False,
            "stdout": "private model output",
            "stderr": "private diagnostics",
            "prompt": "private prompt",
            "session_id": "private session",
        },
    )
    receipt = execute_registered_executor_job(
        job_id="job-pass",
        request=canonical_experience_regression_request(),
        registry=registry,
    )
    assert receipt["executor_available"] is True
    assert receipt["routable"] is True
    assert receipt["authorized"] is True
    assert receipt["successful"] is True
    assert receipt["verdict"] == "PASS"
    assert receipt["hydration_receipt_ok"] is True
    assert receipt["credential_exposed"] is False
    for forbidden in ("stdout", "stderr", "prompt", "session_id"):
        assert forbidden not in receipt


def test_provider_exception_is_classified_without_exception_text():
    registry = ExecutorJobProviderRegistry()

    def fail(request):
        raise RuntimeError("/home/ubuntu/private/path token=secret")

    registry.register(
        job_type="experience.regression",
        provider_id="issue117-v1",
        executor_class="openai-codex-local",
        handler=fail,
    )
    receipt = execute_registered_executor_job(
        job_id="job-error",
        request=canonical_experience_regression_request(),
        registry=registry,
    )
    assert receipt["classification"] == "PROVIDER_ERROR_RUNTIMEERROR"
    text = str(receipt)
    assert "/home/ubuntu/private/path" not in text
    assert "token=secret" not in text


def test_duplicate_provider_registration_fails_closed():
    registry = ExecutorJobProviderRegistry()
    registry.register(
        job_type="experience.regression",
        provider_id="first",
        executor_class="openai-codex-local",
        handler=lambda request: {"verdict": "FAIL"},
    )
    try:
        registry.register(
            job_type="experience.regression",
            provider_id="second",
            executor_class="openai-codex-local",
            handler=lambda request: {"verdict": "PASS"},
        )
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("duplicate provider registration must fail closed")
