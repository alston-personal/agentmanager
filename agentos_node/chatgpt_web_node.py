"""Bootstrap/resume contract for ChatGPT Web as an AgentOS web node.

This module deliberately stays transport-neutral. It does not automate the
ChatGPT UI and it never stores browser credentials. Its only job is to attach
to the authoritative Control Plane, restore canonical project state, and
compile that state into the immutable WebAgentAdapter request consumed by a
browser-side bridge.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from runtime_core.canonical_ir import CanonicalIR

from .control_plane_client import ControlPlaneClient
from .web_agent_adapter import WebAgentAdapter


BOOTSTRAP_PROTOCOL = "agentos.chatgpt-web-bootstrap/v1"
DEFAULT_RUNTIME_ID = "chatgpt-web"


@dataclass(frozen=True)
class ChatGPTWebBootstrap:
    protocol: str
    runtime_id: str
    project_id: str
    session_id: str | None
    recommended_action: str
    current_source: str | None
    latest_task_id: str | None
    current_ir_id: str | None
    current_ir_digest: str | None
    execution_context: dict[str, Any]
    request: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_bootstrap_from_attachment(
    attachment: dict[str, Any],
    *,
    runtime_id: str = DEFAULT_RUNTIME_ID,
) -> ChatGPTWebBootstrap:
    """Compile a `/v1/attach` response into a deterministic resume packet."""

    project_id = str(attachment.get("project_id") or "").strip()
    if not project_id:
        raise ValueError("attachment is missing project_id")

    state = attachment.get("state")
    if not isinstance(state, dict):
        raise ValueError("attachment state must be an object")
    if str(state.get("projectId") or "").strip() != project_id:
        raise ValueError("attachment state projectId mismatch")

    execution_context = attachment.get("execution_context") or {}
    if not isinstance(execution_context, dict):
        raise ValueError("attachment execution_context must be an object")

    action = str(state.get("recommendedAction") or "start")
    source = state.get("currentSource")
    latest_task = state.get("latestTask")
    latest_task_id = None
    if isinstance(latest_task, dict) and latest_task.get("taskId") is not None:
        latest_task_id = str(latest_task["taskId"])

    raw_ir = state.get("currentIR")
    if raw_ir is None:
        return ChatGPTWebBootstrap(
            protocol=BOOTSTRAP_PROTOCOL,
            runtime_id=runtime_id,
            project_id=project_id,
            session_id=str(attachment.get("session_id")) if attachment.get("session_id") else None,
            recommended_action=action,
            current_source=source if isinstance(source, str) else None,
            latest_task_id=latest_task_id,
            current_ir_id=None,
            current_ir_digest=None,
            execution_context=execution_context,
            request=None,
        )
    if not isinstance(raw_ir, dict):
        raise ValueError("attachment currentIR must be an object or null")

    ir = CanonicalIR.from_dict(raw_ir)
    if ir.project_id != project_id:
        raise ValueError("attachment currentIR project_id mismatch")

    request = WebAgentAdapter(runtime_id).build_request(ir)
    return ChatGPTWebBootstrap(
        protocol=BOOTSTRAP_PROTOCOL,
        runtime_id=runtime_id,
        project_id=project_id,
        session_id=str(attachment.get("session_id")) if attachment.get("session_id") else None,
        recommended_action=action,
        current_source=source if isinstance(source, str) else None,
        latest_task_id=latest_task_id,
        current_ir_id=ir.ir_id,
        current_ir_digest=ir.digest(),
        execution_context=execution_context,
        request=request,
    )


def bootstrap_chatgpt_web(
    client: ControlPlaneClient,
    project_id: str,
    *,
    runtime_id: str = DEFAULT_RUNTIME_ID,
) -> ChatGPTWebBootstrap:
    """Attach ChatGPT Web to one AgentOS project and restore its current state."""

    project_id = str(project_id or "").strip()
    if not project_id:
        raise ValueError("project_id is required")
    attachment = client.attach(
        project_id,
        agent={"runtime_id": runtime_id, "kind": "chatgpt_web", "transport": "browser"},
    )
    return build_bootstrap_from_attachment(attachment, runtime_id=runtime_id)
