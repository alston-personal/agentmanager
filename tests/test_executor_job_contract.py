import pytest

from agent_core.executor_job_contract import (
    EXECUTOR_JOB_RECEIPT_SCHEMA,
    ExecutorJobContractError,
    canonical_experience_regression_request,
    project_executor_job_receipt,
    validate_executor_job,
)


def test_canonical_experience_regression_is_exact_and_read_only():
    request = canonical_experience_regression_request()
    spec = validate_executor_job(request)
    assert spec.job_type == "experience.regression"
    assert spec.capability == "agentos.experience.regression"
    assert spec.executor_class == "openai-codex-local"
    assert spec.project_id == "agentos-core"
    assert spec.workload_ref == "issue://117"
    assert spec.authority == "read-only-regression"
    assert spec.read_only is True


@pytest.mark.parametrize(
    "field,value",
    [
        ("command", "bash -lc whoami"),
        ("argv", ["bash", "-lc", "whoami"]),
        ("executable", "/bin/bash"),
        ("cwd", "/home/ubuntu"),
        ("env", {"TOKEN": "x"}),
        ("credential", "secret"),
    ],
)
def test_generic_execution_and_credentials_are_rejected(field, value):
    request = canonical_experience_regression_request()
    request[field] = value
    with pytest.raises(ExecutorJobContractError):
        validate_executor_job(request)


def test_nested_forbidden_execution_field_is_rejected_before_unknown_field_handling():
    request = canonical_experience_regression_request()
    request["options"] = {"shell": "whoami"}
    with pytest.raises(ExecutorJobContractError, match="forbidden generic-execution field"):
        validate_executor_job(request)


@pytest.mark.parametrize(
    "field,value",
    [
        ("project_id", "other-project"),
        ("executor_class", "anthropic-claude-code-extension"),
        ("workload_ref", "issue://999"),
        ("authority", "admin"),
    ],
)
def test_registered_semantics_cannot_be_overridden(field, value):
    request = canonical_experience_regression_request()
    request[field] = value
    with pytest.raises(ExecutorJobContractError):
        validate_executor_job(request)


def test_unknown_job_type_fails_closed():
    request = canonical_experience_regression_request()
    request["job_type"] = "shell.exec"
    with pytest.raises(ExecutorJobContractError, match="unsupported executor job type"):
        validate_executor_job(request)


def test_receipt_keeps_availability_routing_authority_and_success_independent():
    request = canonical_experience_regression_request()
    receipt = project_executor_job_receipt(
        job_id="job-1",
        request=request,
        executor_available=True,
        routable=False,
        authorized=False,
        successful=False,
        result={
            "experiment_id": "exp-1",
            "verdict": "FAIL",
            "baseline_score": 0.0,
            "hydrated_score": 0.0,
            "uplift": 0.0,
            "hydration_receipt_ok": False,
            "classification": "EXECUTOR_NOT_ROUTABLE",
            "stdout": "must not cross boundary",
            "credential": "must not cross boundary",
        },
    )
    assert receipt["schema"] == EXECUTOR_JOB_RECEIPT_SCHEMA
    assert receipt["executor_available"] is True
    assert receipt["routable"] is False
    assert receipt["authorized"] is False
    assert receipt["successful"] is False
    assert receipt["credential_exposed"] is False
    assert "stdout" not in receipt
    assert "credential" not in receipt
