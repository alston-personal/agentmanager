#!/usr/bin/env python3
"""Non-activating Recovery upgrade staging, for the ONE-authorized host owner.

No CLI, network download, signature trust root or activation in this module.
The caller MUST supply independently trusted verifiers for the signed ONE
upgrade authorization and a fresh, authenticated normal-channel rescue probe.
It is unsafe to treat a JSON boolean or a passing unit test as those proofs.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

# Loaded only inside the authorized updater; the normal installer must not use
# this module. The actual independent probe runner remains stdlib-only.
SCHEMA = "agentos.recovery-staged-candidate/v1"
SHA = re.compile(r"[0-9a-f]{64}\Z")


def _digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _atomic_json(target, payload):
    target = Path(target)
    fd, tmp = tempfile.mkstemp(prefix=".recovery-stage-", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def stage_inactive_candidate(*, root, source, manifest, trusted_one_verifier,
                             live_normal_rescue_probe, isolated_candidate_test):
    """Copy validated bytes into inactive slot, without changing active or LKG.

    Verification functions are host authority interfaces, NOT JSON assertions.
    An authoritative ONE/runtime integrator must implement them with real
    signature/trust, identity/realm, expiry, replay and update-lock checks.
    """
    from recovery_slot_runner import load_state, valid_slot, _strict_slot_path

    if not all(callable(x) for x in (trusted_one_verifier,
                                    live_normal_rescue_probe,
                                    isolated_candidate_test)):
        raise ValueError("missing_authoritative_verifiers")
    root = Path(root)
    source = Path(source)
    state = load_state(root)
    if state["pending"] is not None or state["active"] != state["last_known_good"]:
        raise ValueError("another_recovery_update_pending")
    active = state["active"]
    inactive = "B" if active == "A" else "A"
    if not valid_slot(root, state, active):
        raise ValueError("active_recovery_slot_unhealthy")
    if not source.is_file() or source.is_symlink():
        raise ValueError("invalid_recovery_candidate_file")
    if not isinstance(manifest, dict) or set(manifest) != {
            "schema", "candidate_sha256", "node_id", "realm_id",
            "operation_id"} or manifest.get("schema") != SCHEMA:
        raise ValueError("invalid_recovery_candidate_manifest")
    expected = manifest.get("candidate_sha256")
    if not isinstance(expected, str) or not SHA.fullmatch(expected):
        raise ValueError("invalid_recovery_candidate_digest")
    if _digest(source) != expected:
        raise ValueError("recovery_candidate_digest_mismatch")
    if trusted_one_verifier(manifest) is not True:
        raise PermissionError("recovery_one_authority_not_verified")
    if live_normal_rescue_probe(manifest) is not True:
        raise RuntimeError("normal_channel_rescue_not_proven")
    if isolated_candidate_test(source, manifest) is not True:
        raise RuntimeError("isolated_recovery_candidate_test_failed")

    # Persistent exclusive reservation prevents concurrent candidate staging.
    # A failed/interrupted attempt stays BLOCKED until a governed reconciliation
    # confirms the old active channel and explicitly clears the reservation.
    reservation = root / "stage-reservation.lock"
    if (root / "staged-candidate.json").exists():
        raise ValueError("recovery_candidate_already_staged")
    claim = os.open(reservation, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(claim, "w", encoding="utf-8") as claim_out:
        claim_out.write(str(manifest["operation_id"])[:128] + "\n")
        claim_out.flush()
        os.fsync(claim_out.fileno())
    # This phase must not mutate the slot state: only the governed controller
    # can later activate after checking the durable interlock and fresh proof.
    target = _strict_slot_path(root, inactive)
    if target.parent.is_symlink() or target.is_symlink():
        raise ValueError("unsafe_recovery_slot_path")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".staged-candidate-", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as dest, source.open("rb") as src:
            for block in iter(lambda: src.read(65536), b""):
                dest.write(block)
            dest.flush()
            os.fsync(dest.fileno())
        if _digest(name) != expected:
            raise ValueError("staged_recovery_digest_mismatch")
        os.replace(name, target)
    finally:
        if os.path.exists(name):
            os.unlink(name)

    if _digest(target) != expected:
        raise ValueError("stored_recovery_digest_mismatch")
    result = {
        "schema": SCHEMA,
        "operation_id": manifest["operation_id"],
        "node_id": manifest["node_id"],
        "realm_id": manifest["realm_id"],
        "candidate_sha256": expected,
        "slot": inactive,
        "active": active,
        "activation_authorized": False,
        "one_receipt_attested": False,
    }
    # This marker is intentionally NOT read as activation permission by the
    # independent runner. A crash leaves the existing active lane untouched.
    _atomic_json(root / "staged-candidate.json", result)
    return result
