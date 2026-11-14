"""Run real source fragments of the existing installer against isolated Git trees.

The source snapshot, service stop, worktree replacement, unit writing and rollback
function are executed unmodified. Only network source discovery, Python action
imports, systemd and worker processes are simulated. This is NOT Oracle acceptance.
"""
from pathlib import Path
import os
import shlex
import subprocess
import tempfile
import unittest

INSTALLER = Path(__file__).resolve().parents[1] / "scripts/install_action_relay_user.sh"


class ActionRelayInstallerMutationFaultTest(unittest.TestCase):
    def _scenario(self, failure_stage):
        source = INSTALLER.read_text(encoding="utf-8")
        snapshot_begin = source.index('TXN_PARENT=$(dirname "$RUNTIME_ROOT")')
        snapshot_end = source.index("# Converge to exactly one governed consumer for this spool.", snapshot_begin)
        snippet = source[snapshot_begin:snapshot_end]
        # Isolated test pins a local source commit, bypassing network fetch only.
        fetch_begin = snippet.index('  if [ -n "$EXPECTED_SOURCE_COMMIT" ]; then')
        fetch_end = snippet.index('  ( umask 077; mkdir "$TXN_DIR" )', fetch_begin)
        snippet = snippet[:fetch_begin] + snippet[fetch_end:]
        # The test runner need not have the production ubuntu account.
        snippet = snippet.replace('"ubuntu:700"', '"$(id -un):700"')
        stop_begin = source.index('TXN_UNIT_TOUCHED=1\nif [ -f "$UNIT" ]; then')
        stop_end = source.index('# Close the drain/stop race fail-closed.', stop_begin)
        stop_section = source[stop_begin:stop_end]
        change_begin = source.index('TXN_RUNTIME_TOUCHED=1\nif [ -e "$RUNTIME_ROOT" ]')
        change_end = source.index('(\n  cd "$RUNTIME_ROOT"', change_begin)
        change_section = source[change_begin:change_end]
        unit_begin = source.index('cat > "$UNIT" <<EOF')
        unit_end = source.index('\nstable=0', unit_begin)
        unit_section = source[unit_begin:unit_end]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            runtime = root / "runtime" / "action-runtime"
            runtime.parent.mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            for name, value in (("user.name", "Isolated Test"),
                                ("user.email", "test@example.invalid")):
                subprocess.run(["git", "-C", str(repo), "config", name, value], check=True)
            (repo / "generation.txt").write_text("old", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "old"], check=True)
            old_sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
            (repo / "generation.txt").write_text("new", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "commit", "-qam", "new"], check=True)
            new_sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
            subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", "--detach",
                            str(runtime), old_sha], check=True)
            unit = root / "user" / "agentos-action-relay.service"
            marker = root / "data" / "runtime" / "action-relay" / "capabilities.json"
            unit.parent.mkdir(parents=True)
            marker.parent.mkdir(parents=True)
            unit.write_text("old-unit\n", encoding="utf-8")
            marker.write_text('{"generation":"old"}\n', encoding="utf-8")
            log = root / "systemctl.log"
            prefix = f"""
set -euo pipefail
RUNTIME_ROOT={shlex.quote(str(runtime))}
LEGACY_RUNTIME_ROOT={shlex.quote(str(runtime) + ".legacy-pre-worktree")}
REPO={shlex.quote(str(repo))}
UNIT={shlex.quote(str(unit))}
CAPABILITY_MARKER={shlex.quote(str(marker))}
RELAY_ROOT={shlex.quote(str(marker.parent))}
SOURCE_REF=main
EXPECTED_SOURCE_COMMIT=
SOURCE_COMMIT={new_sha}
LOG={shlex.quote(str(log))}
ACTIVE=1
ENABLED=1
systemctl() {{
  printf '%s\n' "$*" >> "$LOG"
  case "$*" in
    "--user stop agentos-action-relay.service") ACTIVE=0 ;;
    "--user start agentos-action-relay.service") ACTIVE=1 ;;
    "--user enable agentos-action-relay.service") ENABLED=1 ;;
    "--user disable agentos-action-relay.service") ENABLED=0 ;;
    "--user is-active --quiet agentos-action-relay.service")
      [ "$ACTIVE" = 1 ]; return ;;
    "--user is-enabled --quiet agentos-action-relay.service")
      [ "$ENABLED" = 1 ]; return ;;
    "--user daemon-reload")
      if [ "$FAULT_STAGE" = reload ] && [ "$NEW_UNIT_PHASE" = 1 ]; then return 88; fi ;;
  esac
  return 0
}}
"""
            # Force an installer failure at the specified stage after the real
            # stage fragment, so the production EXIT trap performs rollback.
            stages = [snippet, stop_section]
            if failure_stage == "stop":
                stages.append("exit 83\n")
            else:
                stages.append(change_section)
                if failure_stage == "worktree":
                    stages.append("exit 84\n")
                else:
                    stages.append("NEW_UNIT_PHASE=1\n")
                    stages.append(unit_section)
                    if failure_stage == "unit":
                        stages.append("exit 85\n")
                    elif failure_stage == "reload":
                        stages.append("exit 86\n")
                    else:
                        raise ValueError(failure_stage)
            result = subprocess.run(
                ["bash", "-c", prefix + "\n".join(stages)],
                text=True, capture_output=True, check=False, timeout=30,
                env={**os.environ, "FAULT_STAGE": failure_stage},
            )
            return {
                "returncode": result.returncode,
                "stderr": result.stderr,
                "head": subprocess.check_output(
                    ["git", "-C", str(runtime), "rev-parse", "HEAD"], text=True).strip(),
                "old_sha": old_sha,
                "generation": (runtime / "generation.txt").read_text(encoding="utf-8"),
                "unit": unit.read_text(encoding="utf-8"),
                "marker": marker.read_text(encoding="utf-8") if marker.exists() else None,
                "pending": (runtime.parent / ".action-relay-install.pending").exists(),
                "log": log.read_text(encoding="utf-8") if log.exists() else "",
            }

    def test_failure_after_managed_stop_restarts_old_generation(self):
        result = self._scenario("stop")
        self._assert_restored(result)

    def test_failure_after_real_git_worktree_reset_restores_old_generation(self):
        result = self._scenario("worktree")
        self._assert_restored(result)

    def test_failure_after_new_systemd_unit_write_restores_previous_unit(self):
        result = self._scenario("unit")
        self._assert_restored(result)

    def test_failed_systemd_reload_restores_prior_generation(self):
        result = self._scenario("reload")
        self._assert_restored(result)

    def _assert_restored(self, result):
        self.assertNotEqual(result["returncode"], 0, result["stderr"])
        self.assertIn("action_relay_transaction=ROLLED_BACK", result["stderr"])
        self.assertEqual(result["head"], result["old_sha"])
        self.assertEqual(result["generation"], "old")
        self.assertEqual(result["unit"], "old-unit\n")
        self.assertEqual(result["marker"], '{"generation":"old"}\n')
        self.assertFalse(result["pending"])
        self.assertIn("--user start agentos-action-relay.service", result["log"])


if __name__ == "__main__":
    unittest.main()
