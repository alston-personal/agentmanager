from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


SCHEMA = "agentos.runtime-converge-request/v1"
CAPABILITY = "node.runtime.converge"
ALLOWED_NODE_IDS = {"oracle-core-node"}
ALLOWED_REPOSITORY = "alston-personal/agentmanager"
ALLOWED_SOURCE_REFS = {"core/integration"}
REQUEST_FIELDS = {"schema", "request_id", "node_id", "repository", "source_ref", "source_commit"}
FORBIDDEN_KEYS = {
    "argv",
    "command",
    "credentials",
    "environment",
    "executable",
    "module",
    "password",
    "script",
    "shell",
    "token",
}


@dataclass(frozen=True, slots=True)
class RuntimeConvergeRequest:
    request_id: str
    node_id: str
    repository: str
    source_ref: str
    source_commit: str

    def as_payload(self) -> dict[str, str]:
        return {
            "schema": SCHEMA,
            "request_id": self.request_id,
            "node_id": self.node_id,
            "repository": self.repository,
            "source_ref": self.source_ref,
            "source_commit": self.source_commit,
        }


def _safe_id(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 256 or text in {".", ".."} or any(ch in text for ch in "/\\\0"):
        raise ValueError(f"invalid_runtime_converge_{field}")
    return text


def validate_runtime_converge_request(payload: Any) -> RuntimeConvergeRequest:
    if not isinstance(payload, dict):
        raise ValueError("runtime_converge_request_must_be_object")
    keys = set(payload)
    if keys != REQUEST_FIELDS:
        forbidden = sorted(keys & FORBIDDEN_KEYS)
        if forbidden:
            raise ValueError(f"runtime_converge_forbidden_fields:{','.join(forbidden)}")
        raise ValueError("runtime_converge_request_shape_invalid")
    if payload.get("schema") != SCHEMA:
        raise ValueError("runtime_converge_schema_invalid")

    request_id = _safe_id(payload.get("request_id"), "request_id")
    node_id = _safe_id(payload.get("node_id"), "node_id")
    repository = str(payload.get("repository") or "").strip()
    source_ref = str(payload.get("source_ref") or "").strip()
    source_commit = str(payload.get("source_commit") or "").strip()

    if node_id not in ALLOWED_NODE_IDS:
        raise ValueError("runtime_converge_node_not_allowed")
    if repository != ALLOWED_REPOSITORY:
        raise ValueError("runtime_converge_repository_not_allowed")
    if source_ref not in ALLOWED_SOURCE_REFS:
        raise ValueError("runtime_converge_source_ref_not_allowed")
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("runtime_converge_source_commit_invalid")

    return RuntimeConvergeRequest(
        request_id=request_id,
        node_id=node_id,
        repository=repository,
        source_ref=source_ref,
        source_commit=source_commit,
    )
