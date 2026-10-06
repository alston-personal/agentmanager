from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install_galaxy_threads_experiment_monitor_user.sh"


class GalaxyMonitorImmutableRuntimeTests(unittest.TestCase):
    def test_installer_materializes_exact_release(self):
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('SOURCE_COMMIT="${AGENTOS_SOURCE_COMMIT:-}"', text)
        self.assertIn('RUNTIME_BASE="$HOME/.local/share/agentos/galaxy-experiment-monitor"', text)
        self.assertIn('RELEASE="$RELEASE_ROOT/$SOURCE_COMMIT"', text)
        self.assertIn('git -C "$REPO" archive "$SOURCE_COMMIT"', text)
        self.assertIn('source_commit=$SOURCE_COMMIT', text)
        self.assertIn('ln -sfn "$RELEASE" "$CURRENT"', text)

    def test_live_units_execute_from_release_not_source_cache(self):
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('WorkingDirectory=$RELEASE', text)
        self.assertIn('Environment=PYTHONPATH=$RELEASE', text)
        self.assertIn('$RELEASE/scripts/monitor_galaxy_threads_experiment_user.py', text)
        self.assertIn('galaxy_experiment_monitor_mutable_checkout_write=NONE', text)
        self.assertNotIn('WorkingDirectory=$REPO', text)
        self.assertNotIn('PYTHONPATH="$REPO"', text)
        self.assertNotIn('install -m 0644 "$tmp" "$REPO/', text)

    def test_source_cache_is_read_only_input(self):
        text = INSTALLER.read_text(encoding="utf-8")
        allowed = [
            'git -C "$REPO" fetch --no-tags origin "$SOURCE_COMMIT"',
            'git -C "$REPO" cat-file -e "$SOURCE_COMMIT^{commit}"',
            'git -C "$REPO" archive "$SOURCE_COMMIT"',
        ]
        repo_lines = [line.strip() for line in text.splitlines() if '$REPO' in line]
        for line in repo_lines:
            self.assertTrue(any(item in line for item in allowed) or 'test -d "$REPO/.git"' in line, line)



    def test_migration_workflow_uses_runner_window_not_direct_oracle(self):
        workflow = (ROOT / ".github" / "workflows" / "oracle-install-galaxy-threads-experiment-monitor.yml").read_text(encoding="utf-8")
        self.assertIn("runs-on: ubuntu-latest", workflow)
        self.assertIn("bash scripts/agentos_dispatch.sh social.monitor runtime.migrate", workflow)
        self.assertIn("galaxy_monitor_runtime_migration_receipt=PASS", workflow)
        self.assertNotIn("runs-on: [self-hosted, Linux, ARM64, oracle]", workflow)

    def test_migration_helper_does_not_trigger_social_cycle(self):
        migration = (ROOT / "scripts" / "migrate_galaxy_monitor_immutable_runtime_user.sh").read_text(encoding="utf-8")
        self.assertIn("galaxy_monitor_runtime_social_cycle_triggered=NO", migration)
        self.assertIn("galaxy_monitor_runtime_mutable_checkout_write=NONE", migration)

if __name__ == "__main__":
    unittest.main()
