#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_core.project_store import list_projects


def build_registry():
    registry: dict[str, dict[str, list[str]]] = defaultdict(lambda: {"providers": [], "required_by": []})
    projects = list_projects()
    for project in projects:
        for capability in project.capabilities_provided:
            if project.display_name not in registry[capability]["providers"]:
                registry[capability]["providers"].append(project.display_name)
        for capability in project.capabilities_required:
            if project.display_name not in registry[capability]["required_by"]:
                registry[capability]["required_by"].append(project.display_name)
    return dict(sorted(registry.items(), key=lambda item: item[0]))


def print_table(registry: dict[str, dict[str, list[str]]]) -> None:
    if not registry:
        print("📭 No capabilities have been declared yet.")
        return

    print("\n| Capability | Providers | Required By |")
    print("| :--- | :--- | :--- |")
    for capability, entry in registry.items():
        providers = ", ".join(entry["providers"]) or "--"
        required_by = ", ".join(entry["required_by"]) or "--"
        print(f"| `{capability}` | {providers} | {required_by} |")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect AgentOS project capability declarations.")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.add_argument("--provides", help="Filter to capabilities provided by a project")
    parser.add_argument("--requires", help="Filter to projects requiring a capability")
    args = parser.parse_args()

    registry = build_registry()

    if args.provides:
        matches = {
            capability: entry
            for capability, entry in registry.items()
            if args.provides in capability or args.provides in entry["providers"]
        }
        registry = matches

    if args.requires:
        matches = {
            capability: entry
            for capability, entry in registry.items()
            if args.requires in capability or args.requires in entry["required_by"]
        }
        registry = matches

    if args.json:
        print(json.dumps(registry, ensure_ascii=False, indent=2))
    else:
        print_table(registry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
