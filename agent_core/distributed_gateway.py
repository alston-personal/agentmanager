"""HTTP transport adapter for the Distributed AgentOS Control Plane."""

from __future__ import annotations

import hmac
import json
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlparse, parse_qs

from runtime_core.canonical_ir import CanonicalIR
from runtime_core.remote_runtime import RemoteRuntimeResult

from .canonical_context import CanonicalContextStore
from .client_auth import ClientPrincipal, ClientTokenStore
from .context_compiler import compile_execution_context
from .distributed_control_plane import DistributedControlPlane
from .project_state import read_project_state
from .approval_broker import list_approvals, resolve_approval, park_approval
from .companion_web import render_companion_html, render_public_entry_html, render_welcome_html, render_platform_review_html, render_platform_auth_gate_html, render_my_one_html
from .shared_auth_bridge import is_shared_auth_path, proxy_shared_auth_request
from .account_realm_onboarding import account_request
from .platform_realm_review import platform_review
from .realm_provisioning import account_virtual_one
from .virtual_one_nodes import owner_node_map, owner_approve_code, device_join, tenant_node_runtime

MAX_REQUEST_BYTES = 1024 * 1024
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
CORE_PROTOCOL = "agentos.core/v0.1"


def validate_bind_security(host: str, token: str | None) -> None:
    if host not in LOOPBACK_HOSTS and not token:
        raise ValueError("AGENTOS_CONTROL_PLANE_TOKEN is required for non-loopback binds")


