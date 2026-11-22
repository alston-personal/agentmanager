"""Systemic engineering admission guard: risk classification and negative cases."""
import unittest

from scripts.systemic_engineering_preflight import classify, validate_manifest, SCHEMA


def example():
    return {
        "schema": SCHEMA,
        "change_id": "GOV-20261122-SYSTEMIC-PREFLIGHT",
        "goal": "Prevent high-risk incremental patching before inventory",
        "risk_tier": "high",
        "phase": "implementation",
        "status": "in-progress",
        "scope_inventory": ["Core release and execution surfaces"],
        "existing_capabilities": ["AGENTS.md, governance directory, engineering authority"],
        "authority_map": ["GitHub human approval / ONE canonical runtime authority"],
        "failure_modes": ["parallel writers bypass preflight"],
        "implementation_plan": ["PR-local CI admission guard"],
        "verification_plan": ["negative unit tests and PR CI"],
        "rollback_plan": ["revert guard through protected PR approval"],
        "unknowns": ["Oracle deployment acceptance remains separate"],
        "reviewers": ["human protected-branch approver required"],
        "evidence_refs": ["docs/governance/decisions/GOV-2026-09-17-001-discovery-cost-reuse-floor.md"],
        "ready_for_implementation": True,
        "review_status": "reviewed",
    }


class PreflightTests(unittest.TestCase):
    def test_high_risk_sources_and_lightweight_docs(self):
        self.assertEqual(classify(["agentos_node/action_relay.py"]), "high")
        self.assertEqual(classify([".github/workflows/engineering-authority.yml"]), "high")
        self.assertEqual(classify(["AGENTS.md"]), "high")
        self.assertEqual(classify(["docs/design-notes.md"]), "standard")
        self.assertEqual(classify(["tests/test_math.py"]), "standard")

    def test_valid_complete_manifest(self):
        self.assertEqual(validate_manifest(example(), ["agentos_node/action_relay.py"]), [])

    def test_incomplete_or_unreviewed_manifest(self):
        for field in ("scope_inventory", "existing_capabilities", "authority_map",
                      "failure_modes", "implementation_plan", "verification_plan",
                      "rollback_plan", "unknowns", "reviewers", "evidence_refs"):
            with self.subTest(field=field):
                data = example()
                data[field] = []
                self.assertTrue(validate_manifest(data, ["agent_core/runtime_dispatcher.py"]))
        data = example()
        data["review_status"] = "pending"
        self.assertIn("review_not_recorded",
                      validate_manifest(data, ["agent_core/runtime_dispatcher.py"]))
        data = example()
        data["phase"] = "inventory"
        self.assertIn("invalid_implementation_phase",
                      validate_manifest(data, ["agent_core/runtime_dispatcher.py"]))

    def test_proposal_can_be_recorded_before_implementation(self):
        data = example()
        data.update(phase="design", status="proposed", ready_for_implementation=False,
                    review_status="pending")
        self.assertEqual(validate_manifest(data, ["AGENTS.md"]), [])

    def test_no_self_certified_empty_evidence(self):
        data = example()
        data["authority_map"] = ["unknown"]
        self.assertIn("unresolved_authority",
                      validate_manifest(data, ["agentos_node/action_relay.py"]))


if __name__ == "__main__":
    unittest.main()
