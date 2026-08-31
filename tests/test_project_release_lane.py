import unittest

from scripts.check_project_release_lane import decide


class ProjectReleaseLaneTest(unittest.TestCase):
    def test_layoutlib_development_main_denied(self):
        self.assertEqual(
            decide("layoutlib", "development_write", "main"),
            (False, "development_write_to_promotion_branch_denied"),
        )

    def test_layoutlib_development_develop_allowed(self):
        self.assertEqual(
            decide("layoutlib", "development_write", "develop"),
            (True, "development_lane_allowed"),
        )

    def test_layoutlib_feature_allowed(self):
        self.assertTrue(decide("layoutlib", "development_write", "feature/door-recovery")[0])

    def test_layoutlib_promotion_requires_human_approval(self):
        self.assertEqual(
            decide("layoutlib", "promotion", "main"),
            (False, "explicit_human_approval_required"),
        )
        self.assertEqual(
            decide("layoutlib", "promotion", "main", True),
            (True, "promotion_allowed"),
        )

    def test_layoutlib_poc_requires_develop(self):
        self.assertEqual(
            decide("layoutlib", "poc_deploy", "main"),
            (False, "poc_requires_develop_candidate"),
        )
        self.assertEqual(
            decide("layoutlib", "poc_deploy", "develop"),
            (True, "poc_candidate_allowed"),
        )

    def test_layoutlib_production_requires_main(self):
        self.assertEqual(
            decide("layoutlib", "production_deploy", "develop"),
            (False, "production_requires_promoted_state"),
        )
        self.assertEqual(
            decide("layoutlib", "production_deploy", "main"),
            (True, "production_candidate_allowed"),
        )


if __name__ == "__main__":
    unittest.main()
