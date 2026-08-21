"""Gateway service wrapper that actively wakes push-based runtimes."""

from __future__ import annotations

from typing import Any

from .distributed_gateway import DistributedGatewayService
from .runtime_dispatcher import RuntimeDispatcher


class DispatchingGatewayService(DistributedGatewayService):
    """Add active dispatch after submit and after auto-continuation enqueue."""

    def __init__(self, store: Any, dispatcher: RuntimeDispatcher) -> None:
        super().__init__(store)
        self.dispatcher = dispatcher

    def submit(self, body: dict[str, Any]) -> dict[str, Any]:
        response = super().submit(body)
        task = response["task"]
        response["dispatch"] = self.dispatcher.dispatch_task(task["taskId"])
        return response

    def complete(self, task_id: str, body: dict[str, Any]) -> dict[str, Any]:
        response = super().complete(task_id, body)
        enqueued = response.get("enqueuedTask")
        response["dispatch"] = (
            self.dispatcher.dispatch_task(enqueued["taskId"])
            if isinstance(enqueued, dict) and enqueued.get("taskId")
            else None
        )
        return response
