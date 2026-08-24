"""Authenticated continuation of AgentOS Node onboarding after identity claim.

The bootstrap session is scoped only to metadata submission. A Node may submit
its capability manifest and local-cognition descriptors, but it may not provide a
governance_ref or grant itself authority. Successful submission consumes the
bootstrap session and stops at REGISTERED unless Core-owned governance later
completes activation through a separate path.
"""

from __future__ import annotations

from agent_core.bootstrap_session_store import BootstrapSessionStore
from agent_core.enrollment_service import EnrollmentReceipt
from agent_core.node_reconciliation import LocalCognitionDescriptor
from agent_core.onboarding_pipeline import NodeOnboardingPipeline
from runtime_core.node_v1 import CapabilityObservation, CapabilityState, NodeCapabilityManifest, NodeIdentity
from runtime_core.onboarding_v1 import NodeLifecycle


def _parse_manifest(payload: object) -> NodeCapabilityManifest:
    if not isinstance(payload, dict):
        raise ValueError("capability manifest payload is required")
    identity_payload = payload.get("identity")
    capabilities_payload = payload.get("capabilities")
    if not isinstance(identity_payload, dict) or not isinstance(capabilities_payload, list):
        raise ValueError("manifest identity/capabilities are required")
    identity_data = dict(identity_payload)
    identity_data["labels"] = tuple(identity_data.get("labels", ()))
    identity = NodeIdentity(**identity_data)
    capabilities: list[CapabilityObservation] = []
    for raw in capabilities_payload:
        if not isinstance(raw, dict):
            raise ValueError("capability entries must be objects")
        item = dict(raw)
        item["state"] = CapabilityState(item.get("state", CapabilityState.DISCOVERED.value))
        item["risk_tags"] = tuple(item.get("risk_tags", ()))
        capabilities.append(CapabilityObservation(**item))
    return NodeCapabilityManifest(
        identity=identity,
        observed_at=str(payload.get("observed_at", "")),
        capabilities=tuple(capabilities),
        metadata=dict(payload.get("metadata", {})),
        schema_version=str(payload.get("schema_version", "agentos.node-capability-manifest/v1")),
    )


def _parse_local_cognition(payload: object) -> tuple[LocalCognitionDescriptor, ...]:
    if payload is None:
        return ()
    if not isinstance(payload, list):
        raise ValueError("local_cognition must be a list")
    descriptors: list[LocalCognitionDescriptor] = []
    for raw in payload:
        if not isinstance(raw, dict):
            raise ValueError("local cognition descriptors must be objects")
        descriptors.append(LocalCognitionDescriptor(**raw))
    return tuple(descriptors)


class OnboardingSubmissionApi:
    def __init__(self, *, pipeline: NodeOnboardingPipeline, sessions: BootstrapSessionStore) -> None:
        self.pipeline = pipeline
        self.sessions = sessions

    def submit(self, payload: dict[str, object]) -> dict[str, object]:
        token = str(payload.get("bootstrap_token", ""))
        manifest = _parse_manifest(payload.get("manifest"))
        local_cognition = _parse_local_cognition(payload.get("local_cognition"))

        # Validate token and Node binding before any lifecycle mutation. Consume
        # immediately before mutation so replay cannot race two onboarding writes.
        node_id = self.sessions.authenticate(token, required_scope="onboarding.submit", consume=False)
        if manifest.identity.node_id != node_id:
            raise PermissionError("bootstrap session is bound to a different Node")

        current = self.pipeline.directory.checkpoint(node_id)
        if current is None:
            raise KeyError(f"Node identity claim is not registered: {node_id}")
        if current.lifecycle not in {NodeLifecycle.IDENTIFIED, NodeLifecycle.ACTIVE, NodeLifecycle.OFFLINE}:
            raise PermissionError(f"Node lifecycle does not accept onboarding submission: {current.lifecycle.value}")
        if current.identity_id and current.identity_id != manifest.identity.identity_id:
            raise PermissionError("manifest identity does not match claimed Node identity")

        self.sessions.authenticate(token, required_scope="onboarding.submit", consume=True)
        receipt = EnrollmentReceipt(node_identity=manifest.identity, claim_id="bootstrap-session", checkpoint=current)
        result = self.pipeline.ingest(
            receipt=receipt,
            manifest=manifest,
            local_cognition=local_cognition,
            # Canonical known/contradiction sets are Core-owned and must not be
            # supplied by an untrusted Node. The integration layer may enrich
            # these from the Cognitive Kernel in a later trusted call.
            known_hashes=set(),
            contradicted_hashes=set(),
            governance_ref=None,
        )
        delta = None
        if result.capability_delta is not None:
            delta = {
                "schema": result.capability_delta.schema_version,
                "previous_manifest_id": result.capability_delta.previous_manifest_id,
                "current_manifest_id": result.capability_delta.current_manifest_id,
                "changes": [
                    {
                        "capability": change.capability,
                        "before": change.before.value if change.before else None,
                        "after": change.after.value if change.after else None,
                    }
                    for change in result.capability_delta.changes
                ],
            }
        return {
            "schema": "agentos.onboarding-submit-response/v1",
            "node_id": node_id,
            "lifecycle": result.checkpoint.lifecycle.value,
            "manifest_id": manifest.manifest_id,
            "reconciliation_plan_id": result.reconciliation.plan_id,
            "governance": {
                "can_activate": result.governance.can_activate,
                "missing_profiles": [gap.capability for gap in result.governance.governance_gaps],
            },
            "capability_delta": delta,
            "bootstrap_session_consumed": True,
        }
