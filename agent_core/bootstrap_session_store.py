"""Short-lived, scope-bound bootstrap sessions for Node onboarding.

A successful Join claim establishes identity but does not grant normal Node
authority. This store issues a fresh bearer credential usable only for the
remaining onboarding metadata submission. Raw tokens are never persisted and a
successful submission consumes the session.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import secrets
import sqlite3
from typing import Callable


class BootstrapSessionError(PermissionError):
    pass


class BootstrapSessionStore:
    def __init__(self, db_path: str, *, now: Callable[[], datetime] | None = None) -> None:
        self.db_path = db_path
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        return db

    def _init_db(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS bootstrap_sessions (
                    session_id TEXT PRIMARY KEY,
                    token_hash TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    consumed_at TEXT
                )
                """
            )

    @staticmethod
    def _digest(token: str) -> str:
        return sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _parse_time(value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)

    def issue(self, *, node_id: str, scope: str = "onboarding.submit", ttl_minutes: int = 10) -> tuple[str, str, str]:
        if not node_id.strip() or not scope.strip():
            raise ValueError("node_id and scope are required")
        if ttl_minutes < 1 or ttl_minutes > 30:
            raise ValueError("bootstrap session ttl_minutes must be 1..30")
        token = secrets.token_urlsafe(32)
        session_id = "bs_" + secrets.token_hex(12)
        expires = self._now() + timedelta(minutes=ttl_minutes)
        expires_at = expires.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        with self._connect() as db:
            db.execute(
                "INSERT INTO bootstrap_sessions(session_id, token_hash, node_id, scope, expires_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, self._digest(token), node_id, scope, expires_at),
            )
        return session_id, token, expires_at

    def authenticate(self, token: str, *, required_scope: str, consume: bool = False) -> str:
        if not token.strip():
            raise BootstrapSessionError("bootstrap session token is required")
        now = self._now()
        with self._connect() as db:
            if consume:
                db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM bootstrap_sessions WHERE token_hash = ?",
                (self._digest(token),),
            ).fetchone()
            if row is None:
                raise BootstrapSessionError("unknown bootstrap session")
            if row["consumed_at"] is not None:
                raise BootstrapSessionError("bootstrap session already consumed")
            if row["scope"] != required_scope:
                raise BootstrapSessionError("bootstrap session scope mismatch")
            if now >= self._parse_time(row["expires_at"]):
                raise BootstrapSessionError("bootstrap session expired")
            if consume:
                consumed_at = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
                updated = db.execute(
                    "UPDATE bootstrap_sessions SET consumed_at = ? WHERE session_id = ? AND consumed_at IS NULL",
                    (consumed_at, row["session_id"]),
                )
                if updated.rowcount != 1:
                    raise BootstrapSessionError("bootstrap session consumption race")
            return str(row["node_id"])
