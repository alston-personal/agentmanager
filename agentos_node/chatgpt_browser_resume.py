"""Resume an AgentOS project through the existing external browser bridge.

This module keeps the AgentOS/browser boundary narrow:
- AgentOS owns canonical state and context compilation.
- `ai-browser-bridge` owns ChatGPT browser/session automation.
- ChatGPT receives a compiled continuation prompt and returns untrusted semantic output.

No browser DOM selectors, cookies, login state, or profile management live here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any

from .ai_browser_bridge import AiBrowserBridgeClient, BrowserBridgeReply
from .chatgpt_web_node import ChatGPTWebBootstrap, bootstrap_chatgpt_web
from .control_plane_client import ControlPlaneClient


RESUME_PROMPT_PROTOCOL = "agentos.chatgpt-browser-resume/v1"


@dataclass(frozen=True)
class ChatGPTBrowserResumeResult:
    protocol: str
    project_id: str
    runtime_id: str
    session_id: str | None
    current_ir_id: str | None
    current_ir_digest: str | None
    bridge_reply: BrowserBridgeReply

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        return value


def compile_resume_prompt(packet: ChatGPTWebBootstrap, *, user_intent: str = "continue") -> str:
    """Compile a deterministic continuation prompt from an AgentOS bootstrap packet."""

    payload = {
        "protocol": RESUME_PROMPT_PROTOCOL,
        "instruction": (
            "Continue the existing implementation from the authoritative AgentOS state below. "
            "Do not redesign the project from scratch. Treat AgentOS canonical state and compiled "
            "execution context as authoritative over conversational memory. If the state is insufficient, "
            "state exactly what is missing instead of inventing prior work."
        ),
        "user_intent": str(user_intent or "continue").strip() or "continue",
        "project_id": packet.project_id,
        "session_id": packet.session_id,
        "recommended_action": packet.recommended_action,
        "current_source": packet.current_source,
        "latest_task_id": packet.latest_task_id,
        "current_ir_id": packet.current_ir_id,
        "current_ir_digest": packet.current_ir_digest,
        "execution_context": packet.execution_context,
        "web_agent_request": packet.request,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def resume_via_browser(
    control_plane: ControlPlaneClient,
    bridge: AiBrowserBridgeClient,
    project_id: str,
    *,
    runtime_id: str = "chatgpt-web",
    user_intent: str = "continue",
    timeout_seconds: float = 180.0,
) -> ChatGPTBrowserResumeResult:
    """Attach to AgentOS, compile the resume prompt, and send it to ChatGPT via bridge."""

    packet = bootstrap_chatgpt_web(control_plane, project_id, runtime_id=runtime_id)
    prompt = compile_resume_prompt(packet, user_intent=user_intent)
    replies = bridge.ask(prompt, providers=("chatgpt",), timeout_seconds=timeout_seconds)
    if len(replies) != 1:
        raise RuntimeError("expected exactly one ChatGPT bridge reply")
    return ChatGPTBrowserResumeResult(
        protocol=RESUME_PROMPT_PROTOCOL,
        project_id=packet.project_id,
        runtime_id=packet.runtime_id,
        session_id=packet.session_id,
        current_ir_id=packet.current_ir_id,
        current_ir_digest=packet.current_ir_digest,
        bridge_reply=replies[0],
    )
