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

    def test_paw_inherits_root_pdca_and_safety_policy(self):
        registry = RoleRegistry(REGISTRY)
        paw = registry.resolve("sector.paw")
        self.assertEqual(paw.parent_role_id, "core.root")
        self.assertEqual(paw.protocols["pdca"], "root.pdca.v1")
        self.assertIn("truth_provenance", paw.must_obey)
        self.assertIn("claim_unverified_side_effects", paw.must_not)
        self.assertNotIn("merge_protected_main", paw.capabilities)

    def test_missing_parent_or_cycle_fail_closed(self):
        import tempfile
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "roles.yml"
            p.write_text(yaml.safe_dump({"roles": [
                {"id": "one", "status": "active", "parent_role_id": "missing"},
            ]}))
            with self.assertRaises(KeyError):
                RoleRegistry(p).resolve("one")
            p.write_text(yaml.safe_dump({"roles": [
                {"id": "one", "status": "active", "parent_role_id": "two"},
                {"id": "two", "status": "active", "parent_role_id": "one"},
            ]}))
            with self.assertRaisesRegex(ValueError, "inheritance cycle"):
                RoleRegistry(p).resolve("one")

    def test_spec_steward_capability_is_hydrated(self):
        registry = RoleRegistry(REGISTRY)
        steward = registry.resolve("governance.spec_steward")
        self.assertEqual(steward.kind, "governance")
        self.assertIn("governance.spec.audit", steward.capabilities)
        self.assertIn("closure_gap", steward.outputs)


if __name__ == "__main__":
    unittest.main()
