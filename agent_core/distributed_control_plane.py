"""Canonical IR integration for the existing AgentOS Control Plane.

The base ControlPlaneStore remains a transport-neutral capability/task queue.
This extension adds Distributed AgentOS semantics: immutable IR submission,
lease validation, runtime-result verification, and guarded auto-continuation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from runtime_core.canonical_ir import CanonicalIR
from runtime_core.remote_runtime import RemoteRuntimeResult

from .control_plane import ControlPlaneStore


TASK_PROTOCOL = "agentos.distributed-task/v1"
RESULT_PROTOCOL = "agentos.distributed-result/v1"
DEFAULT_MAX_AUTO_CONTINUATION_HOPS = 32


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

    def lease_next_ir(
        self,
        node_id: str,
        capabilities: list[str],
        lease_seconds: int = 60,
    ) -> IRTaskLease | None:
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
