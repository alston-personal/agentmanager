from __future__ import annotations

import unittest
from scripts.role_reality_guard import check_role_reality


class RoleRealityTests(unittest.TestCase):
    def test_zero_paper_phantoms_in_active_roles(self) -> None:
        """Enforces that no role declared active lacks physical worker, directory, or receipts."""
        reports, breaches = check_role_reality()
        self.assertEqual(
            len(breaches),
            0,
            f"Found paper phantoms masquerading as active roles: {breaches}",
        )
        self.assertTrue(len(reports) >= 5, "At least 5 core roles must be live")


if __name__ == "__main__":
    unittest.main()

