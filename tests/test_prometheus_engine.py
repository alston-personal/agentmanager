from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_core.prometheus_engine import generate_synergy_report, scan_fire_patterns, scan_specs_for_modernization


class TestPrometheusEngine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data_root = self.root / "agent-data"
        self.specs_dir = self.data_root / "specs"
        self.specs_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_scan_fire_patterns_extracts_core_innovations(self):
        # Create a mock Hermes recon ledger
        hermes_dir = self.data_root / "personas" / "sector-hermes"
        hermes_dir.mkdir(parents=True, exist_ok=True)
        (hermes_dir / "recon_ledger.json").write_text("""{
  "schema": "agentos.hermes-recon-ledger/v1",
  "records": [
    {
      "id": "recon-mock-weapon",
      "name": "mock-weapon (v1.0)",
      "target_repo": "https://github.com/mock/weapon",
      "summary": "Mock anti-slop engine"
    }
  ]
}""", encoding="utf-8")

        patterns = scan_fire_patterns(self.root, self.data_root)
        self.assertGreaterEqual(len(patterns), 4)
        pattern_ids = {p["pattern_id"] for p in patterns}
        self.assertIn("pattern-runtime-api-dispatch", pattern_ids)
        self.assertIn("pattern-thin-client-heartbeat-ota", pattern_ids)
        self.assertIn("pattern-dynamic-atlas-avatar-endpoint", pattern_ids)
        self.assertIn("hermes-weapon-recon-mock-weapon", pattern_ids)

    def test_scan_specs_detects_outdated_assumptions(self):
        # Create an outdated spec with legacy git push dispatching
        outdated_spec = self.specs_dir / "legacy_flow.md"
        outdated_spec.write_text("""# Legacy Flow
Edge nodes push tasks using git push to fabric.json.
Also monitors pulse board states.
""", encoding="utf-8")

        # Create a modern spec
        modern_spec = self.specs_dir / "modern_flow.md"
        modern_spec.write_text("""# Modern Flow
Uses POST /v1/tasks runtime API dispatching.
""", encoding="utf-8")

        candidates = scan_specs_for_modernization(self.data_root)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["spec_name"], "legacy_flow.md")
        self.assertEqual(len(candidates[0]["modernization_hints"]), 2)

    def test_generate_synergy_report_produces_governed_report(self):
        report = generate_synergy_report(self.root, self.data_root)
        self.assertEqual(report["schema"], "agentos.architecture-synergy-report/v1")
        self.assertEqual(report["scout"], "system.prometheus")
        self.assertGreaterEqual(report["fire_patterns_count"], 3)
        self.assertGreaterEqual(len(report["strategic_uplift_proposals"]), 2)
