import unittest
from unittest.mock import patch

import scripts.documentation_reality_guard as guard


class DocumentationRealityGuardTests(unittest.TestCase):
    def test_current_static_reality_is_valid(self):
        self.assertEqual(guard.static_errors(), [])

    def test_core_paths_are_architecture_sensitive(self):
        self.assertTrue(guard.is_architecture_path("agent_core/control_plane.py"))
        self.assertTrue(guard.is_architecture_path("scripts/continuation_state.py"))
        self.assertFalse(guard.is_architecture_path("docs/USER_GUIDE.md"))

    def test_architecture_change_requires_authoritative_doc(self):
        with patch.object(
            guard,
            "changed_files",
            return_value={"agent_core/control_plane.py", "tests/test_control_plane.py"},
        ):
            errors = guard.coupling_errors("base")
        self.assertEqual(len(errors), 1)
        self.assertIn("without an authoritative documentation update", errors[0])

    def test_architecture_change_with_current_state_update_passes(self):
        with patch.object(
            guard,
            "changed_files",
            return_value={"agent_core/control_plane.py", "docs/CURRENT_STATE.md"},
        ):
            errors = guard.coupling_errors("base")
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
