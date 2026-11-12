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
          or reserved_file.read_text(encoding="utf-8").strip() != op
          or stage_record.get("slot") not in ("A", "B")
          or stage_record.get("active") != lkg):
        classification = "GOVERNED_RECONCILIATION_REQUIRED"
    elif phase == "STAGED":
        classification = (
            "AWAITING_AUTHORITATIVE_ACTIVATION" if
            active == lkg and pending is None and a_ok
            else "GOVERNED_RECONCILIATION_REQUIRED"
        )
    elif phase == "ACTIVATED":
        classification = (
            "AWAITING_ONE_RECEIPT" if
            active == stage_record["slot"] and pending == active and a_ok
            else "GOVERNED_RECONCILIATION_REQUIRED"
        )
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
