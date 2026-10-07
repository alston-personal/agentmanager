import unittest

from agent_core.continuation import ContinuationOrigin, ContinuationResolver


class TestContinuationResolver(unittest.TestCase):
    def setUp(self):
        self.resolver = ContinuationResolver()

    def test_same_node_executor_wins_over_other_node_recent_work(self):
        bindings = [
            {
                "work_id": "work-oracle-runner",
                "state": "active",
                "node_id": "oracle",
                "executor_id": "shell",
                "participant_id": "codex",
                "updated_at": "2026-10-07T05:00:00Z",
            },
            {
                "work_id": "work-vopc-gui",
                "state": "active",
                "node_id": "vopc5750",
                "executor_id": "gui-worker",
                "participant_id": "codex",
                "updated_at": "2026-10-07T04:00:00Z",
            },
        ]

        result = self.resolver.resolve(
            bindings,
            origin=ContinuationOrigin(
                node_id="vopc5750",
                executor_id="gui-worker",
                participant_id="codex",
            ),
        )

        self.assertEqual(result.work_id, "work-vopc-gui")
        self.assertEqual(result.source, "participant_executor")

    def test_participants_on_same_node_do_not_steal_each_others_work(self):
        bindings = [
            {
                "work_id": "work-codex",
                "state": "active",
                "node_id": "vopc5750",
                "executor_id": "codex-cli",
                "participant_id": "codex",
            },
            {
                "work_id": "work-gemini",
                "state": "active",
                "node_id": "vopc5750",
                "executor_id": "gemini-cli",
                "participant_id": "gemini",
            },
        ]

        result = self.resolver.resolve(
            bindings,
            origin=ContinuationOrigin(
                node_id="vopc5750",
                executor_id="gemini-cli",
                participant_id="gemini",
            ),
        )

        self.assertEqual(result.work_id, "work-gemini")

    def test_new_session_resumes_executor_work(self):
        bindings = [
            {
                "work_id": "work-browser",
                "state": "suspended",
                "node_id": "oracle",
                "executor_id": "browser-gui",
                "participant_id": "gemini-web",
                "session_id": "old-session",
            }
        ]

        result = self.resolver.resolve(
            bindings,
            origin=ContinuationOrigin(
                node_id="oracle",
                executor_id="browser-gui",
                participant_id="gemini-web",
                session_id="new-session",
            ),
        )

        self.assertEqual(result.work_id, "work-browser")
        self.assertEqual(result.source, "participant_executor")

    def test_fresh_node_falls_back_only_to_node_assignment(self):
        bindings = [
            {
                "work_id": "work-other-node",
                "state": "active",
                "node_id": "oracle",
                "node_assigned": True,
            },
            {
                "work_id": "work-new-node",
                "state": "assigned",
                "node_id": "dqa03backup",
                "node_assigned": True,
            },
        ]

        result = self.resolver.resolve(
            bindings,
            origin=ContinuationOrigin(node_id="dqa03backup"),
        )

        self.assertEqual(result.work_id, "work-new-node")
        self.assertEqual(result.source, "node")

    def test_global_assignment_must_not_target_another_node(self):
        bindings = [
            {
                "work_id": "work-global-oracle",
                "state": "assigned",
                "node_id": "oracle",
                "global_assigned": True,
            },
            {
                "work_id": "work-global-unbound",
                "state": "assigned",
                "global_assigned": True,
            },
        ]

        result = self.resolver.resolve(
            bindings,
            origin=ContinuationOrigin(node_id="vopc5750"),
        )

        self.assertEqual(result.work_id, "work-global-unbound")
        self.assertEqual(result.source, "global_assignment")

    def test_explicit_work_id_has_highest_precedence(self):
        bindings = [
            {
                "work_id": "work-local",
                "state": "active",
                "node_id": "vopc5750",
                "executor_id": "codex-cli",
                "participant_id": "codex",
            },
            {
                "work_id": "work-explicit",
                "state": "suspended",
                "node_id": "oracle",
            },
        ]

        result = self.resolver.resolve(
            bindings,
            origin=ContinuationOrigin(
                node_id="vopc5750",
                executor_id="codex-cli",
                participant_id="codex",
            ),
            explicit_work_id="work-explicit",
        )

        self.assertEqual(result.work_id, "work-explicit")
        self.assertEqual(result.source, "explicit_work")

    def test_no_context_does_not_guess_most_recent_global_work(self):
        bindings = [
            {
                "work_id": "work-unrelated",
                "state": "active",
                "node_id": "oracle",
                "executor_id": "shell",
                "updated_at": "2026-10-07T06:00:00Z",
            }
        ]

        result = self.resolver.resolve(bindings, origin=ContinuationOrigin())

        self.assertIsNone(result.work_id)
        self.assertEqual(result.source, "no_continuation")


if __name__ == "__main__":
    unittest.main()
