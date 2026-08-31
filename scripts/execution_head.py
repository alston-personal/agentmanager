#!/usr/bin/env python3
"""Collect and arbitrate per-project execution heads.

Git remote state is evidence, not necessarily the newest project truth. A local
workspace can legitimately be ahead of origin; AgentOS must publish that state
so other nodes can resume from the freshest trustworthy execution head.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

SCHEMA = "agentos.execution-head/v1"
DEFAULT_FRESH_SECONDS = 300


@dataclass
class ExecutionHead:
    schema: str
    project_id: str
    source: str
    node: str
    workspace: str
    branch: str | None
    local_head: str | None
    upstream: str | None
    remote_head: str | None
    ahead: int | None
    behind: int | None
    dirty: bool | None
    version: str | None
    version_source: str | None
    latest_tag: str | None
    observed_at: str
    confidence: float = 1.0
    error: str | None = None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _run_git(workspace: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(workspace), text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout.strip()


def _read_json_version(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    value = data.get("version") if isinstance(data, dict) else None
    return str(value).strip() if value else None


def discover_version(workspace: Path, project_yaml: dict[str, Any] | None = None) -> tuple[str | None, str | None]:
    project_yaml = project_yaml or {}
    configured = project_yaml.get("version_file") or project_yaml.get("version_path")
    candidates: list[Path] = []
    if configured:
        candidates.append(workspace / str(configured))
    candidates.extend([
        workspace / "extension" / "manifest.json",
        workspace / "package.json",
        workspace / "pyproject.toml",
        workspace / ".version",
    ])
    seen: set[Path] = set()
    for path in candidates:
        if path in seen or not path.exists() or not path.is_file():
            continue
        seen.add(path)
        if path.suffix == ".json":
            version = _read_json_version(path)
            if version:
                return version, str(path.relative_to(workspace))
        elif path.name == ".version":
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value, ".version"
        elif path.name == "pyproject.toml":
            in_project = False
            for raw in path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if line.startswith("["):
                    in_project = line == "[project]"
                    continue
                if in_project and line.startswith("version") and "=" in line:
                    value = line.split("=", 1)[1].strip().strip("\"'")
                    if value:
                        return value, "pyproject.toml"
    return None, None


def load_project_yaml(project_dir: Path) -> dict[str, Any]:
    path = project_dir / "project.yaml"
    if not path.exists() or yaml is None:
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def resolve_workspace(project_id: str, project_dir: Path, project_yaml: dict[str, Any]) -> Path | None:
    candidates = [project_yaml.get("actual_code_path"), project_yaml.get("workspace"), project_yaml.get("code_path")]
    for value in candidates:
        if value:
            path = Path(os.path.expandvars(os.path.expanduser(str(value))))
            if path.exists():
                return path.resolve()
    agentmanager_root = Path(os.environ.get("AGENTMANAGER_ROOT", Path(__file__).resolve().parent.parent))
    fallback = agentmanager_root / "workspace" / project_id
    if fallback.exists():
        return fallback.resolve()
    return None


def _node_id() -> str:
    configured = os.environ.get("AGENTOS_NODE_ID")
    if configured:
        return configured
    if hasattr(os, "uname"):
        return os.uname().nodename
    return os.environ.get("COMPUTERNAME", "unknown")


def collect_execution_head(project_id: str, project_dir: Path, *, node: str | None = None) -> ExecutionHead:
    project_yaml = load_project_yaml(project_dir)
    workspace = resolve_workspace(project_id, project_dir, project_yaml)
    now = utc_now().isoformat()
    node = node or _node_id()
    if workspace is None:
        return ExecutionHead(SCHEMA, project_id, "local-git", node, "", None, None, None, None,
                             None, None, None, None, None, None, now, 0.0, "workspace_not_found")
    try:
        local_head = _run_git(workspace, "rev-parse", "HEAD")
        branch = _run_git(workspace, "branch", "--show-current", check=False) or None
        upstream = _run_git(workspace, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", check=False) or None
        remote_head = (_run_git(workspace, "rev-parse", "@{u}", check=False) or None) if upstream else None
        ahead = behind = None
        if upstream:
            counts = _run_git(workspace, "rev-list", "--left-right", "--count", f"{upstream}...HEAD", check=False)
            parts = counts.split()
            if len(parts) == 2 and all(p.isdigit() for p in parts):
                behind, ahead = int(parts[0]), int(parts[1])
        dirty = bool(_run_git(workspace, "status", "--porcelain", check=False))
        latest_tag = _run_git(workspace, "describe", "--tags", "--abbrev=0", check=False) or None
        version, version_source = discover_version(workspace, project_yaml)
        return ExecutionHead(SCHEMA, project_id, "local-git", node, str(workspace), branch, local_head,
                             upstream, remote_head, ahead, behind, dirty, version, version_source,
                             latest_tag, now)
    except Exception as exc:
        return ExecutionHead(SCHEMA, project_id, "local-git", node, str(workspace), None, None, None, None,
                             None, None, None, None, None, None, now, 0.2, str(exc))


def _parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return datetime.fromtimestamp(0, tz=timezone.utc)


def arbitrate_heads(heads: Iterable[dict[str, Any]], *, now: datetime | None = None,
                    fresh_seconds: int = DEFAULT_FRESH_SECONDS) -> dict[str, Any]:
    """Prefer fresh valid execution evidence and expose disagreements.

    Evidence with a collection error is retained for diagnostics but is never
    allowed to outrank valid project state merely because it was observed more
    recently.
    """
    now = now or utc_now()
    source_rank = {"local-git": 300, "execution-receipt": 290, "remote-git": 200, "release": 150, "status-md": 100}
    normalized = [dict(h) for h in heads if isinstance(h, dict)]
    if not normalized:
        return {"winner": None, "fresh": False, "conflicts": [], "invalid_evidence": [], "reason": "no_evidence"}

    valid: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for h in normalized:
        ts = _parse_time(h.get("observed_at") or h.get("timestamp") or h.get("updated_at"))
        age = max(0.0, (now - ts).total_seconds())
        h["age_seconds"] = age
        h["fresh"] = age <= fresh_seconds
        h["source_rank"] = source_rank.get(str(h.get("source")), 0)
        h["confidence"] = float(h.get("confidence", 1.0) or 0.0)
        if h.get("error"):
            h["source_rank"] = -1
            invalid.append(h)
        else:
            valid.append(h)

    pool_base = valid or normalized
    fresh = [h for h in pool_base if h.get("fresh") and not h.get("error")]
    pool = fresh or pool_base
    winner = max(
        pool,
        key=lambda h: (
            h.get("source_rank", -1),
            h.get("confidence", 0.0),
            _parse_time(h.get("observed_at") or h.get("timestamp") or h.get("updated_at")),
        ),
    )

    conflicts = []
    winner_head = winner.get("local_head") or winner.get("remote_head")
    winner_version = winner.get("version")
    for h in valid:
        if h is winner:
            continue
        other_head = h.get("local_head") or h.get("remote_head")
        if ((winner_head and other_head and winner_head != other_head) or
                (winner_version and h.get("version") and winner_version != h.get("version"))):
            conflicts.append({"source": h.get("source"), "node": h.get("node"), "head": other_head,
                              "version": h.get("version"), "fresh": h.get("fresh"),
                              "age_seconds": h.get("age_seconds")})

    return {
        "winner": winner,
        "fresh": bool(winner.get("fresh")),
        "conflicts": conflicts,
        "invalid_evidence": invalid,
        "reason": "fresh_trust_rank" if fresh else ("all_valid_evidence_stale" if valid else "no_valid_evidence"),
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Collect AgentOS project execution head")
    p.add_argument("project_dir")
    p.add_argument("--project-id")
    p.add_argument("--node")
    p.add_argument("--out")
    args = p.parse_args()
    project_dir = Path(args.project_dir).resolve()
    project_id = args.project_id or project_dir.name
    payload = asdict(collect_execution_head(project_id, project_dir, node=args.node))
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if not payload.get("error") else 2


if __name__ == "__main__":
    raise SystemExit(main())
