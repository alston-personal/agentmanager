"""Regression: old Executors cannot resurrect expired/released Realm leases.

These tests only exercise the existing Action Relay in-memory state interface.
No Oracle service, filesystem deployment, ONE or network operation occurs.
"""
from datetime import datetime, timedelta, timezone

import pytest

from agentos_node import action_relay


SHA = "a" * 40
OWNER = "existing-owner"


@pytest.mark.parametrize("state_override,rejection", [
    ({"lease_status": "released"}, "rejected_released_lease"),
    ({"lease_expires_at": "2000-01-01T00:00:00+00:00"}, "rejected_expired_lease"),
    ({"lease_expires_at": None}, "rejected_expired_lease"),
    ({"lease_expires_at": "not-a-date"}, "rejected_expired_lease"),
])
def test_old_lease_cannot_be_renewed(tmp_path, monkeypatch, state_override, rejection):
    state = {
        "schema": "agentos.core-deployment/v1",
        "deployment_generation": 17,
        "desired_core_commit": SHA,
        "lease_owner": OWNER,
        "lease_status": "active",
        "lease_expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
        "deployment_status": "desired",
    }
    state.update(state_override)
    writes = []
    monkeypatch.setattr(action_relay, "_DEPLOYMENT_LOCK", tmp_path / "lease.lock")
    monkeypatch.setattr(action_relay, "_deployment_state_read", lambda: dict(state))
    monkeypatch.setattr(action_relay, "_deployment_state_write", lambda payload: writes.append(payload))
    monkeypatch.setattr(action_relay, "_observed_realm_commit", lambda: None)
    response = action_relay._renew_realm_fabric_deployment({
        "desired_core_commit": SHA, "lease_owner": OWNER,
        "deployment_generation": 17,
    })
    assert response["ok"] is False
    assert response["deployment_status"] == rejection
    assert writes == []


def test_active_lease_can_still_be_renewed(tmp_path, monkeypatch):
    state = {
        "schema": "agentos.core-deployment/v1",
        "deployment_generation": 17,
        "desired_core_commit": SHA,
        "lease_owner": OWNER,
        "lease_status": "active",
        "lease_expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
        "deployment_status": "desired",
    }
    writes = []
    monkeypatch.setattr(action_relay, "_DEPLOYMENT_LOCK", tmp_path / "lease.lock")
    monkeypatch.setattr(action_relay, "_deployment_state_read", lambda: dict(state))
    monkeypatch.setattr(action_relay, "_deployment_state_write", lambda payload: writes.append(payload))
    monkeypatch.setattr(action_relay, "_observed_realm_commit", lambda: None)
    response = action_relay._renew_realm_fabric_deployment({
        "desired_core_commit": SHA, "lease_owner": OWNER,
        "deployment_generation": 17,
    })
    assert response["ok"] is True
    assert response["deployment_generation"] == 17
    assert response["desired_core_commit"] == SHA
    assert len(writes) == 1
