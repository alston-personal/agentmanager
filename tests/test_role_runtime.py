import unittest
from pathlib import Path

from agent_core.role_runtime import RoleRegistry


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / ".agent" / "roles" / "registry.yaml"


class RoleRuntimeTest(unittest.TestCase):
    def test_active_role_registry_is_machine_hydratable(self):
        registry = RoleRegistry(REGISTRY)
        ids = registry.ids()
        self.assertIn("governance.spec_steward", ids)
        self.assertIn("sector.paw", ids)
        self.assertNotIn("governance.arbiter", ids)

    def test_proposed_role_cannot_be_activated_as_runtime_contract(self):
        registry = RoleRegistry(REGISTRY)
        with self.assertRaises(ValueError):
            registry.resolve("governance.arbiter")

    def test_upstream_role_contract_is_inherited_deterministically(self):
        registry = RoleRegistry(REGISTRY)
        paw = registry.resolve("sector.paw")
        self.assertEqual(paw.upstream_roles, ["sector.weaver"])
        self.assertIn("specification_closure", paw.must_obey)
        self.assertIn("capability_boundary", paw.must_obey)
        self.assertIn("receipts_over_claims", paw.must_obey)
        self.assertIn("architecture_decision", paw.outputs)
        self.assertIn("execution_receipt", paw.outputs)

    def test_spec_steward_capability_is_hydrated(self):
        registry = RoleRegistry(REGISTRY)
        steward = registry.resolve("governance.spec_steward")
        self.assertEqual(steward.kind, "governance")
        self.assertIn("governance.spec.audit", steward.capabilities)
        self.assertIn("closure_gap", steward.outputs)


if __name__ == "__main__":
    unittest.main()
