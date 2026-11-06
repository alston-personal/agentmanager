"""Durable runtime-owned canonical development context for AgentOS Core.

Repository `.agentos/development-context.json` files are immutable seeds/snapshots.
This store owns the mutable runtime copy in the Control Plane data layer so
successful, verified receipts can advance context without writing source files.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class CanonicalContextStore:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS canonical_contexts (
                    project_id TEXT PRIMARY KEY,
                    document_json TEXT NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 1,
                    seed_revision TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS canonical_context_checkpoints (
                    checkpoint_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    task_id TEXT,
                    revision INTEGER NOT NULL,
                    checkpoint_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS canonical_context_checkpoints_project
                    ON canonical_context_checkpoints(project_id, created_at);
                """
            )

    def load(self, project_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT document_json, revision, seed_revision, updated_at FROM canonical_contexts WHERE project_id=?",
                (project_id,),
            ).fetchone()
        if row is None:
            return None
        document = json.loads(row["document_json"])
        if not isinstance(document, dict):
            raise ValueError("stored canonical context must be an object")
        document = dict(document)
        document["_runtime_context"] = {
            "revision": int(row["revision"]),
            "seed_revision": row["seed_revision"],
            "updated_at": row["updated_at"],
        }
        return document

    def seed(self, project_id: str, document: dict[str, Any], *, seed_revision: str | None = None) -> dict[str, Any]:
        if not project_id or not isinstance(document, dict):
            raise ValueError("project_id and context document are required")
        now = _now()
        clean = dict(document)
        clean.pop("_runtime_context", None)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO canonical_contexts(
                    project_id, document_json, revision, seed_revision, updated_at
                ) VALUES (?, ?, 1, ?, ?)
                """,
                (project_id, json.dumps(clean, ensure_ascii=False, sort_keys=True), seed_revision, now),
            )
        loaded = self.load(project_id)
        assert loaded is not None
        return loaded

    def checkpoint(
        self,
        project_id: str,
        *,
        checkpoint_id: str,
        task_id: str | None,
        completed_action: str,
        finding: str,
        next_action: str | None = None,
    ) -> dict[str, Any]:
        if not project_id or not checkpoint_id:
            raise ValueError("project_id and checkpoint_id are required")
        completed_action = completed_action.strip()
        finding = finding.strip()
        next_action = (next_action or "").strip() or None
        if not completed_action or not finding:
            raise ValueError("completed_action and finding are required")

        now = _now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            replay = connection.execute(
                "SELECT checkpoint_json FROM canonical_context_checkpoints WHERE checkpoint_id=?",
                (checkpoint_id,),
            ).fetchone()
            if replay is not None:
                connection.commit()
                return json.loads(replay["checkpoint_json"])

            row = connection.execute(
                "SELECT document_json, revision FROM canonical_contexts WHERE project_id=?",
                (project_id,),
            ).fetchone()
            if row is None:
                connection.rollback()
                raise KeyError(f"canonical context is not seeded: {project_id}")
            document = json.loads(row["document_json"])
            active = document.get("active_work")
            if not isinstance(active, dict):
                connection.rollback()
                raise ValueError("canonical context active_work must be an object")

            actions = active.get("next_actions")
            if not isinstance(actions, list) or not all(isinstance(x, str) for x in actions):
                connection.rollback()
                raise ValueError("canonical context next_actions must be an array of strings")
            if completed_action not in actions:
                connection.rollback()
                raise ValueError("completed_action is not an active next_action")
            actions = [x for x in actions if x != completed_action]
            if next_action and next_action not in actions:
                actions.insert(0, next_action)

            findings = active.get("current_findings")
            if not isinstance(findings, list):
                findings = []
            if finding not in findings:
                findings.append(finding)

            active = dict(active)
            active["next_actions"] = actions
            active["current_findings"] = findings
            document = dict(document)
            document["active_work"] = active
            document["updated_at"] = now
            document.pop("_runtime_context", None)
            revision = int(row["revision"]) + 1
            result = {
                "schema": "agentos.context-checkpoint/v0.1",
                "project_id": project_id,
                "checkpoint_id": checkpoint_id,
                "task_id": task_id,
                "revision": revision,
                "completed_action": completed_action,
                "finding": finding,
                "next_action": actions[0] if actions else None,
                "updated_at": now,
            }
            connection.execute(
                "UPDATE canonical_contexts SET document_json=?, revision=?, updated_at=? WHERE project_id=?",
                (json.dumps(document, ensure_ascii=False, sort_keys=True), revision, now, project_id),
            )
            connection.execute(
                """
                INSERT INTO canonical_context_checkpoints(
                    checkpoint_id, project_id, task_id, revision, checkpoint_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (checkpoint_id, project_id, task_id, revision, json.dumps(result, ensure_ascii=False, sort_keys=True), now),
            )
            connection.commit()
        return result
