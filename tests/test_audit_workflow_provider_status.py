"""Provider workflow-state join must not mistake absence for disabled or active."""
import unittest
from scripts.audit_workflow_provider_status import merge_provider


class ProviderWorkflowStateTest(unittest.TestCase):
    def test_source_and_provider_state_are_distinct(self):
        source = {
            "workflows": [
                {"path": ".github/workflows/legacy.yml",
                 "is_active_workflow_path": True, "legacy_push": True,
                 "classification": "mutating_signal"},
                {"path": ".github/workflows/missing.yml",
                 "is_active_workflow_path": True, "legacy_push": True,
                 "classification": "mutating_signal"},
                {"path": ".github/workflows/history/archived.yml",
                 "is_active_workflow_path": False, "legacy_push": True,
                 "classification": "mutating_signal"},
            ]
        }
        result = merge_provider(source, [
            {"path": ".github/workflows/legacy.yml", "id": 77, "state": "disabled_manually"}
        ])
        self.assertEqual(result["source_root_workflows"], 2)
        self.assertEqual(result["legacy_push_mutating_state_counts"]["disabled_manually"], 1)
        self.assertEqual(result["legacy_push_mutating_state_counts"]["not_registered"], 1)
        self.assertEqual(len(result["legacy_push_mutating_workflows"]), 2)

    def test_unknown_provider_state_not_trusted(self):
        source = {"workflows": [
            {"path": ".github/workflows/a.yml", "is_active_workflow_path": True,
             "legacy_push": True, "classification": "mutating_signal"}]}
        result = merge_provider(source, [
            {"path": ".github/workflows/a.yml", "id": 1, "state": "custom_active"}
        ])
        self.assertEqual(result["legacy_push_mutating_state_counts"], {"unknown": 1})


if __name__ == "__main__":
    unittest.main()
