"""Deterministic tests for Core deployment Capability -- no real deployment."""
from __future__ import annotations
import json
from pathlib import Path
import unittest

from agent_core.deployment_capability import (
    DeploymentContractError, evaluate_deployment_gate,
    load_target, validate_deployment_intent, PROOF_KEYS,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = json.loads((ROOT / "governance/deployment-capabilities.json").read_text())

def request(operation="promote", **changes):
    value = {
        "schema": "agentos.deployment-capability/v1",
        "request_id": "release-request-0000001",
        "deployment_id": "release-generation-0000001",
        "project_id": "studio-web",
        "target_id": "studio.public-site",
        "operation": operation,
        "source_commit": "a" * 40,
        "source_ref": "main",
        "expected_generation": 4,
    }
    value.update(changes)
    return value

def proof(**changes):
    value = {field: True for field in PROOF_KEYS if field not in ("current_generation", "current_source_commit")}
    value["current_generation"] = 4
    value["current_source_commit"] = "a" * 40
    value.update(changes)
    return value

class DeploymentCapabilityContractTests(unittest.TestCase):
    def test_declared_capabilities_reuse_existing_lanes_and_start_source_only(self):
        for target_id, entry in REGISTRY["targets"].items():
            spec = load_target(REGISTRY, target_id)
            self.assertEqual(spec.migration_state, "source_only")
            self.assertGreater(len(spec.release_carriers), 0)
            self.assertNotIn("shell", json.dumps(entry))
        self.assertEqual(len(REGISTRY["targets"]), 2)

    def test_inspection_never_executes_and_can_pass_with_empty_auth(self):
        result = evaluate_deployment_gate(
            request("inspect"), REGISTRY, proof(authority_granted=False,
            exclusive_lease_held=False, rollback_ready=False))
        self.assertEqual(result["result"], "PASS")
        self.assertFalse(result["execution_performed"])
        self.assertFalse(result["release_receipt"])

    def test_stage_requires_authority_lease_and_exact_artifact(self):
        result = evaluate_deployment_gate(request("stage"), REGISTRY,
            proof(authority_granted=False, exclusive_lease_held=False,
            artifact_integrity_verified=False))
        self.assertEqual(result["result"], "BLOCKED")
        self.assertIn("authority_granted", result["reasons"])
        self.assertIn("exclusive_lease_held", result["reasons"])
        self.assertIn("artifact_integrity_verified", result["reasons"])

    def test_promote_fails_closed_without_actual_live_root_writer_census(self):
        result = evaluate_deployment_gate(request(), REGISTRY,
            proof(serving_root_verified=False, writers_reconciled=False,
            rollback_ready=False))
        self.assertEqual(result["result"], "BLOCKED")
        self.assertIn("serving_root_verified", result["reasons"])
        self.assertIn("writers_reconciled", result["reasons"])
        self.assertIn("rollback_ready", result["reasons"])
        self.assertIn("live_authority_not_accepted", result["reasons"])

    def test_source_only_cannot_self_authorize_promotion(self):
        result = evaluate_deployment_gate(request(), REGISTRY, proof())
        self.assertEqual(result["result"], "BLOCKED")
        self.assertEqual(result["reasons"], ["live_authority_not_accepted"])

    def test_verified_registry_does_not_execute_release(self):
        trusted = json.loads(json.dumps(REGISTRY))
        trusted["targets"]["studio.public-site"]["migration_state"] = "live_verified"
        result = evaluate_deployment_gate(request(), trusted, proof())
        self.assertEqual(result["result"], "PASS")
        self.assertFalse(result["execution_performed"])
        self.assertFalse(result["release_receipt"])

    def test_stale_generation_and_no_previous_rollback_are_blocked(self):
        result = evaluate_deployment_gate(request("rollback", expected_generation=5),
            REGISTRY, proof(previous_release_available=False))
        self.assertIn("stale_deployment_generation", result["reasons"])
        self.assertIn("previous_release_available", result["reasons"])

    def test_verify_requires_actual_release_receipt_and_protected_api(self):
        result = evaluate_deployment_gate(request("verify"), REGISTRY,
            proof(release_receipt_verified=False, protected_apis_verified=False))
        self.assertIn("release_receipt_verified", result["reasons"])
        self.assertIn("protected_apis_verified", result["reasons"])

    def test_exact_request_and_proof_shape_enforced(self):
        candidates = [
            request(shell="rm -rf /"),
            request(repository="evil/repo"),
            request(operation="arbitrary"),
            request(source_commit="main"),
            request(source_ref="core/integration"),
            request(project_id="zeus-writer"),
            request(expected_generation=True),
        ]
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                with self.assertRaises(DeploymentContractError):
                    evaluate_deployment_gate(candidate, REGISTRY, proof())
        with self.assertRaises(DeploymentContractError):
            evaluate_deployment_gate(request(), REGISTRY, {**proof(), "command": "echo hi"})
        with self.assertRaises(DeploymentContractError):
            evaluate_deployment_gate(request(), REGISTRY, proof(authority_granted=1))

    def test_verify_detects_stale_release_sha_despite_all_green_flags(self):
        result = evaluate_deployment_gate(request("verify"), REGISTRY,
            proof(current_source_commit="b" * 40))
        self.assertEqual(result["result"], "BLOCKED")
        self.assertIn("observed_release_sha_mismatch", result["reasons"])

    def test_registry_cannot_claim_new_execution_authority(self):
        forged = json.loads(json.dumps(REGISTRY))
        forged["authority"] = "arbitrary-runtime-shell"
        with self.assertRaises(DeploymentContractError):
            validate_deployment_intent(request(), forged)

    def test_unlisted_target_cannot_be_provisioned_by_request(self):
        with self.assertRaises(DeploymentContractError):
            validate_deployment_intent(request(target_id="zeus-writer.production"), REGISTRY)

if __name__ == "__main__":
    unittest.main()
