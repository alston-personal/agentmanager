"""Bounded executor-job extension for the existing ubuntu Action Relay.

This module deliberately reuses ``agentos_node.action_relay`` and its spool,
digest, at-most-once, quarantine, and ubuntu-owned worker boundary. It loads
fixed semantic actions only; no generic shell or argv surface is introduced.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from agent_core.executor_job_contract import (
    EXECUTOR_JOB_SCHEMA,
    project_executor_job_receipt,
    project_executor_job_submission,
    validate_executor_job,
    validate_executor_job_id,
)
from agentos_node.action_relay import ACTIONS, ActionRelayClient, main as action_relay_main
from agentos_node.executor_job_adapter import run_registered_executor_job
from agentos_node.issue117_experience_provider import register_issue117_provider_if_available


ACTION = "agentos.executor.job"
DEFAULT_ROOT = Path("/home/ubuntu/agent-data/runtime/action-relay")
_REQUEST_FIELDS = ("job_type", "project_id", "executor_class", "workload_ref", "authority")

ISSUE117_PROVIDER_REGISTERED = register_issue117_provider_if_available()


def _request_projection(request: Mapping[str, Any]) -> dict[str, Any]:
    validate_executor_job(request)
    return {key: request[key] for key in _REQUEST_FIELDS}


def _request_from_receipt(receipt: Mapping[str, Any]) -> dict[str, Any] | None:
    candidate = {"schema": EXECUTOR_JOB_SCHEMA}
    for key in _REQUEST_FIELDS:
        value = receipt.get(key)
        if not isinstance(value, str) or not value:
            return None
        candidate[key] = value
    validate_executor_job(candidate)
    return candidate


def _execute(params: dict[str, Any]) -> dict[str, Any]:
    if set(params) != {"request"} or not isinstance(params.get("request"), dict):
        raise ValueError("executor-job relay accepts only a canonical request object")
    request = dict(params["request"])
    validate_executor_job(request)
    return {**_request_projection(request), **run_registered_executor_job(request=request)}


if ACTION in ACTIONS and ACTIONS[ACTION] is not _execute:
    raise RuntimeError("executor-job Action Relay action already registered differently")
ACTIONS[ACTION] = _execute

from agentos_node import runtime_converge_action_relay as _runtime_converge_action_relay  # noqa: E402,F401


class ActionRelayExecutorJobDispatcher:
    """Submit/inspect fixed semantic work through the shared Action Relay spool.

    ``inspect`` remains the historical controller receipt facade. It now routes
    runtime-converge receipts by their persisted semantic action before applying
    executor-job projection, so action-* IDs remain unambiguous.
    """

    def __init__(self, root: str | Path = DEFAULT_ROOT):
        self.root = Path(root)
        self.client = ActionRelayClient(self.root)
        self._requests: dict[str, dict[str, Any]] = {}

    def submit(self, *, node_id: str, request: Mapping[str, Any]) -> dict[str, Any]:
        validate_executor_job(request)
        capsule = self.client.submit(ACTION, {"request": dict(request)})
        job_id = validate_executor_job_id(str(capsule["capsule_id"]))
        self._requests[job_id] = dict(request)
        return project_executor_job_submission(job_id=job_id, node_id=node_id, request=request)

    def _recover_request(self, job_id: str) -> dict[str, Any] | None:
        request = self._requests.get(job_id)
        if request is not None:
            return request
        for base in (self.root / "inbox", self.root / "processing", self.root / "quarantine"):
            path = base / f"{job_id}.json"
            if not path.is_file():
                continue
            capsule = json.loads(path.read_text(encoding="utf-8"))
            params = capsule.get("params") or {}
            candidate = params.get("request") if isinstance(params, dict) else None
            if isinstance(candidate, dict):
                validate_executor_job(candidate)
                request = dict(candidate)
                self._requests[job_id] = request
                return request
        receipt_path = self.root / "receipts" / f"{job_id}.json"
        if receipt_path.is_file():
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            request = _request_from_receipt(receipt)
            if request is not None:
                self._requests[job_id] = request
                return request
        return None

    def inspect(self, job_id: str) -> dict[str, Any] | None:
        job_id = validate_executor_job_id(job_id)
        receipt = self.client.receipt(job_id)
        if receipt is not None and receipt.get("action") == _runtime_converge_action_relay.ACTION:
            return _runtime_converge_action_relay.ActionRelayRuntimeConvergeDispatcher(self.root).inspect(job_id)
        if receipt is None:
            return None
        request = self._recover_request(job_id)
        if request is None:
            raise RuntimeError("executor-job request provenance unavailable")
        if receipt.get("action") not in (None, ACTION):
            raise RuntimeError("executor-job relay receipt action mismatch")
        if receipt.get("outcome") == "unknown":
            return project_executor_job_receipt(
                job_id=job_id,
                request=request,
                executor_available=True,
                routable=True,
                authorized=True,
                successful=False,
                result={"classification": "EXECUTION_OUTCOME_UNKNOWN"},
            )
        return project_executor_job_receipt(
            job_id=job_id,
            request=request,
            executor_available=bool(receipt.get("executor_available")),
            routable=bool(receipt.get("routable")),
            authorized=bool(receipt.get("authorized")),
            successful=bool(receipt.get("successful")),
            result=receipt,
        )


def main(argv: list[str] | None = None) -> int:
    return action_relay_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
