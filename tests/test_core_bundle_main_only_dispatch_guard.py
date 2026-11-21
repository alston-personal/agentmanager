"""Regression: the canonical Core bundle release is manual, main-only, exact-source."""

from pathlib import Path


def test_core_bundle_deployment_requires_explicit_exact_main():
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github/workflows/oracle-core-bundle-immutable-runtime-convergence.yml"
    ).read_text(encoding="utf-8")
    event_header = workflow.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
    assert "workflow_dispatch:" in event_header
    assert "pull_request:" in event_header
    assert "\n  push:" not in event_header
    assert "expected_main_sha:" in event_header
    assert "core_bundle_approved:" in event_header
    jobs = workflow.split("\n  converge:\n", 1)[1]
    guard = jobs.split("\n    runs-on:", 1)[0]
    assert "github.event_name == 'workflow_dispatch'" in guard
    assert "github.ref_name == 'main'" in guard
    assert "inputs.core_bundle_approved == true" in guard
    assert "github.ref_name == 'core/integration'" not in guard
    assert "EXPECTED_MAIN_SHA: ${{ inputs.expected_main_sha }}" in jobs
    assert 'test "${GITHUB_SHA}" = "${EXPECTED_MAIN_SHA}"' in jobs
    assert 'test "${GITHUB_REF}" = refs/heads/main' in jobs
    teams = workflow.split("\n  teams-immutable-cutover:\n", 1)[1].split("\n  converge:\n", 1)[0]
    assert "inputs.teams_only == true" in teams
    assert "github.ref_name == 'main'" in teams
    assert 'test "${GITHUB_SHA}" = "${EXPECTED_MAIN_SHA}"' in teams
    assert "bash \"$DEPLOY\" \"$SHA\"" in teams
