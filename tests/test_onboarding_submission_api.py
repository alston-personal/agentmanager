import pytest

from agent_core.bootstrap_session_store import BootstrapSessionError, BootstrapSessionStore
from agent_core.governance_registry import GovernanceRegistry
from agent_core.node_directory_store import NodeDirectoryStore
from agent_core.node_onboarding import NodeOnboardingCoordinator
from agent_core.node_registry import NodeRegistry
from agent_core.onboarding_pipeline import NodeOnboardingPipeline
from agent_core.onboarding_submission_api import OnboardingSubmissionApi
from runtime_core.node_v1 import NodeIdentity
from runtime_core.onboarding_v1 import NodeLifecycle, OnboardingCheckpoint


def _setup(tmp_path):
    identity = NodeIdentity(
        node_id="node-a",
        realm_id="realm-personal",
        hostname="camera-01",
        platform="linux",
        arch="aarch64",
    )
    directory = NodeDirectoryStore(str(tmp_path / "nodes.db"))
    directory.initialize_node(
        OnboardingCheckpoint(
            node_id=identity.node_id,
            lifecycle=NodeLifecycle.IDENTIFIED,
            observed_at="2026-08-22T12:00:00Z",
            identity_id=identity.identity_id,
        )
    )
    pipeline = NodeOnboardingPipeline(
        directory=directory,
        coordinator=NodeOnboardingCoordinator(nodes=NodeRegistry(), governance=GovernanceRegistry()),
    )
    sessions = BootstrapSessionStore(str(tmp_path / "sessions.db"))
    api = OnboardingSubmissionApi(pipeline=pipeline, sessions=sessions)
    return identity, directory, sessions, api


def _manifest(identity: NodeIdentity):
    return {
        "identity": {
            "node_id": identity.node_id,
            "realm_id": identity.realm_id,
            "hostname": identity.hostname,
            "platform": identity.platform,
            "arch": identity.arch,
            "profile": identity.profile,
            "labels": [],
            "schema_version": identity.schema_version,
        },
        "observed_at": "2026-08-22T12:00:02Z",
        "capabilities": [
            {
                "capability": "camera.observe",
                "source": "device:/dev/video*",
                "state": "discovered",
                "risk_tags": ["privacy", "sensor"],
            }
        ],
        "metadata": {"discovery_mode": "read-only", "authorization_inferred": False},
        "schema_version": "agentos.node-capability-manifest/v1",
    }


def test_submission_consumes_bootstrap_session_and_stops_before_authority(tmp_path) -> None:
    identity, directory, sessions, api = _setup(tmp_path)
    _, token, _ = sessions.issue(node_id=identity.node_id)
    response = api.submit(
        {
            "bootstrap_token": token,
            "manifest": _manifest(identity),
            "local_cognition": [
                {
                    "local_ref": "local-memory-1",
                    "content_hash": "h1",
                    "kind": "knowledge",
                    "provenance": "agentos-local-store",
                }
            ],
            # A Node-supplied governance reference is intentionally ignored by
            # the protocol; only Core-owned governance may activate the Node.
            "governance_ref": "node-self-issued",
        }
    )
    assert response["lifecycle"] == "registered"
    assert response["governance"]["can_activate"] is False
    assert response["governance"]["missing_profiles"] == ["camera.observe"]
    assert directory.checkpoint(identity.node_id).lifecycle is NodeLifecycle.REGISTERED
    with pytest.raises(BootstrapSessionError, match="already consumed"):
        sessions.authenticate(token, required_scope="onboarding.submit")


def test_submission_session_is_bound_to_claimed_node(tmp_path) -> None:
    identity, directory, sessions, api = _setup(tmp_path)
    _, token, _ = sessions.issue(node_id="node-other")
    with pytest.raises(PermissionError, match="different Node"):
        api.submit({"bootstrap_token": token, "manifest": _manifest(identity)})
    assert directory.checkpoint(identity.node_id).lifecycle is NodeLifecycle.IDENTIFIED
