"""Governed deployment Capability contract v1 for existing AgentOS execution lanes.

This module is a fail-closed *decision and receipt projection*, NOT a new
scheduler, shell, production publisher, credential store, or authorization grant.
The existing #165 execution authority, Runner Window and product-owned adapters
remain the only sources of execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

SCHEMA = "agentos.deployment-capability/v1"
RECEIPT_SCHEMA = "agentos.deployment-gate-receipt/v1"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
OPS = frozenset(("inspect", "stage", "promote", "verify", "rollback"))
MUTATIONS = frozenset(("stage", "promote", "rollback"))
INPUT_KEYS = frozenset((
    "schema", "request_id", "deployment_id", "project_id", "target_id",
    "operation", "source_commit", "source_ref", "expected_generation",
))
PROOF_KEYS = frozenset((
    "authority_granted", "executor_available", "source_verified",
    "source_reproducible", "target_observed", "serving_root_verified",
    "writers_reconciled", "critical_routes_verified", "protected_apis_verified",
    "rollback_ready", "rollback_rehearsed", "exclusive_lease_held",
    "artifact_integrity_verified", "release_receipt_verified",
    "current_generation", "current_source_commit", "previous_release_available",
    "dependencies_verified",
))
PROOF_BOOLEAN_KEYS = PROOF_KEYS - {"current_generation", "current_source_commit"}


class DeploymentContractError(ValueError):
    pass


@dataclass(frozen=True)
class Target:
    target_id: str
    project_id: str
    repository: str
    source_ref: str
    resource_id: str
    authority_issue: int
    # Names point to existing governed workflows, not to a new executor.
    release_carriers: tuple[str, ...]
    verification_carriers: tuple[str, ...]
    # Until promoted with runtime evidence, active is not inferred.
    migration_state: str
    dependencies: tuple[str, ...]


def _reject(reason: str) -> None:
    raise DeploymentContractError(reason)


def load_target(registry: Mapping[str, Any], target_id: str) -> Target:
    if registry.get("schema") != SCHEMA:
        _reject("unsupported_deployment_registry")
    if (registry.get("authority") != "source-discovery-only-no-new-dispatch"
            or registry.get("governed_execution_contract") != "agentos.execution-request/v1"
            or registry.get("one_executor_contract") != "agentos.executor-job/v1"):
        _reject("registry_cannot_grant_execution_authority")
    entries = registry.get("targets")
    if not isinstance(entries, dict) or target_id not in entries:
        _reject("target_not_registered")
    spec = entries[target_id]
    if not isinstance(spec, dict) or set(spec) != {
        "project_id", "repository", "source_ref", "resource_id",
        "authority_issue", "release_carriers", "verification_carriers",
        "migration_state", "dependencies",
    }:
        _reject("invalid_target_definition")
    for name in ("release_carriers", "verification_carriers"):
        carriers = spec[name]
        if (not isinstance(carriers, list) or not carriers
                or not all(isinstance(x, str) and re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,99}", x) for x in carriers)
                or len(set(carriers)) != len(carriers)):
            _reject("invalid_carrier_registry")
    for name in ("project_id", "repository", "source_ref", "resource_id"):
        if not isinstance(spec[name], str) or not spec[name]:
            _reject("invalid_target_identity")
    if (not isinstance(spec["authority_issue"], int)
            or isinstance(spec["authority_issue"], bool)
            or spec["authority_issue"] <= 0):
        _reject("invalid_target_authority")
    deps = spec["dependencies"]
    if (not isinstance(deps, list) or len(set(map(str, deps))) != len(deps)
            or any(not isinstance(item, str) or item == target_id or item not in entries for item in deps)):
        _reject("invalid_target_dependencies")
    if spec["migration_state"] not in ("source_only", "live_verified"):
        _reject("invalid_migration_state")
    return Target(target_id, spec["project_id"], spec["repository"],
                  spec["source_ref"], spec["resource_id"], spec["authority_issue"],
                  tuple(spec["release_carriers"]), tuple(spec["verification_carriers"]),
                  spec["migration_state"], tuple(deps))


def validate_deployment_intent(request: Mapping[str, Any],
                               registry: Mapping[str, Any]) -> Target:
    """Reject caller-selected repo, ref, target, command, runtime or adapter."""
    if not isinstance(request, Mapping) or set(request) != INPUT_KEYS:
        _reject("request_shape_not_allowlisted")
    if request.get("schema") != SCHEMA:
        _reject("invalid_request_schema")
    target_id = request.get("target_id")
    if not isinstance(target_id, str):
        _reject("invalid_target_id")
    target = load_target(registry, target_id)
    if request["project_id"] != target.project_id:
        _reject("project_identity_mismatch")
    if request["source_ref"] != target.source_ref:
        _reject("source_ref_not_authorized")
    if request["operation"] not in OPS:
        _reject("operation_not_registered")
    if not isinstance(request["source_commit"], str) or not SHA40.fullmatch(request["source_commit"]):
        _reject("exact_source_commit_required")
    for name in ("request_id", "deployment_id"):
        value = request[name]
        if (not isinstance(value, str)
                or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{7,127}", value)):
            _reject("invalid_opaque_identifier")
    generation = request["expected_generation"]
    if type(generation) is not int or generation < 0:
        _reject("invalid_expected_generation")
    return target


def evaluate_deployment_gate(request: Mapping[str, Any],
                             registry: Mapping[str, Any],
                             observed: Mapping[str, Any]) -> dict[str, Any]:
    """Consume verified provider evidence and return a non-executable gate result.

    A passed gate is NOT a deployment, nor a delegation of execution authority.
    A stage/promote/rollback must still be performed by the existing bound lane.
    """
    target = validate_deployment_intent(request, registry)
    if not isinstance(observed, Mapping) or set(observed) != PROOF_KEYS:
        _reject("proof_shape_not_allowlisted")
    if any(type(observed[key]) is not bool for key in PROOF_BOOLEAN_KEYS):
        _reject("invalid_proof_value")
    if type(observed["current_generation"]) is not int or observed["current_generation"] < 0:
        _reject("invalid_runtime_generation")
    sha = observed["current_source_commit"]
    if sha is not None and (not isinstance(sha, str) or not SHA40.fullmatch(sha)):
        _reject("invalid_observed_source_commit")

    reasons: list[str] = []
    op = request["operation"]
    def require(field: str) -> None:
        if observed[field] is not True:
            reasons.append(field)

    # Always require independently observed target state and valid source.
    require("executor_available")
    require("source_verified")
    require("target_observed")

    if observed["current_generation"] != request["expected_generation"]:
        reasons.append("stale_deployment_generation")

    if op in MUTATIONS:
        for field in ("authority_granted", "exclusive_lease_held", "artifact_integrity_verified"):
            require(field)
    if op in ("stage", "promote"):
        require("source_reproducible")
    if op == "promote":
        if target.dependencies:
            require("dependencies_verified")
        for field in ("serving_root_verified", "writers_reconciled",
                      "critical_routes_verified", "protected_apis_verified",
                      "rollback_ready", "rollback_rehearsed"):
            require(field)
        # Never self-certify a root cutover based on source-only changes.
        if target.migration_state != "live_verified":
            reasons.append("live_authority_not_accepted")
    if op == "verify":
        if target.dependencies:
            require("dependencies_verified")
        # An older release can be healthy, but cannot verify this immutable intent.
        if observed["current_source_commit"] != request["source_commit"]:
            reasons.append("observed_release_sha_mismatch")
        for field in ("serving_root_verified", "critical_routes_verified",
                      "protected_apis_verified", "release_receipt_verified"):
            require(field)
    if op == "rollback":
        for field in ("previous_release_available", "rollback_ready"):
            require(field)

    return {
        "schema": RECEIPT_SCHEMA,
        "request_id": request["request_id"],
        "deployment_id": request["deployment_id"],
        "target_id": target.target_id,
        "project_id": target.project_id,
        "operation": op,
        "source_commit": request["source_commit"],
        "expected_generation": request["expected_generation"],
        "observed_generation": observed["current_generation"],
        "result": "PASS" if not reasons else "BLOCKED",
        "reasons": reasons,
        # Explicitly not the terminal release receipt or permission to dispatch.
        "execution_performed": False,
        "release_receipt": False,
        "capability_registered": True,
        "release_carriers": list(target.release_carriers),
    }
