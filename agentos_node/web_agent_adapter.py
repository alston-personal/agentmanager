"""Canonical IR adapter contract for browser/web-hosted AI agents.

A web agent receives an immutable Canonical IR request envelope and returns only
semantic execution output. The adapter, not the web model, owns lineage and
continuation construction so project/parent/hop metadata cannot be forged by a
model response.
"""

from __future__ import annotations

from typing import Any

from runtime_core.canonical_ir import CanonicalIR
from runtime_core.remote_runtime import ExecutionOutcome, RemoteRuntimeResult, RemoteRuntimeWorker


REQUEST_PROTOCOL = "agentos.web-agent-request/v1"
RESPONSE_PROTOCOL = "agentos.web-agent-result/v1"


class WebAgentAdapter:
    def __init__(self, runtime_id: str) -> None:
        if not runtime_id:
            raise ValueError("runtime_id is required")
        self.runtime_id = runtime_id

    def build_request(self, ir: CanonicalIR) -> dict[str, Any]:
        """Build the deterministic request envelope presented to a web agent."""
        return {
            "protocol": REQUEST_PROTOCOL,
            "runtime_id": self.runtime_id,
            "input_ir_id": ir.ir_id,
            "input_digest": ir.digest(),
            "canonical_ir": ir.to_dict(),
            "response_contract": {
                "protocol": RESPONSE_PROTOCOL,
                "required": [
                    "protocol",
                    "runtime_id",
                    "input_ir_id",
                    "input_digest",
                    "status",
                    "result",
                ],
                "status_values": ["succeeded", "failed"],
                "optional": ["next_capability", "auto_continue", "continuation"],
                "rule": "Return semantic result only; never construct continuation_ir.",
            },
        }

    def consume_response(self, ir: CanonicalIR, response: dict[str, Any]) -> RemoteRuntimeResult:
        """Validate a web-agent response and derive a trusted runtime result."""
        if response.get("protocol") != RESPONSE_PROTOCOL:
            raise ValueError("unsupported web agent response protocol")
        if response.get("runtime_id") != self.runtime_id:
            raise ValueError("web agent runtime_id mismatch")
        if response.get("input_ir_id") != ir.ir_id:
            raise ValueError("web agent input_ir_id mismatch")
        if response.get("input_digest") != ir.digest():
            raise ValueError("web agent input_digest mismatch")

        status = response.get("status")
        raw_result = response.get("result")
        if not isinstance(raw_result, dict):
            raise ValueError("web agent result must be an object")

        if status == "failed":
            return RemoteRuntimeResult(
                status="failed",
                runtime_id=self.runtime_id,
                input_ir_id=ir.ir_id,
                input_digest=ir.digest(),
                result=raw_result,
            )
        if status != "succeeded":
            raise ValueError("web agent status must be succeeded or failed")

        next_capability = response.get("next_capability")
        if next_capability is not None and not isinstance(next_capability, str):
            raise ValueError("next_capability must be a string when present")
        auto_continue = response.get("auto_continue", False)
        if not isinstance(auto_continue, bool):
            raise ValueError("auto_continue must be boolean")
        continuation = response.get("continuation") or {}
        if not isinstance(continuation, dict):
            raise ValueError("continuation must be an object")

        outcome = ExecutionOutcome(
            result=raw_result,
            next_capability=next_capability,
            continuation=continuation,
            auto_continue=auto_continue,
        )
        worker = RemoteRuntimeWorker(self.runtime_id)
        worker.register(ir.capability, lambda current: outcome)
        return worker.execute(ir)
