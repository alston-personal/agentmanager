#!/usr/bin/env python3
"""Compare complete workflow source inventories without executing or modifying workflows."""
import argparse
import json
from pathlib import Path


def compare(legacy, main):
    old = {r["path"]: r for r in legacy["workflows"] if r["is_active_workflow_path"]}
    new = {r["path"]: r for r in main["workflows"] if r["is_active_workflow_path"]}
    common = sorted(old.keys() & new.keys())
    differing = [p for p in common if old[p]["source_sha256"] != new[p]["source_sha256"]]
    legacy_only = sorted(old.keys() - new.keys())
    main_only = sorted(new.keys() - old.keys())
    legacy_publisher = sorted(
        p for p, r in old.items()
        if r["legacy_push"] and r["classification"] == "mutating_signal"
    )
    main_manual = sorted(
        p for p, r in new.items()
        if r["manual_trigger"] and r["classification"] == "mutating_signal"
    )
    legacy_not_main = sorted(p for p in legacy_publisher if p not in new)
    overlapping_drift = sorted(p for p in legacy_publisher if p in differing)
    return {
        "schema": "agentos.cross-branch-workflow-publication-compare/v1",
        "disclaimer": "Static source signals only. No enabled-state, branch rules, runtime or real deployment proof.",
        "legacy_root_workflows": len(old),
        "main_root_workflows": len(new),
        "common_paths": len(common),
        "identical_path_source": len(common) - len(differing),
        "different_source_count": len(differing),
        "legacy_only_paths": legacy_only,
        "main_only_paths": main_only,
        "legacy_mutating_push_candidates": legacy_publisher,
        "legacy_mutating_push_missing_from_main": legacy_not_main,
        "legacy_mutating_push_diverged_on_main": overlapping_drift,
        "main_manual_mutating_candidates": main_manual,
        "different_source_paths": differing,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy", type=Path, required=True)
    parser.add_argument("--main", dest="main_source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    legacy = json.loads(args.legacy.read_text(encoding="utf-8"))
    canonical = json.loads(args.main_source.read_text(encoding="utf-8"))
    result = compare(legacy, canonical)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    for name in (
        "legacy_root_workflows", "main_root_workflows", "common_paths",
        "identical_path_source", "different_source_count"
    ):
        print("workflow_compare_" + name + "=" + str(result[name]))
    for name in (
        "legacy_only_paths", "main_only_paths", "legacy_mutating_push_candidates",
        "legacy_mutating_push_missing_from_main",
        "legacy_mutating_push_diverged_on_main", "main_manual_mutating_candidates"
    ):
        print("workflow_compare_" + name + "=" + str(len(result[name])))


if __name__ == "__main__":
    main()
