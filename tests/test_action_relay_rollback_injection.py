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
    def _run_rollback(self, fail_git=False, incorrect_readback=False, stuck_running=False,
                      missing_legacy_backup=False, dirty_restored_worktree=False):
        script = SCRIPT.read_text(encoding="utf-8")
        start = script.index("rollback_action_relay_install() {")
        end = script.index("\n}\n# The only recovery route", start) + 2
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
            if missing_legacy_backup:
                (root / "runtime").mkdir()
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
TXN_RUNTIME_KIND={"directory" if missing_legacy_backup else "worktree"}
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
  if [ "$3" = "status" ]; then
    if [ "${INJECT_DIRTY_WORKTREE:-0}" = 1 ]; then printf '?? new-generation-residue.py\\n'; fi
  fi
  if [ "$3" = "rev-parse" ]; then
    if [ "${{INJECT_BAD_READBACK:-0}}" = 1 ]; then printf '%040d\\n' 0
    else printf '%s\\n' "$TXN_OLD_HEAD"; fi
  fi
  return 0
}}
systemctl() {{
  printf "systemctl %s\\n" "$*" >> "$LOG"
  case "$*" in
    "--user stop agentos-action-relay.service")
      if [ "${{INJECT_STUCK_RUNNING:-0}}" != 1 ]; then ACTIVE=0; fi ;;
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
            env = dict(os.environ, INJECT_GIT_FAILURE="1" if fail_git else "0",
                       INJECT_BAD_READBACK="1" if incorrect_readback else "0",
                       INJECT_STUCK_RUNNING="1" if stuck_running else "0",
                       INJECT_DIRTY_WORKTREE="1" if dirty_restored_worktree else "0")
            completed = subprocess.run(
                ["bash", "-c", "set -euo pipefail\n" + prelude + function + "\nrollback_action_relay_install 15\n"],
                env=env, text=True, capture_output=True, check=False,
                timeout=10,
            )
            return {
                "returncode": completed.returncode,
                "stderr": completed.stderr,
                "unit": unit.read_text(encoding="utf-8"),
                "marker": marker.read_text(encoding="utf-8") if marker.exists() else None,
                "snapshot_exists": snapshot.exists(),
                "commands": log.read_text(encoding="utf-8"),
            }

    def test_persisted_transaction_metadata_is_parseable_newline_record(self):
        source = SCRIPT.read_text(encoding="utf-8")
        line = next(line for line in source.splitlines()
                    if line.startswith('printf "prior_kind='))
        fmt = line.split('"')[1]
        self.assertIn(r"\n", fmt)
        self.assertNotIn(r"\\n", fmt)
        rendered = subprocess.run(
            ["bash", "-c", 'printf "' + fmt + '" worktree '
             + '1111111111111111111111111111111111111111 1 1 1 1'],
            check=True, capture_output=True, text=True,
        ).stdout
        self.assertTrue(rendered.endswith("\n"))
        self.assertNotIn(r"\n", rendered)
        self.assertEqual(len(rendered.splitlines()), 1)
        self.assertIn("prior_kind=worktree prior_head=", rendered)

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

    def test_missing_legacy_directory_backup_fails_closed(self):
        r = self._run_rollback(missing_legacy_backup=True)
        self.assertEqual(r["returncode"], 74)
        self.assertIn("action_relay_transaction=ROLLBACK_FAILED", r["stderr"])
        self.assertNotIn("action_relay_transaction=ROLLED_BACK", r["stderr"])
        self.assertTrue(r["snapshot_exists"])
        self.assertIsNone(r["marker"])

    def test_untracked_worktree_residue_never_claims_rollback_success(self):
        r = self._run_rollback(dirty_restored_worktree=True)
        self.assertEqual(r["returncode"], 74)
        self.assertIn("action_relay_transaction=ROLLBACK_FAILED", r["stderr"])
        self.assertNotIn("action_relay_transaction=ROLLED_BACK", r["stderr"])
        self.assertTrue(r["snapshot_exists"])
        self.assertIsNone(r["marker"])
        self.assertIn("status --porcelain --untracked-files=all", r["commands"])

    def test_generation_readback_mismatch_never_claims_rollback_success(self):
        r = self._run_rollback(incorrect_readback=True)
        self.assertIn("action_relay_transaction=ROLLBACK_FAILED", r["stderr"])
        self.assertTrue(r["snapshot_exists"])
        self.assertEqual(r["returncode"], 74)
        self.assertIsNone(r["marker"])

    def test_running_consumer_blocks_worktree_restore(self):
        r = self._run_rollback(stuck_running=True)
        self.assertIn("reason=service_remains_active", r["stderr"])
        self.assertTrue(r["snapshot_exists"])
        self.assertNotIn("reset --hard", r["commands"])
        self.assertIsNone(r["marker"])

    def test_injected_rollback_failure_keeps_snapshot_and_reports_failure(self):
        r = self._run_rollback(fail_git=True)
        self.assertEqual(r["returncode"], 74)
        self.assertIn("action_relay_transaction=ROLLBACK_FAILED", r["stderr"])
        self.assertTrue(r["snapshot_exists"])
        self.assertNotIn("action_relay_transaction=ROLLED_BACK", r["stderr"])
        self.assertIsNone(r["marker"])


if __name__ == "__main__":
    unittest.main()
