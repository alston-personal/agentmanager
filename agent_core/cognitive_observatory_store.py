"""Durable append-only timeline storage for Cognitive Observatory records."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any

from runtime_core.observatory_v1 import CognitiveDelta, CognitiveSnapshot


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class CognitiveObservatoryStore:
    """SQLite timeline store; it records observations but grants no authority."""

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
                CREATE TABLE IF NOT EXISTS cognitive_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    trigger_ref TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                );
                CREATE INDEX IF NOT EXISTS idx_cognitive_snapshots_project_time
                    ON cognitive_snapshots(project_id, captured_at, snapshot_id);

                CREATE TABLE IF NOT EXISTS cognitive_deltas (
                    delta_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    from_snapshot_id TEXT NOT NULL,
                    to_snapshot_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    FOREIGN KEY(from_snapshot_id) REFERENCES cognitive_snapshots(snapshot_id),
                    FOREIGN KEY(to_snapshot_id) REFERENCES cognitive_snapshots(snapshot_id)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_cognitive_delta_lineage
                    ON cognitive_deltas(project_id, from_snapshot_id, to_snapshot_id);
                """
            )

    def persist_snapshot(self, snapshot: CognitiveSnapshot) -> str:
        payload = _canonical(snapshot.to_dict())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT payload_json FROM cognitive_snapshots WHERE snapshot_id=?",
                (snapshot.snapshot_id,),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO cognitive_snapshots(snapshot_id,project_id,captured_at,trigger_ref,payload_json) VALUES (?,?,?,?,?)",
                    (snapshot.snapshot_id, snapshot.project_id, snapshot.captured_at, snapshot.trigger_ref, payload),
                )
            elif row["payload_json"] != payload:
                raise ValueError("snapshot id collision with different payload")
        return snapshot.snapshot_id

    def persist_delta(self, delta: CognitiveDelta) -> str:
        payload = _canonical({**delta.__dict__, "delta_id": delta.delta_id})
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            refs = conn.execute(
                "SELECT snapshot_id,project_id FROM cognitive_snapshots WHERE snapshot_id IN (?,?)",
                (delta.from_snapshot_id, delta.to_snapshot_id),
            ).fetchall()
            found = {row["snapshot_id"]: row["project_id"] for row in refs}
            if set(found) != {delta.from_snapshot_id, delta.to_snapshot_id}:
                raise ValueError("delta snapshot lineage must be persisted first")
            if any(project_id != delta.project_id for project_id in found.values()):
                raise ValueError("delta snapshot lineage belongs to another project")
            row = conn.execute(
                "SELECT payload_json FROM cognitive_deltas WHERE delta_id=?",
                (delta.delta_id,),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO cognitive_deltas(delta_id,project_id,from_snapshot_id,to_snapshot_id,payload_json) VALUES (?,?,?,?,?)",
                    (delta.delta_id, delta.project_id, delta.from_snapshot_id, delta.to_snapshot_id, payload),
                )
            elif row["payload_json"] != payload:
                raise ValueError("delta id collision with different payload")
        return delta.delta_id

    def snapshot_payload(self, snapshot_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM cognitive_snapshots WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchone()
        return None if row is None else json.loads(row["payload_json"])

    def timeline(self, project_id: str) -> tuple[dict[str, Any], ...]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT snapshot_id,captured_at,trigger_ref,payload_json,recorded_at FROM cognitive_snapshots WHERE project_id=? ORDER BY captured_at,snapshot_id",
                (project_id,),
            ).fetchall()
        return tuple(
            {
                "snapshot_id": row["snapshot_id"],
                "captured_at": row["captured_at"],
                "trigger_ref": row["trigger_ref"],
                "payload": json.loads(row["payload_json"]),
                "recorded_at": row["recorded_at"],
            }
            for row in rows
        )

    def deltas(self, project_id: str) -> tuple[dict[str, Any], ...]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT delta_id,from_snapshot_id,to_snapshot_id,payload_json,recorded_at FROM cognitive_deltas WHERE project_id=? ORDER BY recorded_at,delta_id",
                (project_id,),
            ).fetchall()
        return tuple(
            {
                "delta_id": row["delta_id"],
                "from_snapshot_id": row["from_snapshot_id"],
                "to_snapshot_id": row["to_snapshot_id"],
                "payload": json.loads(row["payload_json"]),
                "recorded_at": row["recorded_at"],
            }
            for row in rows
        )
