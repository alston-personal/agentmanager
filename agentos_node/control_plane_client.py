"""Lightweight HTTP client for the Distributed AgentOS Control Plane."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen

from runtime_core.canonical_ir import CanonicalIR
from runtime_core.remote_runtime import RemoteRuntimeResult


LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class ControlPlaneClientError(RuntimeError):
    pass


class ControlPlaneHTTPError(ControlPlaneClientError):
    def __init__(self, status: int, payload: dict[str, Any]) -> None:
        self.status = status
        self.payload = payload
        super().__init__(f"control plane HTTP {status}: {payload.get('error', 'request_failed')}")


class ControlPlaneClient:
    """JSON client shared by lightweight nodes, IDE adapters, and remote runtimes."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout: float = 30.0,
        allow_insecure_http: bool = False,
    ) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("base_url must be an absolute http(s) URL")
        if parsed.scheme == "http" and parsed.hostname not in LOOPBACK_HOSTS and not allow_insecure_http:
            raise ValueError("non-loopback control plane requires HTTPS unless allow_insecure_http=True")
        self.base_url = base_url.rstrip("/") + "/"
        self.token = token
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(urljoin(self.base_url, path.lstrip("/")), data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                error_payload = json.loads(raw)
            except json.JSONDecodeError:
                error_payload = {"error": "http_error", "message": raw}
            if not isinstance(error_payload, dict):
                error_payload = {"error": "http_error", "payload": error_payload}
            raise ControlPlaneHTTPError(exc.code, error_payload) from exc
        except URLError as exc:
            raise ControlPlaneClientError(f"control plane unavailable: {exc.reason}") from exc

        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ControlPlaneClientError("control plane response root must be an object")
        return value

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def attach(self, project_id: str, *, agent: dict[str, Any] | None = None) -> dict[str, Any]:
        project_id = str(project_id or "").strip()
        if not project_id:
            raise ValueError("project_id is required")
        return self._request(
            "POST",
            "/v1/attach",
            {"project_id": project_id, "agent": dict(agent or {})},
        )

    def resolve_active_project(self, *, hint: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if hint is not None and str(hint).strip():
            payload["hint"] = str(hint).strip()
        return self._request("POST", "/v1/projects/resolve-active", payload)

    def resolve_enrollment(self, reference: str) -> dict[str, Any]:
        return self._request("POST", "/v1/nodes/enrollment/resolve", {"reference": reference})

    def claim_enrollment(self, ticket: str, claim: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/v1/nodes/enrollment/claim", {"ticket": ticket, "claim": claim})

    def list_nodes(self) -> dict[str, Any]:
        return self._request("GET", "/v1/nodes")

    def get_node(self, node_id: str) -> dict[str, Any]:
        node_id = str(node_id or "").strip()
        if not node_id:
            raise ValueError("node_id is required")
        return self._request("GET", f"/v1/nodes/{quote(node_id, safe='')}")

    def get_node_capabilities(self, node_id: str) -> dict[str, Any]:
        node_id = str(node_id or "").strip()
        if not node_id:
            raise ValueError("node_id is required")
        return self._request("GET", f"/v1/nodes/{quote(node_id, safe='')}/capabilities")

    def nodes_for_capability(self, capability: str) -> dict[str, Any]:
        capability = str(capability or "").strip()
        if not capability:
            raise ValueError("capability is required")
        return self._request("GET", f"/v1/capabilities/{quote(capability, safe='')}/nodes")

    def submit_ir(
        self,
        ir: CanonicalIR,
        *,
        idempotency_key: str | None = None,
        target_node_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"canonical_ir": ir.to_dict()}
        if idempotency_key:
            payload["idempotency_key"] = idempotency_key
        if target_node_id:
            payload["target_node_id"] = target_node_id
        return self._request("POST", "/v1/ir/submit", payload)

    def lease(
        self,
        node_id: str,
        capabilities: list[str],
        *,
        lease_seconds: int = 60,
    ) -> dict[str, Any] | None:
        response = self._request(
            "POST",
            "/v1/lease",
            {"node_id": node_id, "capabilities": capabilities, "lease_seconds": lease_seconds},
        )
        lease = response.get("lease")
        if lease is not None and not isinstance(lease, dict):
            raise ControlPlaneClientError("lease response must be an object or null")
        return lease

    def lease_task(
        self,
        task_id: str,
        node_id: str,
        *,
        lease_seconds: int = 60,
    ) -> dict[str, Any] | None:
        response = self._request(
            "POST",
            f"/v1/tasks/{task_id}/lease",
            {"node_id": node_id, "lease_seconds": lease_seconds},
        )
        lease = response.get("lease")
        if lease is not None and not isinstance(lease, dict):
            raise ControlPlaneClientError("exact lease response must be an object or null")
        return lease

    def complete(
        self,
        task_id: str,
        result: RemoteRuntimeResult,
        *,
        enqueue_continuation: bool | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"runtime_result": result.to_dict()}
        if enqueue_continuation is not None:
            payload["enqueue_continuation"] = enqueue_continuation
        return self._request("POST", f"/v1/tasks/{task_id}/complete", payload)

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/tasks/{task_id}")

    def get_project_state(self, project_id: str) -> dict[str, Any]:
        project_id = str(project_id or "").strip()
        if not project_id:
            raise ValueError("project_id is required")
        encoded = quote(project_id, safe="")
        return self._request("GET", f"/v1/projects/{encoded}/state")
