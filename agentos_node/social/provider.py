from __future__ import annotations

from typing import Any

from .contracts import SocialRequest, receipt_for, utc_now
from .governance import RuntimeWriteAcceptance
from .public_threads import ThreadsPublicReadError, resolve_public_post
from .registry import default_registry
from .threads import ThreadsCapability


class SocialProvider:
    """Stateless product adapter. It does not persist product content or Q/A data."""

    def __init__(self, *, threads: ThreadsCapability | None = None, public_threads_resolver=resolve_public_post) -> None:
        self.threads = threads
        self.public_threads_resolver = public_threads_resolver

    def capabilities(self) -> dict[str, Any]:
        return {
            "schema": "agentos.social-capabilities/v1",
            "capabilities": [
                {"name": item.name, "platform": item.platform, "operation": item.operation, "write": item.write, "runtime_accepted": item.runtime_accepted}
                for item in default_registry.list()
            ],
        }

    def invoke(self, payload: dict[str, Any], *, acceptance: RuntimeWriteAcceptance | None = None) -> dict[str, Any]:
        request = SocialRequest(**payload).validate()
        capability = f"social.{request.platform}.{request.operation}"
        default_registry.get(capability)
        started = utc_now()

        if request.platform != "threads":
            return receipt_for(request, started_at=started, ok=False, capability=capability, error_code="provider_adapter_not_runtime_accepted").to_dict()

        if request.operation == "public_post.read":
            try:
                source = self.public_threads_resolver(request.object_id or "")
                return receipt_for(request, started_at=started, ok=True, capability=capability, result={"source": source}).to_dict()
            except ThreadsPublicReadError as exc:
                return receipt_for(request, started_at=started, ok=False, capability=capability, error_code=str(exc)).to_dict()

        if self.threads is None:
            return receipt_for(request, started_at=started, ok=False, capability=capability, error_code="threads_runtime_not_configured").to_dict()
        if request.operation == "status":
            return self.threads.status(request)
        if request.operation in {"publish", "reply"}:
            return self.threads.publish(request, acceptance=acceptance)
        if request.operation == "disconnect":
            return self.threads.disconnect(request, acceptance=acceptance)
        return receipt_for(request, started_at=started, ok=False, capability=capability, error_code="operation_requires_provider_route").to_dict()
