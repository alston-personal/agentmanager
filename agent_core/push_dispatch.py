"""Hardened push-dispatch primitives for Distributed AgentOS.

This layer keeps the original RuntimeDispatcher contract stable while fixing two
push-specific concerns: an external wake must carry the exact task id, and a
previously dispatched wake must become retryable after the stale timeout when
the durable task is still submitted (for example after lease expiry/crash).
"""

from __future__ import annotations

from datetime import timedelta
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request

from runtime_core.canonical_ir import CanonicalIR

from .runtime_dispatcher import (
    DispatchTransportError,
    GitHubActionsDispatchTransport,
    RuntimeDispatcher,
    RuntimeTarget,
    _now,
    _parse_timestamp,
    _timestamp,
)


class ExactGitHubActionsDispatchTransport(GitHubActionsDispatchTransport):
    """GitHub Actions wake transport that binds workflow execution to task_id."""

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
                "task_id": str(task["taskId"]),
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


class ResilientRuntimeDispatcher(RuntimeDispatcher):
    """RuntimeDispatcher with stale dispatched-wake recovery.

    A task may return to `submitted` after its runtime leased it and then crashed.
    The original `dispatched` receipt therefore cannot be permanent. Once the
    configured stale timeout elapses, another wake with the same stable
    dispatch_id is allowed; the exact task lease remains the final execution
    fence.
    """

    def _claim_dispatch(self, task_id: str, target: RuntimeTarget) -> tuple[dict[str, Any], bool]:
        now = _now()
        stale_before = now - timedelta(seconds=self.dispatch_timeout_seconds)
        retry_before = now - timedelta(seconds=self.dispatch_retry_seconds)
        with self.store._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM runtime_dispatches WHERE task_id=? AND target_id=?",
                (task_id, target.target_id),
            ).fetchone()
            if row is not None:
                current = dict(row)
                updated_at = _parse_timestamp(current["updated_at"])
                if current["status"] in {"dispatching", "dispatched"} and updated_at >= stale_before:
                    connection.commit()
                    return current, False
                if current["status"] == "failed" and updated_at >= retry_before:
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
                import uuid

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
