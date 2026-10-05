from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentos_node import bootstrap_control as bc


@dataclass(frozen=True, slots=True)
class RunnerWindowIntent:
    capability: str
    operation: str
    action: str
    allowed_payload_keys: frozenset[str] = frozenset()


INTENTS: tuple[RunnerWindowIntent, ...] = (
    RunnerWindowIntent("agentos.dispatch", "probe", bc.ACTION_RUNNER_WINDOW_PROBE),
    RunnerWindowIntent("agentos.relay", "status", bc.ACTION_RELAY_STATUS),
    RunnerWindowIntent("agentos.scheduler", "status", bc.ACTION_SCHEDULER_STATUS),
    RunnerWindowIntent("agentos.relay", "restart", bc.ACTION_RELAY_RESTART),
    RunnerWindowIntent("agentos.runtime", "repair", bc.ACTION_REPAIR_TRANSPORT),
    RunnerWindowIntent("agentos.executor", "job.submit", bc.ACTION_EXECUTOR_JOB_SUBMIT, frozenset({"job_type"})),
    RunnerWindowIntent("agentos.executor", "job.inspect", bc.ACTION_EXECUTOR_JOB_INSPECT, frozenset({"job_id"})),
    RunnerWindowIntent("node.runtime", "transactional-ota", bc.ACTION_NODE_TRANSACTIONAL_OTA, frozenset({"node_id", "candidate_commit"})),
    RunnerWindowIntent("node.realm", "inspect", bc.ACTION_REALM_NODE_INSPECT, frozenset({"node_id"})),
    RunnerWindowIntent("node.desktop", "probe", bc.ACTION_REALM_DESKTOP_PROBE, frozenset({"node_id"})),
    RunnerWindowIntent("media.google-flow", "generate", bc.ACTION_GOOGLE_FLOW_GENERATE, frozenset({"prompt"})),
    RunnerWindowIntent("media.google-vids", "generate", bc.ACTION_GOOGLE_VIDS_GENERATE, frozenset({"prompt"})),
    RunnerWindowIntent("browser.gui", "smoke", bc.ACTION_SMOKE_GUI_WORKER),
    RunnerWindowIntent("social.runtime", "deploy", bc.ACTION_DEPLOY_SOCIAL_RUNTIME),
    RunnerWindowIntent("content.social", "reconcile", bc.ACTION_RECONCILE_CONTENT_SOCIAL, frozenset({"account_ref"})),
    RunnerWindowIntent("social.publish", "mio.approved", bc.ACTION_PUBLISH_MIO_APPROVED, frozenset({"post_key"})),
    RunnerWindowIntent("threads.dm", "probe", bc.ACTION_PROBE_THREADS_WEB_DM),
    RunnerWindowIntent("threads.dm", "read", bc.ACTION_READ_THREADS_WEB_DM),
    RunnerWindowIntent("threads.dm", "login.probe", bc.ACTION_PROBE_THREADS_WEB_DM_LOGIN),
    RunnerWindowIntent("threads.dm", "login.start", bc.ACTION_START_THREADS_WEB_DM_LOGIN),
    RunnerWindowIntent("chatgpt.web", "probe", bc.ACTION_PROBE_CHATGPT_WEB),
    RunnerWindowIntent("chatgpt.web", "bridge.install", bc.ACTION_INSTALL_CHATGPT_WEB_BRIDGE),
    RunnerWindowIntent("chatgpt.web", "session.accept", bc.ACTION_ACCEPT_CHATGPT_WEB_SESSION),
    RunnerWindowIntent("gemini.web", "probe", bc.ACTION_PROBE_GEMINI_WEB),
    RunnerWindowIntent("gemini.web", "bridge.install", bc.ACTION_INSTALL_GEMINI_WEB_BRIDGE),
    RunnerWindowIntent("gemini.web", "session.accept", bc.ACTION_ACCEPT_GEMINI_WEB_SESSION),
    RunnerWindowIntent("gemini.web", "login.start", bc.ACTION_START_GEMINI_WEB_LOGIN),
    RunnerWindowIntent("gemini.web", "roundtrip.accept", bc.ACTION_ACCEPT_GEMINI_WEB_ROUNDTRIP),
    RunnerWindowIntent("studio.mio", "deploy", bc.ACTION_DEPLOY_STUDIO_WEB_MIO, frozenset({"studio_commit"})),
    RunnerWindowIntent("mio.dm", "decide", bc.ACTION_RUN_MIO_DM_DECISION, frozenset({"source_run_id", "username"})),
    RunnerWindowIntent("persona.runtime", "oursong.activate", bc.ACTION_ACTIVATE_OURSONG_PERSONA),
    RunnerWindowIntent("persona.runtime", "oursong.status", bc.ACTION_PROBE_OURSONG_PERSONA),
    RunnerWindowIntent("persona.runtime", "pdca.origin.probe", bc.ACTION_PROBE_PERSONA_PDCA_RUNTIME),
)

_BY_PUBLIC_KEY = {(item.capability, item.operation): item for item in INTENTS}
_BY_ACTION = {item.action: item for item in INTENTS}


def resolve_intent(
    capability: str,
    operation: str,
    *,
    source_commit: str,
    payload: dict[str, Any] | None = None,
) -> tuple[RunnerWindowIntent, dict[str, Any]]:
    key = (str(capability or "").strip(), str(operation or "").strip())
    intent = _BY_PUBLIC_KEY.get(key)
    if intent is None:
        raise ValueError(f"runner window intent is not registered: capability={key[0]!r} operation={key[1]!r}")
    body = dict(payload or {})
    unknown = set(body) - set(intent.allowed_payload_keys)
    if unknown:
        raise ValueError(f"runner window payload keys not allowed: {sorted(unknown)}")
    params: dict[str, Any] = {"source_commit": source_commit}
    params.update(body)
    return intent, params


def public_intent_for_action(action: str) -> dict[str, str] | None:
    intent = _BY_ACTION.get(str(action or ""))
    if intent is None:
        return None
    return {"capability": intent.capability, "operation": intent.operation}


def catalog() -> list[dict[str, Any]]:
    return [
        {
            "capability": item.capability,
            "operation": item.operation,
            "payload_keys": sorted(item.allowed_payload_keys),
        }
        for item in INTENTS
    ]
