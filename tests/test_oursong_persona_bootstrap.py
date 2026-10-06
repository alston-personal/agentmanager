"""Offline acceptance for oursong persona bootstrap.

No network, Threads account, Oracle host, or credentials are used.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class OursongBootstrapAcceptanceTests(unittest.TestCase):
    def run_bootstrap(self, home: Path, data_root: Path | None = None):
        env = os.environ.copy()
        env["HOME"] = str(home)
        if data_root is not None:
            env["AGENTOS_PERSONA_DATA_ROOT"] = str(data_root)
        proc = subprocess.run(
            [sys.executable, "scripts/bootstrap_oursong_persona_user.py"],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        return proc

    def test_bootstrap_creates_required_state_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            first = self.run_bootstrap(home)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIn("oursong_bootstrap=PASS", first.stdout)

            root = home / "agent-data" / "personas" / "oursong_alstonhuang"
            required = [
                "character_core.json",
                "persona_state.json",
                "ir/current.json",
                "pdca/config.json",
                "pdca/state.json",
                "events/events.jsonl",
                "relationships/README.md",
            ]
            for rel in required:
                self.assertTrue((root / rel).exists(), rel)

            character = json.loads((root / "character_core.json").read_text())
            state = json.loads((root / "persona_state.json").read_text())
            ir = json.loads((root / "ir/current.json").read_text())
            pdca_config = json.loads((root / "pdca/config.json").read_text())
            pdca_state = json.loads((root / "pdca/state.json").read_text())

            self.assertEqual(character["character_id"], "oursong-alstonhuang-001")
            self.assertEqual(state["character_id"], "oursong-alstonhuang-001")
            self.assertEqual(ir["persona_id"], "oursong-alstonhuang-001")
            self.assertEqual(pdca_config["persona_id"], "oursong-alstonhuang-001")
            self.assertEqual(pdca_state["persona_id"], "oursong-alstonhuang-001")
            self.assertTrue(pdca_config["enabled"])
            self.assertEqual(pdca_state["status"], "RUNNING")

            marker = root / "character_core.json"
            original = marker.read_text()
            second = self.run_bootstrap(home)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("oursong_bootstrap=SKIP:character_core.json", second.stdout)
            self.assertEqual(marker.read_text(), original)

    def test_bootstrap_supports_explicit_authoritative_data_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            home = base / "home"
            home.mkdir()
            data_root = base / "authoritative-agent-data"
            proc = self.run_bootstrap(home, data_root)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            root = data_root / "personas" / "oursong_alstonhuang"
            self.assertTrue((root / "pdca/state.json").is_file())
            state = json.loads((root / "pdca/state.json").read_text())
            self.assertEqual(state["persona_id"], "oursong-alstonhuang-001")
            self.assertFalse((home / "agent-data" / "personas" / "oursong_alstonhuang").exists())


if __name__ == "__main__":
    unittest.main()


class OursongActivationIsolationTests(unittest.TestCase):
    def test_activation_does_not_install_or_start_shared_persona_heartbeat(self):
        text=(Path(__file__).resolve().parents[1] / "scripts" / "activate_oursong_persona_user.sh").read_text()
        self.assertNotIn('install -m 0755 "${RELEASE}/scripts/persona_pdca_heartbeat_user.py"', text)
        self.assertNotIn('systemctl --user start agentos-persona-pdca-heartbeat.service', text)
        self.assertIn('oursong_heartbeat_ownership=external', text)
