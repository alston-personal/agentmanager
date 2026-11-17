import json
import unittest
from pathlib import Path

from scripts.wow_companion_suite import MANIFEST, SuitePlanError, build_plan


class WowCompanionSuiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(Path(MANIFEST).read_text(encoding="utf-8"))

    def test_minimal_is_independent_of_agentos_account(self):
        plan = build_plan(self.manifest, "minimal")
        self.assertEqual(plan["execution"], "dry-run-only")
        self.assertIn("ai-secretary", plan["selected"])
        self.assertIn("companion-bridge", plan["selected"])
        self.assertFalse(plan["installable"])

    def test_standard_third_party_requires_review(self):
        plan = build_plan(self.manifest, "standard")
        self.assertIn("baganator", plan["requires_user_license_and_version_review"])

    def test_required_cannot_be_removed(self):
        with self.assertRaisesRegex(SuitePlanError, "required"):
            build_plan(self.manifest, "minimal", exclude=["companion-core"])

    def test_reject_ui_conflicts(self):
        with self.assertRaisesRegex(SuitePlanError, "Conflicting"):
            build_plan(self.manifest, "minimal", extra=["elvui", "bartender4"])

    def test_unknown_module_is_rejected(self):
        with self.assertRaisesRegex(SuitePlanError, "Unknown modules"):
            build_plan(self.manifest, "minimal", extra=["random-addon"])

    def test_reject_excluded_dependency(self):
        with self.assertRaisesRegex(SuitePlanError, "requires excluded"):
            build_plan(self.manifest, "minimal", extra=["buff-assist"], exclude=["companion-core"])

    def test_does_not_claim_installer_ready(self):
        for profile in self.manifest["profiles"]:
            plan = build_plan(self.manifest, profile)
            self.assertFalse(plan["installable"])
            self.assertTrue(plan["warnings"])

    def test_manifest_has_unique_ids(self):
        ids = [m["id"] for m in self.manifest["modules"]]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
