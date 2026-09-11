from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


ATTESTATION_SCHEMA = "agentos.antigravity-preinvocation-attestation/v1"
INSPECT_SCHEMA = "agentos.antigravity-lifecycle-inspect/v1"
MAX_ATTESTATION_BYTES = 65_536

_SAFE_FIELDS = (
    "recorded_at",
    "runtime_source_commit",
    "hook_schema",
    "outcome",
    "invocation_num",
    "conversation_id_sha256",
    "model_name",
    "executor_class",
    "executor_identity_bound",
    "injection_emitted",
    "source",
    "selection_source",
    "project_id",
    "index_id",
    "ir_id",
    "workspace_path_count",
    "workspace_paths_sha256",
    "credential_exposed",
)


def _candidate_paths() -> tuple[Path, ...]:
    paths: list[Path] = []
    explicit = str(os.environ.get("AGENTOS_PREINVOCATION_AUDIT_PATH") or "").strip()
    if explicit:
        paths.append(Path(explicit).expanduser())

    local_app_data = str(os.environ.get("LOCALAPPDATA") or "").strip()
    if local_app_data:
        paths.append(
            Path(local_app_data)
            / "AgentOS"
            / "state"
            / "mcp"
            / "antigravity-preinvocation-last.json"
        )

    data_root = str(os.environ.get("AGENT_DATA_ROOT") or "").strip()
    if data_root:
        paths.append(Path(data_root) / "runtime" / "antigravity-preinvocation-last.json")

    # Oracle-local default only. Windows clients normally resolve through
    # LOCALAPPDATA above; this fallback keeps the reader aligned with the hook's
    # own non-Windows default without accepting a caller-supplied path.
    if os.name != "nt" and not data_root:
        paths.append(Path("/home/ubuntu/agent-data/runtime/antigravity-preinvocation-last.json"))

    result: list[Path] = []
    for path in paths:
        if path not in result:
            result.append(path)
    return tuple(result)


def _bounded_missing() -> dict[str, Any]:
    return {
        "schema": INSPECT_SCHEMA,
        "present": False,
        "valid": False,
        "credential_exposed": False,
    }


def inspect_antigravity_lifecycle() -> dict[str, Any]:
    """Return a bounded, read-only projection of the managed lifecycle attestation.

    The action deliberately exposes neither a filesystem path nor arbitrary JSON
    fields. It is suitable for an existing read-only Node inspection receipt and
    does not execute the IDE hook or mutate lifecycle state.
    """

    path = next((candidate for candidate in _candidate_paths() if candidate.exists()), None)
    if path is None:
        return _bounded_missing()
    if path.is_symlink():
        return {
            "schema": INSPECT_SCHEMA,
            "present": True,
            "valid": False,
            "classification": "LIFECYCLE_ATTESTATION_SYMLINK_REJECTED",
            "credential_exposed": False,
        }
    try:
        if path.stat().st_size > MAX_ATTESTATION_BYTES:
            raise ValueError("oversized")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return {
            "schema": INSPECT_SCHEMA,
            "present": True,
            "valid": False,
            "classification": "LIFECYCLE_ATTESTATION_INVALID",
            "credential_exposed": False,
        }
    if not isinstance(payload, dict) or payload.get("schema") != ATTESTATION_SCHEMA:
        return {
            "schema": INSPECT_SCHEMA,
            "present": True,
            "valid": False,
            "classification": "LIFECYCLE_ATTESTATION_SCHEMA_INVALID",
            "credential_exposed": False,
        }

    safe = {field: payload.get(field) for field in _SAFE_FIELDS if field in payload}
    safe.update(
        {
            "schema": INSPECT_SCHEMA,
            "attestation_schema": ATTESTATION_SCHEMA,
            "present": True,
            "valid": True,
        }
    )
    # Absence is not evidence of credential isolation. A valid lifecycle record
    # must carry the explicit hook-side boundary marker.
    if payload.get("credential_exposed") is not False:
        safe["valid"] = False
        safe["classification"] = "LIFECYCLE_CREDENTIAL_BOUNDARY_NOT_PROVEN"
    return safe
