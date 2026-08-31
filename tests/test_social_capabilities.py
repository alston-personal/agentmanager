from agent_core.capability_governance import CapabilityGovernor, RiskLevel
from agentos_node.social.contracts import SocialReceipt
from agentos_node.social.credentials import EnvironmentCredentialResolver


def test_social_reads_are_low_risk_and_writes_require_policy():
    governor = CapabilityGovernor()
    read_policy = governor.policy_for('social.threads.replies.read')
    write_policy = governor.policy_for('social.threads.publish')
    assert read_policy is not None and read_policy.risk == RiskLevel.LOW
    assert write_policy is not None and write_policy.risk == RiskLevel.MEDIUM
    assert write_policy.approval == 'policy'
    assert governor.authorize('social.threads.replies.read').allowed is True
    assert governor.authorize('social.threads.publish').allowed is True


def test_logical_credential_ref_resolves_without_exposing_token(monkeypatch):
    monkeypatch.setenv('SOC_THREADS_TOKEN', 'secret-token-value')
    resolver = EnvironmentCredentialResolver()
    assert resolver.present('threads/default') is True
    assert resolver.resolve('threads/default') == 'secret-token-value'
    receipt = SocialReceipt(
        capability='social.threads.identity.read',
        credential_ref='threads/default',
        ok=True,
        started_at='2026-08-31T00:00:00Z',
        completed_at='2026-08-31T00:00:01Z',
        platform='threads',
        operation='identity.read',
        result={'credential_present': True},
    ).to_dict()
    rendered = repr(receipt)
    assert 'threads/default' in rendered
    assert 'secret-token-value' not in rendered


def test_unknown_social_credential_fails_closed():
    resolver = EnvironmentCredentialResolver()
    try:
        resolver.resolve('threads/unknown')
    except KeyError as exc:
        assert 'unknown credential_ref' in str(exc)
    else:
        raise AssertionError('unknown credential ref must fail closed')
