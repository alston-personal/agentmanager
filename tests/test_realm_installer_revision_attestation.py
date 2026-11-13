"""Fail-closed source contract: live status must attest effective-unit fence revision.

This does not install, claim leases or mutate a running Realm service.
"""
from __future__ import annotations
import unittest
from unittest.mock import patch

from agentos_node import action_relay

REVISION = "realm-fabric-effective-unit-fence/v1"


class RealmInstallerRevisionTests(unittest.TestCase):
    @patch.object(action_relay, "_observed_realm_commit", return_value="a" * 40)
    @patch.object(action_relay, "_deployment_state_read", return_value={
        "deployment_generation": 13, "desired_core_commit": "a" * 40,
    })
    def test_live_status_returns_installer_revision(self, *_):
        status = action_relay._realm_fabric_deployment_status({})
        self.assertTrue(status["ok"])
        self.assertEqual(status["installer_revision"], REVISION)
        self.assertEqual(status["deployment_status"], "converged")
        self.assertEqual(status["deployment_generation"], 13)

    def test_untrusted_arguments_cannot_supply_claimed_revision(self):
        for params in (
            {"installer_revision": REVISION},
            {"source_commit": "a" * 40},
            {"cmd": "sudo systemctl restart"},
        ):
            with self.subTest(params=params), self.assertRaises(ValueError):
                action_relay._realm_fabric_deployment_status(params)

    def test_deploy_workflow_rejects_old_live_relay_before_realm_install(self):
        from pathlib import Path
        workflow = (Path(__file__).resolve().parents[1] /
                    ".github/workflows/deploy-realm-fabric-core.yml").read_text()
        proof = workflow.split("      - name: Ensure ubuntu Action Relay runtime contains governed Core capabilities", 1)[1].split(
            "      - name: Install exact Realm Fabric release through Action Relay", 1
        )[0]
        self.assertIn("receipt.get('installer_revision') != 'realm-fabric-effective-unit-fence/v1'", proof)
        self.assertIn("realm_relay_installer_revision_not_attested", proof)
        self.assertIn("realm_deployment_blocked=INSTALLED_RELAY_REVISION_UNVERIFIED", proof)
        self.assertNotIn("bootstrap-action-relay-core-safe.sh", proof)
        self.assertNotIn("READY_AFTER_REFRESH", proof)

    def test_deploy_workflow_pins_checkout_and_does_not_reset_moving_main(self):
        from pathlib import Path
        workflow = (Path(__file__).resolve().parents[1] /
                    ".github/workflows/deploy-realm-fabric-core.yml").read_text()
        self.assertNotIn("git reset --hard origin/main", workflow)
        self.assertEqual(workflow.count('test "$(git rev-parse HEAD)" = "$GITHUB_SHA"'), 2)
        self.assertIn('test "$GITHUB_REF_TYPE" = "branch"', workflow)
        self.assertIn('test "$GITHUB_REF_NAME" = "main"', workflow)

    def test_existing_exact_realm_installer_has_effective_unit_quarantine(self):
        from pathlib import Path
        body = (Path(__file__).resolve().parents[1] / "agentos_node/action_relay.py").read_text()
        self.assertIn("realm_fabric_effective_unit_fence_v1", body)
        self.assertIn("unrecognized runtime-generation.conf; refusing mutation", body)
        self.assertIn("quarantine_legacy_runtime_generation_dropin", body)
        self.assertEqual(body.count("'installer_revision': 'realm-fabric-effective-unit-fence/v1'"), 2)


if __name__ == "__main__":
    unittest.main()
