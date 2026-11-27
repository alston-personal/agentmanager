#!/usr/bin/env python3
"""Promote verified #117 regression evidence into ONE-owned Experience."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_core.experience_store import hydrate_from_one, promote_issue117_regression_evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--authority-receipt-json", required=True)
    parser.add_argument("--active-goal", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    before = hydrate_from_one(
        project_id="agentos-core",
        active_goal=args.active_goal,
        realm="oracle",
        capabilities=("agentos.core.develop", "agentos.one.resolve", "repository.merge"),
        executor="codex",
    )
    promotion = promote_issue117_regression_evidence(
        Path(args.evidence),
        json.loads(args.authority_receipt_json),
    )
    after = hydrate_from_one(
        project_id="agentos-core",
        active_goal=args.active_goal,
        realm="oracle",
        capabilities=("agentos.core.develop", "agentos.one.resolve", "repository.merge"),
        executor="codex",
    )
    payload = {
        "schema": "agentos.experience-regression-promotion-report/v1",
        "ok": True,
        "promotion": promotion,
        "before": {"digest": before["digest"], "experience_ids": before["experience_ids"]},
        "after": {"digest": after["digest"], "experience_ids": after["experience_ids"]},
        "added_experience_ids": sorted(set(after["experience_ids"]) - set(before["experience_ids"])),
        "credential_exposed": False,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
