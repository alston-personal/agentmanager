"""Remote Runtime primitives for Distributed AgentOS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict

from .canonical_ir import CanonicalIR


ExecutorFn = Callable[[CanonicalIR], Any]


@dataclass
class ExecutionOutcome:
    """Structured executor output with an optional next-runtime handoff."""

    result: Dict[str, Any] = field(default_factory=dict)
    next_capability: str | None = None
    continuation: Dict[str, Any] = field(default_factory=dict)
    auto_continue: bool = False


@dataclass
class RemoteRuntimeResult:
    status: str
    runtime_id: str
    input_ir_id: str
    input_digest: str
    result: Dict[str, Any] = field(default_factory=dict)
    continuation_ir: CanonicalIR | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "runtime_id": self.runtime_id,
            "input_ir_id": self.input_ir_id,
            "input_digest": self.input_digest,
            "result": self.result,
            "continuation_ir": self.continuation_ir.to_dict() if self.continuation_ir else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RemoteRuntimeResult":
        required = ("status", "runtime_id", "input_ir_id", "input_digest")
        missing = [key for key in required if not data.get(key)]
        if missing:
            raise ValueError(f"missing runtime result fields: {', '.join(missing)}")
        raw_continuation = data.get("continuation_ir")
        if raw_continuation is not None and not isinstance(raw_continuation, dict):
            raise ValueError("continuation_ir must be an object or null")
        raw_result = data.get("result") or {}
        if not isinstance(raw_result, dict):
            raise ValueError("runtime result payload must be an object")
        return cls(
            status=str(data["status"]),
            runtime_id=str(data["runtime_id"]),
            input_ir_id=str(data["input_ir_id"]),
            input_digest=str(data["input_digest"]),
            result=raw_result,
            continuation_ir=CanonicalIR.from_dict(raw_continuation) if raw_continuation else None,
        )


class RemoteRuntimeWorker:
    """Capability-gated worker that consumes and emits Canonical IR.

    Runtimes register named capabilities explicitly. This keeps remote workers
    transportable without turning GitHub Actions or web adapters into arbitrary
    command-execution endpoints.
    """

    def __init__(self, runtime_id: str) -> None:
        if not runtime_id:
            raise ValueError("runtime_id is required")
        self.runtime_id = runtime_id
        self._executors: dict[str, ExecutorFn] = {}

    def register(self, capability: str, executor: ExecutorFn) -> None:
        if not capability:
            raise ValueError("capability is required")
        self._executors[capability] = executor

    @property
    def capabilities(self) -> list[str]:
        return sorted(self._executors)

    def execute(self, ir: CanonicalIR) -> RemoteRuntimeResult:
        executor = self._executors.get(ir.capability)
        if executor is None:
            return RemoteRuntimeResult(
                status="rejected",
                runtime_id=self.runtime_id,
                input_ir_id=ir.ir_id,
                input_digest=ir.digest(),
                result={
                    "error": "unsupported_capability",
                    "requested": ir.capability,
                    "available": self.capabilities,
                },
            )

        try:
            raw_outcome = executor(ir)
        except Exception as exc:
            return RemoteRuntimeResult(
                status="failed",
                runtime_id=self.runtime_id,
                input_ir_id=ir.ir_id,
                input_digest=ir.digest(),
                result={"error": "executor_failed", "message": str(exc)},
            )

        if isinstance(raw_outcome, ExecutionOutcome):
            outcome = raw_outcome
        elif isinstance(raw_outcome, dict):
            outcome = ExecutionOutcome(result=raw_outcome)
        else:
            return RemoteRuntimeResult(
                status="failed",
                runtime_id=self.runtime_id,
                input_ir_id=ir.ir_id,
                input_digest=ir.digest(),
                result={"error": "invalid_executor_result", "type": type(raw_outcome).__name__},
            )

        continuation_metadata = {
            "completed_by": self.runtime_id,
            "previous_capability": ir.capability,
            "ready_for_next_agent": True,
            "auto_continue": outcome.auto_continue,
        }
        if outcome.next_capability:
            continuation_metadata["next_capability"] = outcome.next_capability
        continuation_metadata.update(outcome.continuation)

        continuation = ir.derive_continuation(
            payload=outcome.result,
            continuation=continuation_metadata,
            capability=outcome.next_capability or ir.capability,
        )
        return RemoteRuntimeResult(
            status="succeeded",
            runtime_id=self.runtime_id,
            input_ir_id=ir.ir_id,
            input_digest=ir.digest(),
            result=outcome.result,
            continuation_ir=continuation,
        )
