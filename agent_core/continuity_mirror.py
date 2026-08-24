"""Private GitHub continuity mirror for agents that cannot reach the Control Plane.

The Control Plane remains authoritative. This mirror publishes a compact,
machine-readable project checkpoint into the private AgentOS Data Layer so
connectors (including ChatGPT's GitHub connector) can read the latest Canonical
IR without receiving Control Plane network credentials.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from runtime_core.canonical_ir import CanonicalIR

from .dispatching_gateway import DispatchingGatewayService
from .project_state import read_project_state


MIRROR_PROTOCOL = "agentos.continuity-mirror/v1"
SAFE_PROJECT_ID = re.compile(r"^[A-Za-z0-9._-]+$")


class ContinuityMirrorError(RuntimeError):
    pass


def build_continuity_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    project_id = str(state.get("projectId") or "").strip()
    if not project_id:
        raise ValueError("project state is missing projectId")
    raw_ir = state.get("currentIR")
    current_ir = CanonicalIR.from_dict(raw_ir) if isinstance(raw_ir, dict) else None
    task = state.get("latestTask") if isinstance(state.get("latestTask"), dict) else None
    task_summary = None
    if task is not None:
        task_summary = {
            key: task.get(key)
            for key in (
                "taskId",
                "status",
                "capability",
                "projectId",
                "targetNodeId",
                "leaseUntil",
                "createdAt",
                "updatedAt",
                "result",
            )
            if key in task
        }
    return {
        "protocol": MIRROR_PROTOCOL,
        "project_id": project_id,
        "recommended_action": state.get("recommendedAction"),
        "current_source": state.get("currentSource"),
        "current_ir_digest": current_ir.digest() if current_ir else None,
        "canonical_ir": current_ir.to_dict() if current_ir else None,
        "latest_task": task_summary,
    }


class GitHubContinuityMirror:
    def __init__(
        self,
        repository: str,
        token: str,
        *,
        branch: str = "main",
        root: str = "projects",
        api_base: str = "https://api.github.com",
        timeout: float = 5.0,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        if repository.count("/") != 1:
            raise ValueError("continuity mirror repository must be owner/name")
        if not token:
            raise ValueError("continuity mirror GitHub token is required")
        cleaned_root = root.strip("/") or "projects"
        if ".." in cleaned_root.split("/") or "\\" in cleaned_root:
            raise ValueError("continuity mirror root contains an unsafe path segment")
        self.repository = repository
        self.token = token
        self.branch = branch
        self.root = cleaned_root
        self.api_base = api_base.rstrip("/")
        self.timeout = timeout
        self.opener = opener

    @staticmethod
    def _project_slug(project_id: str) -> str:
        project_id = str(project_id or "").strip()
        if not project_id:
            raise ValueError("project_id is required")
        if SAFE_PROJECT_ID.fullmatch(project_id):
            return project_id
        encoded = base64.urlsafe_b64encode(project_id.encode("utf-8")).decode("ascii").rstrip("=")
        return f"~{encoded}"

    def path_for(self, project_id: str) -> str:
        return f"{self.root}/{self._project_slug(project_id)}/continuity/latest.json"

    def _request(self, request: Request) -> tuple[int, bytes]:
        try:
            with self.opener(request, timeout=self.timeout) as response:
                return int(getattr(response, "status", 200)), response.read()
        except HTTPError as exc:
            raw = exc.read()
            if exc.code in {404, 409}:
                return exc.code, raw
            text = raw.decode("utf-8", errors="replace")
            raise ContinuityMirrorError(f"GitHub continuity mirror HTTP {exc.code}: {text}") from exc
        except URLError as exc:
            raise ContinuityMirrorError(f"GitHub continuity mirror unavailable: {exc.reason}") from exc

    def _contents_url(self, path: str) -> str:
        owner, repo = self.repository.split("/", 1)
        encoded_path = quote(path, safe="/")
        return (
            f"{self.api_base}/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"
            f"/contents/{encoded_path}"
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _read_existing(self, url: str) -> tuple[str | None, bytes | None]:
        get_url = f"{url}?ref={quote(self.branch, safe='')}"
        status, existing_raw = self._request(Request(get_url, headers=self._headers(), method="GET"))
        if status == 404:
            return None, None
        try:
            existing = json.loads(existing_raw.decode("utf-8"))
            existing_sha = existing.get("sha")
            encoded = existing.get("content") or ""
            decoded = base64.b64decode(encoded.replace("\n", "")) if encoded else b""
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            raise ContinuityMirrorError("invalid GitHub contents response for continuity mirror") from exc
        return existing_sha, decoded

    def publish(self, state: dict[str, Any]) -> dict[str, Any]:
        snapshot = build_continuity_snapshot(state)
        project_id = snapshot["project_id"]
        path = self.path_for(project_id)
        raw = (json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        url = self._contents_url(path)

        for attempt in range(2):
            existing_sha, decoded = self._read_existing(url)
            if decoded == raw:
                return {"status": "unchanged", "path": path, "projectId": project_id}

            payload: dict[str, Any] = {
                "message": f"continuity: update {project_id} checkpoint",
                "content": base64.b64encode(raw).decode("ascii"),
                "branch": self.branch,
            }
            if existing_sha:
                payload["sha"] = existing_sha
            put = Request(
                url,
                data=json.dumps(payload, sort_keys=True).encode("utf-8"),
                headers=self._headers(),
                method="PUT",
            )
            put_status, response_raw = self._request(put)
            if put_status == 409 and attempt == 0:
                continue
            if put_status not in {200, 201}:
                raise ContinuityMirrorError(f"GitHub continuity mirror returned HTTP {put_status}")
            try:
                response = json.loads(response_raw.decode("utf-8")) if response_raw else {}
            except json.JSONDecodeError:
                response = {}
            commit = response.get("commit") if isinstance(response, dict) else None
            return {
                "status": "published",
                "path": path,
                "projectId": project_id,
                "commit": commit.get("sha") if isinstance(commit, dict) else None,
            }
        raise ContinuityMirrorError("GitHub continuity mirror update conflicted repeatedly")


class MirroringDispatchingGatewayService(DispatchingGatewayService):
    """Dispatching gateway that publishes best-effort private continuity snapshots."""

    def __init__(self, store: Any, dispatcher: Any, mirror: Any) -> None:
        super().__init__(store, dispatcher)
        self.mirror = mirror

    def _mirror_project(self, project_id: str) -> dict[str, Any]:
        try:
            return self.mirror.publish(read_project_state(self.store, project_id))
        except Exception as exc:  # mirror degradation must never fail task submission/completion
            return {"status": "degraded", "error": str(exc)}

    def submit(self, body: dict[str, Any]) -> dict[str, Any]:
        response = super().submit(body)
        response["continuityMirror"] = self._mirror_project(response["task"]["projectId"])
        return response

    def complete(self, task_id: str, body: dict[str, Any]) -> dict[str, Any]:
        response = super().complete(task_id, body)
        response["continuityMirror"] = self._mirror_project(response["task"]["projectId"])
        return response
