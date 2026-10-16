import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from agentos_node.github_actions_runs_readonly import list_runs


class GithubActionsRunsReadonlyTests(unittest.TestCase):
    def test_manual_run_discovery(self):
        row = {"databaseId": 321, "url": "https://github.com/alston-personal/agentmanager/actions/runs/321",
               "headSha": "a" * 40, "status": "completed", "conclusion": "success",
               "createdAt": "2026-10-16T01:00:00Z"}
        runner = Mock(return_value=SimpleNamespace(returncode=0, stdout=json.dumps([row])))
        result = list_runs({"workflow": "oracle-deploy-invoice-intake-service.yml"}, runner=runner)
        self.assertTrue(result["ok"])
        self.assertEqual(result["latest"]["run_id"], 321)
        args = runner.call_args.args[0]
        self.assertEqual(args[:3], ["/usr/bin/gh", "run", "list"])
        self.assertEqual(args[args.index("--event")+1], "workflow_dispatch")
        self.assertNotIn("workflow", args[:3])

    def test_rejects_unapproved_workflow(self):
        with self.assertRaises(ValueError):
            list_runs({"workflow": "other.yml"})

    def test_rejects_repo_or_nonmanual_event(self):
        for params in ({"workflow": "oracle-deploy-invoice-intake-service.yml", "repository": "someone/repo"},
                       {"workflow": "oracle-deploy-invoice-intake-service.yml", "event": "push"}):
            with self.assertRaises(ValueError):
                list_runs(params)

    def test_rejects_unbounded_limit(self):
        for limit in (0, 21, True, "20"):
            with self.assertRaises(ValueError):
                list_runs({"workflow": "oracle-deploy-invoice-intake-service.yml", "limit": limit})

    def test_auth_error_is_redacted(self):
        runner = Mock(return_value=SimpleNamespace(returncode=1, stdout="secret", stderr="token"))
        result = list_runs({"workflow": "oracle-deploy-invoice-intake-service.yml"}, runner=runner)
        self.assertFalse(result["ok"])
        self.assertNotIn("secret", str(result))
        self.assertNotIn("token", str(result))


if __name__ == "__main__":
    unittest.main()
