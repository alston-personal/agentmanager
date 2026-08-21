"""Transactional canonical project-state kernel for AgentOS v2.

Execution tasks may finish out of order. This store is the authority that decides
whether a proposed StateDelta can advance a project's HEAD, can be safely merged
onto a newer HEAD, or must be rejected as a conflict.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable

from runtime_core.state_v2 import ProjectState, StateDelta, apply_delta, conflicting_paths


class StateKernelConflict(RuntimeError):
    def __init__(self, project_id: str, base_state_id: str, head_state_id: str, paths: Iterable[tuple[str, ...]]):
        self.project_id = project_id
        self.base_state_id = base_state_id
        self.head_state_id = head_state_id
        self.paths = tuple(sorted(paths))
        rendered = ", ".join("/" + "/".join(path) for path in self.paths)
        super().__init__(
            f"stale state delta conflicts with current HEAD for {project_id}: {rendered or 'unknown conflict'}"
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _commit_id(payload: dict[str, Any]) -> str:
    return "commit_" + sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


class StateKernelStore:
    """SQLite-backed immutable state/commit store with one CAS-protected project HEAD."""

    def __init__(self, db_path: str | Path) -> None:
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
                CREATE TABLE IF NOT EXISTS project_states (
                    state_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS project_states_project
                    ON project_states(project_id, created_at);

                CREATE TABLE IF NOT EXISTS state_commits (
                    commit_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    parent_commit_ids_json TEXT NOT NULL,
                    base_state_id TEXT,
                    result_state_id TEXT NOT NULL,
                    delta_json TEXT,
                    author_principal TEXT NOT NULL,
                    source_work_ids_json TEXT NOT NULL,
                    validation_receipt_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS state_commits_project
                    ON state_commits(project_id, created_at);

                CREATE TABLE IF NOT EXISTS project_heads (
                    project_id TEXT PRIMARY KEY,
                    head_commit_id TEXT NOT NULL,
                    head_state_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _store_state(connection: sqlite3.Connection, state: ProjectState, created_at: str) -> None:
        connection.execute(
            """
            INSERT OR IGNORE INTO project_states(state_id, project_id, state_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (state.state_id, state.project_id, _canonical_json(state.to_dict()), created_at),
        )

    @staticmethod
    def _state_from_row(row: sqlite3.Row | None) -> ProjectState:
        if row is None:
            raise KeyError("unknown project state")
        value = json.loads(row["state_json"])
        return ProjectState.from_dict(value)

    def _load_state(self, connection: sqlite3.Connection, state_id: str) -> ProjectState:
        row = connection.execute(
            "SELECT * FROM project_states WHERE state_id=?",
            (state_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown state: {state_id}")
        return self._state_from_row(row)

    @staticmethod
    def _head_from_row(row: sqlite3.Row | None) -> dict[str, Any]:
        if row is None:
            raise KeyError("unknown project")
        return {
            "projectId": row["project_id"],
            "headCommitId": row["head_commit_id"],
            "headStateId": row["head_state_id"],
            "revision": int(row["revision"]),
            "updatedAt": row["updated_at"],
        }

    def initialize_project(
        self,
        state: ProjectState,
        *,
        author_principal: str,
        validation_receipt: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        author_principal = str(author_principal or "").strip()
        if not author_principal:
            raise ValueError("author_principal is required")
        created_at = _now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM project_heads WHERE project_id=?",
                (state.project_id,),
            ).fetchone()
            if existing is not None:
                raise ValueError(f"project already initialized: {state.project_id}")
            self._store_state(connection, state, created_at)
            commit_payload = {
                "project_id": state.project_id,
                "parent_commit_ids": [],
                "base_state_id": None,
                "result_state_id": state.state_id,
                "delta_id": None,
                "author_principal": author_principal,
                "source_work_ids": [],
                "validation_receipt": validation_receipt or {"status": "initialized"},
                "created_at": created_at,
            }
            commit_id = _commit_id(commit_payload)
            connection.execute(
                """
                INSERT INTO state_commits(
                    commit_id, project_id, parent_commit_ids_json, base_state_id,
                    result_state_id, delta_json, author_principal,
                    source_work_ids_json, validation_receipt_json, created_at
                ) VALUES (?, ?, ?, NULL, ?, NULL, ?, ?, ?, ?)
                """,
                (
                    commit_id,
                    state.project_id,
                    "[]",
                    state.state_id,
                    author_principal,
                    "[]",
                    _canonical_json(commit_payload["validation_receipt"]),
                    created_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO project_heads(project_id, head_commit_id, head_state_id, revision, updated_at)
                VALUES (?, ?, ?, 1, ?)
                """,
                (state.project_id, commit_id, state.state_id, created_at),
            )
        return self.head(state.project_id)

    def head(self, project_id: str) -> dict[str, Any]:
        project_id = str(project_id or "").strip()
        if not project_id:
            raise ValueError("project_id is required")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM project_heads WHERE project_id=?",
                (project_id,),
            ).fetchone()
            head = self._head_from_row(row)
            state = self._load_state(connection, head["headStateId"])
        head["state"] = state.to_dict()
        return head

    def get_state(self, state_id: str) -> ProjectState:
        with self._connect() as connection:
            return self._load_state(connection, state_id)

    def get_commit(self, commit_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM state_commits WHERE commit_id=?",
                (commit_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown commit: {commit_id}")
        return {
            "commitId": row["commit_id"],
            "projectId": row["project_id"],
            "parentCommitIds": json.loads(row["parent_commit_ids_json"]),
            "baseStateId": row["base_state_id"],
            "resultStateId": row["result_state_id"],
            "delta": json.loads(row["delta_json"]) if row["delta_json"] else None,
            "authorPrincipal": row["author_principal"],
            "sourceWorkIds": json.loads(row["source_work_ids_json"]),
            "validationReceipt": json.loads(row["validation_receipt_json"]),
            "createdAt": row["created_at"],
        }

    def commit_delta(
        self,
        delta: StateDelta,
        *,
        author_principal: str,
        source_work_ids: Iterable[str] = (),
        validation_receipt: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        author_principal = str(author_principal or "").strip()
        if not author_principal:
            raise ValueError("author_principal is required")
        source_work_ids = tuple(sorted({str(item) for item in source_work_ids if str(item)}))
        receipt = validation_receipt or {"status": "accepted"}
        created_at = _now()

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            head_row = connection.execute(
                "SELECT * FROM project_heads WHERE project_id=?",
                (delta.project_id,),
            ).fetchone()
            head = self._head_from_row(head_row)
            base_state = self._load_state(connection, delta.base_state_id)
            if base_state.project_id != delta.project_id:
                raise ValueError("delta base state belongs to a different project")
            current_state = self._load_state(connection, head["headStateId"])

            merged_from_stale_base = current_state.state_id != base_state.state_id
            conflicts: set[tuple[str, ...]] = set()
            if merged_from_stale_base:
                conflicts = conflicting_paths(base_state, current_state, delta)
                if conflicts:
                    raise StateKernelConflict(
                        delta.project_id,
                        delta.base_state_id,
                        current_state.state_id,
                        conflicts,
                    )

            result_state = apply_delta(current_state, delta)
            self._store_state(connection, result_state, created_at)
            validation = dict(receipt)
            validation.setdefault("status", "accepted")
            validation["mergedFromStaleBase"] = merged_from_stale_base
            validation["baseStateId"] = delta.base_state_id
            validation["previousHeadStateId"] = current_state.state_id

            commit_payload = {
                "project_id": delta.project_id,
                "parent_commit_ids": [head["headCommitId"]],
                "base_state_id": delta.base_state_id,
                "result_state_id": result_state.state_id,
                "delta_id": delta.delta_id,
                "author_principal": author_principal,
                "source_work_ids": list(source_work_ids),
                "validation_receipt": validation,
                "created_at": created_at,
            }
            commit_id = _commit_id(commit_payload)
            connection.execute(
                """
                INSERT INTO state_commits(
                    commit_id, project_id, parent_commit_ids_json, base_state_id,
                    result_state_id, delta_json, author_principal,
                    source_work_ids_json, validation_receipt_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    commit_id,
                    delta.project_id,
                    _canonical_json(commit_payload["parent_commit_ids"]),
                    delta.base_state_id,
                    result_state.state_id,
                    _canonical_json(delta.to_dict()),
                    author_principal,
                    _canonical_json(list(source_work_ids)),
                    _canonical_json(validation),
                    created_at,
                ),
            )
            cursor = connection.execute(
                """
                UPDATE project_heads
                SET head_commit_id=?, head_state_id=?, revision=revision+1, updated_at=?
                WHERE project_id=? AND revision=? AND head_commit_id=?
                """,
                (
                    commit_id,
                    result_state.state_id,
                    created_at,
                    delta.project_id,
                    head["revision"],
                    head["headCommitId"],
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("project HEAD changed during commit")

        updated = self.head(delta.project_id)
        updated["commit"] = self.get_commit(commit_id)
        return updated
