#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"PyYAML required: {exc}")

ROOT = Path(__file__).resolve().parent.parent
CONSTITUTION = ROOT / ".agent" / "CONSTITUTION.yaml"
ROLE_REGISTRY = ROOT / ".agent" / "roles" / "registry.yaml"
BASELINE = ROOT / ".agent" / "governance" / "immutable_baseline.yaml"


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"expected object in {path}")
    return data


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def index_principles(constitution: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in constitution.get("principles", []) or []:
        if isinstance(item, dict) and item.get("id"):
            result[str(item["id"])] = item
    return result


def validate() -> tuple[list[str], list[str], dict[str, Any]]:
    errors: list[str] = []
    warnings: list[str] = []
    constitution = load_yaml(CONSTITUTION)
    registry = load_yaml(ROLE_REGISTRY)
    baseline = load_yaml(BASELINE)

    principles = index_principles(constitution)
    immutable = baseline.get("immutable_principles", {}) or {}
    for principle_id, expected_statement in immutable.items():
        item = principles.get(str(principle_id))
        if item is None:
            errors.append(f"immutable principle missing: {principle_id}")
            continue
        if item.get("level") != "immutable":
            errors.append(f"immutable principle downgraded: {principle_id}")
        if str(item.get("statement")) != str(expected_statement):
            errors.append(f"immutable principle changed without baseline migration: {principle_id}")

    role_ids: set[str] = set()
    for role in registry.get("roles", []) or []:
        if not isinstance(role, dict):
            errors.append("invalid role entry")
            continue
        role_id = str(role.get("id") or "").strip()
        if not role_id:
            errors.append("role missing id")
            continue
        if role_id in role_ids:
            errors.append(f"duplicate role id: {role_id}")
        role_ids.add(role_id)
        for required in role.get("must_obey", []) or []:
            if str(required) not in principles:
                errors.append(f"role {role_id} references unknown principle: {required}")
        source = role.get("source")
        status = str(role.get("status") or "")
        if source:
            source_path = ROOT / str(source)
            if not source_path.exists():
                errors.append(f"role {role_id} source missing: {source}")
        elif status == "active":
            errors.append(f"active role {role_id} has no source")
        if status == "proposed":
            warnings.append(f"proposed role not yet enforceable: {role_id}")

    keeper = constitution.get("governance", {}).get("constitution_keeper")
    steward = constitution.get("governance", {}).get("spec_steward")
    for required_role in (keeper, steward):
        if required_role and required_role not in role_ids:
            errors.append(f"governance role missing from registry: {required_role}")

    for artifact in constitution.get("protected_artifacts", []) or []:
        if not (ROOT / str(artifact)).exists():
            errors.append(f"protected artifact missing: {artifact}")

    legacy = registry.get("legacy_instances", []) or []
    for item in legacy:
        if isinstance(item, dict) and item.get("status") == "stale":
            warnings.append(f"stale legacy role must not be runtime truth: {item.get('id')}")

    attestation = {
        "schema": "agentos.policy-attestation/v1",
        "constitution_version": constitution.get("constitution_version"),
        "role_set_version": registry.get("role_set_version"),
        "baseline_version": baseline.get("baseline_version"),
        "constitution_sha256": sha256_file(CONSTITUTION),
        "role_registry_sha256": sha256_file(ROLE_REGISTRY),
        "immutable_baseline_sha256": sha256_file(BASELINE),
        "active_roles": sorted(
            str(role.get("id")) for role in registry.get("roles", []) or []
            if isinstance(role, dict) and role.get("status") == "active"
        ),
        "proposed_roles": sorted(
            str(role.get("id")) for role in registry.get("roles", []) or []
            if isinstance(role, dict) and role.get("status") == "proposed"
        ),
        "status": "PASS" if not errors else "FAIL",
    }
    return errors, warnings, attestation


def main() -> int:
    p = argparse.ArgumentParser(description="Validate AgentOS constitution/roles and emit policy attestation")
    p.add_argument("--json", action="store_true")
    p.add_argument("--attestation-out")
    args = p.parse_args()

    errors, warnings, attestation = validate()
    if args.attestation_out:
        out = Path(args.attestation_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(attestation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps({"errors": errors, "warnings": warnings, "attestation": attestation}, ensure_ascii=False, indent=2))
    else:
        print(f"AgentOS Drift Guard: {attestation['status']}")
        print(f"constitution={attestation['constitution_version']} role_set={attestation['role_set_version']}")
        for warning in warnings:
            print(f"WARN: {warning}")
        for error in errors:
            print(f"ERROR: {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
