import pytest

from agent_core.capability_governance import CapabilityGovernor


def test_high_risk_network_fault_requires_recovery():
    governor = CapabilityGovernor()
    denied = governor.authorize('network.disconnect', preflight_ok=True, recovery_armed=False)
    assert denied.allowed is False
    assert denied.recovery_required is True

    allowed = governor.authorize('network.disconnect', preflight_ok=True, recovery_armed=True)
    assert allowed.allowed is True


def test_reboot_preflight_failure_is_denied():
    governor = CapabilityGovernor()
    decision = governor.authorize('system.reboot', preflight_ok=False, recovery_armed=True)
    assert decision.allowed is False
    assert decision.reason == 'preflight failed'


def test_unknown_capability_fails_closed():
    governor = CapabilityGovernor()
    assert governor.authorize('unknown.power').allowed is False


def test_format_is_denied():
    governor = CapabilityGovernor()
    assert governor.authorize('filesystem.format').allowed is False
