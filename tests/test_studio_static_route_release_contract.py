from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
REUSABLE = ROOT / ".github/workflows/reusable-studio-static-route-release.yml"
CONSUMER = ROOT / ".github/workflows/oracle-release-milkcat-world-mvp.yml"
GOVERNANCE = ROOT / ".agent/governance/studio_release_capabilities.yaml"
ASSET = ROOT / "docs/asset-registry/studio-static-route-release.yaml"


class StudioStaticRouteReleaseContractTest(unittest.TestCase):
    def test_reusable_workflow_has_required_safety_contract(self):
        text = REUSABLE.read_text(encoding="utf-8")
        for required in (
            "workflow_call:",
            "acceptance_anchors:",
            "rollback()",
            "local_nginx_studio_static_route_acceptance=PASS",
            "public_studio_static_route_acceptance=PASS",
            "Roll back route after public acceptance failure",
            "steps.publish.outcome == 'success'",
            "public_failure_rollback=PASS",
            "failure_stage=public_acceptance",
            "studio_static_route_deploy=PASS",
        ):
            self.assertIn(required, text)

    def test_nested_world_halls_are_checked_before_existing_public_failure_rollback(self):
        reusable = REUSABLE.read_text(encoding="utf-8")
        consumer = CONSUMER.read_text(encoding="utf-8")
        self.assertIn("acceptance_nested_routes:", reusable)
        self.assertIn("acceptance_nested_anchors:", reusable)
        self.assertIn("public_studio_static_nested_route_acceptance=PASS", reusable)
        self.assertLess(
            reusable.index("public_studio_static_nested_route_acceptance=PASS"),
            reusable.index("- name: Roll back route after public acceptance failure"),
        )
        for hall in ("tarot", "ziwei", "library", "gallery", "layoutlib", "fengshui", "lab"):
            self.assertIn(f"        {hall}", consumer)
        self.assertIn("        回到本館入口", consumer)
        self.assertIn("        .hall-shell", consumer)
        # Unlaunched Ziwei has a deliberately disabled link; all seven pages
        # still require native World return, inlined CSS, and a destination card.
        self.assertNotIn('        target="_blank"', consumer)
        self.assertIn('        destination-card', consumer)
        self.assertIn('        .hall-shell', consumer)

    def test_world_es_module_is_verified_as_executable_before_success_and_rollback(self):
        reusable = REUSABLE.read_text(encoding="utf-8")
        consumer = CONSUMER.read_text(encoding="utf-8")
        self.assertIn("acceptance_js_module:", reusable)
        self.assertIn("acceptance_js_anchor:", reusable)
        self.assertIn("public_studio_static_js_module_acceptance=PASS", reusable)
        self.assertIn("public JS module MIME rejected", reusable)
        self.assertLess(
            reusable.index("public_studio_static_js_module_acceptance=PASS"),
            reusable.index("- name: Roll back route after public acceptance failure"),
        )
        self.assertIn("acceptance_focused_nested_route: layoutlib", consumer)
        self.assertIn("acceptance_focused_nested_anchor: 'href=\"/layout-lab/\"'", consumer)
        self.assertIn("public_studio_static_focused_nested_route_acceptance=PASS", reusable)
        self.assertLess(
            reusable.index("public_studio_static_focused_nested_route_acceptance=PASS"),
            reusable.index("- name: Roll back route after public acceptance failure"),
        )
        self.assertIn("acceptance_js_module: world-navigation.js", consumer)
        self.assertIn("acceptance_js_anchor: export function createWalkabilityMap", consumer)
        self.assertIn("        /world/world-navigation.js", consumer)
        self.assertNotIn("        /world/world-navigation.mjs", consumer)

    def test_reusable_workflow_has_opt_in_platform_execution_contract(self):
        text = REUSABLE.read_text(encoding="utf-8")
        for required in (
            "credit_account:",
            "credit_cost:",
            "Prepare governed platform execution",
            "scripts/milkcat_platform_execution.py prepare",
            "--capability studio.static-route.release",
            "--sync-studio-capabilities",
            "Settle governed platform execution",
            "scripts/milkcat_platform_execution.py settle",
            "inputs.credit_account != ''",
        ):
            self.assertIn(required, text)
        self.assertIn("default: ''", text)
        self.assertIn("default: 0", text)

    def test_world_is_parameter_only_consumer(self):
        text = CONSUMER.read_text(encoding="utf-8")
        self.assertIn("uses: ./.github/workflows/reusable-studio-static-route-release.yml", text)
        self.assertIn("route: world", text)
        self.assertIn("credit_account: ${{ inputs.credit_account || '' }}", text)
        self.assertIn("credit_cost: ${{ inputs.credit_cost || 0 }}", text)
        self.assertNotIn("npm run build", text)
        self.assertNotIn("ssh -o StrictHostKeyChecking", text)
        self.assertNotIn("milkcat_platform_execution.py", text)

    def test_governance_registry_names_canonical_capability(self):
        text = GOVERNANCE.read_text(encoding="utf-8")
        self.assertIn("studio_static_route_release:", text)
        self.assertIn("provider_id: service://studio.static-route.release", text)
        self.assertIn("capability_uri: capability://studio.static-route.release", text)
        self.assertIn("status: extracted-first-consumer", text)
        self.assertIn("status: production-verified-before-extraction", text)
        self.assertIn("verified_run: 35192062500", text)

    def test_asset_registry_points_to_canonical_source_and_live_evidence(self):
        text = ASSET.read_text(encoding="utf-8")
        self.assertIn("asset_id: studio-static-route-release", text)
        self.assertIn("canonical_source: .github/workflows/reusable-studio-static-route-release.yml", text)
        self.assertIn("first_consumer: milkcat-world", text)
        self.assertIn("evidence_scope: shared-carrier-live", text)
        self.assertIn("predecessor_release_run: 35192062500", text)
        self.assertIn("shared_carrier_live_verification: passed", text)
        self.assertIn("shared_carrier_release_run: 35199712046", text)
        self.assertIn("shared_carrier_main_commit: 369585b7d4a6f3885e0d0c79aeca57b8957fd164", text)
        self.assertIn("shared_carrier_contract_acceptance: passed", text)
        self.assertIn("shared_carrier_build_publish_acceptance: passed", text)
        self.assertIn("shared_carrier_public_acceptance: passed", text)
        self.assertIn("public_failure_rollback_path: present-and-not-triggered", text)
        self.assertIn("broadly_proven_requires: second-production-consumer", text)


if __name__ == "__main__":
    unittest.main()
