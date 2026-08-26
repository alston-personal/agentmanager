from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Iterable


class RiskLevel(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass(frozen=True)
class RecoveryRequirement:
    required: bool = False
    max_fault_seconds: int | None = None
    local_watchdog_required: bool = False
    rollback_action: str | None = None

    def __post_init__(self) -> None:
        if self.max_fault_seconds is not None and self.max_fault_seconds <= 0:
            raise ValueError('max_fault_seconds must be positive')
        if self.required and not (self.rollback_action or self.local_watchdog_required):
            raise ValueError('required recovery needs rollback_action or local watchdog')


@dataclass(frozen=True)
class CapabilityPolicy:
    capability: str
    risk: RiskLevel
    approval: str = 'auto'
    reversible: bool = True
    recovery: RecoveryRequirement = field(default_factory=RecoveryRequirement)
    evidence: tuple[str, ...] = ()
    max_lease_seconds: int | None = None

    def __post_init__(self) -> None:
        if not self.capability:
            raise ValueError('capability is required')
        if self.approval not in {'auto', 'policy', 'human', 'two_key', 'deny'}:
            raise ValueError('invalid approval mode')
        if self.max_lease_seconds is not None and self.max_lease_seconds <= 0:
            raise ValueError('max_lease_seconds must be positive')
        if self.risk >= RiskLevel.HIGH and self.approval == 'auto':
            raise ValueError('high-risk capability cannot be unconditional auto approval')
        if self.risk >= RiskLevel.HIGH and self.recovery.required is False and self.reversible:
            raise ValueError('high-risk reversible capability requires recovery governance')


DEFAULT_CAPABILITY_POLICIES: dict[str, CapabilityPolicy] = {
    'desktop.session.inspect': CapabilityPolicy(
        'desktop.session.inspect', RiskLevel.LOW, evidence=('receipt',)
    ),
    'desktop.windows.inspect': CapabilityPolicy(
        'desktop.windows.inspect', RiskLevel.LOW, evidence=('receipt',)
    ),
    'desktop.screenshot': CapabilityPolicy(
        'desktop.screenshot', RiskLevel.MEDIUM, approval='policy', evidence=('private_screenshot', 'receipt'), max_lease_seconds=300
    ),
    'desktop.open_url': CapabilityPolicy(
        'desktop.open_url', RiskLevel.MEDIUM, approval='policy', evidence=('receipt',), max_lease_seconds=300
    ),
    'desktop.mouse': CapabilityPolicy(
        'desktop.mouse', RiskLevel.MEDIUM, approval='policy', evidence=('before_state', 'receipt', 'after_state'), max_lease_seconds=300
    ),
    'desktop.keyboard': CapabilityPolicy(
        'desktop.keyboard', RiskLevel.MEDIUM, approval='policy', evidence=('before_state', 'receipt', 'after_state'), max_lease_seconds=300
    ),
    'service.restart': CapabilityPolicy(
        'service.restart', RiskLevel.HIGH, approval='policy', recovery=RecoveryRequirement(required=True, rollback_action='service.start'), evidence=('preflight', 'receipt', 'postcheck')
    ),
    'network.disconnect': CapabilityPolicy(
        'network.disconnect', RiskLevel.HIGH, approval='policy', recovery=RecoveryRequirement(required=True, max_fault_seconds=120, local_watchdog_required=True, rollback_action='network.reconnect'), evidence=('preflight', 'recovery_armed', 'offline_observed', 'online_observed')
    ),
    'system.reboot': CapabilityPolicy(
        'system.reboot', RiskLevel.HIGH, approval='policy', recovery=RecoveryRequirement(required=True, max_fault_seconds=300, local_watchdog_required=True, rollback_action='node.reconnect'), evidence=('preflight', 'reboot_armed', 'boot_id_changed', 'online_observed')
    ),
    'filesystem.format': CapabilityPolicy(
        'filesystem.format', RiskLevel.CRITICAL, approval='deny', reversible=False, evidence=('denied',)
    ),
}


@dataclass(frozen=True)
class ActionAuthorization:
    allowed: bool
    capability: str
    reason: str
    requires_human: bool = False
    requires_two_key: bool = False
    recovery_required: bool = False
    max_lease_seconds: int | None = None


class CapabilityGovernor:
    def __init__(self, policies: Iterable[CapabilityPolicy] | None = None):
        source = policies if policies is not None else DEFAULT_CAPABILITY_POLICIES.values()
        self._policies = {policy.capability: policy for policy in source}

    def policy_for(self, capability: str) -> CapabilityPolicy | None:
        return self._policies.get(capability)

    def authorize(
        self,
        capability: str,
        *,
        recovery_armed: bool = False,
        preflight_ok: bool = True,
        human_approved: bool = False,
        second_key_approved: bool = False,
    ) -> ActionAuthorization:
        policy = self.policy_for(capability)
        if policy is None:
            return ActionAuthorization(False, capability, 'capability has no governance policy')
        if policy.approval == 'deny':
            return ActionAuthorization(False, capability, 'capability is denied by policy')
        if not preflight_ok:
            return ActionAuthorization(False, capability, 'preflight failed', recovery_required=policy.recovery.required)
        if policy.recovery.required and not recovery_armed:
            return ActionAuthorization(False, capability, 'recovery is not armed', recovery_required=True, max_lease_seconds=policy.max_lease_seconds)
        if policy.approval == 'human' and not human_approved:
            return ActionAuthorization(False, capability, 'human approval required', requires_human=True, recovery_required=policy.recovery.required)
        if policy.approval == 'two_key' and not (human_approved and second_key_approved):
            return ActionAuthorization(False, capability, 'two-key approval required', requires_human=True, requires_two_key=True, recovery_required=policy.recovery.required)
        return ActionAuthorization(True, capability, 'authorized', recovery_required=policy.recovery.required, max_lease_seconds=policy.max_lease_seconds)
