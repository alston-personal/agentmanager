from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import spec_steward


class SpecStewardFalseCompletionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.specs_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_proposed_spec_with_open_items_is_allowed(self) -> None:
        spec_content = """---
title: Proposed Feature Spec
status: proposed
owner: alice
target_projects:
  - test-project
---

# Proposed Feature Spec

- [ ] Task 1 still pending
- [ ] Task 2 research
"""
        spec_file = self.specs_dir / "proposed-feature.md"
        spec_file.write_text(spec_content, encoding="utf-8")

        with patch.object(spec_steward, "SPECS_DIR", self.specs_dir), \
             patch.object(spec_steward, "load_projects_by_id", return_value={"test-project": object()}):
            findings = spec_steward.build_findings()

        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding.status, "proposed")
        self.assertEqual(finding.open_items, 2)
        # Having open items in proposed spec must NOT trigger FALSE_COMPLETION
        self.assertFalse(any("FALSE_COMPLETION" in note for note in finding.notes))

    def test_completed_spec_with_open_items_triggers_false_completion(self) -> None:
        spec_content = """---
title: Prematurely Closed Spec
status: closed
owner: bob
target_projects:
  - test-project
---

# Prematurely Closed Spec

- [x] Task 1 done
- [ ] Task 2 incomplete!
"""
        spec_file = self.specs_dir / "premature-closed.md"
        spec_file.write_text(spec_content, encoding="utf-8")

        with patch.object(spec_steward, "SPECS_DIR", self.specs_dir), \
             patch.object(spec_steward, "load_projects_by_id", return_value={"test-project": object()}):
            findings = spec_steward.build_findings()

        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding.status, "closed")
        self.assertEqual(finding.open_items, 1)
        # Open items in closed/implemented spec MUST trigger FALSE_COMPLETION
        self.assertTrue(any("FALSE_COMPLETION" in note for note in finding.notes))
        self.assertIn("marked as 'closed' but has 1 open checklist item(s)", "; ".join(finding.notes))

    def test_implemented_spec_without_verified_receipt_triggers_false_completion(self) -> None:
        spec_content = """---
title: Production Feature
status: implemented
owner: charlie
target_projects:
  - test-project
production_url: https://example.com/app
---

# Production Feature

- [x] Task 1 done
"""
        spec_file = self.specs_dir / "unverified-prod.md"
        spec_file.write_text(spec_content, encoding="utf-8")

        with patch.object(spec_steward, "SPECS_DIR", self.specs_dir), \
             patch.object(spec_steward, "load_projects_by_id", return_value={"test-project": object()}):
            findings = spec_steward.build_findings()

        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertTrue(any("FALSE_COMPLETION" in note for note in finding.notes))


if __name__ == "__main__":
    unittest.main()
