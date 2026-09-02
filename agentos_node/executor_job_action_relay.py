"""Bounded executor-job extension for the existing ubuntu Action Relay.

This module deliberately reuses ``agentos_node.action_relay`` and its spool,
digest, at-most-once, quarantine, and ubuntu-owned worker boundary. It adds one
fixed semantic action only; no generic shell or argv surface is introduced.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from agent_core.executor_job_contract import (
    project_executor_job_receipt,
    project_executor_job_submission,
    validate_executor_job,
    validate_executor_job_id,
)
from agentos_node.action_relay import ACTIONS, ActionRelayClient, main as action_relay_main
from agentos_node.executor_job_adapter import run_registered_executor_job


ACTION = "agentos.executor.job"
DEFAULT_ROOT = Path("/home/ubuntu/agent-data/runtime/action-relay")


def _execute(params: dict[str, Any]) -> dict[str, Any]:
    if set(params) != {"request"} or not isinstance(params.get("request"), dict):
        raise ValueError("executor-job relay accepts only a canonical request object")
    request = dict(params["request"])
    validate_executor_job(request)
    return run_registered_executor_job(request=request)


# Trusted-process registration. Importing this module extends the same fixed
# Action Relay ACTIONS table used by both producer and ubuntu worker process.
if ACTION in ACTIONS and ACTIONS[ACTION] is not _execute:
    raise RuntimeError("executor-job Action Relay action already registered differently")
ACTIONS[ACTION] = _execute


class ActionRelayExecutorJobDispatcher:
    """Submit/inspect bounded jobs through the existing Action Relay spool."""

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

    def inspect(self, job_id: str) -> dict[str, Any] | None:
        job_id = validate_executor_job_id(job_id)
        request = self._requests.get(job_id)
        if request is None:
            # Controller restart may lose the in-memory request cache. Recover
            # only from the immutable relay capsule/receipt, never from caller
            # supplied filesystem input.
            for base in (self.root / "inbox", self.root / "processing", self.root / "quarantine"):
                path = base / f"{job_id}.json"
                if path.is_file():
                    import json
                    capsule = json.loads(path.read_text(encoding="utf-8"))
                    params = capsule.get("params") or {}
                    candidate = params.get("request") if isinstance(params, dict) else None
                    if isinstance(candidate, dict):
                        validate_executor_job(candidate)
                        request = dict(candidate)
                        self._requests[job_id] = request
                        break
        receipt = self.client.receipt(job_id)
        if receipt is None:
            return None
        if request is None:
            # A terminal receipt without a recoverable canonical request cannot
            # safely be projected into the semantic contract.
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
    """Run the original Action Relay worker with the fixed job action loaded."""
    return action_relay_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
