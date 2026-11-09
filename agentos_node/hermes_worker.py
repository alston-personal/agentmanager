"""One-shot governed Hermes worker using the existing Employee Worker Host.

Consumes only an exact Node-acknowledged ONE wake with a matching S4 delivery
record, then executes a fixed read-only GitHub metadata scan. Never spins,
bootstraps employees, selects credentials, installs tools or grants authority.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from agent_core.core_supervisor import RECONCILE_INTENT_SCHEMA
from agent_core.core_supervisor_service import INTENT_RECORD_SCHEMA
from agent_core.core_supervisor_delivery import DELIVERY_STATE_SCHEMA
from agent_core.core_work_items import WorkItemStore
from agent_core.employee_lifecycle import EmployeeLifecycle
from agent_core.employee_presence import WAKE_CAPABILITY
from agent_core.employee_runtime import EmployeeRuntime
from agent_core.employee_skills import EmployeeSkillRegistry, EmployeeSkillService
from agent_core.employee_wake import EmployeeWakePlanner
from agent_core.hermes_github_scan import run_scan, github_repo_get, lifecycle_scan_summary, DEFAULT_REPOS, atomic_json_write
from agent_core.hermes_scan_policy import ScanSignals, propose_scan
from agent_core.role_runtime import RoleRegistry
from agentos_node.employee_wake_inbox import WAKE_RECEIPT_SCHEMA, ALLOWED_INTENT_KEYS, ROUTE_KEYS, WAKE_ROUTE_SCHEMA
from agent_core.spec_steward_acceptance import EXPECTED_AUTHORITY_POLICY, EXPECTED_TRANSPORT

EMPLOYEE = "hermes-technology-scout"
ROLE = "research.hermes"
SKILL = "github.technology.scan"
SCHEMA = "agentos.hermes-worker-cli-result/v1"
SOURCE_ROOT = Path(__file__).resolve().parent.parent


def _read_json(path: Path) -> dict:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj,dict):
        raise ValueError("invalid_hermes_evidence")
    return obj


def _is_hermes_assignment(assignment_id: str) -> bool:
    root = "hermes-2120-discovery-v1"
    if assignment_id == root:
        return True
    prefix = root+"-cycle-"
    return assignment_id.startswith(prefix) and len(assignment_id) == len(prefix)+6 and assignment_id[len(prefix):].isdigit()


def _verify_delivery(runtime_root: Path, capsule: dict, intent: dict) -> None:
    """Exact match against canonical S4 delivery and immutable Supervisor intent."""
    matches = 0
    for path in sorted((runtime_root/"supervisor"/"deliveries").glob("reconcile_*.json")):
        try:
            delivery = _read_json(path)
            if (delivery.get("schema") != DELIVERY_STATE_SCHEMA
                or delivery.get("status") != "awaiting_claim"
                or delivery.get("employee_id") != EMPLOYEE
                or delivery.get("assignment_id") != capsule["assignment_id"]
                or delivery.get("wake_id") != capsule["wake_id"]
                or delivery.get("node_id") != capsule["node_id"]
                or delivery.get("presence_id") != capsule["presence_id"]
                or delivery.get("presence_generation") != capsule["presence_generation"]
                or delivery.get("transport") != EXPECTED_TRANSPORT
                or delivery.get("authority_policy_id") != EXPECTED_AUTHORITY_POLICY
                or delivery.get("capability") != WAKE_CAPABILITY
                or delivery.get("dispatch_performed") is not True):
                continue
            reconcile_id = delivery.get("reconcile_id")
            if not isinstance(reconcile_id,str) or path.stem != reconcile_id:
                continue
            if not delivery.get("task_id") or not delivery.get("wake_attempt_id"):
                continue
            record = _read_json(runtime_root/"supervisor"/"intents"/(reconcile_id+".json"))
            ri = record.get("intent")
            if (record.get("schema") != INTENT_RECORD_SCHEMA
                or record.get("reconcile_id") != reconcile_id
                or record.get("state") != "planned"
                or record.get("dispatch_performed") is not False
                or not isinstance(ri,dict)
                or ri.get("schema") != RECONCILE_INTENT_SCHEMA
                or ri.get("kind") != "employee_wake"
                or ri.get("employee_id") != EMPLOYEE
                or ri.get("assignment_id") != capsule["assignment_id"]
                or ri.get("authority_boundary") != "observe_and_select_only"
                or ri.get("credential_exposed") is not False
                or any(ri.get(k) != "unbound" for k in ("node_selection","executor_selection","transport_selection","capability_authority"))
                or ri.get("wake_intent") != intent):
                continue
            matches += 1
        except (OSError,ValueError,KeyError,TypeError):
            continue
    if matches != 1:
        raise PermissionError("hermes_governed_delivery_missing_or_ambiguous")


def process_exact(*, runtime_root: Path, wake_root: Path, worker_state_root: Path,
                  node_id: str, wake_id: str, presence_generation: int,
                  fetch=None) -> dict:
    """Act only on one specifically addressed, source-controlled, bounded task."""
    runtime_root, wake_root, worker_state_root = (
        runtime_root.resolve(),wake_root.resolve(),worker_state_root.resolve()
    )
    if not all(p.is_absolute() for p in (runtime_root,wake_root,worker_state_root)):
        raise ValueError("absolute_roots_required")
    if (runtime_root == worker_state_root or runtime_root == wake_root
        or wake_root == worker_state_root
        or runtime_root in worker_state_root.parents or runtime_root in wake_root.parents):
        raise ValueError("runtime_root_must_be_distinct")
    if not wake_id or presence_generation < 1 or "/" in wake_id or "\\" in wake_id:
        raise ValueError("invalid_exact_wake_selector")
    directory = wake_root/EMPLOYEE
    matches=[]
    for path in directory.glob("*.json"):
        try:
            cap=_read_json(path)
        except (OSError,ValueError):
            continue
        if cap.get("wake_id")==wake_id and cap.get("presence_generation")==presence_generation:
            matches.append(cap)
    if len(matches)!=1:
        raise PermissionError("hermes_wake_missing_or_ambiguous")
    capsule=matches[0]
    if capsule.get("schema") != WAKE_RECEIPT_SCHEMA or capsule.get("node_id") != node_id:
        raise PermissionError("hermes_wake_node_mismatch")
    if capsule.get("employee_id")!=EMPLOYEE or not _is_hermes_assignment(str(capsule.get("assignment_id") or "")):
        raise PermissionError("hermes_wake_scope_invalid")
    intent=capsule.get("wake_intent")
    route=capsule.get("employee_wake_route")
    if not isinstance(intent,dict) or set(intent)!=ALLOWED_INTENT_KEYS or not isinstance(route,dict) or set(route)!=ROUTE_KEYS:
        raise ValueError("hermes_capsule_schema_invalid")
    if (intent.get("employee_id")!=EMPLOYEE or intent.get("assignment_id")!=capsule["assignment_id"]
        or intent.get("role_ids")!=[ROLE] or intent.get("skill_ids")!=[SKILL]
        or intent.get("wake_id")!=wake_id
        or intent.get("credential_exposed") is not False
        or intent.get("authority_boundary")!="selection_only_no_execution"
        or intent.get("executor_selection")!="unbound"
        or intent.get("transport_selection")!="unbound"
        or route.get("schema")!=WAKE_ROUTE_SCHEMA
        or route.get("employee_id")!=EMPLOYEE or route.get("node_id")!=node_id
        or route.get("presence_id")!=capsule.get("presence_id")
        or route.get("presence_generation")!=presence_generation):
        raise PermissionError("hermes_wake_intent_invalid")
    raw=json.dumps({"wake_intent":intent,"employee_wake_route":route},sort_keys=True,
                   separators=(",",":"),ensure_ascii=False).encode()
    if capsule.get("digest")!=hashlib.sha256(raw).hexdigest():
        raise PermissionError("hermes_wake_digest_invalid")
    runtime=EmployeeRuntime(runtime_root)
    lifecycle=EmployeeLifecycle(runtime)
    assignment=runtime.get_assignment(capsule["assignment_id"])
    employee=runtime.get_employee(EMPLOYEE)
    if assignment.employee_id!=EMPLOYEE or employee.role_ids!=[ROLE] or employee.skill_ids!=[SKILL]:
        raise PermissionError("hermes_employee_contract_invalid")
    item=WorkItemStore(runtime).get(capsule["assignment_id"])
    if item.employee_id!=EMPLOYEE or SKILL not in item.required_capabilities or "one-governed-dispatch" not in item.authority_requirements:
        raise PermissionError("hermes_work_item_not_authorized")
    skills=EmployeeSkillService(runtime,
        RoleRegistry(SOURCE_ROOT/".agent/roles/registry.yaml"),
        EmployeeSkillRegistry(SOURCE_ROOT/"governance/employee-skills.json"))
    req=skills.build_request(EMPLOYEE,SKILL,"scan",{"assignment_id":assignment.assignment_id})
    if req.get("execution_authority")!="external_governed_dispatcher":
        raise PermissionError("hermes_skill_not_governed")
    current=EmployeeWakePlanner(lifecycle).plan_next(EMPLOYEE)
    if current is None or current.as_dict()!=intent:
        raise PermissionError("hermes_wake_stale")
    _verify_delivery(runtime_root,capsule,intent)
    lease_key=hashlib.sha256((wake_id+":"+str(presence_generation)).encode()).hexdigest()[:24]
    lease_id="hermeslease_"+lease_key
    # Durable pre-execution marker: once started, uncertain crashes are never
    # silently replayed by the host.
    work_dir=worker_state_root/EMPLOYEE
    work_dir.mkdir(parents=True,exist_ok=True)
    state_path=work_dir/(lease_id+".json")
    if state_path.exists():
        raise RuntimeError("hermes_prior_execution_requires_reconciliation")
    atomic_json_write(state_path,{"schema":"agentos.hermes-worker-state/v1","status":"launching",
                                   "assignment_id":assignment.assignment_id,"wake_id":wake_id})
    runtime.bind_executor(EMPLOYEE,provider="agentos-native-github-metadata",model="read-only-v1")
    lease=lifecycle.claim(assignment.assignment_id,EMPLOYEE,lease_id,lease_seconds=300)
    if lease.generation!=intent["expected_lease_generation"]:
        raise RuntimeError("hermes_unexpected_lease_generation")
    actual_fetch=fetch if fetch is not None else lambda repo: github_repo_get(repo,timeout=3)
    repos=list(DEFAULT_REPOS[:5])
    if "ruvnet/RuView" not in repos:
        repos.append("ruvnet/RuView")
    previous=work_dir/"hermes-scan-state.json"
    old={}
    if previous.exists():
        old=_read_json(previous)
        if old.get("schema")!="agentos.hermes-state/v1":
            raise ValueError("hermes_prior_state_invalid")
    report=run_scan(repos,actual_fetch,old_fingerprints=old.get("fingerprints",{}))
    if not report["findings"]:
        raise RuntimeError("hermes_no_github_sources")
    signals=ScanSignals(meaningful_findings=report["changed_count"],
        consecutive_empty_scans=0 if report["changed_count"] else int(old.get("consecutive_empty_scans",0))+1)
    plan=propose_scan(now=datetime.now(timezone.utc),last_scan_at=datetime.now(timezone.utc),signals=signals)
    summary=lifecycle_scan_summary(report,next_interval_hours=plan.interval_hours)
    new_hashes=dict(old.get("fingerprints",{}))
    new_hashes.update({x["repo"].casefold():x["fingerprint"] for x in report["findings"]})
    digest=summary["report_sha256"]
    # Write report and cursor before the canonical checkpoint/terminal receipt.
    atomic_json_write(work_dir/("hermes-scan-"+digest[:16]+".json"),report)
    atomic_json_write(previous,{"schema":"agentos.hermes-state/v1",
        "last_scan_at":report["scan_at"],"fingerprints":new_hashes,
        "consecutive_empty_scans":signals.consecutive_empty_scans,
        "last_meaningful_findings":report["changed_count"]})
    head="hermes:scan:"+digest[:24]
    lifecycle.checkpoint(assignment.assignment_id,lease_id,head)
    lifecycle.finish(assignment.assignment_id,lease_id,state="completed",result_summary=summary)
    atomic_json_write(state_path,{"schema":"agentos.hermes-worker-state/v1",
        "status":"completed","assignment_id":assignment.assignment_id,"wake_id":wake_id,
        "thread_head":head,"report_digest":digest})
    return {"schema":SCHEMA,"status":"completed","work_performed":True,
        "employee_id":EMPLOYEE,"assignment_id":assignment.assignment_id,
        "wake_id":wake_id,"presence_generation":presence_generation,
        "lease_generation":lease.generation,"thread_head":head,
        "error_code":None,"executor_provider":"agentos-native-github-metadata",
        "executor_model":"read-only-v1","credential_exposed":False,
        "session_identity_exposed":False,"verified_marker_emitted":False}
