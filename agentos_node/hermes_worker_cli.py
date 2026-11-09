"""Single-shot Hermes adapter CLI for the existing AgentOS Employee Worker Host."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from agentos_node.hermes_worker import process_exact, SCHEMA, EMPLOYEE, _is_hermes_assignment


def absolute(value: str) -> Path:
    path=Path(value).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("absolute_path_required")
    return path.resolve()


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(prog="agentos-hermes-worker")
    parser.add_argument("--runtime-root",type=absolute,required=True)
    parser.add_argument("--wake-root",type=absolute,required=True)
    parser.add_argument("--worker-state-root",type=absolute,required=True)
    parser.add_argument("--node-id",required=True)
    parser.add_argument("--assignment-id",required=True)
    parser.add_argument("--wake-id",required=True)
    parser.add_argument("--presence-generation",type=int,required=True)
    parser.add_argument("--once",action="store_true",required=True)
    args=parser.parse_args(argv)
    if args.presence_generation < 1:
        parser.error("invalid_presence_generation")
    if not _is_hermes_assignment(args.assignment_id):
        parser.error("invalid_hermes_assignment")
    try:
        result=process_exact(runtime_root=args.runtime_root,wake_root=args.wake_root,
             worker_state_root=args.worker_state_root,node_id=args.node_id,
             wake_id=args.wake_id,presence_generation=args.presence_generation,
             assigned_id=args.assignment_id)
    except (OSError,ValueError,RuntimeError,PermissionError) as exc:
        # Only fixed internal error identifiers may cross the Worker Host.
        # Never expose paths, URLs, API data, credentials or exception text.
        internal_codes = {
            "hermes_wake_missing_or_ambiguous", "hermes_wake_node_mismatch",
            "hermes_wake_scope_invalid", "hermes_assigned_work_mismatch",
            "hermes_capsule_schema_invalid", "hermes_wake_intent_invalid",
            "hermes_wake_digest_invalid", "hermes_employee_contract_invalid",
            "hermes_work_item_not_authorized", "hermes_skill_not_governed",
            "hermes_wake_stale", "hermes_governed_delivery_missing_or_ambiguous",
            "hermes_prior_execution_requires_reconciliation",
            "hermes_unexpected_lease_generation", "hermes_no_github_sources",
            "hermes_snapshot_identity_or_digest_invalid",
            "hermes_snapshot_sources_invalid", "hermes_snapshot_repo_not_allowlisted",
            "hermes_snapshot_timestamp_invalid", "hermes_prior_state_invalid",
            "hermes_metadata_employee_invalid", "hermes_metadata_wake_not_current",
            "hermes_metadata_resume_not_authorized", "lease_expired",
            "active_lease_required", "assignment_already_leased",
            "future_last_scan_at",
        }
        detail = str(exc)
        code = detail if detail in internal_codes else "hermes_worker_" + type(exc).__name__.lower()
        result={"schema":SCHEMA,"status":"failed","work_performed":False,
            "employee_id":EMPLOYEE,"assignment_id":args.assignment_id,
            "wake_id":args.wake_id,"presence_generation":args.presence_generation,
            "lease_generation":0,"error_code":code,"executor_provider":"unbound",
            "executor_model":"","credential_exposed":False,
            "session_identity_exposed":False,"verified_marker_emitted":False}
        print(json.dumps(result,ensure_ascii=False))
        return 2
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
