"""Bounded Hermes public GitHub metadata feed via the *existing* ONE Wake Node.

The network-isolated Employee Worker Host never gets outbound access. The
Wake Node, which already has network authority for ONE, fetches a fixed public
allowlist ONLY after a canonical S4 Hermes wake is independently verified.
No new daemon, generic URL input, credentials or arbitrary job execution.
"""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agent_core.employee_runtime import EmployeeRuntime
from agent_core.employee_lifecycle import EmployeeLifecycle
from agent_core.employee_wake import EmployeeWakePlanner
from agent_core.core_work_items import WorkItemStore
from agent_core.hermes_github_scan import (
    DEFAULT_REPOS, github_repo_get, normalized_repo, evaluate, atomic_json_write,
)
from agentos_node.hermes_worker import _is_hermes_assignment, _verify_delivery

SCHEMA = "agentos.hermes-network-snapshot/v1"
EMPLOYEE = "hermes-technology-scout"
ROSTER = tuple(dict.fromkeys((*DEFAULT_REPOS[:5], "ruvnet/RuView")))
MAX_SOURCES = 6
MAX_BODY = 200_000


def snapshot_path(state_root: Path, assignment_id: str, wake_id: str) -> Path:
    if not _is_hermes_assignment(assignment_id):
        raise ValueError("invalid_hermes_assignment")
    if not wake_id or len(wake_id) > 160 or not all(c.isalnum() or c in "_-" for c in wake_id):
        raise ValueError("invalid_hermes_wake_id")
    return state_root / EMPLOYEE / ("metadata-" + assignment_id + "-" + wake_id + ".json")


def _stamp(payload: dict[str, Any]) -> str:
    obj={k:v for k,v in payload.items() if k!="sha256"}
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()


def validate_snapshot(
    snapshot: dict[str, Any], *, assignment_id: str, wake_id: str,
    presence_generation: int,
) -> dict[str, dict]:
    if (snapshot.get("schema")!=SCHEMA or snapshot.get("assignment_id")!=assignment_id
        or snapshot.get("wake_id")!=wake_id
        or snapshot.get("presence_generation")!=presence_generation
        or snapshot.get("sha256")!=_stamp(snapshot)):
        raise PermissionError("hermes_snapshot_identity_or_digest_invalid")
    sources=snapshot.get("sources")
    if not isinstance(sources,dict) or not sources or len(sources)>MAX_SOURCES:
        raise ValueError("hermes_snapshot_sources_invalid")
    allowed={normalized_repo(x).casefold() for x in ROSTER}
    if any(normalized_repo(repo).casefold() not in allowed or not isinstance(meta,dict)
           for repo,meta in sources.items()):
        raise PermissionError("hermes_snapshot_repo_not_allowlisted")
    at=str(snapshot.get("observed_at") or "")
    instant=datetime.fromisoformat(at.replace("Z","+00:00"))
    if instant.tzinfo is None or instant > datetime.now(timezone.utc):
        raise ValueError("hermes_snapshot_timestamp_invalid")
    for repo,meta in sources.items():
        evaluate(repo,meta,now=at)  # identity + non-executable data validation
    return sources


