"""Isolated fault injection for the existing Action Relay rollback routine.

Runs the rollback shell function in temporary paths with mocked git/systemctl,
without invoking the production installer or touching Oracle services.
"""
from pathlib import Path
import os
import shlex
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install_action_relay_user.sh"


class ActionRelayRollbackInjectionTest(unittest.TestCase):
    def _run_rollback(self, fail_git=False):
        script = SCRIPT.read_text(encoding="utf-8")
        start = script.index("rollback_action_relay_install() {")
        end = script.index("\ntrap 'rollback_action_relay_install", start)
        function = script[start:end]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = root / "snapshot"
            snapshot.mkdir()
            unit = root / "action-relay.service"
            marker = root / "capabilities.json"
            (snapshot / "unit").write_text("old unit", encoding="utf-8")
            (snapshot / "capabilities").write_text("old capability", encoding="utf-8")
            unit.write_text("new unit", encoding="utf-8")
            marker.write_text("new capability", encoding="utf-8")
            log = root / "commands.log"
            prelude = f"""
TXN_DIR={shlex.quote(str(snapshot))}
UNIT={shlex.quote(str(unit))}
CAPABILITY_MARKER={shlex.quote(str(marker))}
RUNTIME_ROOT={shlex.quote(str(root / "runtime"))}
REPO={shlex.quote(str(root / "repo"))}
LEGACY_RUNTIME_ROOT={shlex.quote(str(root / "legacy"))}
TXN_COMMITTED=0
TXN_UNIT_TOUCHED=1
TXN_RUNTIME_KIND=worktree
TXN_OLD_HEAD=1111111111111111111111111111111111111111
TXN_UNIT_PRESENT=1
TXN_MARKER_PRESENT=1
TXN_OLD_ACTIVE=1
TXN_OLD_ENABLED=1
LOG={shlex.quote(str(log))}
ACTIVE=1
ENABLED=1
git() {{
  printf "git %s\\n" "$*" >> "$LOG"
  if [ "${{INJECT_GIT_FAILURE:-0}}" = 1 ]; then return 40; fi
  if [ "$3" = "rev-parse" ]; then printf '%s\\n' "$TXN_OLD_HEAD"; fi
  return 0
}}
systemctl() {{
  printf "systemctl %s\\n" "$*" >> "$LOG"
  case "$*" in
    "--user stop agentos-action-relay.service") ACTIVE=0 ;;
    "--user start agentos-action-relay.service") ACTIVE=1 ;;
    "--user enable agentos-action-relay.service") ENABLED=1 ;;
    "--user disable agentos-action-relay.service") ENABLED=0 ;;
    "--user is-active --quiet agentos-action-relay.service")
      [ "$ACTIVE" = 1 ]; return ;;
    "--user is-enabled --quiet agentos-action-relay.service")
      [ "$ENABLED" = 1 ]; return ;;
  esac
  return 0
}}
"""
            env = dict(os.environ, INJECT_GIT_FAILURE="1" if fail_git else "0")
            completed = subprocess.run(
                ["bash", "-c", "set -euo pipefail\n" + prelude + function + "\nrollback_action_relay_install 15\n"],
                env=env, text=True, capture_output=True, check=False,
                timeout=10,
            )
            return {
                "returncode": completed.returncode,
                "stderr": completed.stderr,
                "unit": unit.read_text(encoding="utf-8"),
                "marker": marker.read_text(encoding="utf-8"),
                "snapshot_exists": snapshot.exists(),
                "commands": log.read_text(encoding="utf-8"),
            }

    def test_injected_failure_restores_unit_marker_and_old_generation(self):
        r = self._run_rollback()
        self.assertEqual(r["returncode"], 15)
        self.assertIn("action_relay_transaction=ROLLED_BACK", r["stderr"])
        self.assertEqual(r["unit"], "old unit")
        self.assertEqual(r["marker"], "old capability")
        self.assertFalse(r["snapshot_exists"])
        self.assertIn("reset --hard 1111111111111111111111111111111111111111", r["commands"])
        self.assertIn("systemctl --user daemon-reload", r["commands"])
        self.assertIn("systemctl --user start agentos-action-relay.service", r["commands"])

    def test_injected_rollback_failure_keeps_snapshot_and_reports_failure(self):
        r = self._run_rollback(fail_git=True)
        self.assertEqual(r["returncode"], 15)
        self.assertIn("action_relay_transaction=ROLLBACK_FAILED", r["stderr"])
        self.assertTrue(r["snapshot_exists"])
        self.assertNotIn("action_relay_transaction=ROLLED_BACK", r["stderr"])


if __name__ == "__main__":
    unittest.main()
