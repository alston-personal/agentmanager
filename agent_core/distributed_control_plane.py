"""Canonical IR integration for the existing AgentOS Control Plane.

The base ControlPlaneStore remains a transport-neutral capability/task queue.
This extension adds Distributed AgentOS semantics: immutable IR submission,
lease validation, runtime-result verification, and guarded auto-continuation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from typing import Any

from runtime_core.canonical_ir import CanonicalIR
from runtime_core.remote_runtime import RemoteRuntimeResult

from .control_plane import ControlPlaneStore


TASK_PROTOCOL = "agentos.distributed-task/v1"
RESULT_PROTOCOL = "agentos.distributed-result/v1"
DEFAULT_MAX_AUTO_CONTINUATION_HOPS = 32


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class IRTaskLease:
    task_id: str
    node_id: str
    lease_until: str | None
    idempotency_key: str
    ir: CanonicalIR

    def to_dict(self) -> dict[str, Any]:
        return {
            "taskId": self.task_id,
            "nodeId": self.node_id,
            "leaseUntil": self.lease_until,
            "idempotencyKey": self.idempotency_key,
            "canonicalIR": self.ir.to_dict(),
            "inputDigest": self.ir.digest(),
        }


class DistributedControlPlane(ControlPlaneStore):
    """ControlPlaneStore with Canonical IR task/continuation semantics."""

    def __init__(self, *args: Any, max_auto_continuation_hops: int = DEFAULT_MAX_AUTO_CONTINUATION_HOPS, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if max_auto_continuation_hops < 1:
            raise ValueError("max_auto_continuation_hops must be >= 1")
        self.max_auto_continuation_hops = max_auto_continuation_hops

    def get_task(self, task_id: str) -> dict[str, Any]:
        """Read one generic Control Plane task by id."""
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown task: {task_id}")
        return self._task_from_row(row)

    def submit_ir(
        self,
        ir: CanonicalIR,
        *,
        idempotency_key: str | None = None,
        target_node_id: str | None = None,
    ) -> dict[str, Any]:
        digest = ir.digest()
        return self.submit_task(
            capability=ir.capability,
            payload={
                "protocol": TASK_PROTOCOL,
                "canonical_ir": ir.to_dict(),
                "input_digest": digest,
            },
            idempotency_key=idempotency_key or f"canonical-ir:{ir.ir_id}:{digest}",
            project_id=ir.project_id,
            target_node_id=target_node_id,
        )

    def _ir_from_task(self, task: dict[str, Any]) -> CanonicalIR:
        payload = task.get("payload") or {}
        if payload.get("protocol") != TASK_PROTOCOL:
            raise ValueError("task is not a Distributed AgentOS Canonical IR task")
        raw_ir = payload.get("canonical_ir")
        if not isinstance(raw_ir, dict):
            raise ValueError("task canonical_ir must be an object")
        ir = CanonicalIR.from_dict(raw_ir)
        expected_digest = payload.get("input_digest")
        if not expected_digest or ir.digest() != expected_digest:
            raise ValueError("Canonical IR digest mismatch")
        if task.get("capability") != ir.capability:
            raise ValueError("task capability does not match Canonical IR capability")
        if task.get("projectId") != ir.project_id:
            raise ValueError("task project does not match Canonical IR project")
        return ir

    def _durable_push_targets(self, connection: Any) -> set[str]:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='runtime_targets'"
        ).fetchone()
        if table is None:
            return set()
        return {
            str(row["target_id"])
            for row in connection.execute("SELECT target_id FROM runtime_targets WHERE enabled=1")
        }

    def requeue_expired_ir_leases(self) -> int:
        """Return expired Distributed AgentOS leases to the submitted queue.

        Pull-node ownership is released so another node can recover the task.
        Durable push targets registered by RuntimeDispatcher are preserved so the
        dispatcher can safely re-wake the same external runtime after timeout.
        """
        now = _utc_now()
        requeued = 0
        with self._connect() as connection:
            push_targets = self._durable_push_targets(connection)
            rows = connection.execute(
                """
                SELECT task_id, payload_json, target_node_id
                FROM tasks
                WHERE status='leased' AND lease_until IS NOT NULL AND lease_until < ?
                """,
                (now,),
            ).fetchall()
            for row in rows:
                try:
                    payload = json.loads(row["payload_json"])
                except (TypeError, json.JSONDecodeError):
                    continue
                if payload.get("protocol") != TASK_PROTOCOL:
                    continue
                keep_target = row["target_node_id"] in push_targets
                cursor = connection.execute(
                    """
                    UPDATE tasks
                    SET status='submitted', target_node_id=?, lease_until=NULL, updated_at=?
                    WHERE task_id=? AND status='leased'
                    """,
                    (row["target_node_id"] if keep_target else None, now, row["task_id"]),
                )
                requeued += cursor.rowcount
        return requeued

    def lease_next_ir(
        self,
        node_id: str,
        capabilities: list[str],
        lease_seconds: int = 60,
    ) -> IRTaskLease | None:
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be >= 1")
        self.requeue_expired_ir_leases()
        task = self.lease_next_task(node_id, capabilities, lease_seconds=lease_seconds)
        if task is None:
            return None
        try:
            ir = self._ir_from_task(task)
        except Exception as exc:
            self.update_task(task["taskId"], "failed", {"error": "invalid_canonical_ir_task", "message": str(exc)})
            raise
        return IRTaskLease(
            task_id=task["taskId"],
            node_id=node_id,
            lease_until=task["leaseUntil"],
            idempotency_key=task["idempotencyKey"],
            ir=ir,
        )

    def lease_ir_task(
        self,
        task_id: str,
        node_id: str,
        *,
        lease_seconds: int = 60,
    ) -> IRTaskLease | None:
        """Atomically lease one exact Canonical IR task to a runtime.

        Push dispatch carries a task id. Using a generic "lease next" call after
        wake-up can steal a different queued task for the same runtime. This API
        binds the wake-up, lease, and eventual result to the intended task while
        retaining the normal lease as the execution fence.
        """
        if not task_id or not node_id:
            raise ValueError("task_id and node_id are required")
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be >= 1")

        self.requeue_expired_ir_leases()
        now = datetime.now(timezone.utc)
        lease_until = _timestamp(now + timedelta(seconds=lease_seconds))
        updated = _timestamp(now)

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            if row is None:
                connection.rollback()
                raise KeyError(f"unknown task: {task_id}")
            task = self._task_from_row(row)
            if task["status"] != "submitted":
                connection.commit()
                return None
            target = task.get("targetNodeId")
            if target and target != node_id:
                connection.rollback()
                raise ValueError("task is targeted to a different runtime")
            try:
                ir = self._ir_from_task(task)
            except Exception:
                connection.rollback()
                raise

            cursor = connection.execute(
                """
                UPDATE tasks
                SET status='leased', target_node_id=?, lease_until=?, updated_at=?
                WHERE task_id=? AND status='submitted'
                  AND (target_node_id IS NULL OR target_node_id=?)
                """,
                (node_id, lease_until, updated, task_id, node_id),
            )
            if cursor.rowcount != 1:
                connection.commit()
                return None
            row = connection.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            connection.commit()

        leased = self._task_from_row(row)
        return IRTaskLease(
            task_id=leased["taskId"],
            node_id=node_id,
            lease_until=leased["leaseUntil"],
            idempotency_key=leased["idempotencyKey"],
            ir=ir,
        )

    def complete_ir(
        self,
        task_id: str,
        runtime_result: RemoteRuntimeResult,
        *,
        enqueue_continuation: bool | None = None,
    ) -> dict[str, Any]:
        task = self.get_task(task_id)
        if task["status"] not in {"leased", "running"}:
            raise ValueError(f"task {task_id} is not completable from state {task['status']}")
        input_ir = self._ir_from_task(task)

        lease_owner = task.get("targetNodeId")
        if lease_owner and runtime_result.runtime_id != lease_owner:
            raise ValueError("runtime_id does not match current task lease owner")
        if runtime_result.input_ir_id != input_ir.ir_id:
            raise ValueError("runtime result input_ir_id does not match leased Canonical IR")
        if runtime_result.input_digest != input_ir.digest():
            raise ValueError("runtime result input_digest does not match leased Canonical IR")

        continuation = runtime_result.continuation_ir
        if runtime_result.status == "succeeded":
            if continuation is None:
                raise ValueError("successful runtime result must include a continuation IR")
            if continuation.parent_ir_id != input_ir.ir_id:
                raise ValueError("continuation IR parent does not match input IR")
            if continuation.project_id != input_ir.project_id:
                raise ValueError("continuation IR cannot change project_id")
            task_state = "succeeded"
        else:
            task_state = "failed"

        persisted_result = {
            "protocol": RESULT_PROTOCOL,
            **runtime_result.to_dict(),
        }
        updated_task = self.update_task(task_id, task_state, persisted_result)

        enqueued_task = None
        continuation_blocked = None
        if task_state == "succeeded" and continuation is not None:
            should_enqueue = (
                bool(continuation.continuation.get("auto_continue"))
                if enqueue_continuation is None
                else enqueue_continuation
            )
            if should_enqueue:
                if continuation.hop_count > self.max_auto_continuation_hops:
                    continuation_blocked = "hop_limit"
                else:
                    enqueued_task = self.submit_ir(
                        continuation,
                        idempotency_key=f"continuation:{task_id}:{continuation.digest()}",
                    )

        return {
            "task": updated_task,
            "continuationIR": continuation.to_dict() if continuation else None,
            "enqueuedTask": enqueued_task,
            "continuationBlocked": continuation_blocked,
        }

    def load_continuation_ir(self, task_id: str) -> CanonicalIR | None:
        task = self.get_task(task_id)
        result = task.get("result") or {}
        if result.get("protocol") != RESULT_PROTOCOL:
            return None
        raw = result.get("continuation_ir")
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise ValueError("stored continuation_ir must be an object")
        return CanonicalIR.from_dict(raw)
