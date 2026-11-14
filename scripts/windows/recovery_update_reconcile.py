#!/usr/bin/env python3
"""Read-only Recovery/ONE crash reconciliation.

The independent Recovery runner persists slot state on Windows. The ONE host
owns a separate durable SQLite interlock. These stores cannot commit atomically
across hosts. This diagnostic classifies interrupted transitions; it NEVER
unlocks, approves, activates, installs or deletes a recovery reservation.
A genuine ONE receipt and independent authority are needed to complete them.
"""
from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path

from recovery_slot_runner import load_state, valid_slot

SCHEMA = "agentos.recovery-interlock-reconciliation/v1"
STAGE_SCHEMA = "agentos.recovery-staged-candidate/v1"
GATE_SCHEMA = "agentos.dual-channel-update-state/v1"


def reconcile(*, root, gate, participant_id):
    if not isinstance(participant_id, str) or not participant_id:
        raise ValueError("invalid_reconciliation_participant")
    if not isinstance(gate, dict) or gate.get("schema") != GATE_SCHEMA:
        raise ValueError("untrusted_channel_interlock_state")
    if gate.get("active_lane") not in (None, "recovery"):
        raise ValueError("different_lane_update_in_progress")
    if gate.get("phase") not in (
        "IDLE", "STAGED", "ACTIVATED", "ROLLBACK_REQUIRED", "HUMAN_REQUIRED"
    ):
        raise ValueError("invalid_reconciliation_gate_phase")
    root = Path(root)
    state = load_state(root)
    active = state["active"]
    lkg = state["last_known_good"]
    a_ok = valid_slot(root, state, active)
    lkg_ok = valid_slot(root, state, lkg)
    staged_file = root / "staged-candidate.json"
    reserved_file = root / "stage-reservation.lock"
    stage_exists = staged_file.exists()
    reservation_exists = reserved_file.exists()
    phase = gate["phase"]
    op = gate.get("operation_id")
    stage_record = None
    if stage_exists:
        stage_record = json.loads(staged_file.read_text(encoding="utf-8"))
        if not isinstance(stage_record, dict) or stage_record.get("schema") != STAGE_SCHEMA:
            raise ValueError("invalid_staged_recovery_record")
    pending = state["pending"]

    if not lkg_ok:
        classification = "HUMAN_REQUIRED_LKG_CORRUPT"
    elif phase == "HUMAN_REQUIRED":
        classification = "HUMAN_REQUIRED"
    elif phase == "IDLE":
        classification = (
            "READY" if a_ok and active == lkg and pending is None
            and not stage_exists and not reservation_exists
            and gate.get("active_lane") is None and op is None
            else "GOVERNED_RECONCILIATION_REQUIRED"
        )
    elif gate.get("active_lane") != "recovery" or not op:
        classification = "GOVERNED_RECONCILIATION_REQUIRED"
    elif not stage_exists or not reservation_exists:
        # Crash could occur after BEGIN but before the stage was committed.
        classification = "GOVERNED_RECONCILIATION_REQUIRED"
    elif (stage_record.get("operation_id") != op
          or stage_record.get("node_id") != participant_id
          or stage_record.get("activation_authorized") is not False
          or stage_record.get("one_receipt_attested") is not False
          or reserved_file.read_text(encoding="utf-8").strip() != op
          or stage_record.get("slot") not in ("A", "B")
          or state["digests"].get(stage_record["slot"]) not in (
              stage_record.get("candidate_sha256"), None)
          or (state["digests"].get(stage_record["slot"]) is None
              and active == stage_record["slot"])
          or (stage_record.get("active") != lkg and not (
              phase == "ACTIVATED" and pending is None
              and active == lkg == stage_record.get("slot")
              and stage_record.get("active") != active))):
        classification = "GOVERNED_RECONCILIATION_REQUIRED"
    elif phase == "STAGED":
        classification = (
            "AWAITING_AUTHORITATIVE_ACTIVATION" if
            active == lkg and pending is None and a_ok
            else "GOVERNED_RECONCILIATION_REQUIRED"
        )
    elif phase == "ACTIVATED":
        if active == stage_record["slot"] and pending == active and a_ok:
            classification = "AWAITING_ONE_RECEIPT"
        elif (active == lkg == stage_record["slot"]
              and pending is None and a_ok):
            # Windows accepted the candidate locally, but the ONE gate has
            # NOT yet committed VERIFY. Never infer authorization from disk.
            classification = "GOVERNED_POST_ACCEPTANCE_RECONCILIATION"
        else:
            classification = "GOVERNED_RECONCILIATION_REQUIRED"
    elif phase == "ROLLBACK_REQUIRED":
        # Distinguish pre-rollback from a crash AFTER Windows has committed
        # its LKG restoration but BEFORE ONE acknowledges/clears the gate.
        # This evidence is not proof the local change was authorized.
        if (active == stage_record["slot"] and pending == active
                and lkg != active and lkg_ok):
            classification = "AWAITING_AUTHORIZED_ROLLBACK"
        elif active == lkg and pending is None and a_ok:
            classification = "GOVERNED_POST_ROLLBACK_RECONCILIATION"
        else:
            classification = "GOVERNED_RECONCILIATION_REQUIRED"
    else:
        classification = "GOVERNED_RECONCILIATION_REQUIRED"

    # All non-READY states are an update freeze; informational class names are
    # NOT the authority to perform any of the corresponding actions.
    return {
        "schema": SCHEMA,
        "participant_id": participant_id,
        "gate_generation": gate.get("generation"),
        "gate_phase": phase,
        "active_slot": active,
        "lkg_slot": lkg,
        "pending_slot": pending,
        "lkg_integrity_verified": lkg_ok,
        "active_integrity_verified": a_ok,
        "classification": classification,
        "new_update_permitted": False,
        "eligible_for_authoritative_review": classification == "READY",
        "activation_authorized": False,
        "rollback_authorized": False,
        "one_receipt_attested": False,
    }


