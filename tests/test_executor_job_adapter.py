from dataclasses import replace

from agent_core import executor_job_contract
from agent_core.executor_job_contract import canonical_experience_regression_request
from agentos_node import executor_job_adapter
from agentos_node.executor_job_adapter import (
    ExecutorJobProviderRegistry,
    execute_registered_executor_job,
    run_registered_executor_job,
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


def _private_provider_result():
    return {
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
        "path": "/home/ubuntu/private",
        "credential": "must-not-persist",
    }


def _private_registry():
    registry = ExecutorJobProviderRegistry()
    registry.register(
        job_type="experience.regression",
        provider_id="issue117-v1",
        executor_class="openai-codex-local",
        handler=lambda request: _private_provider_result(),
    )
    return registry


def test_registered_provider_is_sanitized_before_transport_persistence():
    semantic = run_registered_executor_job(
        request=canonical_experience_regression_request(),
        registry=_private_registry(),
    )
    assert semantic["successful"] is True
    assert semantic["credential_exposed"] is False
    assert semantic["verdict"] == "PASS"
    for forbidden in ("stdout", "stderr", "prompt", "session_id", "path", "credential"):
        assert forbidden not in semantic


def test_registered_provider_returns_only_sanitized_result_projection():
    receipt = execute_registered_executor_job(
        job_id="job-pass",
        request=canonical_experience_regression_request(),
        registry=_private_registry(),
    )
    assert receipt["executor_available"] is True
    assert receipt["routable"] is True
    assert receipt["authorized"] is True
    assert receipt["successful"] is True
    assert receipt["verdict"] == "PASS"
    assert receipt["hydration_receipt_ok"] is True
    assert receipt["credential_exposed"] is False
    for forbidden in ("stdout", "stderr", "prompt", "session_id", "path", "credential"):
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


def test_required_resource_blocks_provider_before_execution(monkeypatch):
    original = executor_job_contract.JOB_TYPES["experience.regression"]
    monkeypatch.setitem(
        executor_job_contract.JOB_TYPES,
        "experience.regression",
        replace(original, required_resources=("storage://google-drive",)),
    )
    monkeypatch.setattr(
        executor_job_adapter.resource_registry,
        "resource_ready",
        lambda resource_id: (False, "RESOURCE_NOT_READY"),
    )

    called = {"value": False}
    registry = ExecutorJobProviderRegistry()

    def provider(request):
        called["value"] = True
        return {"verdict": "PASS"}

    registry.register(
        job_type="experience.regression",
        provider_id="issue117-v1",
        executor_class="openai-codex-local",
        handler=provider,
    )
    receipt = execute_registered_executor_job(
        job_id="job-resource-blocked",
        request=canonical_experience_regression_request(),
        registry=registry,
    )
    assert called["value"] is False
    assert receipt["executor_available"] is True
    assert receipt["routable"] is False
    assert receipt["authorized"] is False
    assert receipt["successful"] is False
    assert receipt["classification"] == "RESOURCE_NOT_READY"


def test_provider_sanitizer_retains_only_bounded_engineering_diagnostics():
    from agentos_node.executor_job_adapter import _sanitize_provider_result
    raw = {
        "classification": "ENGINEERING_SUBAGENT_SMOKE_COMPLETED_PENDING_VERIFICATION",
        "executor_returncode": 0,
        "executor_timed_out": False,
        "executor_provider": "deterministic-git-probe",
        "worktree_clean": True,
        "observed_head": "a" * 40,
        "stdout": "must-not-cross",
        "stderr": "must-not-cross",
        "path": "/secret",
    }
    safe = _sanitize_provider_result(raw)
    assert safe["classification"] == raw["classification"]
    assert safe["executor_returncode"] == 0
    assert safe["executor_timed_out"] is False
    assert safe["executor_provider"] == "deterministic-git-probe"
    assert safe["worktree_clean"] is True
    assert safe["observed_head"] == "a" * 40
    assert "stdout" not in safe
    assert "stderr" not in safe
    assert "path" not in safe


def test_adapter_preserves_bounded_gemini_cli_version():
    from agentos_node.executor_job_adapter import _sanitize_provider_result

    result = _sanitize_provider_result({
        "gemini_cli_version": "0.99.0",
        "stdout": "must-not-cross",
        "stderr": "must-not-cross",
    })
    assert result["gemini_cli_version"] == "0.99.0"
    assert "stdout" not in result
    assert "stderr" not in result
