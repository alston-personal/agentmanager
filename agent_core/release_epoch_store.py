"""Persistent, fail-closed target-local release-generation coordinator (prototype).

Not wired to production. The trusted ONE release-intent reader, authenticated
operator, actual target state, and rollback evidence MUST be supplied by a
separately verified adapter. A SQLite lease cannot fence a process that ignores
the lease, nor can it roll back external systemd/filesystem/database effects.

Every state-changing operation uses SQLite BEGIN IMMEDIATE for atomic compare-
and-swap. An interrupted claim stays pending until an authorized recovery has
verified the previous installed generation; timeout never steals a lease.
"""
from __future__ import annotations

import re
import secrets
import sqlite3
from pathlib import Path

from agent_core.release_authorization import Decision


SHA_RE = re.compile(r"[a-f0-9]{40}\Z")


class ReleaseFenceError(RuntimeError):
    """Release must fail closed, with a stable machine-readable reason."""


class TargetReleaseEpochStore:
    """One persistent SQLite generation record per immutable target identity.

    This class is deliberately separate from the existing Control Plane task
    ledger and is not an alternate ONE approval authority.
    """

    def __init__(self, database: str | Path):
        self.database = Path(database)

    def _open(self) -> sqlite3.Connection:
        # The directory must be operator-owned and provisioned *beforehand*.
        # Never silently create a production writable path from a request.
        if not self.database.parent.is_dir():
            raise ReleaseFenceError("target_database_directory_missing")
        con = sqlite3.connect(str(self.database), timeout=10, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=10000")
        con.execute("PRAGMA synchronous=FULL")
        con.execute("""
            CREATE TABLE IF NOT EXISTS target_release_epoch (
                repository TEXT NOT NULL,
                realm_id TEXT NOT NULL,
                environment TEXT NOT NULL,
                active_epoch INTEGER NOT NULL CHECK(active_epoch >= 0),
                active_sha TEXT NOT NULL,
                highest_claimed_epoch INTEGER NOT NULL CHECK(highest_claimed_epoch >= 0),
                pending_epoch INTEGER,
                pending_sha TEXT,
                pending_token TEXT,
                pending_approval TEXT,
                PRIMARY KEY(repository, realm_id, environment)
            )
        """)
        return con

    @staticmethod
    def _identity(repository: str, realm_id: str, environment: str) -> tuple[str, str, str]:
        values = (repository, realm_id, environment)
        if any(not isinstance(v, str) or not v or len(v) > 128 for v in values):
            raise ReleaseFenceError("invalid_target_identity")
        return values

    @staticmethod
    def _row(con: sqlite3.Connection, key: tuple[str, str, str]):
        return con.execute(
            "SELECT * FROM target_release_epoch WHERE repository=? AND realm_id=? AND environment=?",
            key,
        ).fetchone()

    def initialize_from_verified_readback(
        self, *, repository: str, realm_id: str, environment: str,
        installed_sha: str, installed_epoch: int,
    ) -> None:
        """One-time initialization ONLY after independent operator readback.

        Caller must authenticate the live PID/worktree/approval outside this
        function. No unchecked auto-seeding from request fields is permitted.
        """
        key = self._identity(repository, realm_id, environment)
        if not SHA_RE.fullmatch(installed_sha) or type(installed_epoch) is not int or installed_epoch < 0:
            raise ReleaseFenceError("invalid_initial_verified_generation")
        with self._open() as con:
            con.execute("BEGIN IMMEDIATE")
            current = self._row(con, key)
            if current is not None:
                raise ReleaseFenceError("target_already_initialized")
            con.execute(
                "INSERT INTO target_release_epoch "
                "(repository,realm_id,environment,active_epoch,active_sha,highest_claimed_epoch) "
                "VALUES (?,?,?,?,?,?)",
                (*key, installed_epoch, installed_sha, installed_epoch),
            )

    def inspect(self, *, repository: str, realm_id: str, environment: str) -> dict:
        key = self._identity(repository, realm_id, environment)
        with self._open() as con:
            row = self._row(con, key)
        if row is None:
            raise ReleaseFenceError("target_not_initialized")
        # Never disclose the internal fencing token in read-only inspection.
        return {k: row[k] for k in (
            "repository", "realm_id", "environment", "active_epoch",
            "active_sha", "highest_claimed_epoch", "pending_epoch",
            "pending_sha", "pending_approval",
        )}

    def claim(
        self, *, repository: str, realm_id: str, environment: str,
        expected_active_epoch: int, new_epoch: int, source_sha: str,
        approval_receipt_id: str, decision: Decision,
        artifact_digest: str, project_id: str, operation: str,
        authenticated_principal: str,
    ) -> str:
        """Atomic claim; returns a process-held secret token, never a receipt.

        A pure positive authorization decision is a prerequisite, not proof of
        its trustworthy inputs; the adapter must retrieve and bind them.
        """
        key = self._identity(repository, realm_id, environment)
        if not decision.allowed or decision.release_epoch != new_epoch:
            raise ReleaseFenceError("unapproved_release_decision")
        # A decision is only reusable for its original approved release.
        # This is still a data contract, NOT an authenticated ONE reader.
        if (decision.repository != repository or decision.project_id != project_id
                or decision.realm_id != realm_id or decision.environment != environment
                or decision.operation != operation
                or decision.authorized_principal != authenticated_principal
                or decision.source_commit != source_sha
                or decision.approval_receipt_id != approval_receipt_id
                or decision.artifact_digest != artifact_digest):
            raise ReleaseFenceError("release_decision_scope_mismatch")
        if (type(expected_active_epoch) is not int or expected_active_epoch < 0
                or type(new_epoch) is not int or new_epoch < 1
                or not isinstance(source_sha, str) or not SHA_RE.fullmatch(source_sha)
                or not isinstance(approval_receipt_id, str) or not approval_receipt_id):
            raise ReleaseFenceError("invalid_claim")
        token = secrets.token_hex(32)
        with self._open() as con:
            con.execute("BEGIN IMMEDIATE")
            current = self._row(con, key)
            if current is None:
                raise ReleaseFenceError("target_not_initialized")
            if current["pending_token"] is not None:
                raise ReleaseFenceError("release_pending_requires_operator_recovery")
            # A repeated epoch is a replay even after the prior claim
            # committed; distinguish it from a malformed request.
            if new_epoch <= current["highest_claimed_epoch"]:
                raise ReleaseFenceError("release_epoch_replayed")
            if current["active_epoch"] != expected_active_epoch:
                raise ReleaseFenceError("active_generation_changed")
            if new_epoch <= expected_active_epoch:
                raise ReleaseFenceError("invalid_claim")
            con.execute(
                "UPDATE target_release_epoch SET highest_claimed_epoch=?, "
                "pending_epoch=?,pending_sha=?,pending_token=?,pending_approval=? "
                "WHERE repository=? AND realm_id=? AND environment=?",
                (new_epoch, new_epoch, source_sha, token, approval_receipt_id, *key),
            )
        return token

    def assert_current(
        self, *, repository: str, realm_id: str, environment: str,
        epoch: int, token: str,
    ) -> None:
        """Check before *each* external side effect; not a standalone fence."""
        key = self._identity(repository, realm_id, environment)
        if type(epoch) is not int or not isinstance(token, str) or not token:
            raise ReleaseFenceError("invalid_lease_identity")
        with self._open() as con:
            row = self._row(con, key)
        if row is None or row["pending_token"] != token or row["pending_epoch"] != epoch:
            raise ReleaseFenceError("stale_or_missing_release_lease")

    def commit_verified(
        self, *, repository: str, realm_id: str, environment: str,
        epoch: int, token: str, observed_installed_sha: str,
    ) -> None:
        """Finalize ONLY after independent live PID/worktree/health readback."""
        key = self._identity(repository, realm_id, environment)
        if not SHA_RE.fullmatch(observed_installed_sha):
            raise ReleaseFenceError("invalid_observed_release_sha")
        with self._open() as con:
            con.execute("BEGIN IMMEDIATE")
            row = self._row(con, key)
            if (row is None or type(epoch) is not int
                    or row["pending_epoch"] != epoch
                    or row["pending_token"] != token):
                raise ReleaseFenceError("stale_or_missing_release_lease")
            if row["pending_sha"] != observed_installed_sha:
                raise ReleaseFenceError("installed_source_mismatch")
            con.execute(
                "UPDATE target_release_epoch SET active_epoch=?,active_sha=?,"
                "pending_epoch=NULL,pending_sha=NULL,pending_token=NULL,pending_approval=NULL "
                "WHERE repository=? AND realm_id=? AND environment=?",
                (epoch, observed_installed_sha, *key),
            )

    def clear_after_verified_restore(
        self, *, repository: str, realm_id: str, environment: str,
        epoch: int, token: str, observed_restored_sha: str,
    ) -> None:
        """Clear stuck claim only after restoring the previous active release.

        Never decrement highest_claimed_epoch: stale claims stay permanently
        fenced and the next approved intent must use a larger epoch.
        """
        key = self._identity(repository, realm_id, environment)
        with self._open() as con:
            con.execute("BEGIN IMMEDIATE")
            row = self._row(con, key)
            if (row is None or type(epoch) is not int
                    or row["pending_epoch"] != epoch or row["pending_token"] != token):
                raise ReleaseFenceError("stale_or_missing_release_lease")
            if observed_restored_sha != row["active_sha"]:
                raise ReleaseFenceError("restore_not_verified")
            con.execute(
                "UPDATE target_release_epoch SET pending_epoch=NULL,pending_sha=NULL,"
                "pending_token=NULL,pending_approval=NULL "
                "WHERE repository=? AND realm_id=? AND environment=?",
                key,
            )
