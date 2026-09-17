from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.repair_active_canonical_ir_project_id import repair_active_canonical_ir_project_id


class ActiveCanonicalIrProjectIdRepairTests(unittest.TestCase):
    def _root(self, *, project_id=None):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        runtime = root / "runtime"
        project = root / "projects" / "agentos-core"
        continuity = project / "continuity"
        runtime.mkdir(parents=True)
        continuity.mkdir(parents=True)
        (runtime / "active-continuation.json").write_text(
            json.dumps(
                {
                    "schema": "agentos.active-continuation/v1",
                    "project_id": "agentos-core",
                    "index_id": "idx-core-185-claude-ext-1",
                    "ir_id": "ir-core-185-claude-ext-1",
                }
            ),
            encoding="utf-8",
        )
        (project / "execution-head.json").write_text(
            json.dumps(
                {
                    "schema": "agentos.execution-head/v1",
                    "index_id": "idx-core-185-claude-ext-1",
                }
            ),
            encoding="utf-8",
        )
        ir = {
            "schema_version": "agentos.ir/v1",
            "index_id": "idx-core-185-claude-ext-1",
            "ir_id": "ir-core-185-claude-ext-1",
            "goal": "continue #185",
        }
        if project_id is not None:
            ir["project_id"] = project_id
        (continuity / "latest.json").write_text(
            json.dumps(
                {
                    "protocol": "ANCP/1.0",
                    "index_id": "idx-core-185-claude-ext-1",
                    "canonical_ir": ir,
                }
            ),
            encoding="utf-8",
        )
        return td, root

    def test_repairs_only_missing_project_id_without_advancing_generation(self):
        td, root = self._root()
        try:
            result = repair_active_canonical_ir_project_id(root)
            self.assertTrue(result["ok"])
            self.assertTrue(result["repaired"])
            self.assertEqual(result["index_id"], "idx-core-185-claude-ext-1")
            self.assertEqual(result["ir_id"], "ir-core-185-claude-ext-1")
            stored = json.loads((root / "projects" / "agentos-core" / "continuity" / "latest.json").read_text())
            self.assertEqual(stored["canonical_ir"]["project_id"], "agentos-core")
            self.assertEqual(stored["canonical_ir"]["index_id"], "idx-core-185-claude-ext-1")
            self.assertEqual(stored["canonical_ir"]["ir_id"], "ir-core-185-claude-ext-1")
        finally:
            td.cleanup()

    def test_is_idempotent_when_project_id_is_already_valid(self):
        td, root = self._root(project_id="agentos-core")
        try:
            before = (root / "projects" / "agentos-core" / "continuity" / "latest.json").read_bytes()
            result = repair_active_canonical_ir_project_id(root)
            self.assertFalse(result["repaired"])
            self.assertEqual(before, (root / "projects" / "agentos-core" / "continuity" / "latest.json").read_bytes())
        finally:
            td.cleanup()

    def test_refuses_conflicting_nonempty_project_id(self):
        td, root = self._root(project_id="other-project")
        try:
            before = (root / "projects" / "agentos-core" / "continuity" / "latest.json").read_bytes()
            with self.assertRaisesRegex(ValueError, "conflicting non-empty project_id"):
                repair_active_canonical_ir_project_id(root)
            self.assertEqual(before, (root / "projects" / "agentos-core" / "continuity" / "latest.json").read_bytes())
        finally:
            td.cleanup()


if __name__ == "__main__":
    unittest.main()
