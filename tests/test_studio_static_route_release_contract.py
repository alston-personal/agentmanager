from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
REUSABLE = ROOT / ".github/workflows/reusable-studio-static-route-release.yml"
CONSUMER = ROOT / ".github/workflows/oracle-release-milkcat-world-mvp.yml"
GOVERNANCE = ROOT / ".agent/governance/studio_release_capabilities.yaml"


class StudioStaticRouteReleaseContractTest(unittest.TestCase):
    def test_reusable_workflow_has_required_safety_contract(self):
        text = REUSABLE.read_text(encoding="utf-8")
        for required in (
            "workflow_call:",
            "acceptance_anchors:",
            "rollback()",
            "local_nginx_studio_static_route_acceptance=PASS",
            "public_studio_static_route_acceptance=PASS",
            "studio_static_route_deploy=PASS",
        ):
            self.assertIn(required, text)

    def test_world_is_parameter_only_consumer(self):
        text = CONSUMER.read_text(encoding="utf-8")
        self.assertIn("uses: ./.github/workflows/reusable-studio-static-route-release.yml", text)
        self.assertIn("route: world", text)
        self.assertNotIn("npm run build", text)
        self.assertNotIn("ssh -o StrictHostKeyChecking", text)

    def test_governance_registry_names_canonical_capability(self):
        text = GOVERNANCE.read_text(encoding="utf-8")
        self.assertIn("studio_static_route_release:", text)
        self.assertIn("status: extracted-first-consumer", text)
        self.assertIn("verified_run: 35192062500", text)


if __name__ == "__main__":
    unittest.main()
