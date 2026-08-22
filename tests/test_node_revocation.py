import pytest

from agent_core.node_directory_store import NodeDirectoryStore
from agent_core.node_revocation import NodeRevocationService
from runtime_core.onboarding_v1 import NodeLifecycle, OnboardingCheckpoint


def test_revocation_is_durable_and_terminal(tmp_path) -> None:
    directory = NodeDirectoryStore(str(tmp_path / "nodes.db"))
    directory.initialize_node(
        OnboardingCheckpoint(
            node_id="node-a",
            lifecycle=NodeLifecycle.ACTIVE,
            observed_at="2026-08-22T09:00:00Z",
            identity_id="node_identity",
            governance_ref="gov-active",
        )
    )
    receipt = NodeRevocationService(directory).revoke(
        "node-a",
        actor_ref="owner",
        governance_ref="gov-revoke-1",
        reason="device retired",
        observed_at="2026-08-22T09:05:00Z",
    )
    assert receipt.node_id == "node-a"
    assert directory.checkpoint("node-a").lifecycle is NodeLifecycle.REVOKED

    with pytest.raises(ValueError, match="already revoked"):
        NodeRevocationService(directory).revoke(
            "node-a",
            actor_ref="owner",
            governance_ref="gov-revoke-2",
            reason="again",
            observed_at="2026-08-22T09:06:00Z",
        )
