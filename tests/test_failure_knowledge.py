import pytest
from runtime_core.failure_knowledge import FailureKnowledge


def _failure():
    return FailureKnowledge(
        failure_id="F-cross-session-001",
        goal="complete longitudinal experiment",
        approach="resume execution from local session context without reconciliation",
        expected_result="continue latest canonical goal",
        actual_result="continued stale onboarding trajectory",
        failure_class="STALE_EXECUTOR",
        environment_fingerprint="chat-session/tool-surface-A",
        capability_manifest_digest="cap-v1",
        evidence_refs=["PR#3", "CI#656"],
        root_cause="artifact continuity existed but active intent and execution ownership were not canonical",
        root_cause_confidence=0.9,
        recovery="reconcile canonical goal and execution lease before effects",
        retry_conditions=["execution_lease_added", "canonical_goal_revision_changed"],
    )


def test_same_conditions_avoid_known_failure():
    f = _failure()
    assert f.should_avoid_retry(environment_fingerprint="chat-session/tool-surface-A", capability_manifest_digest="cap-v1")


def test_changed_environment_does_not_overgeneralize_failure():
    f = _failure()
    assert not f.should_avoid_retry(environment_fingerprint="agentos-execution-broker/v1", capability_manifest_digest="cap-v2")


def test_explicit_retry_condition_allows_controlled_retry():
    f = _failure()
    assert not f.should_avoid_retry(
        environment_fingerprint="chat-session/tool-surface-A",
        capability_manifest_digest="cap-v1",
        changed_conditions=["execution_lease_added"],
    )


def test_confidence_is_bounded():
    with pytest.raises(ValueError):
        FailureKnowledge(
            failure_id="F", goal="g", approach="a", expected_result="x", actual_result="y",
            failure_class="C", environment_fingerprint="e", capability_manifest_digest="c",
            root_cause_confidence=1.1,
        )
