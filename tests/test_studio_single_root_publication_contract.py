"""Regression guard for retiring ZeusWriter as a Studio publication authority.

Source-only tests. They intentionally cannot assert a live Nginx cutover or a
successful public site publication.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    ".github/workflows/reusable-studio-static-route-release.yml",
    ".github/workflows/oracle-cutover-milkcat-world-home.yml",
    "scripts/deploy_layoutlab_static.py",
    "scripts/deploy_layoutlab_v07_release.py",
    "agentos_node/action_relay.py",
    "agentos_node/layoutlib_production_promote_provider.py",
    ".github/workflows/validate-resource-registry.yml",
)
PUBLISHERS = TARGETS[:2]


class StudioSingleRootPublicationContractTests(unittest.TestCase):
    def test_known_publishers_do_not_write_legacy_zeuswriter_root(self):
        for relative in TARGETS:
            with self.subTest(path=relative):
                source = (ROOT / relative).read_text(encoding="utf-8")
                self.assertNotIn("/home/ubuntu/zeus-writer/website/dist", source)

    def test_both_studio_publishers_guard_served_virtual_host(self):
        for relative in PUBLISHERS:
            with self.subTest(path=relative):
                source = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("LIVE=/home/ubuntu/studio-web/dist", source)
                self.assertIn("studio-web-production-root/v1", source)
                self.assertIn("test -f \"$ROOT_MARKER\"", source)
                self.assertIn("studio.milkcat.org:443:127.0.0.1", source)
                self.assertIn("studio_canonical_vhost_not_active", source)
                self.assertIn("studio_canonical_vhost_root_marker=PASS", source)
                self.assertNotIn("nginx -T 2>&1 | grep -Eq", source)

    def test_layoutlib_and_registry_fail_closed_before_real_studio_root_cutover(self):
        layoutlib = (ROOT / "agentos_node/layoutlib_production_promote_provider.py").read_text(encoding="utf-8")
        registry = (ROOT / ".github/workflows/validate-resource-registry.yml").read_text(encoding="utf-8")
        self.assertIn("STUDIO_ROOT_MARKER", layoutlib)
        self.assertIn("LAYOUTLIB_PRODUCTION_STUDIO_ROOT_NOT_ACTIVE", layoutlib)
        self.assertIn("studio-web-production-root/v1", registry)
        self.assertIn('"repository":"alston-personal/studio-web"', registry)
        self.assertIn('test -r "$MARKER"', registry)

    def test_no_implicit_legacy_root_writes_in_documented_migration(self):
        current = (ROOT / "docs/CURRENT_STATE.md").read_text(encoding="utf-8")
        self.assertIn("Studio canonical root convergence", current)
        self.assertIn("NOT DEPLOYED", current)
        self.assertIn("studio-root-authority.txt", current)


if __name__ == "__main__":
    unittest.main()
