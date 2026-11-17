#!/usr/bin/env python3
"""Read-only, deterministic WoW Companion Suite plan generator.

This is an inventory/validation utility, NOT a game installer.
"""
import argparse
import json
from pathlib import Path

MANIFEST = Path(__file__).resolve().parents[1] / "integrations/wow/companion_suite/manifest.json"


class SuitePlanError(ValueError):
    pass


def build_plan(manifest, profile, extra=(), exclude=()):
    modules = {m["id"]: m for m in manifest["modules"]}
    profiles = manifest["profiles"]
    if profile not in profiles:
        raise SuitePlanError(f"Unknown profile: {profile}")
    requested = set(profiles[profile]) | set(extra)
    excluded = set(exclude)
    unknown = (requested | excluded) - set(modules)
    if unknown:
        raise SuitePlanError(f"Unknown modules: {', '.join(sorted(unknown))}")
    required = {k for k, m in modules.items() if m["required"]}
    if required & excluded:
        raise SuitePlanError(f"Cannot exclude required modules: {', '.join(sorted(required & excluded))}")
    selected = requested - excluded
    selected |= required
    # Expand dependencies; an explicitly excluded dependency is an error.
    pending = list(selected)
    while pending:
        current = pending.pop()
        for dependency in modules[current].get("requires", []):
            if dependency not in modules:
                raise SuitePlanError(f"Missing dependency definition: {dependency}")
            if dependency in excluded:
                raise SuitePlanError(f"{current} requires excluded module {dependency}")
            if dependency not in selected:
                selected.add(dependency)
                pending.append(dependency)
    conflicts = sorted({
        tuple(sorted((name, other)))
        for name in selected
        for other in modules[name].get("conflicts", [])
        if other in selected
    })
    if conflicts:
        raise SuitePlanError("Conflicting modules: " + ", ".join("/".join(pair) for pair in conflicts))
    resolved = [m for m in manifest["modules"] if m["id"] in selected]
    external = [m["id"] for m in resolved if m["owner"] == "third-party"]
    return {
        "schema": "agentos.wow-companion-plan/v1",
        "profile": profile,
        "edition": manifest["edition"],
        "execution": "dry-run-only",
        "selected": [m["id"] for m in resolved],
        "requires_user_license_and_version_review": external,
        "installable": False,
        "warnings": [
            "No game files will be written by this planner.",
            "First-party game/bridge implementation requires governed source migration and live acceptance.",
            "Third-party AddOns require license and target-client compatibility review before download.",
            "Never store provider API keys in WoW SavedVariables.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("minimal", "standard", "explorer", "combat"), default="minimal")
    parser.add_argument("--with", dest="extra", action="append", default=[], metavar="MODULE")
    parser.add_argument("--without", dest="exclude", action="append", default=[], metavar="MODULE")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    try:
        plan = build_plan(manifest, args.profile, args.extra, args.exclude)
    except SuitePlanError as exc:
        parser.error(str(exc))
    print(json.dumps(plan, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
