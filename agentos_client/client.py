"""Thin AgentOS Protocol v0.1 HTTP client.

The client intentionally owns transport only. State, governance, task lifecycle,
and execution remain server-side in the AgentOS Core/Kernel.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


class AgentOSClient:
    def __init__(self, base_url: str, *, token: str | None = None, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.session_id: str | None = None
        self.project_id: str | None = None

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"AgentOS HTTP {exc.code}: {raw}") from exc
        value = json.loads(raw) if raw else {}
        if not isinstance(value, dict):
            raise RuntimeError("AgentOS response must be a JSON object")
        return value

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def attach(self, project_id: str, *, agent: dict[str, Any] | None = None) -> dict[str, Any]:
        result = self._request("POST", "/v1/attach", {"project_id": project_id, "agent": agent or {}})
        self.session_id = str(result["session_id"])
        self.project_id = project_id
        return result

    def get_state(self, project_id: str | None = None) -> dict[str, Any]:
        project = project_id or self.project_id
        if not project:
            raise ValueError("project_id is required before attach")
        return self._request("GET", f"/v1/projects/{quote(project, safe='')}/state")

    def submit_task(
        self,
        *,
        project_id: str | None = None,
        goal: str,
        capability: str,
        payload: dict[str, Any] | None = None,
        constraints: list[str] | None = None,
        context: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        target_node_id: str | None = None,
    ) -> dict[str, Any]:
        project = project_id or self.project_id
        if not project:
            raise ValueError("project_id is required before attach")
        return self._request("POST", "/v1/tasks", {
            "project_id": project,
            "goal": goal,
            "capability": capability,
            "payload": payload or {},
            "constraints": constraints or [],
            "context": context or {},
            "idempotency_key": idempotency_key,
            "target_node_id": target_node_id,
            "session_id": self.session_id,
        })

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/tasks/{quote(task_id, safe='')}")

    def get_receipt(self, task_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/receipts/{quote(task_id, safe='')}")
