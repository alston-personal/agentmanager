#!/usr/bin/env python3
"""Gaia read-only proposal intake over existing local AgentOS registries.

This emits INFORMATIONAL review records, never creates projects, WorkItems,
authorizations, jobs, issues, or runtime receipts. Atlas/global completeness
must still be verified before proposing a NEW project.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_core import governance_directory
from agent_core.gaia_intake import Proposal
from agent_core.gaia_project_adapter import read_local_projects
from agent_core.gaia_directory_adapter import read_governance_directory
from agent_core.gaia_reconcile import reconcile_project_proposal
from agent_core.gaia_decision_record import issue_review_record


def _snapshot_ref(kind: str, origin: str, assets: tuple, errors: tuple[str, ...]) -> str:
    # Local content fingerprint, not proof of authoritative Atlas freshness.
    data = {"assets": [asdict(asset) for asset in assets], "errors": list(errors)}
    digest = sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return f"{kind}:{origin}#local-sha256:{digest}"


def examine(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("proposal_object_required")
    allowed = {"title", "kind", "related_asset_ids", "required_capabilities", "requests_new_trust_boundary"}
    if set(payload) - allowed:
        raise ValueError("unknown_proposal_fields")
    if not isinstance(payload.get("title"), str) or not payload["title"].strip():
        raise ValueError("proposal_title_required")
    if payload.get("kind") != "project":
        raise ValueError("project_proposal_only")
    for field in ("related_asset_ids", "required_capabilities"):
        if not isinstance(payload.get(field, []), list) or any(
            not isinstance(x, str) or not x.strip() for x in payload.get(field, [])
        ):
            raise ValueError("invalid_" + field)
    if not isinstance(payload.get("requests_new_trust_boundary", False), bool):
        raise ValueError("invalid_trust_boundary")
    proposal = Proposal(
        title=payload["title"],
        kind="project",
        related_asset_ids=tuple(payload.get("related_asset_ids", [])),
        required_capabilities=tuple(payload.get("required_capabilities", [])),
        requests_new_trust_boundary=payload.get("requests_new_trust_boundary", False),
    )
    local = read_local_projects()
    directory = read_governance_directory(governance_directory.REGISTRY_PATH)
    decision = reconcile_project_proposal(proposal, local, directory)
    refs = (
        _snapshot_ref("local-project-store", local.provenance, local.assets, local.errors),
        _snapshot_ref("governance-projection", directory.provenance, directory.assets, directory.errors),
    )
    review = issue_review_record(
        proposal, decision, source_refs=refs,
        reviewed_at=datetime.now(timezone.utc).isoformat(),
    )
    return {
        "status": "REVIEWED_INFORMATIONAL_ONLY",
        "review": asdict(review),
        "next_step": (
            "route_to_existing_project_owner_for_scoped_work_intake"
            if decision.canonical_parent else "verify_atlas_global_inventory_before_creation"
        ),
        "creation_authorized": False,
        "execution_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Review one Gaia proposal without mutations")
    parser.add_argument("--proposal", type=Path, required=True, help="JSON proposal file")
    args = parser.parse_args()
    try:
        payload = json.loads(args.proposal.read_text(encoding="utf-8"))
        result = examine(payload)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
