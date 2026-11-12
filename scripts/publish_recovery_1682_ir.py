#!/usr/bin/env python3
"""Publish the #1682 Recovery IR through the existing canonical CAS handoff.

No second IR store and no speculative generation ids. By default prints only
a prepared request. --apply uses the original ONE publisher and requires
explicit expected/new generation ids; a stale or absent ONE IR fails closed.
Run ONLY from the authorized Oracle ONE runtime with its canonical data root.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

PROPOSAL = Path(__file__).resolve().parents[1] / "docs/recovery-1682-canonical-ir-proposal.json"
SCHEMA = "agentos.ir-change-proposal/v1"


def prepare(proposal, *, expected_index_id, expected_ir_id,
            new_index_id, new_ir_id):
    if not isinstance(proposal, dict) or proposal.get("schema") != SCHEMA:
        raise ValueError("invalid_recovery_ir_proposal")
    if proposal.get("project_id") != "agentos-core" or proposal.get("work_item") != "#1682":
        raise ValueError("ir_proposal_project_mismatch")
    if proposal.get("status") != "SOURCE_CI_ONLY_NOT_MERGED_NOT_RUNTIME_ACCEPTED":
        raise ValueError("unexpected_ir_evidence_status")
    if any(proposal.get(key) for key in ("ir_published", "runtime_accepted")):
        raise ValueError("proposal_must_not_claim_published_runtime")
    ids = (expected_index_id, expected_ir_id, new_index_id, new_ir_id)
    if not all(isinstance(value, str) and value.strip() for value in ids):
        raise ValueError("canonical_ir_generation_ids_required")
    if expected_index_id == new_index_id or expected_ir_id == new_ir_id:
        raise ValueError("new_ir_generation_required")
    if any(not isinstance(proposal.get(k), list) or not proposal[k]
           for k in ("pending_tasks", "decisions_append", "evidence")):
        raise ValueError("missing_ir_continuity")
    evidence = proposal["evidence"]
    for item in evidence:
        if (not isinstance(item, dict)
                or not all(item.get(k) for k in ("kind", "verdict", "summary"))):
            raise ValueError("invalid_ir_evidence_entry")
    return {
        "project_id": "agentos-core",
        "expected_index_id": expected_index_id,
        "expected_ir_id": expected_ir_id,
        "new_index_id": new_index_id,
        "new_ir_id": new_ir_id,
        "goal": proposal["goal"],
        "next_action": proposal["next_action"],
        "pending_tasks": proposal["pending_tasks"],
        "decisions_append": proposal["decisions_append"],
        "evidence": evidence,
        "capability": proposal["capability"],
        "execution_status": "in_progress",
        "execution_metadata": {
            **proposal["execution_metadata"],
            "ir_published": False,
        },
    }


def main():
    parser = argparse.ArgumentParser()
    for name in ("expected-index-id", "expected-ir-id", "new-index-id", "new-ir-id"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--data-root")
    parser.add_argument("--governance-path")
    args = parser.parse_args()
    proposal = json.loads(PROPOSAL.read_text(encoding="utf-8"))
    request = prepare(
        proposal,
        expected_index_id=args.expected_index_id,
        expected_ir_id=args.expected_ir_id,
        new_index_id=args.new_index_id,
        new_ir_id=args.new_ir_id,
    )
    if not args.apply:
        print(json.dumps({
            "schema": "agentos.ir-handoff-preparation/v1",
            "status": "PREPARED_NOT_PUBLISHED",
            "request": request,
        }, ensure_ascii=False, sort_keys=True, indent=2))
        return
    # No force/no workaround: the existing method checks the live canonical
    # generation, publishes with CAS and returns an authoritative receipt.
    from agent_core.canonical_ir_handoff import advance_canonical_ir
    result = advance_canonical_ir(
        request, data_root=args.data_root, governance_path=args.governance_path
    )
    if result.get("ok") is not True or not result.get("publish_receipt"):
        raise RuntimeError("canonical_ir_handoff_receipt_missing")
    # Publish receipt alone is insufficient. Read the authoritative ONE
    # execution-head/Canonical IR pair after CAS, and report selector status
    # separately rather than silently re-pointing an unrelated active project.
    from agent_core.resolve_facade import resolve_continuation
    current = resolve_continuation(
        "agentos-core", data_root=args.data_root,
        governance_path=args.governance_path,
    )
    head = current.get("execution_head") or {}
    continuation = current.get("continuation") or {}
    ir = continuation.get("canonical_ir") or {}
    if (head.get("index_id") != request["new_index_id"]
            or ir.get("index_id") != request["new_index_id"]
            or ir.get("ir_id") != request["new_ir_id"]
            or ir.get("parent_ir_id") != request["expected_ir_id"]):
        raise RuntimeError("canonical_ir_post_publish_readback_mismatch")
    from agent_core.active_continuation import read_active_continuation
    try:
        selector = read_active_continuation(args.data_root)
    except FileNotFoundError:
        selector = None
    selector_matches = bool(
        selector and selector.get("project_id") == "agentos-core"
        and selector.get("index_id") == request["new_index_id"]
        and selector.get("ir_id") == request["new_ir_id"]
    )
    result["canonical_ir_readback_verified"] = True
    result["active_selector_matches_new_ir"] = selector_matches
    result["active_selector_requires_reconciliation"] = bool(
        selector and selector.get("project_id") == "agentos-core"
        and not selector_matches
    )
    result["runtime_accepted"] = False
    result["recovery_live_receipt"] = False
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
