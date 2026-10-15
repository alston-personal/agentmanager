from __future__ import annotations

import unittest

from scripts.check_project_release_lane import decide, load_policy


VALID_SHA = "a" * 40


class ProjectReleaseLaneTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy()

    def test_layoutlib_development_lane(self) -> None:
        self.assertEqual(
            decide(self.policy, "layoutlib", "development_write", "develop"),
            (True, "development_lane_allowed"),
        )
        self.assertEqual(
            decide(self.policy, "layoutlib", "development_write", "feature/door-carver"),
            (True, "development_lane_allowed"),
        )
        self.assertEqual(
            decide(self.policy, "layoutlib", "development_write", "main"),
            (False, "development_write_to_promotion_branch_denied"),
        )

    def test_promotion_requires_explicit_human_approval(self) -> None:
        self.assertEqual(
            decide(self.policy, "layoutlib", "promotion", "main"),
            (False, "explicit_human_approval_required"),
        )
        self.assertEqual(
            decide(
                self.policy,
                "layoutlib",
                "promotion",
                "main",
                explicit_human_approval=True,
            ),
            (True, "promotion_allowed"),
        )

    def test_poc_requires_develop_and_exact_sha(self) -> None:
        self.assertEqual(
            decide(self.policy, "layoutlib", "poc_deploy", "develop"),
            (False, "exact_source_sha_required"),
        )
        self.assertEqual(
            decide(
                self.policy,
                "layoutlib",
                "poc_deploy",
                "develop",
                candidate_sha="abc",
            ),
            (False, "exact_source_sha_invalid"),
        )
        self.assertEqual(
            decide(
                self.policy,
                "layoutlib",
                "poc_deploy",
                "main",
                candidate_sha=VALID_SHA,
            ),
            (False, "poc_requires_configured_source_branch"),
        )
        self.assertEqual(
            decide(
                self.policy,
                "layoutlib",
                "poc_deploy",
                "develop",
                candidate_sha=VALID_SHA,
            ),
            (True, "poc_candidate_allowed"),
        )

    def test_production_requires_main_and_exact_sha(self) -> None:
        self.assertEqual(
            decide(
                self.policy,
                "layoutlib",
                "production_deploy",
                "develop",
                candidate_sha=VALID_SHA,
            ),
            (False, "production_requires_configured_source_branch"),
        )
        self.assertEqual(
            decide(
                self.policy,
                "layoutlib",
                "production_deploy",
                "main",
                candidate_sha=VALID_SHA,
            ),
            (True, "production_candidate_allowed"),
        )

    def test_policy_requires_human_promotion_and_pinned_deployments(self) -> None:
        layoutlib = self.policy["projects"]["layoutlib"]
        self.assertEqual(layoutlib["promotion_branch"], "main")
        self.assertIs(layoutlib["promotion_requires"]["explicit_human_approval"], True)
        self.assertIs(layoutlib["promotion_requires"]["pull_request"], True)
        for lane, expected_branch in (("poc", "develop"), ("production", "main")):
            config = layoutlib["deployment"][lane]
            self.assertEqual(config["source_branch"], expected_branch)
            self.assertIs(config["require_exact_source_sha"], True)

    def test_noncanonical_or_uppercase_sha_fails_closed(self) -> None:
        for bad in ("a" * 39, "A" * 40, "a" * 41, "a" * 39 + "z"):
            with self.subTest(candidate_sha=bad):
                self.assertEqual(
                    decide(
                        self.policy, "layoutlib", "poc_deploy", "develop",
                        candidate_sha=bad,
                    ),
                    (False, "exact_source_sha_invalid"),
                )

    def test_unknown_project_is_denied(self) -> None:
        self.assertEqual(
            decide(self.policy, "unknown", "development_write", "develop"),
            (False, "unknown_project"),
        )


if __name__ == "__main__":
    unittest.main()
