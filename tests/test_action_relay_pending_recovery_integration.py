"""Exercise the real installer transaction/recovery section in an isolated shell.

This verifies the actual pending-state parse/restore path, with mocked systemd
and Git interfaces and temporary paths. It does NOT install to Oracle or run the
entire Action Relay installer.
"""
import hashlib
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/install_action_relay_user.sh"
OLD_SHA = "1" * 40


class PendingActionRelayRecoveryIntegrationTest(unittest.TestCase):
    def _run(self, corrupt=False, stuck=False, fail_reset=False, real_git=False, kill_after_reset=False):
        source = SCRIPT.read_text(encoding="utf-8")
        start = source.index('TXN_PARENT=$(dirname "$RUNTIME_ROOT")')
        end = source.index("# Converge to exactly one governed consumer for this spool.", start)
        transaction = source[start:end]
        # The real installer runs as ubuntu. In the isolated temporary fixture
        # validate against the current test user without weakening production.
        transaction = transaction.replace(
            '"ubuntu:700"', '"$(id -un):700"'
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            home = root / "home"
            data = root / "data"
            runtime = root / "runtime" / "action-runtime"
            runtime.parent.mkdir(parents=True)
            old_sha = OLD_SHA
            if real_git:
                repo_path = root / "repo"
                subprocess.run(["git", "init", "-q", str(repo_path)], check=True)
                subprocess.run(["git", "-C", str(repo_path), "config", "user.email", "test@example.invalid"], check=True)
                subprocess.run(["git", "-C", str(repo_path), "config", "user.name", "Isolated Test"], check=True)
                (repo_path / "generation.txt").write_text("old", encoding="utf-8")
                subprocess.run(["git", "-C", str(repo_path), "add", "generation.txt"], check=True)
                subprocess.run(["git", "-C", str(repo_path), "commit", "-qm", "old"], check=True)
                old_sha = subprocess.check_output(["git", "-C", str(repo_path), "rev-parse", "HEAD"], text=True).strip()
                (repo_path / "generation.txt").write_text("new", encoding="utf-8")
                subprocess.run(["git", "-C", str(repo_path), "commit", "-qam", "new"], check=True)
                subprocess.run(["git", "-C", str(repo_path), "worktree", "add", "-q", "--detach", str(runtime)], check=True)
            unit = home / ".config/systemd/user/agentos-action-relay.service"
            marker = data / "runtime/action-relay/capabilities.json"
            unit.parent.mkdir(parents=True)
            marker.parent.mkdir(parents=True)
            pending = runtime.parent / ".action-relay-install.pending"
            pending.mkdir(mode=0o700)
            old_unit = b"[Service]\nDescription=old\n"
            old_marker = b'{"source":"old"}\n'
            (pending / "unit").write_bytes(old_unit)
            (pending / "capabilities").write_bytes(old_marker)
            for name in ("unit", "capabilities"):
                digest = hashlib.sha256((pending / name).read_bytes()).hexdigest()
                (pending / (name + ".sha256")).write_text(
                    digest + "  " + name + "\n", encoding="utf-8"
                )
            (pending / "state").write_text(
                f"prior_kind=worktree prior_head={old_sha} "
                "unit_present=1 marker_present=1 was_active=1 was_enabled=1\n",
                encoding="utf-8"
            )
            if corrupt:
                (pending / "unit").write_bytes(b"CORRUPTED")
            unit.write_text("new unit", encoding="utf-8")
            marker.write_text("new capability", encoding="utf-8")
            command_log = root / "commands.log"
            git_mock = """git() {
  printf 'git %s\\n' "$*" >> "$LOG"
  command git "$@" || return $?
  if [ "$3" = reset ] && [ "${KILL_AFTER_RESET:-0}" = 1 ]; then
    kill -KILL "$"
  fi
} 
""" if real_git else f"""git() {{
  printf 'git %s\\n' "$*" >> "$LOG"
  if [ "$3" = "reset" ] && [ "${{FAIL_RESET:-0}}" = 1 ]; then return 40; fi
  if [ "$3" = "rev-parse" ]; then printf '%s\\n' "{old_sha}"; fi
  return 0
}}
"""
            prefix = f"""
set -euo pipefail
RUNTIME_ROOT={shlex.quote(str(runtime))}
LEGACY_RUNTIME_ROOT={shlex.quote(str(runtime) + ".legacy-pre-worktree")}
REPO={shlex.quote(str(root / "repo"))}
UNIT={shlex.quote(str(unit))}
CAPABILITY_MARKER={shlex.quote(str(marker))}
SOURCE_REF=main
EXPECTED_SOURCE_COMMIT=
LOG={shlex.quote(str(command_log))}
ACTIVE=1
ENABLED=1
systemctl() {{
  printf 'systemctl %s\\n' "$*" >> "$LOG"
  case "$*" in
    "--user stop agentos-action-relay.service")
      if [ "${{STUCK:-0}}" != 1 ]; then ACTIVE=0; fi ;;
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
{git_mock}
"""
            command = ["bash", "-c", prefix + transaction]
            env = {**os.environ, "STUCK": str(int(stuck)),
                   "FAIL_RESET": str(int(fail_reset))}
            first_code = None
            if kill_after_reset:
                self.assertTrue(real_git)
                killed = subprocess.run(
                    command, text=True, capture_output=True, check=False,
                    timeout=20, env={**env, "KILL_AFTER_RESET": "1"},
                )
                first_code = killed.returncode
                self.assertEqual(first_code, -9, killed.stderr)
                self.assertTrue(pending.exists(), "SIGKILL must leave pending snapshot")
            result = subprocess.run(
                command, text=True, capture_output=True, check=False,
                timeout=20, env={**env, "KILL_AFTER_RESET": "0"},
            )
            return {
                "code": result.returncode, "stderr": result.stderr,
                "first_code": first_code,
                "unit": unit.read_bytes(),
                "marker": marker.read_bytes() if marker.exists() else None,
                "pending": pending.exists(),
                "log": command_log.read_text(encoding="utf-8") if command_log.exists() else "",
                "old_unit": old_unit, "old_marker": old_marker,
                "old_sha": old_sha,
                "runtime_generation": (runtime / "generation.txt").read_text(encoding="utf-8") if real_git else None,
            }

    def test_valid_pending_snapshot_recovers_and_exits_without_new_install(self):
        r = self._run()
        self.assertEqual(r["code"], 73, r["stderr"])
        self.assertIn("INTERRUPTED_RECOVERY_STARTED", r["stderr"])
        self.assertIn("action_relay_transaction=ROLLED_BACK", r["stderr"])
        self.assertEqual(r["unit"], r["old_unit"])
        self.assertEqual(r["marker"], r["old_marker"])
        self.assertFalse(r["pending"])
        self.assertIn("reset --hard " + OLD_SHA, r["log"])
        self.assertNotIn("fetch", r["log"])

    def test_pending_recovery_resets_real_git_worktree_to_prior_commit(self):
        r = self._run(real_git=True)
        self.assertEqual(r["code"], 73, r["stderr"])
        self.assertEqual(r["runtime_generation"], "old")
        self.assertEqual(r["unit"], r["old_unit"])
        self.assertEqual(r["marker"], r["old_marker"])
        self.assertFalse(r["pending"])

    def test_sigkill_during_real_git_restore_then_next_run_recovers(self):
        r = self._run(real_git=True, kill_after_reset=True)
        self.assertEqual(r["first_code"], -9)
        self.assertEqual(r["code"], 73, r["stderr"])
        self.assertEqual(r["runtime_generation"], "old")
        self.assertEqual(r["unit"], r["old_unit"])
        self.assertEqual(r["marker"], r["old_marker"])
        self.assertFalse(r["pending"])

    def test_corrupt_backup_refuses_recovery_before_service_stop(self):
        r = self._run(corrupt=True)
        self.assertEqual(r["code"], 72, r["stderr"])
        self.assertIn("checksum mismatch", r["stderr"])
        self.assertTrue(r["pending"])
        self.assertEqual(r["unit"], b"new unit")
        self.assertNotIn("systemctl --user stop", r["log"])

    def test_still_running_service_blocks_restore_and_preserves_snapshot(self):
        r = self._run(stuck=True)
        self.assertEqual(r["code"], 74, r["stderr"])
        self.assertIn("reason=service_remains_active", r["stderr"])
        self.assertTrue(r["pending"])
        self.assertIsNone(r["marker"])
        self.assertNotIn("reset --hard", r["log"])

    def test_failed_git_restore_preserves_snapshot_and_invalidates_marker(self):
        r = self._run(fail_reset=True)
        self.assertEqual(r["code"], 74, r["stderr"])
        self.assertIn("ROLLBACK_FAILED", r["stderr"])
        self.assertTrue(r["pending"])
        self.assertIsNone(r["marker"])


if __name__ == "__main__":
    unittest.main()
