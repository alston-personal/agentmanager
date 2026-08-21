"""Thin IDE/workspace adapter for Distributed AgentOS.

This module deliberately captures only lightweight workspace metadata by default.
Source contents and git diffs are opt-in so IDE clients do not accidentally push
large or sensitive working trees into Canonical IR.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from typing import Any

from runtime_core.canonical_ir import CanonicalIR


DEFAULT_CAPABILITY = "agent.reason"
PROJECT_MARKER_SCHEMA = "agentos.project/v1"
MAX_CHANGED_FILES = 100
DEFAULT_MAX_DIFF_CHARS = 32_000


def _git(args: list[str], cwd: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def detect_ide() -> str:
    env = os.environ
    if env.get("CURSOR_TRACE_ID") or env.get("CURSOR_SESSION_ID"):
        return "cursor"
    if any(key.startswith("ANTIGRAVITY_") for key in env):
        return "antigravity"
    if env.get("VSCODE_PID") or env.get("TERM_PROGRAM") == "vscode":
        return "vscode"
    if env.get("JETBRAINS_IDE") or env.get("IDEA_INITIAL_DIRECTORY"):
        return "jetbrains"
    return env.get("TERM_PROGRAM") or "terminal"


def resolve_workspace(path: str | Path | None = None) -> Path:
    requested = Path(path or os.getcwd()).expanduser().resolve()
    candidate = requested if requested.is_dir() else requested.parent
    root = _git(["rev-parse", "--show-toplevel"], candidate)
    return Path(root).resolve() if root else candidate


def _read_project_marker(workspace: Path) -> dict[str, Any] | None:
    marker = workspace / ".agentos" / "project.json"
    if not marker.exists():
        return None
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def infer_project_id(workspace: Path, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    env_value = os.environ.get("AGENTOS_PROJECT_ID")
    if env_value:
        return env_value
    payload = _read_project_marker(workspace)
    if isinstance(payload, dict) and isinstance(payload.get("project_id"), str) and payload["project_id"].strip():
        return payload["project_id"].strip()
    return workspace.name


def write_project_marker(
    project_id: str | None = None,
    *,
    workspace: str | Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    root = resolve_workspace(workspace)
    resolved_id = str(project_id or root.name).strip()
    if not resolved_id:
        raise ValueError("project_id is required")
    marker_dir = root / ".agentos"
    marker = marker_dir / "project.json"
    current = _read_project_marker(root)
    if current is not None and not force:
        current_id = str(current.get("project_id") or "").strip()
        if current_id == resolved_id:
            return {"projectId": resolved_id, "path": ".agentos/project.json", "created": False}
        raise ValueError(
            f"project marker already exists for {current_id or 'unknown project'}; use --force to replace it"
        )
    marker_dir.mkdir(parents=True, exist_ok=True)
    payload = {"schema": PROJECT_MARKER_SCHEMA, "project_id": resolved_id}
    marker.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"projectId": resolved_id, "path": ".agentos/project.json", "created": True}


def capture_workspace(
    path: str | Path | None = None,
    *,
    include_diff: bool = False,
    max_diff_chars: int = DEFAULT_MAX_DIFF_CHARS,
) -> dict[str, Any]:
    workspace = resolve_workspace(path)
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], workspace)
    commit = _git(["rev-parse", "HEAD"], workspace)
    status = _git(["status", "--porcelain=v1", "--untracked-files=normal"], workspace) or ""
    changed_files: list[str] = []
    for line in status.splitlines():
        if len(line) < 4:
            continue
        changed_files.append(line[3:].split(" -> ")[-1])
        if len(changed_files) >= MAX_CHANGED_FILES:
            break

    snapshot: dict[str, Any] = {
        "name": workspace.name,
        "ide": detect_ide(),
        "git": {
            "isRepository": commit is not None,
            "branch": branch,
            "commit": commit,
            "dirty": bool(status),
            "changedFiles": changed_files,
            "changedFilesTruncated": len(status.splitlines()) > len(changed_files),
        },
    }
    if include_diff and commit is not None:
        diff = _git(["diff", "--no-ext-diff", "--unified=1"], workspace) or ""
        truncated = len(diff) > max_diff_chars
        snapshot["git"]["diff"] = diff[:max_diff_chars]
        snapshot["git"]["diffTruncated"] = truncated
    return snapshot


def build_ide_ir(
    instruction: str,
    *,
    workspace: str | Path | None = None,
    project_id: str | None = None,
    capability: str = DEFAULT_CAPABILITY,
    provider: str | None = None,
    include_diff: bool = False,
) -> CanonicalIR:
    instruction = str(instruction or "").strip()
    if not instruction:
        raise ValueError("instruction is required")
    root = resolve_workspace(workspace)
    context: dict[str, Any] = {
        "source": {"kind": "ide", "adapter": detect_ide()},
        "workspace": capture_workspace(root, include_diff=include_diff),
    }
    if provider:
        context["provider_policy"] = {"preferred_provider": provider}
    return CanonicalIR(
        goal=instruction,
        project_id=infer_project_id(root, project_id),
        capability=capability,
        payload={"instruction": instruction},
        context=context,
    )


def derive_ide_continuation(
    current: CanonicalIR,
    *,
    instruction: str | None = None,
    workspace: str | Path | None = None,
    capability: str | None = None,
    provider: str | None = None,
    include_diff: bool = False,
) -> CanonicalIR:
    context = dict(current.context)
    context["source"] = {"kind": "ide", "adapter": detect_ide()}
    context["workspace"] = capture_workspace(workspace, include_diff=include_diff)
    provider_policy = dict(context.get("provider_policy") or {})
    if provider:
        provider_policy["preferred_provider"] = provider
    if provider_policy:
        context["provider_policy"] = provider_policy

    chosen_capability = capability
    if not chosen_capability:
        next_capability = current.continuation.get("next_capability") if isinstance(current.continuation, dict) else None
        chosen_capability = str(next_capability or current.capability)
    text = str(instruction or "").strip()
    payload = {"instruction": text} if text else dict(current.payload)
    if not payload:
        payload = {"instruction": "Continue from the current Canonical IR state."}

    return CanonicalIR(
        goal=current.goal,
        project_id=current.project_id,
        capability=chosen_capability,
        payload=payload,
        constraints=list(current.constraints),
        context=context,
        artifacts=list(current.artifacts),
        decisions=list(current.decisions),
        pending_tasks=list(current.pending_tasks),
        continuation={"requested_by": "ide_adapter"},
        parent_ir_id=current.ir_id,
        hop_count=current.hop_count + 1,
    )
