from agent_core.executor_job_contract import canonical_experience_regression_request, project_executor_job_receipt


def test_executor_receipt_allows_only_bounded_experience_diagnostics():
    receipt = project_executor_job_receipt(
        job_id='action-diagnostic1234',
        request=canonical_experience_regression_request(),
        executor_available=True,
        routable=True,
        authorized=True,
        successful=False,
        result={
            'runtime_ok': True,
            'hydrated_experience_tool_observed': False,
            'baseline_experience_tool_not_observed': True,
            'hydration_receipt_ok': False,
            'classification': 'EXPERIENCE_HYDRATION_TOOL_NOT_OBSERVED',
            'stderr_tail': 'secret',
            'stdout': 'private',
        },
    )
    assert receipt['runtime_ok'] is True
    assert receipt['hydrated_experience_tool_observed'] is False
    assert receipt['baseline_experience_tool_not_observed'] is True
    assert receipt['hydration_receipt_ok'] is False
    assert receipt['classification'] == 'EXPERIENCE_HYDRATION_TOOL_NOT_OBSERVED'
    assert 'stderr_tail' not in receipt
    assert 'stdout' not in receipt
