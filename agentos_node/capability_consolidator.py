"""Governed capability-state consolidation for persisted AgentOS experience.

This module is intentionally separate from the HTTP ingestion gateway. Browsers
may submit experience, but only a governed executor may consolidate and promote
canonical capability state.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .capability_runtime import (
    CapabilityExperience,
    CapabilityRuntime,
    non_regression_evaluator,
    weighted_numeric_profile_reducer,
)
from .capability_store import CapabilityStore


def _experience_from_dict(value: dict[str, Any]) -> CapabilityExperience:
    return CapabilityExperience(
        capability_id=str(value["capability_id"]),
        node_id=str(value["node_id"]),
        observation=dict(value.get("observation") or {}),
        outcome=dict(value.get("outcome") or {}),
        policy_used=dict(value.get("policy_used") or {}),
        provenance=dict(value.get("provenance") or {}),
        created_at=str(value.get("created_at") or ""),
        schema=str(value.get("schema") or "agentos.capability-experience/v1"),
        experience_id=str(value.get("experience_id") or ""),
    )


def consolidate_profile(
    root: str | Path,
    *,
    capability_id: str = "layoutlib.profile-detection",
    promote: bool = False,
    authority_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    store = CapabilityStore(root)
    store.ensure()
    persisted = store.experiences(capability_id)
    if not persisted:
        raise ValueError(f"no persisted experiences for {capability_id}")

    runtime = CapabilityRuntime()
    current = store.read_state(capability_id, slot="canonical")
    if current:
        runtime.seed_canonical(current)
    for item in persisted:
        runtime.observe(_experience_from_dict(item))

    result = runtime.consolidate(
        capability_id,
        weighted_numeric_profile_reducer(("threshold", "min_wall_length_px")),
        non_regression_evaluator,
    )
    store.write_state(result.candidate.to_dict(), slot="candidate")

    output: dict[str, Any] = {
        "ok": True,
        "capability_id": capability_id,
        "experience_count": len(persisted),
        "promotable": result.promotable,
        "evaluation": dict(result.evaluation),
        "candidate": result.candidate.to_dict(),
        "promoted": False,
    }
    if promote:
        if not result.promotable:
            raise PermissionError("candidate did not pass evaluator")
        if not authority_receipt:
            raise PermissionError("authority receipt is required for promotion")
        canonical = runtime.promote(
            capability_id,
            approved=True,
            authority_receipt=authority_receipt,
        )
        store.write_state(canonical.to_dict(), slot="canonical")
        output["canonical"] = canonical.to_dict()
        output["promoted"] = True
    return output


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--capability-id", default="layoutlib.profile-detection")
    p.add_argument("--promote", action="store_true")
    p.add_argument("--authority-receipt-json", default="")
    args = p.parse_args(argv)
    receipt = json.loads(args.authority_receipt_json) if args.authority_receipt_json else None
    result = consolidate_profile(
        args.root,
        capability_id=args.capability_id,
        promote=args.promote,
        authority_receipt=receipt,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
