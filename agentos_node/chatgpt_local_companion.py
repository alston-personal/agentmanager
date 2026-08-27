"""Local fail-closed companion for ChatGPT browser continuation interception.

The companion exposes only a localhost resume endpoint. It authenticates each
request with a transport token, restores authoritative AgentOS state through the
Control Plane, and returns a compiled continuation prompt. It does not store
canonical state and it never automates the ChatGPT DOM.
"""

from __future__ import annotations

import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .chatgpt_browser_resume import compile_resume_prompt
from .chatgpt_web_node import bootstrap_chatgpt_web
from .control_plane_client import ControlPlaneClient


COMPANION_PROTOCOL = "agentos.chatgpt-local-companion/v1"
MAX_REQUEST_BYTES = 64 * 1024
ALLOWED_ORIGINS = {"https://chatgpt.com", "https://chat.openai.com"}


class ChatGPTLocalCompanionService:
    def __init__(self, client: ControlPlaneClient, *, runtime_id: str = "chatgpt-web") -> None:
        self.client = client
        self.runtime_id = runtime_id

    def resume(self, project_id: str, user_intent: str) -> dict[str, Any]:
        project_id = str(project_id or "").strip()
        user_intent = str(user_intent or "continue").strip() or "continue"
        if not project_id:
            raise ValueError("project_id is required")
        packet = bootstrap_chatgpt_web(self.client, project_id, runtime_id=self.runtime_id)
        return {
            "protocol": COMPANION_PROTOCOL,
            "project_id": packet.project_id,
            "session_id": packet.session_id,
            "current_ir_id": packet.current_ir_id,
            "current_ir_digest": packet.current_ir_digest,
            "recommended_action": packet.recommended_action,
            "compiled_prompt": compile_resume_prompt(packet, user_intent=user_intent),
        }


class ChatGPTLocalCompanionServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        service: ChatGPTLocalCompanionService,
        *,
        token: str,
    ) -> None:
        host, _ = server_address
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("local companion must bind to loopback")
        token = str(token or "")
        if len(token) < 24:
            raise ValueError("companion token must be at least 24 characters")
        self.service = service
        self.auth_token = token
        super().__init__(server_address, ChatGPTLocalCompanionHandler)


class ChatGPTLocalCompanionHandler(BaseHTTPRequestHandler):
    server: ChatGPTLocalCompanionServer

    def _origin(self) -> str:
        return str(self.headers.get("Origin") or "")

    def _cors(self) -> None:
        origin = self._origin()
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-AgentOS-Companion-Token")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self._cors()
        self.end_headers()
        self.wfile.write(raw)

    def _authorized(self) -> bool:
        supplied = str(self.headers.get("X-AgentOS-Companion-Token") or "")
        return bool(supplied) and hmac.compare_digest(supplied, self.server.auth_token)

    def do_OPTIONS(self) -> None:
        if self._origin() not in ALLOWED_ORIGINS:
            self._json(403, {"error": "origin_forbidden"})
            return
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self) -> None:
        if self._origin() not in ALLOWED_ORIGINS:
            self._json(403, {"error": "origin_forbidden"})
            return
        if not self._authorized():
            self._json(401, {"error": "unauthorized"})
            return
        if self.path != "/v1/resume":
            self._json(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or "0")
            if length < 1 or length > MAX_REQUEST_BYTES:
                raise ValueError("invalid request size")
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(body, dict):
                raise ValueError("JSON root must be an object")
            response = self.server.service.resume(
                str(body.get("project_id") or ""),
                str(body.get("user_intent") or "continue"),
            )
            self._json(200, response)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json(400, {"error": "invalid_request", "message": str(exc)})

    def log_message(self, format: str, *args: Any) -> None:
        return
