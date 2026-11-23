import unittest

from agent_core.monthly_report_coordinator import (
    apply_human_review,
    assert_publish_allowed,
    build_review_package,
    is_dqa_work_item_allowed,
)


class MonthlyReportCoordinatorTests(unittest.TestCase):
    def test_public_private_isolation_blocks_personal_projects(self) -> None:
        ok, _ = is_dqa_work_item_allowed("redmine_5", "Upgrade Redmine plugin and verify backup")
        self.assertTrue(ok)

        for proj, text in [
            ("agentos", "Refactor BasePDCAWorker"),
            ("system", "Deploy Mio Threads bot"),
            ("system", "Update WoW companion suite"),
            ("zeus-writer", "Chapter 19 draft"),
            ("unknown_personal", "Random task"),
        ]:
            allowed, reason = is_dqa_work_item_allowed(proj, text)
            self.assertFalse(allowed, f"Should block {proj}: {text}")
            self.assertTrue(reason.startswith(("forbidden_personal_keyword:", "project_not_in_dqa_whitelist:")))

    def test_date_rule_friday_of_last_wednesday_week_and_override(self) -> None:
        # 2026-11 last Wednesday is 2026-11-25 -> Friday of that week is 2026-11-27
        pkg_default = build_review_package(year=2026, month=11, slices=[])
        self.assertEqual(pkg_default["metadata"]["report_date"], "2026-11-27")
        self.assertEqual(pkg_default["metadata"]["report_date_table"], "27 Nov 2026")
        self.assertEqual(pkg_default["metadata"]["page_title"], "2026-11-27 - Weekly Report of Alston")

        # 2026-12 last Wednesday is 2026-12-30 -> Friday crosses month to 2027-01-01
        pkg_cross = build_review_package(year=2026, month=12, slices=[])
        self.assertEqual(pkg_cross["metadata"]["report_date"], "2027-01-01")

        # Explicit override support
        pkg_override = build_review_package(year=2026, month=11, slices=[], override_date="2026-11-24")
        self.assertEqual(pkg_override["metadata"]["report_date"], "2026-11-24")
        self.assertEqual(pkg_override["metadata"]["report_date_table"], "24 Nov 2026")
        self.assertEqual(pkg_override["metadata"]["page_title"], "2026-11-24 - Weekly Report of Alston")

    def test_human_review_gate_blocks_until_explicit_approval_and_supports_deletion(self) -> None:
        slices = [
            {
                "node_id": "dqa03backup",
                "items": [
                    {"project": "redmine_5", "title": "Redmine DB backup verification", "status": "completed", "recent_week": True},
                    {"project": "samba", "title": "NAS mount health check", "status": "proceeding"},
                    {"project": "system", "title": "AgentOS secret leak test", "status": "completed"},
                ],
            }
        ]
        pkg = build_review_package(year=2026, month=11, slices=slices, override_date="2026-11-24")
        # Personal item must be auto-rejected
        self.assertEqual(len(pkg["accepted_items"]), 2)
        self.assertEqual(len(pkg["rejected_items"]), 1)

        # Must block publish before human review
        with self.assertRaises(PermissionError):
            assert_publish_allowed(pkg)

        # Remove 1 item and approve publish
        to_remove = pkg["accepted_items"][1]["item_id"]
        reviewed = apply_human_review(pkg, remove_item_ids={to_remove}, approve_publish=True)
        self.assertEqual(len(reviewed["accepted_items"]), 1)
        assert_publish_allowed(reviewed)

    def test_confluence_publish_helper_preserves_details_macro_user_mention_and_attachments(self) -> None:
        from confluence_publish_helper import (
            format_user_mention,
            link_attachments_in_storage_html,
            wrap_page_properties_details,
        )

        mention = format_user_mention(user_key="ff808181692c65570169472f1ab10083")
        self.assertIn('ri:userkey="ff808181692c65570169472f1ab10083"', mention)

        wrapped = wrap_page_properties_details("<table><tr><th>Date</th><td>27 Nov 2026</td></tr></table>")
        self.assertIn('ac:name="details"', wrapped)
        self.assertEqual(wrap_page_properties_details(wrapped), wrapped)

        linked = link_attachments_in_storage_html(
            "<p>See <code>VPP_TEST_SOP.md</code> and TESTING_LESSONS_LEARNED.md</p>",
            ["VPP_TEST_SOP.md", "TESTING_LESSONS_LEARNED.md"],
        )
        self.assertIn('<ac:link><ri:attachment ri:filename="VPP_TEST_SOP.md" /></ac:link>', linked)
        self.assertIn('<ac:link><ri:attachment ri:filename="TESTING_LESSONS_LEARNED.md" /></ac:link>', linked)


if __name__ == "__main__":
    unittest.main()
