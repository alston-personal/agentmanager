"""Controller-side routing boundary for bounded asynchronous executor jobs.

Core deliberately knows nothing about Oracle spool paths, Linux users, or
ActionRelay implementation details. A Node/runtime supplies an
``ExecutorJobDispatcher`` implementation. This keeps the ONE contract portable
across Nodes while preserving the rule that executor-local credentials and
implementation choices never become model input.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping, Protocol

from agent_core.executor_job_contract import (
    EXECUTOR_JOB_RECEIPT_SCHEMA,
    ExecutorJobContractError,
    project_executor_job_submission,
    validate_executor_job,
    validate_executor_job_id,
)


EXECUTOR_JOB_INSPECTION_SCHEMA = "agentos.executor-job-inspection/v1"
_TERMINAL_STATES = {"completed", "failed", "unknown"}
_NONTERMINAL_STATES = {"queued", "processing"}


class ExecutorJobRoutingError(RuntimeError):
    """Stable fail-closed routing error; no provider-local detail is included."""


class ExecutorJobDispatcher(Protocol):
    """Node/runtime-owned asynchronous transport used by the Core controller."""

    def submit(self, *, node_id: str, request: Mapping[str, Any]) -> str: ...

    def inspect(self, *, node_id: str, job_id: str) -> Mapping[str, Any]: ...


NodeLookup = Callable[[str], Mapping[str, Any]]


class ExecutorJobController:
    """Validate, route, and inspect declared executor jobs without generic exec."""

    def __init__(self, *, node_lookup: NodeLookup, dispatcher: ExecutorJobDispatcher | None):
        self._node_lookup = node_lookup
        self._dispatcher = dispatcher

    def _node(self, node_id: str) -> Mapping[str, Any]:
        value = str(node_id or "").strip()
        if not value:
            raise ExecutorJobContractError("node_id is required")
        node = self._node_lookup(value)
        if not isinstance(node, Mapping):
            raise ExecutorJobRoutingError("NODE_RECORD_INVALID")
        return node

    def submit(self, *, node_id: str, request: Mapping[str, Any]) -> dict[str, Any]:
        spec = validate_executor_job(request)
        node = self._node(node_id)
        if node.get("status") != "online":
            raise ExecutorJobRoutingError("NODE_OFFLINE")
        capabilities = set(node.get("capabilities") or [])
        if spec.capability not in capabilities:
            raise ExecutorJobRoutingError("EXECUTOR_JOB_CAPABILITY_NOT_ADVERTISED")
        if self._dispatcher is None:
            raise ExecutorJobRoutingError("EXECUTOR_JOB_DISPATCHER_UNAVAILABLE")

        job_id = self._dispatcher.submit(node_id=str(node_id), request=request)
        return project_executor_job_submission(
            job_id=job_id,
            node_id=str(node_id),
            request=request,
        )

    def inspect(self, *, node_id: str, job_id: str) -> dict[str, Any]:
        # A completed durable receipt must remain readable after the Node goes
        # offline. Therefore inspect validates Node identity but intentionally
        # does not impose an online/liveness gate.
        self._node(node_id)
        job_id = validate_executor_job_id(job_id)
        if self._dispatcher is None:
            raise ExecutorJobRoutingError("EXECUTOR_JOB_DISPATCHER_UNAVAILABLE")
        observed = self._dispatcher.inspect(node_id=str(node_id), job_id=job_id)
        if not isinstance(observed, Mapping):
            raise ExecutorJobRoutingError("EXECUTOR_JOB_OBSERVATION_INVALID")
        if observed.get("node_id") != str(node_id) or observed.get("job_id") != job_id:
            raise ExecutorJobRoutingError("EXECUTOR_JOB_IDENTITY_MISMATCH")

        state = str(observed.get("state") or "").strip()
        if state not in _NONTERMINAL_STATES | _TERMINAL_STATES:
            raise ExecutorJobRoutingError("EXECUTOR_JOB_STATE_INVALID")

        result = observed.get("result")
        projection: dict[str, Any] = {
            "schema": EXECUTOR_JOB_INSPECTION_SCHEMA,
            "ok": True,
            "job_id": job_id,
            "node_id": str(node_id),
            "state": state,
            "terminal": state in _TERMINAL_STATES,
            "credential_exposed": False,
        }
        classification = observed.get("classification")
        if isinstance(classification, str) and classification:
            projection["classification"] = classification

        if result is not None:
            if not isinstance(result, Mapping):
                raise ExecutorJobRoutingError("EXECUTOR_JOB_RESULT_INVALID")
            if result.get("schema") != EXECUTOR_JOB_RECEIPT_SCHEMA:
                raise ExecutorJobRoutingError("EXECUTOR_JOB_RESULT_SCHEMA_INVALID")
            if result.get("job_id") != job_id:
                raise ExecutorJobRoutingError("EXECUTOR_JOB_RESULT_ID_MISMATCH")
            if result.get("credential_exposed") is not False:
                raise ExecutorJobRoutingError("EXECUTOR_JOB_CREDENTIAL_BOUNDARY_NOT_PROVEN")
            projection["result"] = dict(result)
        elif state == "completed":
            raise ExecutorJobRoutingError("EXECUTOR_JOB_TERMINAL_RESULT_MISSING")

        return projection
