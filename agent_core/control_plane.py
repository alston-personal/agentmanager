"""Small, persistent Control Plane store for the AgentOS ecosystem MVP.

This module owns coordination state only. Project and module source remain in
their repositories, while the SQLite file defaults to the AgentOS data layer.
It intentionally has no network server yet; an HTTP/ANCP adapter can wrap this
store in the next slice.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import config


TASK_STATES = {"submitted", "leased", "running", "succeeded", "failed", "cancelled", "expired"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


class ControlPlaneStore:
    """SQLite-backed registry and task-lease store.

    The methods are deliberately transport-neutral so HTTPS, NATS, or a local
    CLI can share exactly the same coordination semantics.
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path or (config.RUNTIME_DIR / "control-plane.sqlite3"))
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
                CREATE TABLE IF NOT EXISTS nodes (
                    node_id TEXT PRIMARY KEY,
                    manifest_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'registered',
                    last_heartbeat TEXT NOT NULL,
                    resources_json TEXT NOT NULL DEFAULT '{}',
                    active_tasks_json TEXT NOT NULL DEFAULT '[]'
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    capability TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    project_id TEXT,
                    target_node_id TEXT,
                    status TEXT NOT NULL,
                    lease_until TEXT,
                    result_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS tasks_status_capability
                    ON tasks(status, capability);
                """
            )

    def register_node(self, manifest: dict[str, Any]) -> dict[str, Any]:
        if manifest.get("apiVersion") != "agentos/v1" or manifest.get("kind") != "Node":
            raise ValueError("node manifest must use apiVersion agentos/v1 and kind Node")
        metadata = manifest.get("metadata") or {}
        node_id = str(metadata.get("id") or "")
        if not node_id:
            raise ValueError("node manifest metadata.id is required")

        now = _timestamp(_now())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO nodes(node_id, manifest_json, status, last_heartbeat)
                VALUES (?, ?, 'registered', ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    manifest_json=excluded.manifest_json,
                    status='registered',
                    last_heartbeat=excluded.last_heartbeat
                """,
                (node_id, json.dumps(manifest, sort_keys=True), now),
            )
        return {"nodeId": node_id, "status": "registered", "lastHeartbeat": now}

    def heartbeat(
        self,
        node_id: str,
        resources: dict[str, Any] | None = None,
        active_task_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        now = _timestamp(_now())
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE nodes
                SET status='online', last_heartbeat=?, resources_json=?, active_tasks_json=?
                WHERE node_id=?
                """,
                (
                    now,
                    json.dumps(resources or {}, sort_keys=True),
                    json.dumps(active_task_ids or []),
                    node_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"unknown node: {node_id}")
        return {"nodeId": node_id, "status": "online", "lastHeartbeat": now}

    def record_harvest_report(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Record ANCP node.harvest_report payload to local store and agent-data."""
        device_alias = payload.get("device_alias") or payload.get("hostname") or "unknown_node"
        node_file = config.AGENT_DATA_ROOT / "handoffs" / "nodes" / f"{device_alias}.json"
        node_file.parent.mkdir(parents=True, exist_ok=True)
        with open(node_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return {"deviceAlias": device_alias, "recordedAt": _timestamp(_now()), "savedTo": str(node_file)}


    def find_capable_nodes(self, capability: str) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        with self._connect() as connection:
            for row in connection.execute("SELECT * FROM nodes WHERE status IN ('registered', 'online')"):
                manifest = json.loads(row["manifest_json"])
                capabilities = manifest.get("spec", {}).get("capabilities", [])
                names = {
                    item.get("name")
                    for item in capabilities
                    if isinstance(item, dict)
                }
                if capability in names:
                    matches.append(
                        {
                            "nodeId": row["node_id"],
                            "status": row["status"],
                            "resources": json.loads(row["resources_json"]),
                        }
                    )
        return matches

    def submit_task(
        self,
        capability: str,
        payload: dict[str, Any],
        idempotency_key: str,
        project_id: str | None = None,
        target_node_id: str | None = None,
    ) -> dict[str, Any]:
        if not capability or not idempotency_key:
            raise ValueError("capability and idempotency_key are required")
        now = _timestamp(_now())
        task_id = f"task_{uuid.uuid4().hex}"
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM tasks WHERE idempotency_key=?", (idempotency_key,)
            ).fetchone()
            if existing:
                return self._task_from_row(existing)
            connection.execute(
                """
                INSERT INTO tasks(
                    task_id, idempotency_key, capability, payload_json,
                    project_id, target_node_id, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'submitted', ?, ?)
                """,
                (
                    task_id,
                    idempotency_key,
                    capability,
                    json.dumps(payload, sort_keys=True),
                    project_id,
                    target_node_id,
                    now,
                    now,
                ),
            )
            row = connection.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        return self._task_from_row(row)

    def lease_next_task(
        self,
        node_id: str,
        capabilities: list[str],
        lease_seconds: int = 60,
    ) -> dict[str, Any] | None:
        if not capabilities:
            return None
        placeholders = ",".join("?" for _ in capabilities)
        now = _now()
        lease_until = _timestamp(now + timedelta(seconds=lease_seconds))
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                f"""
                SELECT * FROM tasks
                WHERE status='submitted'
                  AND capability IN ({placeholders})
                  AND (target_node_id IS NULL OR target_node_id=?)
                ORDER BY created_at
                LIMIT 1
                """,
                [*capabilities, node_id],
            ).fetchone()
            if row is None:
                connection.commit()
                return None
            updated = _timestamp(now)
            connection.execute(
                """
                UPDATE tasks
                SET status='leased', target_node_id=?, lease_until=?, updated_at=?
                WHERE task_id=? AND status='submitted'
                """,
                (node_id, lease_until, updated, row["task_id"]),
            )
            row = connection.execute("SELECT * FROM tasks WHERE task_id=?", (row["task_id"],)).fetchone()
            connection.commit()
        return self._task_from_row(row)

    def update_task(
        self,
        task_id: str,
        status: str,
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if status not in TASK_STATES:
            raise ValueError(f"unsupported task state: {status}")
        now = _timestamp(_now())
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE tasks SET status=?, result_json=?, updated_at=?
                WHERE task_id=?
                """,
                (status, json.dumps(result or {}, sort_keys=True), now, task_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"unknown task: {task_id}")
            row = connection.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        return self._task_from_row(row)

    @staticmethod
    def _task_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "taskId": row["task_id"],
            "idempotencyKey": row["idempotency_key"],
            "capability": row["capability"],
            "payload": json.loads(row["payload_json"]),
            "projectId": row["project_id"],
            "targetNodeId": row["target_node_id"],
            "status": row["status"],
            "leaseUntil": row["lease_until"],
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