# Diagnostic-only companion for the existing Windows Realm transfer journal.
# This is intentionally separate from the Recovery A/B slot interlock:
# neither file store is a source of ONE authorization.
REALM_TRANSFER_PENDING_SCHEMA = "agentos.node-realm-transfer-local-pending/v1"
REALM_TRANSFER_RECONCILE_SCHEMA = "agentos.node-realm-transfer-reconciliation/v1"
_DIGEST = re.compile(r"^[0-9a-fA-F]{64}$")
_REALM = re.compile(r"^realm-u-[0-9a-f]{24}$")


def reconcile_realm_transfer(*, install_root, participant_id):
    """Read-only after-crash classification; never authorizes or changes a Node."""
    if not isinstance(participant_id, str) or not participant_id:
        raise ValueError("invalid_reconciliation_participant")
    state_root = Path(install_root) / "state"
    pending_path = state_root / "realm-transfer-pending.json"
    active_path = state_root / "client.json"

    def file_digest(path):
        # Refuse symlinks (including dangling ones). Windows junctions are
        # guarded by the local cutover host before it writes the journal.
        if path.is_symlink():
            raise ValueError("indirect_realm_transfer_state")
        if not path.is_file():
            return None
        return hashlib.sha256(path.read_bytes()).hexdigest()

    if state_root.is_symlink():
        raise ValueError("indirect_realm_transfer_state")
    if pending_path.is_symlink():
        raise ValueError("indirect_realm_transfer_state")
    if not pending_path.is_file():
        return {
            "schema": REALM_TRANSFER_RECONCILE_SCHEMA,
            "participant_id": participant_id,
            "classification": "NO_PENDING_LOCAL_TRANSFER",
            "active_binding_sha256": file_digest(active_path),
            "activation_authorized": False,
            "rollback_authorized": False,
            "one_receipt_attested": False,
            "mutation_permitted": False,
        }
    try:
        pending = json.loads(pending_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("invalid_pending_realm_transfer_record") from exc
    if not isinstance(pending, dict) or pending.get("schema") != REALM_TRANSFER_PENDING_SCHEMA:
        raise ValueError("invalid_pending_realm_transfer_record")
    if (pending.get("state") != "CUTOVER_UNRESOLVED"
            or not isinstance(pending.get("transfer_id"), str)
            or not re.fullmatch(r"[0-9a-f]{32}", pending["transfer_id"])
            or pending.get("node_id") != participant_id
            or not isinstance(pending.get("source_realm_id"), str)
            or not isinstance(pending.get("target_realm_id"), str)
            or not _REALM.fullmatch(pending["source_realm_id"])
            or not _REALM.fullmatch(pending["target_realm_id"])
            or pending["source_realm_id"] == pending["target_realm_id"]
            or not isinstance(pending.get("source_sha256"), str)
            or not isinstance(pending.get("target_sha256"), str)
            or not _DIGEST.fullmatch(pending["source_sha256"])
            or not _DIGEST.fullmatch(pending["target_sha256"])):
        raise ValueError("untrusted_pending_realm_transfer_record")

    active_hash = file_digest(active_path)
    source_hash = pending["source_sha256"].lower()
    target_hash = pending["target_sha256"].lower()
    if active_hash == source_hash:
        classification = "GOVERNED_SOURCE_BINDING_RECONCILIATION"
    elif active_hash == target_hash:
        classification = "GOVERNED_TARGET_BINDING_RECONCILIATION"
    elif active_hash is None:
        classification = "HUMAN_REQUIRED_ACTIVE_BINDING_MISSING"
    else:
        classification = "HUMAN_REQUIRED_BINDING_DIVERGED"

    # Find whether an intact source backup exists, not whether recovery is safe.
    # A digest match proves local bytes only: ONE and the device may disagree.
    backup_status = "missing"
    for backup in state_root.glob("client.realm-rollback-*.json"):
        if file_digest(backup) == source_hash:
            backup_status = "source_bytes_present"
            break
    return {
        "schema": REALM_TRANSFER_RECONCILE_SCHEMA,
        "participant_id": participant_id,
        "transfer_id": pending["transfer_id"],
        "source_realm_id": pending["source_realm_id"],
        "target_realm_id": pending["target_realm_id"],
        "classification": classification,
        "active_binding_sha256": active_hash,
        "source_backup_status": backup_status,
        "activation_authorized": False,
        "rollback_authorized": False,
        "one_receipt_attested": False,
        "mutation_permitted": False,
    }
