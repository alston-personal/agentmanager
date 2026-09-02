from __future__ import annotations

from typing import Any

from agentos_node.employee_worker_host import EmployeeWorkerAdapter, EmployeeWorkerHost, WorkerHostCandidate


class ExactEmployeeWorkerHost(EmployeeWorkerHost):
    """Deployment surface that pins one host cycle to one exact wake capsule.

    `EmployeeWorkerHost` owns the durable dispatch ledger and crash/UNKNOWN
    semantics. This wrapper makes the selected wake immutable for the duration of
    one child launch and passes the exact wake identity to the bounded adapter CLI.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._pinned_candidate: WorkerHostCandidate | None = None

    def _candidates(self) -> list[WorkerHostCandidate]:
        if self._pinned_candidate is not None:
            return [self._pinned_candidate]
        candidates = super()._candidates()
        if candidates:
            self._pinned_candidate = candidates[0]
        return candidates

    def _child_command(self, adapter: EmployeeWorkerAdapter) -> list[str]:
        candidate = self._pinned_candidate
        if candidate is None:
            raise RuntimeError("employee_worker_exact_candidate_missing")
        command = super()._child_command(adapter)
        command.extend(
            [
                "--wake-id",
                str(candidate.capsule["wake_id"]),
                "--presence-generation",
                str(candidate.capsule["presence_generation"]),
            ]
        )
        return command

    def process_one(self) -> dict[str, Any] | None:
        self._pinned_candidate = None
        try:
            return super().process_one()
        finally:
            self._pinned_candidate = None
