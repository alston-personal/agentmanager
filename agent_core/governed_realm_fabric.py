from __future__ import annotations

from typing import Any

from agent_core.capability_governance import CapabilityGovernor
from agent_core.realm_fabric import RealmFabricStore


class GovernedRealmFabricStore(RealmFabricStore):
    """RealmFabricStore with mandatory capability authorization at enqueue time.

    Migration target for ONE control-plane call sites. Existing RealmFabricStore is
    retained temporarily so rollout can be staged without breaking the live Realm.
    """

    def __init__(self, *args: Any, governor: CapabilityGovernor | None = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.governor = governor or CapabilityGovernor()

    def queue_task(self, node_id: str, task: dict[str, Any]) -> dict[str, Any]:
        capability = str(task.get('action') or '')
        decision = self.governor.authorize(
            capability,
            recovery_armed=bool(task.get('governance', {}).get('recovery_armed')),
            preflight_ok=bool(task.get('governance', {}).get('preflight_ok', True)),
            human_approved=bool(task.get('governance', {}).get('human_approved')),
            second_key_approved=bool(task.get('governance', {}).get('second_key_approved')),
        )
        if not decision.allowed:
            raise PermissionError(f'capability denied: {capability}: {decision.reason}')
        queued = dict(task)
        queued['governance_decision'] = {
            'allowed': True,
            'reason': decision.reason,
            'recovery_required': decision.recovery_required,
            'max_lease_seconds': decision.max_lease_seconds,
        }
        return super().queue_task(node_id, queued)
