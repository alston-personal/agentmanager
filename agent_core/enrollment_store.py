"""Durable, single-use AgentOS Node enrollment invitations.

Raw join secrets are never persisted. The store keeps only a SHA-256 digest,
expiry and claim state. Successful claim consumes the invitation permanently.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import secrets
import sqlite3
from typing import Callable

from runtime_core.onboarding_v1 import BootstrapPolicy, EnrollmentClaim, JoinEnvelope, JoinReference, JoinTicket


class EnrollmentError(RuntimeError):
    pass


class EnrollmentStore:
    def __init__(self, db_path: str, *, now: Callable[[], datetime] | None = None) -> None:
        self.db_path = db_path
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _init_db(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS enrollments (
                    enrollment_id TEXT PRIMARY KEY,
                    secret_hash TEXT NOT NULL,
                    realm_id TEXT NOT NULL,
                    core_url TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    nonce TEXT NOT NULL,
                    bootstrap_policy_json TEXT NOT NULL,
                    issuer TEXT NOT NULL,
                    consumed_at TEXT,
                    claim_id TEXT,
                    device_fingerprint TEXT,
                    node_public_key TEXT
                )
                """
            )

    @staticmethod
    def _digest(secret: str) -> str:
        return sha256(secret.encode("utf-8")).hexdigest()

    @staticmethod
    def _parse_expiry(value: str) -> datetime:
        try:
            expiry = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise EnrollmentError("invalid enrollment expiry") from exc
        return expiry if expiry.tzinfo is not None else expiry.replace(tzinfo=timezone.utc)

    def issue(
        self,
        *,
        realm_id: str,
        core_url: str,
        expires_at: str,
        bootstrap_policy: BootstrapPolicy | None = None,
        issuer: str = "agentos-core",
    ) -> tuple[JoinEnvelope, str]:
        secret = secrets.token_urlsafe(24)
        enrollment_id = "enr_" + secrets.token_hex(12)
        nonce = secrets.token_urlsafe(18)
        policy = bootstrap_policy or BootstrapPolicy()
        envelope = JoinEnvelope(
            enrollment_id=enrollment_id,
            realm_id=realm_id,
            core_url=core_url,
            expires_at=expires_at,
            nonce=nonce,
            bootstrap_policy=policy,
            issuer=issuer,
        )
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO enrollments (
                    enrollment_id, secret_hash, realm_id, core_url, expires_at,
                    nonce, bootstrap_policy_json, issuer
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    enrollment_id,
                    self._digest(secret),
                    realm_id,
                    core_url,
                    expires_at,
                    nonce,
                    json.dumps(asdict(policy), sort_keys=True, separators=(",", ":")),
                    issuer,
                ),
            )
        return envelope, secret

    def issue_reference(self, **kwargs: object) -> JoinReference:
        envelope, secret = self.issue(**kwargs)
        return JoinReference(core_url=envelope.core_url, enrollment_id=envelope.enrollment_id, secret=secret)

    def resolve(self, reference: JoinReference) -> JoinTicket:
        """Resolve compact QR/link material to authoritative Core policy without consuming it."""
        now = self._now()
        with self._connect() as db:
            row = db.execute("SELECT * FROM enrollments WHERE enrollment_id = ?", (reference.enrollment_id,)).fetchone()
        if row is None:
            raise EnrollmentError("unknown enrollment invitation")
        if row["consumed_at"] is not None:
            raise EnrollmentError("enrollment invitation already consumed")
        if row["secret_hash"] != self._digest(reference.secret):
            raise EnrollmentError("invalid enrollment secret")
        if row["core_url"] != reference.core_url:
            raise EnrollmentError("join reference Core does not match issued invitation")
        if now >= self._parse_expiry(row["expires_at"]):
            raise EnrollmentError("enrollment invitation expired")
        policy_payload = json.loads(row["bootstrap_policy_json"])
        if "requested_capabilities" in policy_payload:
            policy_payload["requested_capabilities"] = tuple(policy_payload["requested_capabilities"])
        envelope = JoinEnvelope(
            enrollment_id=row["enrollment_id"],
            realm_id=row["realm_id"],
            core_url=row["core_url"],
            expires_at=row["expires_at"],
            nonce=row["nonce"],
            bootstrap_policy=BootstrapPolicy(**policy_payload),
            issuer=row["issuer"],
        )
        return JoinTicket(envelope=envelope, secret=reference.secret)

    def claim(self, *, envelope: JoinEnvelope, secret: str, claim: EnrollmentClaim) -> str:
        if claim.enrollment_id != envelope.enrollment_id:
            raise EnrollmentError("claim enrollment_id does not match join envelope")
        now = self._now()
        if now >= self._parse_expiry(envelope.expires_at):
            raise EnrollmentError("enrollment invitation expired")

        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM enrollments WHERE enrollment_id = ?", (envelope.enrollment_id,)).fetchone()
            if row is None:
                raise EnrollmentError("unknown enrollment invitation")
            if row["consumed_at"] is not None:
                raise EnrollmentError("enrollment invitation already consumed")
            if row["secret_hash"] != self._digest(secret):
                raise EnrollmentError("invalid enrollment secret")
            if row["realm_id"] != envelope.realm_id or row["core_url"] != envelope.core_url or row["nonce"] != envelope.nonce:
                raise EnrollmentError("join envelope does not match issued invitation")
            expected_policy = json.dumps(asdict(envelope.bootstrap_policy), sort_keys=True, separators=(",", ":"))
            if row["bootstrap_policy_json"] != expected_policy:
                raise EnrollmentError("join bootstrap policy was modified")

            consumed_at = now.isoformat().replace("+00:00", "Z")
            updated = db.execute(
                """
                UPDATE enrollments
                SET consumed_at = ?, claim_id = ?, device_fingerprint = ?, node_public_key = ?
                WHERE enrollment_id = ? AND consumed_at IS NULL
                """,
                (consumed_at, claim.claim_id, claim.device_fingerprint, claim.node_public_key, envelope.enrollment_id),
            )
            if updated.rowcount != 1:
                raise EnrollmentError("enrollment claim lost single-use race")
        return claim.claim_id
