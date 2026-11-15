"""The existing Bootstrap Control transport repair must not route to legacy integration."""
import unittest
from unittest.mock import patch

from agentos_node import bootstrap_control


class TransportRepairCanonicalSourceTest(unittest.TestCase):
    def test_exact_source_repair_uses_main_not_integration(self):
        source = "a" * 40
        with patch.object(bootstrap_control, "_run_canonical_script", return_value={"ok": True}) as call:
            result = bootstrap_control._execute(bootstrap_control.ACTION_REPAIR_TRANSPORT, source)
        self.assertEqual(result, {"ok": True})
        call.assert_called_once_with(
            "scripts/repair_antigravity_relay_user.sh",
            timeout=180,
            source_commit=source,
            env_extra={"AGENTOS_ACTION_SPOOL_PREPROVISIONED": "1", "AGENTOS_REF": "main"},
        )

    def test_unpinned_repair_cannot_default_to_integration(self):
        with patch.object(bootstrap_control, "_run_canonical_script", return_value={"ok": True}) as call:
            bootstrap_control._execute(bootstrap_control.ACTION_REPAIR_TRANSPORT, None)
        self.assertEqual(call.call_args.kwargs["env_extra"]["AGENTOS_REF"], "main")
        self.assertIsNone(call.call_args.kwargs["source_commit"])

    def test_manual_safe_chronos_uses_real_ubuntu_owner_not_agentos_node_runner(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github/workflows/oracle-bootstrap-action-relay-via-chronos-safe.yml").read_text(encoding="utf-8")
        script = root / "scripts/bootstrap_action_relay_via_chronos_safe_v2.sh"
        import subprocess
        self.assertEqual(subprocess.run(["bash", "-n", str(script)], capture_output=True).returncode, 0)
        self.assertIn("  workflow_dispatch:", workflow)
        self.assertNotIn("  push:", workflow)
        self.assertNotIn("  issue_comment:", workflow)
        self.assertNotIn("runs-on: [self-hosted, Linux, ARM64, oracle]", workflow)
        self.assertIn("runs-on: ubuntu-latest", workflow)
        self.assertIn('test "$GITHUB_EVENT_NAME" = workflow_dispatch', workflow)
        self.assertIn('test "$GITHUB_REF_NAME" = main', workflow)
        self.assertIn('test "$(git rev-parse HEAD)" = "$GITHUB_SHA"', workflow)
        self.assertIn('test "${DEPLOY_USER:-}" = ubuntu', workflow)
        self.assertIn('test "$(id -un)" = ubuntu', workflow)
        self.assertIn('test "$(git -C /home/ubuntu/agentmanager rev-parse origin/main)" = "$expected"', workflow)
        self.assertIn("AGENTOS_SOURCE_COMMIT=$GITHUB_SHA GITHUB_RUN_ID=$GITHUB_RUN_ID bash -s", workflow)
        self.assertIn("< scripts/bootstrap_action_relay_via_chronos_safe_v2.sh", workflow)
        self.assertIn("webfactory/ssh-agent@v0.9.0", workflow)
        self.assertIn("chmod 2770", script.read_text(encoding="utf-8"))
        self.assertNotIn("sudo ", workflow)
        self.assertNotIn("systemctl --user restart", workflow)

    def test_existing_repair_script_enforces_exact_sha_and_realm_separation(self):
        from pathlib import Path
        script = (Path(__file__).resolve().parents[1] / "scripts" /
                  "repair_antigravity_relay_user.sh").read_text(encoding="utf-8")
        self.assertIn('git -C "$REPO" merge-base --is-ancestor "$SOURCE_COMMIT" "$SOURCE_REF_HEAD"', script)
        self.assertIn('realm_fabric_mutation=NONE', script)
        self.assertNotIn("systemctl --user restart agentos-realm-fabric.service", script)


if __name__ == "__main__":
    unittest.main()
