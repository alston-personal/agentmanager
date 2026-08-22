"""Durable SQLite persistence for SideEffect Ledger records and audit events."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from agent_core.side_effect_ledger import SideEffectRecord


class SideEffectLedgerStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS side_effect_records (
                    side_effect_id TEXT PRIMARY KEY,
                    intent_id TEXT NOT NULL,
                    work_id TEXT,
                    kind TEXT NOT NULL,
                    target TEXT NOT NULL,
                    intent_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    authorization_reason TEXT NOT NULL,
                    compensation_ref TEXT,
                    receipt_ref TEXT,
                    failure_reason TEXT,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS side_effect_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    side_effect_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    FOREIGN KEY(side_effect_id) REFERENCES side_effect_records(side_effect_id)
                );
                CREATE INDEX IF NOT EXISTS idx_side_effect_events_effect
                    ON side_effect_events(side_effect_id, event_id);
                """
            )

    def persist(self, record: SideEffectRecord, *, event_type: str) -> SideEffectRecord:
        if not event_type.strip():
            raise ValueError("event_type is required")
        payload = json.dumps(asdict(record), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT payload_json FROM side_effect_records WHERE side_effect_id = ?",
                (record.side_effect_id,),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """INSERT INTO side_effect_records (
                        side_effect_id,intent_id,work_id,kind,target,intent_hash,status,
                        idempotency_key,authorization_reason,compensation_ref,receipt_ref,
                        failure_reason,payload_json
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        record.side_effect_id,
                        record.intent_id,
                        record.work_id,
                        record.kind,
                        record.target,
                        record.intent_hash,
                        record.status,
                        record.idempotency_key,
                        record.authorization_reason,
                        record.compensation_ref,
                        record.receipt_ref,
                        record.failure_reason,
                        payload,
                    ),
                )
            else:
                conn.execute(
                    """UPDATE side_effect_records SET
                        status=?, compensation_ref=?, receipt_ref=?, failure_reason=?, payload_json=?
                       WHERE side_effect_id=?""",
                    (
                        record.status,
                        record.compensation_ref,
                        record.receipt_ref,
                        record.failure_reason,
                        payload,
                        record.side_effect_id,
                    ),
                )
            conn.execute(
                "INSERT INTO side_effect_events(side_effect_id,event_type,payload_json) VALUES (?,?,?)",
                (record.side_effect_id, event_type, payload),
            )
        return record

    def get(self, side_effect_id: str) -> SideEffectRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM side_effect_records WHERE side_effect_id = ?",
                (side_effect_id,),
            ).fetchone()
        if row is None:
            return None
        return SideEffectRecord(**json.loads(row["payload_json"]))

    def by_idempotency_key(self, key: str) -> SideEffectRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM side_effect_records WHERE idempotency_key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        return SideEffectRecord(**json.loads(row["payload_json"]))

    def events(self, side_effect_id: str) -> tuple[dict[str, str], ...]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT event_type,payload_json,created_at FROM side_effect_events WHERE side_effect_id=? ORDER BY event_id",
                (side_effect_id,),
            ).fetchall()
        return tuple(
            {
                "event_type": row["event_type"],
                "payload_json": row["payload_json"],
                "created_at": row["created_at"],
            }
            for row in rows
        )
