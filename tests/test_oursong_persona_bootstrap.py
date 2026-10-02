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
    def run_bootstrap(self, home: Path):
        env = os.environ.copy()
        env["HOME"] = str(home)
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


if __name__ == "__main__":
    unittest.main()
