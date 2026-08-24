from agent_core.node_reconciliation import (
    LocalCognitionDescriptor,
    ReconciliationDisposition,
    plan_node_reconciliation,
)


def test_reconciliation_never_copies_raw_content_and_classifies_safely() -> None:
    items = [
        LocalCognitionDescriptor("local-known", "h-known", "knowledge", "node-db"),
        LocalCognitionDescriptor("local-new", "h-new", "knowledge", "node-db"),
        LocalCognitionDescriptor("local-secret", "h-secret", "credential", "browser-profile", sensitive=True),
        LocalCognitionDescriptor("local-only", "h-local", "cache", "node-cache", node_local_only=True),
        LocalCognitionDescriptor("local-newer", "h-newer", "knowledge", "node-db", supersedes_hash="h-known"),
        LocalCognitionDescriptor("local-conflict", "h-conflict", "knowledge", "node-db"),
    ]

    plan = plan_node_reconciliation(
        node_id="node-oracle-01",
        observed_at="2026-08-22T09:00:00Z",
        local_items=items,
        known_hashes={"h-known"},
        contradicted_hashes={"h-conflict"},
    )

    by_ref = {item.local_ref: item for item in plan.candidates}
    assert by_ref["local-known"].disposition is ReconciliationDisposition.LINK_EXISTING
    assert by_ref["local-new"].disposition is ReconciliationDisposition.CANDIDATE_PROMOTION
    assert by_ref["local-secret"].disposition is ReconciliationDisposition.BLOCK_SENSITIVE
    assert by_ref["local-only"].disposition is ReconciliationDisposition.KEEP_NODE_LOCAL
    assert by_ref["local-newer"].disposition is ReconciliationDisposition.SUPERSESSION_REVIEW
    assert by_ref["local-conflict"].disposition is ReconciliationDisposition.CONTRADICTION_REVIEW
    assert by_ref["local-new"].authority_required is True
    assert by_ref["local-secret"].authority_required is False
    assert plan.plan_id.startswith("nrec_")
