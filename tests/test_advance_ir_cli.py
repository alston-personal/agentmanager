from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_core.project_continuation_index import publish_project_continuation
from scripts.advance_ir_cli import advance_ir, inspect_ir


class AdvanceIrCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "projects" / "agentos-core").mkdir(parents=True)
        publish_project_continuation(
            {
                "project_id": "agentos-core",
                "execution_head": {
                    "schema": "agentos.execution-head/v1",
                    "index_id": "idx-seed-1",
                    "active_goal": "Seed goal",
                    "execution_head": {"status": "in_progress"},
                },
                "continuation": {
                    "protocol": "ANCP/1.0",
                    "index_id": "idx-seed-1",
                    "recommended_action": "Seed next action",
                    "canonical_ir": {
                        "schema_version": "agentos.ir/v1",
                        "index_id": "idx-seed-1",
                        "ir_id": "ir-seed-1",
                        "goal": "Seed goal",
                        "constraints": ["Preserve logic/data separation"],
                        "decisions": ["Canonical IR is authoritative"],
                        "pending_tasks": ["Task A"],
                        "evidence": [],
                        "continuation": {
                            "recommended_action": "Seed next action",
                            "next_action": "Seed next action",
                        },
                        "capability": "agentos.one.resolve",
                    },
                },
            },
            data_root=self.root,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_advance_and_activate_keeps_selector_in_sync(self) -> None:
        gov_dir = self.root / "governance"
        gov_dir.mkdir(parents=True, exist_ok=True)
        (gov_dir / "work-items.json").write_text(
            json.dumps(
                {
                    "schema": "agentos.work-completion/v1",
                    "items": {
                        "w1": {"status": "done"},
                        "w2": {"status": "blocked"},
                    },
                }
            ),
            encoding="utf-8",
        )

        result = advance_ir(
            new_index_id="idx-seed-2",
            new_ir_id="ir-seed-2",
            goal="Unified goal",
            next_action="Verify unified runtime",
            decisions_append=["Keep selector and IR synchronized"],
            include_completion_summary=True,
            data_root=self.root,
        )
        self.assertTrue(result["ok"])
        status = inspect_ir(data_root=self.root)
        self.assertEqual(status["index_id"], "idx-seed-2")
        self.assertEqual(status["ir_id"], "ir-seed-2")
        self.assertEqual(status["parent_ir_id"], "ir-seed-1")
        self.assertTrue(status["active_selector_matches"])
        self.assertEqual(status["evidence_count"], 1)


if __name__ == "__main__":
    unittest.main()
