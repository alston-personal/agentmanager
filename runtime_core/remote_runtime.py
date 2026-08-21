"""Remote Runtime primitives for Distributed AgentOS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict

from .canonical_ir import CanonicalIR


ExecutorFn = Callable[[CanonicalIR], Dict[str, Any]]


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

        result = executor(ir)
        continuation = ir.derive_continuation(
            payload=result,
            continuation={
                "completed_by": self.runtime_id,
                "previous_capability": ir.capability,
                "ready_for_next_agent": True,
            },
        )
        return RemoteRuntimeResult(
            status="succeeded",
            runtime_id=self.runtime_id,
            input_ir_id=ir.ir_id,
            input_digest=ir.digest(),
            result=result,
            continuation_ir=continuation,
        )
