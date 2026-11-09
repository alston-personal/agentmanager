#!/usr/bin/env python3
"""Bounded, read-only Gaia Oracle intake diagnostic via existing Runner Window.

This probes the live local Project Store and Governance Directory. It cannot
register a project, WorkItem, Employee assignment, or authorization.
"""
from __future__ import annotations

import json
from scripts.gaia_proposal_intake import examine


def main() -> int:
    result = examine({
        "title": "Personal Device Secretary",
        "kind": "project",
        "related_asset_ids": ["project://mobile-node"],
    })
    review = result["review"]
    decision = review["decision"]
    print("gaia_intake_probe=PASS")
    print("gaia_intake_schema=" + str(review["schema"]))
    print("gaia_intake_disposition=" + str(decision["disposition"]))
    print("gaia_intake_parent=" + str(decision.get("canonical_parent") or "none"))
    print("gaia_intake_review_hash=" + str(review["content_hash"]))
    print("gaia_intake_execution_authorized=false")
    print("gaia_intake_creation_authorized=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
