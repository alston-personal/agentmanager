"""Bootstrap/resume contract for ChatGPT Web as an AgentOS web node.

This module deliberately stays transport-neutral.  It does not automate the
ChatGPT UI and it never stores browser credentials.  Its only job is to restore
the authoritative project state from the Control Plane and compile that state
into the immutable WebAgentAdapter request consumed by a browser-side bridge.
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
    recommended_action: str
    current_source: str | None
    latest_task_id: str | None
    current_ir_id: str | None
    current_ir_digest: str | None
    request: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_bootstrap_from_project_state(
    state: dict[str, Any],
    *,
    runtime_id: str = DEFAULT_RUNTIME_ID,
) -> ChatGPTWebBootstrap:
    """Compile a Control Plane project-state response into a web-node resume packet.

    The Control Plane remains authoritative.  Browser/model code receives only
    an immutable Canonical IR request and cannot manufacture project lineage.
    """

    project_id = str(state.get("projectId") or "").strip()
    if not project_id:
        raise ValueError("project state is missing projectId")

    action = str(state.get("recommendedAction") or "start")
    source = state.get("currentSource")
    latest_task = state.get("latestTask")
    latest_task_id = None
    if isinstance(latest_task, dict):
        raw_task_id = latest_task.get("taskId")
        if raw_task_id is not None:
            latest_task_id = str(raw_task_id)

    raw_ir = state.get("currentIR")
    if raw_ir is None:
        return ChatGPTWebBootstrap(
            protocol=BOOTSTRAP_PROTOCOL,
            runtime_id=runtime_id,
            project_id=project_id,
            recommended_action=action,
            current_source=source if isinstance(source, str) else None,
            latest_task_id=latest_task_id,
            current_ir_id=None,
            current_ir_digest=None,
            request=None,
        )
    if not isinstance(raw_ir, dict):
        raise ValueError("project state currentIR must be an object or null")

    ir = CanonicalIR.from_dict(raw_ir)
    if ir.project_id != project_id:
        raise ValueError("project state currentIR project_id mismatch")

    adapter = WebAgentAdapter(runtime_id)
    request = adapter.build_request(ir)
    return ChatGPTWebBootstrap(
        protocol=BOOTSTRAP_PROTOCOL,
        runtime_id=runtime_id,
        project_id=project_id,
        recommended_action=action,
        current_source=source if isinstance(source, str) else None,
        latest_task_id=latest_task_id,
        current_ir_id=ir.ir_id,
        current_ir_digest=ir.digest(),
        request=request,
    )


def bootstrap_chatgpt_web(
    client: ControlPlaneClient,
    project_id: str,
    *,
    runtime_id: str = DEFAULT_RUNTIME_ID,
) -> ChatGPTWebBootstrap:
    """Restore one project's current canonical state for a ChatGPT Web node."""

    project_id = str(project_id or "").strip()
    if not project_id:
        raise ValueError("project_id is required")
    state = client.get_project_state(project_id)
    return build_bootstrap_from_project_state(state, runtime_id=runtime_id)
