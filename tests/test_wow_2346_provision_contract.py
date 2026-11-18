"""The Suite is a separate, fixed-scope repository provision action, not #2297."""
import subprocess
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from agentos_node import bootstrap_control as bootstrap

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/provision_wow_2346_suite_repo_user.sh"
WORKFLOW = ROOT / ".github/workflows/oracle-provision-ziwei-master-via-bootstrap.yml"


class Wow2346SuiteRepoProvisionContract(unittest.TestCase):
    def test_suite_script_fixed_identity_and_private(self):
        result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        content = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('test "$(id -un)" = "ubuntu"', content)
        self.assertIn("unset GH_TOKEN GITHUB_TOKEN", content)
        self.assertIn('repo="alston-personal/wow-companion-suite"', content)
        self.assertIn('gh repo create "$repo" --private --add-readme', content)
        self.assertIn('test "$actual_name" = "$repo"', content)
        self.assertIn('test "$is_private" = "true"', content)
        self.assertIn('test "$default_branch" = "main"', content)
        self.assertNotIn("$1", content)
        self.assertNotIn("eval ", content)
        self.assertNotIn("wow-nav-assist", content)
        self.assertNotIn("wow-agentos-addon", content)

    def test_suite_action_is_distinct_from_2297(self):
        self.assertNotEqual(bootstrap.ACTION_PROVISION_WOW_2346_SUITE_REPO,
                            bootstrap.ACTION_PROVISION_WOW_2297_REPOS)
        self.assertIn(bootstrap.ACTION_PROVISION_WOW_2346_SUITE_REPO,
                      bootstrap.ALLOWED_ACTIONS)
        with patch.object(bootstrap, "_run_canonical_script", return_value={"ok": True}) as fn:
            self.assertEqual(bootstrap._execute(bootstrap.ACTION_PROVISION_WOW_2346_SUITE_REPO,
                                                  "a"*40), {"ok": True})
        fn.assert_called_once_with("scripts/provision_wow_2346_suite_repo_user.sh",
                                   timeout=120, source_commit="a"*40)

    def test_rejects_unpinned_suite_bootstrap_request(self):
        req = {
            "schema": bootstrap.SCHEMA,
            "request_id": "demo",
            "action": bootstrap.ACTION_PROVISION_WOW_2346_SUITE_REPO,
            "params": {},
        }
        with self.assertRaisesRegex(ValueError, "requires exact source_commit"):
            bootstrap._validate_request(Path("/tmp/demo.request.json"), req)

    def test_rejects_arbitrary_repository_parameter(self):
        req = {
            "schema": bootstrap.SCHEMA,
            "request_id": "demo",
            "action": bootstrap.ACTION_PROVISION_WOW_2346_SUITE_REPO,
            "params": {"source_commit": "a"*40, "repository": "evil/other"},
        }
        with self.assertRaisesRegex(ValueError, "unsupported bootstrap params"):
            bootstrap._validate_request(Path("/tmp/demo.request.json"), req)

    def test_workflow_exact_owner_and_main_sha_guard(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("github.actor == 'alstonhuang'", source)
        self.assertIn("  workflow_dispatch:", source)
        self.assertNotIn("  schedule:", source)
        self.assertNotIn("  push:", source)
        self.assertIn("          - wow-2297", source)
        self.assertIn("          - wow-2346", source)
        self.assertIn("ACTION=agentos.repository.provision_wow_2346_suite_repo", source)
        self.assertIn('test "$GITHUB_SHA" = "$SOURCE_COMMIT"', source)
        self.assertIn("wow_2346_repository_provision=PASS", source)
        self.assertIn("'default_branch=main' in lines", source)

    def test_existing_shared_workflow_shell_stays_valid(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        marker = "        run: |" + chr(10)
        self.assertEqual(workflow.count(marker), 1)
        script = textwrap.dedent(workflow.split(marker, 1)[1])
        result = subprocess.run(["bash", "-n"], input=script, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(script.count('python3 - "$REQUEST"'), 1)
        self.assertEqual(script.count('python3 - "$RECEIPT"'), 1)


if __name__ == "__main__":
    unittest.main()
