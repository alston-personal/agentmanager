from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "closure_audit.py"
SPEC = importlib.util.spec_from_file_location("closure_audit", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ClosureAuditTests(unittest.TestCase):
    def _item(self, **updates):
        item = {
            "id": "x",
            "owner": "governance.spec_steward",
            "stage": "DISCOVERED",
            "implementation": [],
            "integration_evidence": [],
            "verification_evidence": [],
            "operating_evidence": [],
            "regression_guard": [],
            "gaps": ["not done"],
        }
        item.update(updates)
        return item

    def test_discovered_item_may_have_no_evidence(self):
        self.assertEqual([], MODULE.audit({"items": [self._item()]}))

    def test_implemented_requires_implementation(self):
        errors = MODULE.audit({"items": [self._item(stage="IMPLEMENTED")]})
        self.assertTrue(any("requires implementation evidence" in e for e in errors))

    def test_verified_requires_integration_and_verification(self):
        errors = MODULE.audit(
            {
                "items": [
                    self._item(
                        stage="VERIFIED",
                        implementation=["a.py"],
                    )
                ]
            }
        )
        self.assertTrue(any("requires integration evidence" in e for e in errors))
        self.assertTrue(any("requires verification evidence" in e for e in errors))

    def test_guarded_requires_operating_and_guard(self):
        errors = MODULE.audit(
            {
                "items": [
                    self._item(
                        stage="GUARDED",
                        implementation=["a.py"],
                        integration_evidence=["runtime"],
                        verification_evidence=["test"],
                    )
                ]
            }
        )
        self.assertTrue(any("requires operating evidence" in e for e in errors))
        self.assertTrue(any("requires regression guard" in e for e in errors))

    def test_closed_cannot_keep_gaps(self):
        errors = MODULE.audit(
            {
                "items": [
                    self._item(
                        stage="CLOSED",
                        implementation=["a.py"],
                        integration_evidence=["runtime"],
                        verification_evidence=["test"],
                        operating_evidence=["receipt"],
                        regression_guard=["guard"],
                    )
                ]
            }
        )
        self.assertTrue(any("cannot retain gaps" in e for e in errors))

    def test_closed_with_complete_evidence_passes(self):
        item = self._item(
            stage="CLOSED",
            implementation=["a.py"],
            integration_evidence=["runtime"],
            verification_evidence=["test"],
            operating_evidence=["receipt"],
            regression_guard=["guard"],
            gaps=[],
        )
        self.assertEqual([], MODULE.audit({"items": [item]}))


if __name__ == "__main__":
    unittest.main()
