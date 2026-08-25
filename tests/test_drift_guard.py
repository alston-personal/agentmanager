import unittest
from unittest.mock import patch

import scripts.drift_guard as dg


class DriftGuardTests(unittest.TestCase):
    def test_current_governance_contract_is_valid(self):
        errors, warnings, attestation = dg.validate()
        self.assertEqual(errors, [])
        self.assertEqual(attestation["status"], "PASS")
        self.assertIn("governance.keeper", attestation["active_roles"])
        self.assertIn("governance.spec_steward", attestation["active_roles"])

    def test_immutable_principle_change_fails(self):
        original = dg.load_yaml

        def fake(path):
            data = original(path)
            if path == dg.CONSTITUTION:
                data = dict(data)
                items = [dict(item) for item in data["principles"]]
                items[0]["statement"] = "silently changed"
                data["principles"] = items
            return data

        with patch.object(dg, "load_yaml", side_effect=fake):
            errors, _, attestation = dg.validate()
        self.assertTrue(any("immutable principle changed" in e for e in errors))
        self.assertEqual(attestation["status"], "FAIL")

    def test_unknown_role_principle_fails(self):
        original = dg.load_yaml

        def fake(path):
            data = original(path)
            if path == dg.ROLE_REGISTRY:
                data = dict(data)
                roles = [dict(role) for role in data["roles"]]
                roles[0]["must_obey"] = list(roles[0]["must_obey"]) + ["does.not.exist"]
                data["roles"] = roles
            return data

        with patch.object(dg, "load_yaml", side_effect=fake):
            errors, _, _ = dg.validate()
        self.assertTrue(any("unknown principle" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