def produce_snapshot(
    *, runtime_root: Path, wake_root: Path, state_root: Path,
    capsule: dict[str, Any], fetch: Callable[[str], dict] | None = None,
) -> dict[str, Any]:
    """One exact governed S4 Hermes wake -> one immutable public metadata snapshot."""
    if (capsule.get("employee_id")!=EMPLOYEE
        or not _is_hermes_assignment(str(capsule.get("assignment_id") or ""))):
        raise PermissionError("hermes_metadata_not_authorized")
    assignment_id=str(capsule["assignment_id"])
    wake_id=str(capsule["wake_id"])
    generation=capsule.get("presence_generation")
    if type(generation) is not int or generation < 1:
        raise PermissionError("hermes_metadata_generation_invalid")
    _verify_delivery(runtime_root,capsule,capsule.get("wake_intent") or {})
    runtime=EmployeeRuntime(runtime_root)
    assignment=runtime.get_assignment(assignment_id)
    employee=runtime.get_employee(EMPLOYEE)
    item=WorkItemStore(runtime).get(assignment_id)
    if (item.employee_id != EMPLOYEE or item.assignment_id != assignment_id
        or item.state != "open" or item.source_kind != "schedule"
        or "github.technology.scan" not in item.required_capabilities
        or "one-governed-dispatch" not in item.authority_requirements
        or "hermes-scheduled-continuation-authorized" not in item.authority_requirements):
        raise PermissionError("hermes_metadata_work_item_not_authorized")
    if (assignment.employee_id != EMPLOYEE
        or employee.role_ids!=["research.hermes"]
        or employee.skill_ids!=["github.technology.scan"]):
        raise PermissionError("hermes_metadata_employee_invalid")
    # Pending first runs and expired-lease resumes are both selected by the
    # canonical read-only planner. An active non-expired lease must NOT trigger
    # a second external metadata fetch or concurrent worker.
    lifecycle = EmployeeLifecycle(runtime)
    planned = EmployeeWakePlanner(lifecycle).plan_next(EMPLOYEE)
    wake_intent = capsule.get("wake_intent")
    if (planned is None or planned.assignment_id != assignment_id
        or not isinstance(wake_intent, dict)
        or planned.as_dict() != wake_intent):
        raise PermissionError("hermes_metadata_wake_not_current")
    if assignment.state == "pending":
        if planned.mode != "fresh" or planned.resume_required:
            raise PermissionError("hermes_metadata_fresh_intent_invalid")
    elif assignment.state == "active":
        prior = lifecycle.get_lease(assignment_id)
        if (prior is None or prior.status != "active"
            or not lifecycle.lease_expired(prior)
            or planned.mode != "resume"
            or not planned.resume_required
            or planned.expected_lease_generation != prior.generation + 1):
            raise PermissionError("hermes_metadata_resume_not_authorized")
    else:
        raise PermissionError("hermes_metadata_assignment_not_runnable")
    dest=snapshot_path(state_root,assignment_id,wake_id)
    if dest.exists():
        existing=json.loads(dest.read_text(encoding="utf-8"))
        validate_snapshot(existing,assignment_id=assignment_id,wake_id=wake_id,
                          presence_generation=generation)
        return {"status":"already_present","assignment_id":assignment_id}
    request=fetch or (lambda repo: github_repo_get(repo,timeout=3))
    sources:dict[str,dict]={}
    errors=[]
    for repo in ROSTER[:MAX_SOURCES]:
        try:
            result=request(repo)
            evaluate(repo,result,now=datetime.now(timezone.utc).isoformat())
            raw=json.dumps(result,ensure_ascii=False)
            if len(raw.encode("utf-8")) > MAX_BODY:
                raise ValueError("oversized_metadata")
            sources[repo]=result
        except (ValueError,RuntimeError,OSError,TypeError):
            errors.append(repo)
    if not sources:
        return {"status":"source_unavailable","assignment_id":assignment_id,"failure_count":len(errors)}
    snapshot={"schema":SCHEMA,"employee_id":EMPLOYEE,
              "assignment_id":assignment_id,"wake_id":wake_id,
              "presence_generation":generation,
              "observed_at":datetime.now(timezone.utc).isoformat(),
              "sources":sources,"failure_count":len(errors)}
    snapshot["sha256"]=_stamp(snapshot)
    # The source of authority is still S4 delivery, not this metadata artifact.
    atomic_json_write(dest,snapshot)
    return {"status":"materialized","assignment_id":assignment_id,
            "source_count":len(sources),"failure_count":len(errors)}


def tick(*, runtime_root: Path, wake_root: Path, state_root: Path,
         fetch: Callable[[str], dict] | None = None) -> dict[str,Any]:
    """Bounded, nonblocking-on-idle hook within existing ONE Wake Node loop."""
    directory=wake_root/EMPLOYEE
    if not directory.is_dir():
        return {"status":"idle"}
    for path in sorted(directory.glob("*.json")):
        try:
            capsule=json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(capsule,dict) or capsule.get("employee_id")!=EMPLOYEE:
                continue
            assignment_id=str(capsule.get("assignment_id") or "")
            wake_id=str(capsule.get("wake_id") or "")
            dest=snapshot_path(state_root,assignment_id,wake_id)
            if dest.exists():
                # Old wakes must not starve later scheduled cycles.
                continue
            result=produce_snapshot(runtime_root=runtime_root,wake_root=wake_root,
                                    state_root=state_root,capsule=capsule,fetch=fetch)
            if result.get("status") in ("materialized","source_unavailable"):
                return result
        except (PermissionError,ValueError,RuntimeError,OSError,KeyError,TypeError):
            continue
    return {"status":"idle"}
