from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_core.governance_directory import GovernanceEntity, get, register, resolve, seed_core


class GovernanceDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "directory.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_port_manager_is_exclusive_owner(self):
        seed_core(self.path)
        owners = resolve("capability://network.port.allocate", self.path)
        self.assertTrue(owners)
        self.assertEqual(owners[0]["id"], "manager://port")
        self.assertIs(owners[0]["authority"]["exclusive"], True)

    def test_exclusive_duplicate_owner_is_rejected(self):
        seed_core(self.path)
        duplicate = GovernanceEntity(
            id="manager://rogue-port-manager",
            kind="manager",
            name="Rogue Port Manager",
            owns=["capability://network.port.allocate"],
            provides=["capability://network.port.allocate"],
            implementation={},
            authority={"exclusive": True},
            state="implemented",
        )
        with self.assertRaisesRegex(ValueError, "exclusive ownership conflict"):
            register(duplicate, path=self.path)

    def test_roles_are_mirrored_from_versioned_role_registry(self):
        seed_core(self.path)
        steward = get("role://governance.spec_steward", self.path)
        self.assertIsNotNone(steward)
        self.assertIs(steward["authority"]["canonical_role_contract"], True)
        self.assertTrue(steward["metadata"]["role_set_version"])
        self.assertEqual(steward["implementation"]["canonical_registry"], ".agent/roles/registry.yaml")

    def test_stale_legacy_role_is_not_resolved(self):
        seed_core(self.path)
        stale = get("role://instance.agentmanager_paw", self.path)
        self.assertIsNotNone(stale)
        self.assertEqual(stale["state"], "stale")


if __name__ == "__main__":
    unittest.main()
