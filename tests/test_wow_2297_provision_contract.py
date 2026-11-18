"""Contract tests: fixed #2297 repo provisioning is NOT generic GitHub execution."""
from __future__ import annotations

import subprocess
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from agentos_node import bootstrap_control as bootstrap

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/provision_wow_2297_repos_user.sh"
WORKFLOW = ROOT / ".github/workflows/oracle-provision-ziwei-master-via-bootstrap.yml"


class WoW2297ProvisionContract(unittest.TestCase):
    def test_fixed_script_syntax_and_identity(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True).returncode, 0)
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('test "$(id -un)" = "ubuntu"', script)
        self.assertIn("unset GH_TOKEN GITHUB_TOKEN", script)
        self.assertIn("for name in wow-agentos-addon wow-nav-assist;", script)
        self.assertIn('gh repo create "$repo" --private', script)
        self.assertIn('test "$actual_name" = "$repo"', script)
        self.assertIn('test "$is_private" = "true"', script)
        self.assertNotIn("$1", script)
        self.assertNotIn("eval ", script)

    def test_live_workflow_bash_is_syntactically_valid_and_single_shot(self):
        """Compile the REAL workflow run payload; token-matching alone missed a broken quote."""
        workflow = WORKFLOW.read_text(encoding="utf-8")
        marker = "        run: |\\n"
        self.assertEqual(workflow.count(marker), 1)
        script = textwrap.dedent(workflow.split(marker, 1)[1])
        checked = subprocess.run(["bash", "-n"], input=script, text=True,
                                 capture_output=True, check=False)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(script.count('python3 - "$REQUEST"'), 1)
        self.assertEqual(script.count('python3 - "$RECEIPT"'), 1)
        self.assertEqual(script.count("wow_2297_repo_provision=PASS"), 1)
        self.assertIn("grep -Eq '^[0-9a-f]{40}
        action = bootstrap.ACTION_PROVISION_WOW_2297_REPOS
        self.assertIn(action, bootstrap.ALLOWED_ACTIONS)
        with patch.object(bootstrap, "_run_canonical_script", return_value={"ok": True}) as fn:
            self.assertEqual(bootstrap._execute(action, "a"*40), {"ok": True})
        fn.assert_called_once_with("scripts/provision_wow_2297_repos_user.sh",
                                   timeout=150, source_commit="a"*40)

    def test_dispatch_is_manual_exact_actor_and_uses_bootstrap(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:", text)
        self.assertNotIn("  push:", text)
        self.assertNotIn("  schedule:", text)
        self.assertIn("github.actor == 'alstonhuang'", text)
        self.assertIn("test \"$GITHUB_SHA\" = \"$SOURCE_COMMIT\"", text)
        self.assertIn("agentos.repository.provision_wow_2297_repos", text)
        self.assertIn("agentos.bootstrap-request/v1", text)
        self.assertIn("agentos.bootstrap-receipt/v1", text)
        self.assertIn("assert r.get('ok') is True", text)
        self.assertIn("wow_2297_repo_provision=PASS", text)


if __name__ == "__main__":
    unittest.main()
", script)
        self.assertLess(script.index('test "$GITHUB_SHA" = "$SOURCE_COMMIT"'),
                        script.index('python3 - "$REQUEST"'))

    def test_bootstrap_existing_fixed_action_selected(self):
        action = bootstrap.ACTION_PROVISION_WOW_2297_REPOS
        self.assertIn(action, bootstrap.ALLOWED_ACTIONS)
        with patch.object(bootstrap, "_run_canonical_script", return_value={"ok": True}) as fn:
            self.assertEqual(bootstrap._execute(action, "a"*40), {"ok": True})
        fn.assert_called_once_with("scripts/provision_wow_2297_repos_user.sh",
                                   timeout=150, source_commit="a"*40)

    def test_dispatch_is_manual_exact_actor_and_uses_bootstrap(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:", text)
        self.assertNotIn("  push:", text)
        self.assertNotIn("  schedule:", text)
        self.assertIn("github.actor == 'alstonhuang'", text)
        self.assertIn("test \"$GITHUB_SHA\" = \"$SOURCE_COMMIT\"", text)
        self.assertIn("agentos.repository.provision_wow_2297_repos", text)
        self.assertIn("agentos.bootstrap-request/v1", text)
        self.assertIn("agentos.bootstrap-receipt/v1", text)
        self.assertIn("assert r.get('ok') is True", text)
        self.assertIn("wow_2297_repo_provision=PASS", text)


if __name__ == "__main__":
    unittest.main()