class DistributedGatewayService:
    """Transport-neutral Kernel operations used by HTTP and future adapters."""

    def __init__(self, store: DistributedControlPlane) -> None:
        self.store = store
        self.context_store = CanonicalContextStore(store.db_path)

    def attach(self, body: dict[str, Any]) -> dict[str, Any]:
        project_id = str(body.get("project_id") or "").strip()
        if not project_id:
            raise ValueError("project_id is required")
        agent = body.get("agent") or {}
        if not isinstance(agent, dict):
            raise ValueError("agent must be an object")
        state = read_project_state(self.store, project_id)
        execution_context = compile_execution_context(
            project_id,
            state,
            agent=agent,
            context_store=self.context_store,
        )
        return {
            "protocol": CORE_PROTOCOL,
            "session_id": f"aos_{uuid.uuid4().hex}",
            "project_id": project_id,
            "agent": agent,
            "state": state,
            "execution_context": execution_context,
            "capabilities": {
                "state.read": True,
                "task.submit": True,
                "task.read": True,
                "receipt.read": True,
                "context.compile": True,
                "context.checkpoint": True,
                "production.deploy": "gated",
            },
        }

    def resolve_active_project(
        self,
        body: dict[str, Any],
        *,
        principal: ClientPrincipal | None = None,
    ) -> dict[str, Any]:
        """Resolve the most recently active readable project, optionally using a hint.

        The durable source is the canonical task ledger.  Browser/device/session
        metadata is intentionally excluded so the result is stable across ChatGPT
        devices.  A scoped principal never learns project ids outside its scope.
        """

        hint = str(body.get("hint") or "").strip().casefold()
        with self.store._connect() as connection:
            rows = connection.execute(
                """
                SELECT project_id, MAX(updated_at) AS last_active_at
                FROM tasks
                WHERE project_id IS NOT NULL AND TRIM(project_id) <> ''
                GROUP BY project_id
                ORDER BY last_active_at DESC, project_id ASC
                """
            ).fetchall()

        candidates: list[dict[str, Any]] = []
        for row in rows:
            project_id = str(row["project_id"] or "").strip()
            if not project_id:
                continue
            if principal is not None and not principal.allows_project(project_id):
                continue
            state = read_project_state(self.store, project_id)
            current_ir = state.get("currentIR") if isinstance(state.get("currentIR"), dict) else {}
            goal = str(current_ir.get("goal") or "")
            score = 0
            if hint:
                project_folded = project_id.casefold()
                goal_folded = goal.casefold()
                if hint == project_folded:
                    score = 100
                elif hint in project_folded:
                    score = 80
                elif hint in goal_folded:
                    score = 60
                else:
                    hint_terms = [term for term in hint.replace("/", " ").replace("-", " ").split() if len(term) >= 2]
                    score = sum(10 for term in hint_terms if term in project_folded or term in goal_folded)
            candidates.append(
                {
                    "project_id": project_id,
                    "last_active_at": row["last_active_at"],
                    "recommended_action": state.get("recommendedAction"),
                    "current_source": state.get("currentSource"),
                    "goal": goal or None,
                    "hint_score": score,
                }
            )

        if not candidates:
            return {
                "protocol": "agentos.active-project/v1",
                "resolution": "none",
                "project_id": None,
                "candidates": [],
            }

        ranked = candidates
        if hint:
            ranked = sorted(
                candidates,
                key=lambda item: (int(item["hint_score"]), str(item["last_active_at"] or ""), item["project_id"]),
                reverse=True,
            )
            best_score = int(ranked[0]["hint_score"])
            if best_score <= 0:
                return {
                    "protocol": "agentos.active-project/v1",
                    "resolution": "no_hint_match",
                    "project_id": None,
                    "candidates": ranked[:5],
                }
            tied = [item for item in ranked if int(item["hint_score"]) == best_score]
            if len(tied) > 1 and tied[0]["last_active_at"] == tied[1]["last_active_at"]:
                return {
                    "protocol": "agentos.active-project/v1",
                    "resolution": "ambiguous",
                    "project_id": None,
                    "candidates": tied[:5],
                }

        selected = ranked[0]
        return {
            "protocol": "agentos.active-project/v1",
            "resolution": "resolved",
            "project_id": selected["project_id"],
            "selected": selected,
            "candidates": ranked[:5],
        }

    def submit(self, body: dict[str, Any]) -> dict[str, Any]:
        raw_ir = body.get("canonical_ir")
        if not isinstance(raw_ir, dict):
            raise ValueError("canonical_ir must be an object")
        ir = CanonicalIR.from_dict(raw_ir)
        task = self.store.submit_ir(ir, idempotency_key=body.get("idempotency_key"), target_node_id=body.get("target_node_id"))
        return {"task": task, "inputDigest": ir.digest()}

    def submit_task(self, body: dict[str, Any]) -> dict[str, Any]:
        project_id = str(body.get("project_id") or "").strip()
        goal = str(body.get("goal") or "").strip()
        capability = str(body.get("capability") or "").strip()
        if not project_id or not goal or not capability:
            raise ValueError("project_id, goal and capability are required")
        payload = body.get("payload") or {}
        context = body.get("context") or {}
        constraints = body.get("constraints") or []
        if not isinstance(payload, dict) or not isinstance(context, dict):
            raise ValueError("payload and context must be objects")
        if not isinstance(constraints, list) or not all(isinstance(x, str) for x in constraints):
            raise ValueError("constraints must be an array of strings")
        if body.get("session_id"):
            context = dict(context)
            context["agentos_session_id"] = str(body["session_id"])
        ir = CanonicalIR(goal=goal, project_id=project_id, capability=capability, payload=payload, constraints=constraints, context=context)
        task = self.store.submit_ir(ir, idempotency_key=body.get("idempotency_key"), target_node_id=body.get("target_node_id"))
        return {"protocol": CORE_PROTOCOL, "task": task, "canonical_ir": ir.to_dict(), "inputDigest": ir.digest()}

    def lease(self, body: dict[str, Any]) -> dict[str, Any]:
        node_id = str(body.get("node_id") or "")
        capabilities = body.get("capabilities") or []
        if not node_id:
            raise ValueError("node_id is required")
        if not isinstance(capabilities, list) or not all(isinstance(item, str) for item in capabilities):
            raise ValueError("capabilities must be an array of strings")
        lease_seconds = int(body.get("lease_seconds", 60))
        lease = self.store.lease_next_ir(node_id, capabilities, lease_seconds=lease_seconds)
        return {"lease": lease.to_dict() if lease else None}

    def lease_task(self, task_id: str, body: dict[str, Any]) -> dict[str, Any]:
        node_id = str(body.get("node_id") or "")
        if not node_id:
            raise ValueError("node_id is required")
        lease_seconds = int(body.get("lease_seconds", 60))
        lease = self.store.lease_ir_task(task_id, node_id, lease_seconds=lease_seconds)
        return {"lease": lease.to_dict() if lease else None}

    def complete(self, task_id: str, body: dict[str, Any]) -> dict[str, Any]:
        raw_result = body.get("runtime_result")
        if not isinstance(raw_result, dict):
            raise ValueError("runtime_result must be an object")
        enqueue = body.get("enqueue_continuation")
        if enqueue is not None and not isinstance(enqueue, bool):
            raise ValueError("enqueue_continuation must be boolean or omitted")
        epoch = body.get("lease_epoch")
        if type(epoch) is not int or epoch < 1:
            raise ValueError("LEASE_EPOCH_REQUIRED")
        return self.store.complete_ir(
            task_id, RemoteRuntimeResult.from_dict(raw_result),
            lease_epoch=epoch, enqueue_continuation=enqueue,
        )

    def get_task(self, task_id: str) -> dict[str, Any]:
        return {"task": self.store.get_task(task_id)}

    def get_receipt(self, task_id: str) -> dict[str, Any]:
        task = self.store.get_task(task_id)
        status = str(task.get("status") or "")
        persisted = task.get("result") if isinstance(task.get("result"), dict) else {}
        evidence = persisted.get("result") if isinstance(persisted.get("result"), dict) else None
        return {
            "protocol": "agentos.receipt/v0.1",
            "task_id": task_id,
            "terminal": status in {"succeeded", "failed", "cancelled", "expired"},
            "status": status,
            "executor": persisted.get("runtime_id"),
            "evidence": evidence,
            "task": task,
        }

    def project_state(self, project_id: str) -> dict[str, Any]:
        return read_project_state(self.store, project_id)


class DistributedGatewayServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], service: DistributedGatewayService, token: str | None = None) -> None:
        host, _ = server_address
        validate_bind_security(host, token)
        self.service = service
        self.auth_token = token
        self.client_tokens = ClientTokenStore(service.store)
        super().__init__(server_address, DistributedGatewayHandler)


def get_node_map() -> dict[str, Any]:
    from .node_registry import NodeRegistry
    return NodeRegistry().node_map()


def approve_node_join(code: str) -> dict[str, Any]:
    from .realm_fabric import RealmFabricStore
    return RealmFabricStore().approve_join(code)


class DistributedGatewayHandler(BaseHTTPRequestHandler):
    server: DistributedGatewayServer

    def _html(self, status: int, html_str: str) -> None:
        data = html_str.encode("utf-8")
        self.send_response(status)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _bearer(self) -> str | None:
        header = self.headers.get("Authorization", "")
        return header[7:] if header.startswith("Bearer ") else None

    def _is_root(self) -> bool:
        expected = self.server.auth_token
        if not expected:
            return True
        supplied = self._bearer()
        return supplied is not None and hmac.compare_digest(supplied, expected)

    def _principal(self) -> ClientPrincipal | None:
        if self._is_root():
            return None
        supplied = self._bearer()
        return self.server.client_tokens.principal(supplied or "")

    def _require(
        self,
        permission: str,
        *,
        project_id: str | None = None,
        capability: str | None = None,
    ) -> bool:
        if self._is_root():
            return True
        principal = self._principal()
        allowed = principal is not None and principal.allows_permission(permission)
        if allowed and project_id is not None:
            allowed = principal.allows_project(project_id)
        if allowed and capability is not None:
            allowed = principal.allows_capability(capability)
        if allowed:
            return True
        payload: dict[str, Any] = {"error": "forbidden", "required_permission": permission}
        if project_id is not None:
            payload["project_id"] = project_id
        if capability is not None:
            payload["capability"] = capability
        self._json(403 if self._bearer() else 401, payload)
        return False

    def _require_root(self) -> bool:
        if self._is_root():
            return True
        self._json(403 if self._bearer() else 401, {"error": "root_credential_required"})
        return False

    def _read_body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValueError("Content-Length is required")
        length = int(raw_length)
        if length < 0 or length > MAX_REQUEST_BYTES:
            raise ValueError("request body too large")
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(body, dict):
            raise ValueError("JSON root must be an object")
        return body

    def _route(self) -> tuple[str, list[str]]:
        path = urlparse(self.path).path
        return path, [part for part in path.split("/") if part]

    def _shared_auth(self, method: str) -> bool:
        path, _ = self._route()
        if not is_shared_auth_path(path):
            return False
        try:
            status, headers, body = proxy_shared_auth_request(
                raw_path=self.path, method=method,
                host=self.headers.get("Host", ""),
                cookie=self.headers.get("Cookie"),
            )
        except (OSError, ValueError, TimeoutError):
            self._json(503, {"error": "shared_auth_service_unavailable"})
            return True
        self.send_response(status)
        self.send_header("Cache-Control", "no-store")
        for key, value in headers:
            if key.lower() != "cache-control":
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if method != "HEAD":
            self.wfile.write(body)
        return True

    def do_HEAD(self) -> None:
        if self._shared_auth('HEAD'): return
        path, parts = self._route()
        if path in ("", "/"):
            data = render_public_entry_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Robots-Tag", "noindex, nofollow")
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            return
        if path in ("/welcome", "/welcome/"):
            data = render_welcome_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Robots-Tag", "noindex, nofollow")
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            return
        if path in ("/companion", "/companion/"):
            data = render_companion_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Robots-Tag", "noindex, nofollow")
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            return
        self.send_response(405)
        self.end_headers()

    def do_GET(self) -> None:
        if self._shared_auth('GET'): return
        path, parts = self._route()
        if path in ("", "/"):
            self._html(200, render_public_entry_html())
            return
        if path in ("/welcome", "/welcome/"):
            self._html(200, render_welcome_html())
            return
        if len(parts) == 4 and parts[:2] == ["v1", "realms"] and parts[3] in {"health", "bootstrap", "tasks"}:
            query = parse_qs(urlparse(self.path).query)
            node_id = str((query.get("node_id") or [""])[0])
            bearer = str(self.headers.get("Authorization") or "")
            token = bearer[7:] if bearer.startswith("Bearer ") else ""
            code, result = tenant_node_runtime(
                host=self.headers.get("Host", ""), realm_id=parts[2],
                action=parts[3], method="GET", node_id=node_id, token=token,
            )
            self._json(code, result)
            return
        if path == "/v1/account/virtual-one/nodes":
            code, payload = owner_node_map(
                host=self.headers.get("Host", ""), cookie=self.headers.get("Cookie")
            )
            self._json(code, payload)
            return
        if path == "/v1/account/virtual-one":
            code, result = account_virtual_one(
                host=self.headers.get("Host", ""), cookie=self.headers.get("Cookie")
            )
            self._json(code, result)
            return
        if path in ("/my-one", "/my-one/"):
            code, result = account_virtual_one(
                host=self.headers.get("Host", ""), cookie=self.headers.get("Cookie")
            )
            if code != 200:
                # Distinguish anonymous 401, non-member 403 and invalid
                # virtual-host 400. No Realm data is leaked on denial.
                self._json(code, {"ok": False, "error": result.get("error", "realm_membership_required")})
                return
            self._html(200, render_my_one_html())
            return
        if path == "/v1/account/realm-request":
            try:
                code, result = account_request(method="GET", host=self.headers.get("Host", ""),
                                               cookie=self.headers.get("Cookie"), origin=None)
                self._json(code, result)
            except (OSError, ValueError):
                self._json(503, {"ok": False, "error": "registration_unavailable"})
            return
        if path in ("/platform", "/platform/"):
            try:
                code, result = platform_review(
                    method="GET", host=self.headers.get("Host", ""),
                    cookie=self.headers.get("Cookie"), origin=None
                )
                if code in (401, 403):
                    # Render an actionable denial screen without revealing
                    # any protected queue contents. The API remains JSON/deny.
                    self._html(code, render_platform_auth_gate_html(authenticated=code == 403))
                    return
                if code != 200:
                    self._json(code, {"ok": False, "error": result.get("error", "review_unavailable")})
                    return
                self._html(200, render_platform_review_html())
            except (OSError, ValueError):
                self._json(503, {"ok": False, "error": "review_unavailable"})
            return
        if path == "/v1/platform/realm-requests":
            try:
                code, payload = platform_review(
                    method="GET", host=self.headers.get("Host", ""),
                    cookie=self.headers.get("Cookie"), origin=None
                )
                self._json(code, payload)
            except (OSError, ValueError):
                self._json(503, {"ok": False, "error": "review_unavailable"})
            return
        if path in ("/companion", "/companion/"):
            self._html(200, render_companion_html())
            return
        if path == "/v1/approvals" or parts == ["v1", "approvals"]:
            if not self._require_root(): return
            self._json(200, list_approvals())
            return
        if path == "/v1/nodes" or parts == ["v1", "nodes"]:
            if not self._require_root(): return
            self._json(200, get_node_map())
            return
        if path == "/health":
            self._json(200, {"status": "ok", "service": "distributed-agentos-control-plane", "protocol": CORE_PROTOCOL})
            return
        try:
            if len(parts) == 3 and parts[:2] == ["v1", "tasks"]:
                response = self.server.service.get_task(parts[2])
                project_id = str(response["task"].get("projectId") or "")
                if not self._require("task.read", project_id=project_id): return
                self._json(200, response); return
            if len(parts) == 3 and parts[:2] == ["v1", "receipts"]:
                response = self.server.service.get_receipt(parts[2])
                project_id = str(response["task"].get("projectId") or "")
                if not self._require("task.read", project_id=project_id): return
                self._json(200, response); return
            if len(parts) == 4 and parts[:2] == ["v1", "projects"] and parts[3] == "state":
                project_id = unquote(parts[2])
                if not self._require("project.read", project_id=project_id): return
                self._json(200, self.server.service.project_state(project_id)); return
            self._json(404, {"error": "not_found"})
        except KeyError as exc:
            self._json(404, {"error": "not_found", "message": str(exc)})
        except ValueError as exc:
            self._json(400, {"error": "invalid_request", "message": str(exc)})

    def do_POST(self) -> None:
        path, parts = self._route()
        try:
            body = self._read_body()
            if len(parts) == 4 and parts[:2] == ["v1", "realms"] and parts[3] in {"heartbeat", "benchmark", "receipts"}:
                bearer = str(self.headers.get("Authorization") or "")
                token = bearer[7:] if bearer.startswith("Bearer ") else ""
                code, result = tenant_node_runtime(
                    host=self.headers.get("Host", ""), realm_id=parts[2],
                    action=parts[3], method="POST", node_id=str(body.get("node_id") or ""),
                    token=token, body=body,
                )
                self._json(code, result)
                return
            if path == "/v1/account/virtual-one/join/approve":
                code, result = owner_approve_code(
                    host=self.headers.get("Host", ""), cookie=self.headers.get("Cookie"),
                    origin=self.headers.get("Origin"), code=str(body.get("code") or "")
                )
                self._json(code, result)
                return
            if len(parts) == 5 and parts[0:2] == ["v1", "realms"] and parts[3] == "join":
                # Device flow never receives an operator bearer or realm map.
                # Realm-specific request IDs and high-entropy claim secrets
                # are verified exclusively inside the selected tenant store.
                code, result = device_join(
                    host=self.headers.get("Host", ""), realm_id=parts[2],
                    action=parts[4], body=body
                )
                self._json(code, result)
                return
            if path == "/v1/platform/realm-requests":
                code, result = platform_review(
                    method="POST", host=self.headers.get("Host", ""),
                    cookie=self.headers.get("Cookie"),
                    origin=self.headers.get("Origin"), body=body,
                )
                self._json(code, result)
                return
            if path == "/v1/account/realm-request":
                code, result = account_request(
                    method="POST", host=self.headers.get("Host", ""),
                    cookie=self.headers.get("Cookie"),
                    origin=self.headers.get("Origin"), body=body,
                )
                self._json(code, result)
                return
            if parts[:2] in (["v1", "nodes"], ["v1", "approvals"]) and not self._require_root():
                return
            if path in ("/v1/nodes/approve",) or (len(parts) == 3 and parts[:2] == ["v1", "nodes"] and parts[2] == "approve"):
                code = str(body.get("code") or "").strip().upper()
                if not code:
                    self._json(400, {"success": False, "error": "code is required"})
                    return
                try:
                    res = approve_node_join(code)
                    self._json(200, {"success": True, **res})
                except Exception as exc:
                    self._json(400, {"success": False, "error": str(exc)})
                return
            if path in ("/v1/approvals/decide",) or (len(parts) == 3 and parts[:2] == ["v1", "approvals"] and parts[2] == "decide"):
                approval_id = str(body.get("id") or "")
                decision = str(body.get("decision") or "")
                approver = str(body.get("approver") or "mobile-operator")
                reason = str(body.get("reason") or "")
                res = resolve_approval(approval_id, decision, approver=approver, reason=reason)
                self._json(200 if res.get("success") else 400, res)
                return
            if path in ("/v1/approvals/park",) or (len(parts) == 3 and parts[:2] == ["v1", "approvals"] and parts[2] == "park"):
                entry = park_approval(
                    approval_id=str(body.get("id") or ""),
                    project_id=str(body.get("project_id") or "agentmanager"),
                    actor=str(body.get("actor") or "agent"),
                    title=str(body.get("title") or ""),
                    action_type=str(body.get("action_type") or "general"),
                    payload=body.get("payload") or {},
                    next_unblocked_task=str(body.get("next_unblocked_task") or ""),
                )
                self._json(201, entry)
                return
            if path == "/v1/attach":
                project_id = str(body.get("project_id") or "")
                if not self._require("project.read", project_id=project_id): return
                self._json(200, self.server.service.attach(body)); return
            if path == "/v1/projects/resolve-active":
                if not self._require("project.read"): return
                self._json(200, self.server.service.resolve_active_project(body, principal=self._principal())); return
            if path == "/v1/tasks":
                project_id = str(body.get("project_id") or "")
                capability = str(body.get("capability") or "")
                if not self._require("task.submit", project_id=project_id, capability=capability): return
                self._json(202, self.server.service.submit_task(body)); return
            if path == "/v1/ir/submit":
                if not self._require_root(): return
                self._json(200, self.server.service.submit(body)); return
            if path == "/v1/lease":
                if not self._require_root(): return
                self._json(200, self.server.service.lease(body)); return
            if len(parts) == 4 and parts[:2] == ["v1", "tasks"] and parts[3] == "lease":
                if not self._require_root(): return
                self._json(200, self.server.service.lease_task(parts[2], body)); return
            if len(parts) == 4 and parts[:2] == ["v1", "tasks"] and parts[3] == "complete":
                if not self._require_root(): return
                self._json(200, self.server.service.complete(parts[2], body)); return
            self._json(404, {"error": "not_found"})
        except KeyError as exc:
            self._json(404, {"error": "not_found", "message": str(exc)})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json(400, {"error": "invalid_request", "message": str(exc)})

    def log_message(self, format: str, *args: Any) -> None:
        return
