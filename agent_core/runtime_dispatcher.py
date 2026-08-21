"""Active runtime dispatch for Distributed AgentOS.

The Control Plane owns durable tasks. RuntimeDispatcher only decides whether a
submitted Canonical IR task should wait for a pull-based node or actively wake a
push-based runtime such as GitHub Actions or a web-agent bridge.

Every push dispatch is persisted in the same SQLite database so retries are
observable and duplicate wake-ups are bounded. Task leasing remains the final
execution fence: even if an external wake-up is duplicated, only one runtime can
lease and complete the task.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
import uuid

from runtime_core.canonical_ir import CanonicalIR

from .distributed_control_plane import DistributedControlPlane


DISPATCH_PROTOCOL = "agentos.runtime-dispatch/v1"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass
class RuntimeTarget:
    target_id: str
    kind: str
    capabilities: tuple[str, ...]
    priority: int = 100
    config: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.target_id:
            raise ValueError("target_id is required")
        if not self.kind:
            raise ValueError("target kind is required")
        if not self.capabilities or not all(isinstance(item, str) and item for item in self.capabilities):
            raise ValueError("target capabilities must contain non-empty strings")

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities


class DispatchTransportError(RuntimeError):
    pass


class DispatchTransport(ABC):
    kind: str

    @abstractmethod
    def dispatch(
        self,
        *,
        target: RuntimeTarget,
        task: dict[str, Any],
        ir: CanonicalIR,
        dispatch_id: str,
    ) -> dict[str, Any]:
        """Wake the external runtime and return transport metadata."""


class GitHubActionsDispatchTransport(DispatchTransport):
    kind = "github_actions"

    def __init__(
        self,
        token: str,
        *,
        api_base: str = "https://api.github.com",
        timeout: float = 20.0,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        if not token:
            raise ValueError("GitHub token is required")
        self.token = token
        self.api_base = api_base.rstrip("/")
        self.timeout = timeout
        self.opener = opener

    def dispatch(
        self,
        *,
        target: RuntimeTarget,
        task: dict[str, Any],
        ir: CanonicalIR,
        dispatch_id: str,
    ) -> dict[str, Any]:
        repository = str(target.config.get("repository") or "")
        workflow = str(target.config.get("workflow") or "distributed-agentos-worker.yml")
        ref = str(target.config.get("ref") or "main")
        control_plane_url = str(target.config.get("control_plane_url") or "")
        if repository.count("/") != 1:
            raise DispatchTransportError("GitHub Actions target repository must be owner/name")
        if not control_plane_url:
            raise DispatchTransportError("GitHub Actions target requires control_plane_url")
        parsed = urlparse(control_plane_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise DispatchTransportError("GitHub Actions control_plane_url must be absolute HTTPS")

        owner, repo = repository.split("/", 1)
        url = (
            f"{self.api_base}/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"
            f"/actions/workflows/{quote(workflow, safe='')}/dispatches"
        )
        payload = {
            "ref": ref,
            "inputs": {
                "control_plane_url": control_plane_url,
                "runtime_id": target.target_id,
                "dispatch_id": dispatch_id,
            },
        }
        request = Request(
            url,
            data=json.dumps(payload, sort_keys=True).encode("utf-8"),
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            method="POST",
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                status = int(getattr(response, "status", 204))
                if status not in {200, 201, 202, 204}:
                    raise DispatchTransportError(f"GitHub workflow dispatch returned HTTP {status}")
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise DispatchTransportError(f"GitHub workflow dispatch HTTP {exc.code}: {raw}") from exc
        except URLError as exc:
            raise DispatchTransportError(f"GitHub workflow dispatch unavailable: {exc.reason}") from exc

        return {
            "external_ref": f"github-actions:{repository}:{workflow}:{dispatch_id}",
            "http_status": status,
        }


class WebhookDispatchTransport(DispatchTransport):
    """Wake an authorized bridge for a web agent or other push runtime."""

    kind = "webhook"

    def __init__(
        self,
        *,
        tokens: dict[str, str] | None = None,
        timeout: float = 20.0,
        allow_insecure_http: bool = False,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self.tokens = dict(tokens or {})
        self.timeout = timeout
        self.allow_insecure_http = allow_insecure_http
        self.opener = opener

    def dispatch(
        self,
        *,
        target: RuntimeTarget,
        task: dict[str, Any],
        ir: CanonicalIR,
        dispatch_id: str,
    ) -> dict[str, Any]:
        endpoint = str(target.config.get("endpoint") or "")
        if not endpoint:
            raise DispatchTransportError("webhook target requires endpoint")
        parsed = urlparse(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise DispatchTransportError("webhook endpoint must be absolute http(s)")
        if (
            parsed.scheme == "http"
            and parsed.hostname not in LOOPBACK_HOSTS
            and not self.allow_insecure_http
        ):
            raise DispatchTransportError("non-loopback webhook endpoint requires HTTPS")

        payload = {
            "protocol": DISPATCH_PROTOCOL,
            "dispatch_id": dispatch_id,
            "task_id": task["taskId"],
            "runtime_id": target.target_id,
            "capability": ir.capability,
            "project_id": ir.project_id,
            "input_digest": ir.digest(),
            "canonical_ir": ir.to_dict(),
            "control_plane_url": target.config.get("control_plane_url"),
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
        }
        token = self.tokens.get(target.target_id)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(
            endpoint,
            data=json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                status = int(getattr(response, "status", 200))
                raw = response.read().decode("utf-8") if hasattr(response, "read") else ""
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise DispatchTransportError(f"webhook dispatch HTTP {exc.code}: {raw}") from exc
        except URLError as exc:
            raise DispatchTransportError(f"webhook dispatch unavailable: {exc.reason}") from exc

        if status < 200 or status >= 300:
            raise DispatchTransportError(f"webhook dispatch returned HTTP {status}")
        external_ref = endpoint
        if raw:
            try:
                response_payload = json.loads(raw)
            except json.JSONDecodeError:
                response_payload = None
            if isinstance(response_payload, dict) and response_payload.get("external_ref"):
                external_ref = str(response_payload["external_ref"])
        return {"external_ref": external_ref, "http_status": status}


class RuntimeDispatcher:
    """Policy + durable dispatch state layered over DistributedControlPlane."""

    def __init__(
        self,
        store: DistributedControlPlane,
        *,
        dispatch_timeout_seconds: int = 120,
    ) -> None:
        if dispatch_timeout_seconds < 1:
            raise ValueError("dispatch_timeout_seconds must be >= 1")
        self.store = store
        self.dispatch_timeout_seconds = dispatch_timeout_seconds
        self.targets: dict[str, RuntimeTarget] = {}
        self.transports: dict[str, DispatchTransport] = {}
        self._init_dispatch_state()

    def _init_dispatch_state(self) -> None:
        with self.store._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runtime_dispatches (
                    task_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    target_kind TEXT NOT NULL,
                    dispatch_id TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    external_ref TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(task_id, target_id)
                );
                CREATE INDEX IF NOT EXISTS runtime_dispatches_status
                    ON runtime_dispatches(status, updated_at);
                """
            )

    def register_transport(self, transport: DispatchTransport) -> None:
        self.transports[transport.kind] = transport

    def register_target(self, target: RuntimeTarget) -> None:
        self.targets[target.target_id] = target

    def _runtime_policy(self, ir: CanonicalIR) -> dict[str, Any]:
        policy = ir.context.get("runtime_policy") if isinstance(ir.context, dict) else None
        return policy if isinstance(policy, dict) else {}

    def _select_target(self, task: dict[str, Any], ir: CanonicalIR) -> RuntimeTarget | None:
        explicit_target = task.get("targetNodeId")
        if explicit_target:
            target = self.targets.get(str(explicit_target))
            if target and target.supports(ir.capability) and target.kind in self.transports:
                return target
            return None

        policy = self._runtime_policy(ir)
        denied_targets = {
            str(item) for item in (policy.get("deny_targets") or [])
            if isinstance(item, str)
        }
        allowed_kinds_raw = policy.get("allowed_kinds")
        allowed_kinds = (
            {str(item) for item in allowed_kinds_raw if isinstance(item, str)}
            if isinstance(allowed_kinds_raw, list)
            else None
        )

        candidates = [
            target
            for target in self.targets.values()
            if target.supports(ir.capability)
            and target.kind in self.transports
            and target.target_id not in denied_targets
            and (allowed_kinds is None or target.kind in allowed_kinds)
        ]
        preferred = policy.get("preferred_target")
        if isinstance(preferred, str):
            for target in candidates:
                if target.target_id == preferred:
                    return target
        candidates.sort(key=lambda item: (item.priority, item.target_id))
        return candidates[0] if candidates else None

    def _online_pull_nodes(self, capability: str) -> list[str]:
        return sorted(
            item["nodeId"]
            for item in self.store.find_capable_nodes(capability)
            if item.get("status") == "online"
        )

    def _claim_dispatch(self, task_id: str, target: RuntimeTarget) -> tuple[dict[str, Any], bool]:
        now = _now()
        stale_before = now - timedelta(seconds=self.dispatch_timeout_seconds)
        with self.store._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM runtime_dispatches WHERE task_id=? AND target_id=?",
                (task_id, target.target_id),
            ).fetchone()
            if row is not None:
                current = dict(row)
                if current["status"] == "dispatched":
                    connection.commit()
                    return current, False
                if (
                    current["status"] == "dispatching"
                    and _parse_timestamp(current["updated_at"]) >= stale_before
                ):
                    connection.commit()
                    return current, False
                connection.execute(
                    """
                    UPDATE runtime_dispatches
                    SET status='dispatching', attempts=attempts+1,
                        last_error=NULL, updated_at=?
                    WHERE task_id=? AND target_id=?
                    """,
                    (_timestamp(now), task_id, target.target_id),
                )
            else:
                dispatch_id = f"dispatch_{uuid.uuid4().hex}"
                connection.execute(
                    """
                    INSERT INTO runtime_dispatches(
                        task_id, target_id, target_kind, dispatch_id, status,
                        attempts, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'dispatching', 1, ?, ?)
                    """,
                    (
                        task_id,
                        target.target_id,
                        target.kind,
                        dispatch_id,
                        _timestamp(now),
                        _timestamp(now),
                    ),
                )
            row = connection.execute(
                "SELECT * FROM runtime_dispatches WHERE task_id=? AND target_id=?",
                (task_id, target.target_id),
            ).fetchone()
            connection.commit()
        return dict(row), True

    def _finish_dispatch(
        self,
        task_id: str,
        target_id: str,
        *,
        status: str,
        external_ref: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        now = _timestamp(_now())
        with self.store._connect() as connection:
            connection.execute(
                """
                UPDATE runtime_dispatches
                SET status=?, external_ref=?, last_error=?, updated_at=?
                WHERE task_id=? AND target_id=?
                """,
                (status, external_ref, error, now, task_id, target_id),
            )
            row = connection.execute(
                "SELECT * FROM runtime_dispatches WHERE task_id=? AND target_id=?",
                (task_id, target_id),
            ).fetchone()
        return dict(row)

    @staticmethod
    def _receipt(row: dict[str, Any], *, status_override: str | None = None) -> dict[str, Any]:
        return {
            "dispatchId": row.get("dispatch_id"),
            "taskId": row.get("task_id"),
            "targetId": row.get("target_id"),
            "targetKind": row.get("target_kind"),
            "status": status_override or row.get("status"),
            "attempts": row.get("attempts"),
            "externalRef": row.get("external_ref"),
            "error": row.get("last_error"),
        }

    def dispatch_task(self, task_id: str) -> dict[str, Any]:
        task = self.store.get_task(task_id)
        if task["status"] != "submitted":
            return {
                "taskId": task_id,
                "status": "skipped",
                "reason": f"task_state:{task['status']}",
            }
        try:
            ir = self.store._ir_from_task(task)
        except ValueError:
            return {"taskId": task_id, "status": "skipped", "reason": "not_distributed_ir"}

        explicit_target = task.get("targetNodeId")
        if explicit_target and explicit_target not in self.targets:
            return {
                "taskId": task_id,
                "status": "waiting_for_pull",
                "targetId": explicit_target,
            }

        policy = self._runtime_policy(ir)
        prefer_push = bool(policy.get("prefer_push"))
        online_nodes = self._online_pull_nodes(ir.capability)
        if online_nodes and not explicit_target and not prefer_push:
            return {
                "taskId": task_id,
                "status": "waiting_for_pull",
                "capability": ir.capability,
                "onlineNodes": online_nodes,
            }

        target = self._select_target(task, ir)
        if target is None:
            return {
                "taskId": task_id,
                "status": "no_target",
                "capability": ir.capability,
                "onlineNodes": online_nodes,
            }

        if not explicit_target:
            task = self._target_submitted_ir_task(task_id, target.target_id)

        row, should_send = self._claim_dispatch(task_id, target)
        if not should_send:
            existing_status = "already_dispatched" if row["status"] == "dispatched" else "dispatching"
            return self._receipt(row, status_override=existing_status)

        transport = self.transports[target.kind]
        try:
            metadata = transport.dispatch(
                target=target,
                task=task,
                ir=ir,
                dispatch_id=row["dispatch_id"],
            )
        except Exception as exc:
            failed = self._finish_dispatch(
                task_id,
                target.target_id,
                status="failed",
                error=str(exc),
            )
            return self._receipt(failed)

        completed = self._finish_dispatch(
            task_id,
            target.target_id,
            status="dispatched",
            external_ref=str(metadata.get("external_ref") or "") or None,
        )
        return self._receipt(completed)

    def _target_submitted_ir_task(self, task_id: str, target_id: str) -> dict[str, Any]:
        now = _timestamp(_now())
        with self.store._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            if row is None:
                connection.rollback()
                raise KeyError(f"unknown task: {task_id}")
            task = self.store._task_from_row(row)
            self.store._ir_from_task(task)
            if task["status"] != "submitted":
                connection.rollback()
                raise ValueError(f"task {task_id} is not targetable from state {task['status']}")
            current_target = task.get("targetNodeId")
            if current_target and current_target != target_id:
                connection.rollback()
                raise ValueError(f"task {task_id} is already targeted to {current_target}")
            connection.execute(
                "UPDATE tasks SET target_node_id=?, updated_at=? WHERE task_id=? AND status='submitted'",
                (target_id, now, task_id),
            )
            row = connection.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            connection.commit()
        return self.store._task_from_row(row)

    def _submitted_task_ids(self, limit: int) -> list[str]:
        with self.store._connect() as connection:
            rows = connection.execute(
                "SELECT task_id FROM tasks WHERE status='submitted' ORDER BY created_at LIMIT ?",
                (limit,),
            ).fetchall()
        return [str(row["task_id"]) for row in rows]

    def dispatch_pending(self, *, limit: int = 20) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        return [self.dispatch_task(task_id) for task_id in self._submitted_task_ids(limit)]
