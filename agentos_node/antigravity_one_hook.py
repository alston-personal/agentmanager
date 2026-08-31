from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from agentos_node.one_mcp import OracleLocalGateway

HOOK_SCHEMA = "agentos.antigravity-one-preinvocation/v0.1"


def _workspace_candidates(raw_paths: Any) -> list[tuple[str, str]]:
    if not isinstance(raw_paths, list):
        return []
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw in raw_paths:
        value = str(raw or "").strip()
        if not value:
            continue
        path = Path(value)
        name = path.name.strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append((value, name))
    return out


def _compact_resolution(workspace: str, result: dict[str, Any]) -> dict[str, Any]:
    project = result.get("project") if isinstance(result.get("project"), dict) else {}
    resolution = result.get("project_resolution") if isinstance(result.get("project_resolution"), dict) else {}
    resolved = resolution.get("resolved") if isinstance(resolution.get("resolved"), dict) else {}
    return {
        "workspace": workspace,
        "project_id": project.get("id") or resolved.get("project_id"),
        "project_name": project.get("name"),
        "schema": result.get("schema"),
        "active_goal": result.get("active_goal"),
        "next_action": result.get("next_action"),
        "mutation_allowed": bool(result.get("mutation_allowed")),
        "canonical_repo": resolved.get("repo"),
        "canonical_branch": resolved.get("branch"),
        "canonical_path": resolved.get("canonical_path"),
        "canonical_node": resolved.get("node"),
        "availability": result.get("availability") or {},
        "provenance": result.get("provenance") or {},
    }


def build_injection(payload: dict[str, Any], gateway: OracleLocalGateway | None = None) -> dict[str, Any]:
    # Hydrate only once per fresh conversation. The injected step remains in the
    # trajectory for later turns, avoiding repeated context/token overhead.
    if int(payload.get("invocationNum") or 0) != 0:
        return {}

    workspaces = _workspace_candidates(payload.get("workspacePaths"))
    if not workspaces:
        return {}

    one = gateway or OracleLocalGateway()
    status = one.status()
    resolutions: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for workspace, candidate in workspaces:
        try:
            result = one.resolve(candidate)
        except (KeyError, ValueError):
            # An unrelated workspace is not an AgentOS bootstrap failure.
            continue
        except Exception as exc:  # pragma: no cover - live diagnostics only
            failures.append({"workspace": workspace, "error": f"{type(exc).__name__}: {exc}"})
            continue
        if result.get("schema") != "agentos.resolve/v1":
            failures.append({"workspace": workspace, "error": "unexpected resolve schema"})
            continue
        resolutions.append(_compact_resolution(workspace, result))

    # Global hook is intentionally silent outside AgentOS-governed workspaces.
    if not resolutions and not failures:
        return {}

    envelope = {
        "schema": HOOK_SCHEMA,
        "source": "ONE_PREINVOCATION_HOOK",
        "status_schema": status.get("schema"),
        "connected": bool(status.get("connected")),
        "realm_id": status.get("realm_id"),
        "node_id": status.get("node_id"),
        "surface": "antigravity",
        "executor_class": "antigravity-gemini",
        "model_name": payload.get("modelName"),
        "credential_exposed": False,
        "resolutions": resolutions,
        "failures": failures,
    }
    message = (
        "AgentOS ONE canonical pre-invocation hydration. This state was resolved "
        "before the model was called; do not replace it with Pulse/PM2/local-memory "
        "reconstruction. Newer explicit user intent still wins. If continuing work, "
        "use the resolved active_goal/next_action and authority boundary below. "
        "When reporting bootstrap provenance, state source=ONE_PREINVOCATION_HOOK.\n"
        + json.dumps(envelope, ensure_ascii=False, sort_keys=True)
    )
    return {"injectSteps": [{"ephemeralMessage": message}]}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook input must be a JSON object")
        output = build_injection(payload)
    except Exception as exc:  # Fail open for Antigravity, but inject a bounded diagnostic.
        output = {
            "injectSteps": [
                {
                    "ephemeralMessage": (
                        "ONE_PREHOOK_BLOCKED: AgentOS pre-invocation hydration failed: "
                        f"{type(exc).__name__}: {exc}. Do not claim ONE-connected state "
                        "from local Pulse/PM2/memory scans."
                    )
                }
            ]
        }
    json.dump(output, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
