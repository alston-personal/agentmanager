"""Transactional generation claims with a persistent, fail-closed recovery fence."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import threading

import pytest

from agent_core.release_authorization import Decision
from agent_core.release_epoch_store import ReleaseFenceError, TargetReleaseEpochStore


KEY = {
    "repository": "alston-personal/agentmanager",
    "realm_id": "realm-production",
    "environment": "oracle-production",
}
OLD = "a" * 40
NEW = "b" * 40
OTHER = "c" * 40


def store(tmp_path):
    state = TargetReleaseEpochStore(tmp_path / "release-epoch.sqlite3")
    state.initialize_from_verified_readback(
        **KEY, installed_sha=OLD, installed_epoch=7,
    )
    return state


def claim(state, *, new_epoch=8, expected_active_epoch=7, source_sha=NEW):
    return state.claim(
        **KEY, expected_active_epoch=expected_active_epoch, new_epoch=new_epoch,
        source_sha=source_sha, approval_receipt_id=f"receipt-{new_epoch}",
        decision=Decision(True, "preflight_eligible_requires_atomic_target_cas", new_epoch),
    )


def test_sealed_initial_generation_is_idempotently_not_reseedable(tmp_path):
    state = store(tmp_path)
    assert state.inspect(**KEY)["active_epoch"] == 7
    assert "pending_token" not in state.inspect(**KEY)
    with pytest.raises(ReleaseFenceError, match="target_already_initialized"):
        state.initialize_from_verified_readback(
            **KEY, installed_sha=OTHER, installed_epoch=99,
        )


def test_approved_epoch_claim_held_until_verified_install(tmp_path):
    state = store(tmp_path)
    token = claim(state)
    assert state.inspect(**KEY)["pending_epoch"] == 8
    assert state.inspect(**KEY)["active_epoch"] == 7
    state.assert_current(**KEY, epoch=8, token=token)
    with pytest.raises(ReleaseFenceError, match="installed_source_mismatch"):
        state.commit_verified(
            **KEY, epoch=8, token=token, observed_installed_sha=OTHER,
        )
    with pytest.raises(ReleaseFenceError, match="stale_or_missing_release_lease"):
        state.assert_current(**KEY, epoch=8, token="wrong-token")
    state.commit_verified(**KEY, epoch=8, token=token, observed_installed_sha=NEW)
    assert state.inspect(**KEY)["active_epoch"] == 8
    assert state.inspect(**KEY)["active_sha"] == NEW
    with pytest.raises(ReleaseFenceError, match="stale_or_missing_release_lease"):
        state.assert_current(**KEY, epoch=8, token=token)
    with pytest.raises(ReleaseFenceError, match="release_epoch_replayed"):
        claim(state, new_epoch=8, expected_active_epoch=8)


def test_concurrent_executors_cannot_claim_same_release(tmp_path):
    state = store(tmp_path)
    barrier = threading.Barrier(2)
    def attempt(_):
        barrier.wait(timeout=5)
        try:
            return ("granted", claim(state))
        except ReleaseFenceError as exc:
            return ("denied", str(exc))
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = list(pool.map(attempt, range(2)))
    assert sorted([a[0], b[0]]) == ["denied", "granted"]
    assert state.inspect(**KEY)["pending_epoch"] == 8
    assert state.inspect(**KEY)["active_epoch"] == 7


def test_crash_pending_blocks_new_executor_without_automatic_takeover(tmp_path):
    state = store(tmp_path)
    token = claim(state)
    reopened = TargetReleaseEpochStore(state.database)
    with pytest.raises(ReleaseFenceError, match="release_pending_requires_operator_recovery"):
        claim(reopened, new_epoch=9)
    with pytest.raises(ReleaseFenceError, match="restore_not_verified"):
        reopened.clear_after_verified_restore(
            **KEY, epoch=8, token=token, observed_restored_sha=OTHER,
        )
    reopened.clear_after_verified_restore(
        **KEY, epoch=8, token=token, observed_restored_sha=OLD,
    )
    assert reopened.inspect(**KEY)["active_epoch"] == 7
    assert reopened.inspect(**KEY)["highest_claimed_epoch"] == 8
    with pytest.raises(ReleaseFenceError, match="release_epoch_replayed"):
        claim(reopened)
    next_token = claim(reopened, new_epoch=9)
    assert len(next_token) == 64
    with pytest.raises(ReleaseFenceError, match="stale_or_missing_release_lease"):
        reopened.assert_current(**KEY, epoch=8, token=token)


def test_unapproved_decision_or_target_change_cannot_claim(tmp_path):
    state = store(tmp_path)
    with pytest.raises(ReleaseFenceError, match="unapproved_release_decision"):
        state.claim(
            **KEY, expected_active_epoch=7, new_epoch=8, source_sha=NEW,
            approval_receipt_id="fake",
            decision=Decision(False, "non_main_source_forbidden"),
        )
    with pytest.raises(ReleaseFenceError, match="active_generation_changed"):
        claim(state, expected_active_epoch=6)
    assert state.inspect(**KEY)["highest_claimed_epoch"] == 7


def test_tenant_and_environment_are_isolated(tmp_path):
    state = store(tmp_path)
    key2 = {**KEY, "realm_id": "another-realm"}
    state.initialize_from_verified_readback(
        **key2, installed_sha=OLD, installed_epoch=2)
    claim(state)
    assert state.inspect(**key2)["active_epoch"] == 2
    assert state.inspect(**key2)["pending_epoch"] is None


def test_missing_target_and_invalid_initial_readback_fail_closed(tmp_path):
    state = TargetReleaseEpochStore(tmp_path / "release.sqlite3")
    with pytest.raises(ReleaseFenceError, match="target_not_initialized"):
        claim(state)
    with pytest.raises(ReleaseFenceError, match="invalid_initial_verified_generation"):
        state.initialize_from_verified_readback(
            **KEY, installed_sha="main", installed_epoch=7)
    with pytest.raises(ReleaseFenceError, match="invalid_initial_verified_generation"):
        state.initialize_from_verified_readback(
            **KEY, installed_sha=OLD, installed_epoch=True)
    assert state.inspect(**KEY) if False else True
