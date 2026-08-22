"""Transport adapter contract for AgentOS Node onboarding/directory APIs.

This is deliberately not a production HTTP server. It gives any trusted HTTP
adapter one canonical route table and error model while keeping authentication,
TLS, rate limiting and network exposure outside the protocol semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import unquote

from agent_core.enrollment_api import EnrollmentApi
from agent_core.node_directory_api import NodeDirectoryApi


@dataclass(frozen=True)
class ApiResponse:
    status: int
    body: dict[str, object]


class NodeHttpApi:
    def __init__(
        self,
        *,
        enrollment: EnrollmentApi,
        directory: NodeDirectoryApi,
        now_iso: Callable[[], str] | None = None,
    ) -> None:
        self.enrollment = enrollment
        self.directory = directory
        self._now_iso = now_iso or (
            lambda: datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        )

    def handle(self, method: str, path: str, payload: dict[str, object] | None = None) -> ApiResponse:
        method = method.upper().strip()
        path = "/" + path.strip().lstrip("/")
        body = payload or {}
        try:
            if method == "POST" and path == "/v1/nodes/enrollment/resolve":
                return ApiResponse(200, self.enrollment.resolve(body))
            if method == "POST" and path == "/v1/nodes/enrollment/claim":
                return ApiResponse(200, self.enrollment.claim(body, observed_at=self._now_iso()))
            if method == "GET" and path == "/v1/nodes":
                return ApiResponse(200, self.directory.list_nodes())

            parts = [unquote(part) for part in path.split("/") if part]
            if method == "GET" and len(parts) == 3 and parts[:2] == ["v1", "nodes"]:
                return ApiResponse(200, self.directory.node(parts[2]))
            if method == "GET" and len(parts) == 4 and parts[:2] == ["v1", "nodes"] and parts[3] == "capabilities":
                return ApiResponse(200, self.directory.capabilities(parts[2]))
            if method == "GET" and len(parts) == 4 and parts[0] == "v1" and parts[1] == "capabilities" and parts[3] == "nodes":
                return ApiResponse(200, self.directory.nodes_for_capability(parts[2]))
        except KeyError as exc:
            return ApiResponse(404, {"schema": "agentos.error/v1", "error": "not_found", "message": str(exc)})
        except PermissionError as exc:
            return ApiResponse(403, {"schema": "agentos.error/v1", "error": "forbidden", "message": str(exc)})
        except (TypeError, ValueError) as exc:
            return ApiResponse(400, {"schema": "agentos.error/v1", "error": "invalid_request", "message": str(exc)})

        return ApiResponse(404, {"schema": "agentos.error/v1", "error": "route_not_found", "message": f"no route for {method} {path}"})
