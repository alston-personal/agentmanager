#!/usr/bin/env python3
"""Host-authorized Recovery candidate promotion primitives; NO CLI/deployment.

This module is not reachable from the normal installer, ONE task dispatcher, or
the Recovery probe. Integrators MUST provide independently authenticated
authorizers/receipts and a single-owner durable update interlock. These
interfaces are not an authority on their own.

The existing A/B runner is the only process that consumes slots.json. A
candidate gets a pending state first, and becomes LKG only after a separately
verified, post-activation ONE receipt.
"""
from __future__ import annotations

import json
from pathlib import Path

from recovery_slot_runner import atomic_json, load_state, valid_slot

STAGED_SCHEMA = "agentos.recovery-staged-candidate/v1"


def _staged(root, operation_id):
    if not isinstance(operation_id, str) or not operation_id:
        raise ValueError("invalid_recovery_operation")
    root = Path(root)
    if not (root / "stage-reservation.lock").is_file():
        raise ValueError("recovery_stage_reservation_missing")
    reservation = (root / "stage-reservation.lock").read_text(encoding="utf-8").strip()
    if reservation != operation_id:
        raise ValueError("recovery_stage_operation_mismatch")
    record = json.loads((root / "staged-candidate.json").read_text(encoding="utf-8"))
    if not isinstance(record, dict) or record.get("schema") != STAGED_SCHEMA:
        raise ValueError("invalid_recovery_stage_record")
    if record.get("operation_id") != operation_id:
        raise ValueError("recovery_stage_operation_mismatch")
    if record.get("activation_authorized") is not False or record.get("one_receipt_attested") is not False:
        raise ValueError("recovery_stage_must_not_self_authorize")
    return record


def _require(authority, *args):
    if not callable(authority) or authority(*args) is not True:
        raise PermissionError("recovery_authority_or_proof_missing")


def activate_pending(*, root, operation_id, authorize_activation,
                     normal_channel_live, durable_update_gate):
    """Switch only active to already staged candidate, preserving the old LKG.

    All three callbacks are implemented by the privileged host controller, not
    the candidate, ONE-returned JSON, or an arbitrary user process.
    """
    root = Path(root)
    state = load_state(root)
    record = _staged(root, operation_id)
    candidate = record["slot"]
    if state["pending"] is not None or state["active"] != state["last_known_good"]:
        raise ValueError("recovery_activation_already_pending")
    if candidate not in ("A", "B") or candidate == state["active"]:
        raise ValueError("invalid_recovery_candidate_slot")
    if record["active"] != state["active"] or not valid_slot(root, state, state["last_known_good"]):
        raise ValueError("recovery_lkg_not_verified")
    # The candidate digest is stage-verified independently of slots.json.
    from recovery_slot_runner import _strict_slot_path, digest
    candidate_path = _strict_slot_path(root, candidate)
    if not candidate_path.is_file() or candidate_path.is_symlink():
        raise ValueError("recovery_candidate_missing_or_symlink")
    if digest(candidate_path) != record["candidate_sha256"]:
        raise ValueError("recovery_candidate_changed_since_staging")
    context = {"operation_id": operation_id, "slot": candidate,
               "candidate_sha256": record["candidate_sha256"],
               "node_id": record["node_id"], "realm_id": record["realm_id"]}
    _require(authorize_activation, context)
    _require(normal_channel_live, context)
    _require(durable_update_gate, context, "ACTIVATE")
    # Last known good remains protected in the opposite slot. After a crash
    # the independent launcher can detect a damaged pending candidate.
    updated = {
        **state,
        "active": candidate,
        "pending": candidate,
        "digests": {**state["digests"], candidate: record["candidate_sha256"]},
    }
    atomic_json(root / "slots.json", updated)
    return updated


def accept_pending(*, root, operation_id, verify_candidate_one,
                   verify_normal_live, verify_one_receipt, durable_update_gate):
    """Promote the pending candidate ONLY after real ONE verification.

    No caller-supplied boolean or locally generated receipt is sufficient:
    the host integration must independently check ONE identity, freshness,
    signature, target hash, node, realm and operation id.
    """
    root = Path(root)
    record = _staged(root, operation_id)
    state = load_state(root)
    candidate = record["slot"]
    if state["pending"] != candidate or state["active"] != candidate:
        raise ValueError("recovery_not_pending_activation")
    if state["last_known_good"] == candidate:
        raise ValueError("recovery_lkg_cannot_be_candidate_yet")
    if state["digests"].get(candidate) != record["candidate_sha256"]:
        raise ValueError("recovery_candidate_digest_not_bound")
    if not valid_slot(root, state, candidate) or not valid_slot(root, state, state["last_known_good"]):
        raise ValueError("recovery_slots_unhealthy")
    context = {"operation_id": operation_id, "slot": candidate,
               "candidate_sha256": record["candidate_sha256"],
               "node_id": record["node_id"], "realm_id": record["realm_id"]}
    _require(verify_candidate_one, context)
    _require(verify_normal_live, context)
    _require(verify_one_receipt, context)
    _require(durable_update_gate, context, "VERIFY")
    # One atomic switch marks the already verified candidate accepted.
    accepted = {**state, "pending": None, "last_known_good": candidate}
    atomic_json(root / "slots.json", accepted)
    # Do not remove persistent reservation automatically: host controller must
    # reconcile its durable interlock and verify accepted state first.
    return accepted


def revert_pending(*, root, operation_id, verify_lkg_one,
                   authorize_rollback, durable_update_gate):
    """Restore LKG with separate authority and post-write gate completion.

    Caller-supplied authority is a privileged ONE-host callback, not a local
    JSON flag. The durable ONE ROLLBACK_REQUIRED lock MUST remain held until
    the local restore is persisted and read back. If the later ONE completion
    receipt fails, the lock remains held for crash reconciliation.
    """
    root = Path(root)
    record = _staged(root, operation_id)
    state = load_state(root)
    if state["pending"] != record["slot"] or state["active"] != record["slot"]:
        raise ValueError("recovery_rollback_not_pending")
    lkg = state["last_known_good"]
    if not valid_slot(root, state, lkg):
        raise ValueError("recovery_lkg_corrupt_human_required")
    context = {"operation_id": operation_id, "lkg": lkg,
               "node_id": record["node_id"], "realm_id": record["realm_id"]}
    _require(verify_lkg_one, context)
    _require(authorize_rollback, context)
    restored = {**state, "active": lkg, "pending": None}
    atomic_json(root / "slots.json", restored)
    committed = load_state(root)
    if (committed["active"] != lkg or committed["last_known_good"] != lkg
            or committed["pending"] is not None
            or not valid_slot(root, committed, lkg)):
        raise RuntimeError("recovery_rollback_local_readback_failed")
    # A final host-issued ONE rollback receipt, verified against the durable
    # gate generation, can only clear the interlock AFTER this local readback.
    _require(durable_update_gate, context, "ROLLBACK_OK")
    return committed
