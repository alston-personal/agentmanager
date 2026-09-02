from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent_core import active_continuation


class ActiveContinuationTests(unittest.TestCase):
    def _resolved(self, *, index_id="idx-1", ir_id="ir-1"):
        return {
            "schema": "agentos.resolve/v1",
            "execution_head": {
                "schema": "agentos.execution-head/v1",
                "index_id": index_id,
            },
            "continuation": {
                "canonical_ir": {
                    "schema_version": "agentos.ir/v1",
                    "index_id": index_id,
                    "ir_id": ir_id,
                    "goal": "test goal",
                }
            },
        }

    def test_activation_writes_pointer_only_after_generation_validation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with mock.patch.object(
                active_continuation,
                "resolve_continuation",
                return_value=self._resolved(),
            ):
                receipt = active_continuation.activate_continuation(
                    "agentos-core",
                    index_id="idx-1",
                    ir_id="ir-1",
                    reason="test",
                    data_root=root,
                )
            self.assertTrue(receipt["ok"])
            payload = json.loads((root / "runtime" / "active-continuation.json").read_text())
            self.assertEqual(payload["schema"], "agentos.active-continuation/v1")
            self.assertEqual(payload["project_id"], "agentos-core")
            self.assertEqual(payload["index_id"], "idx-1")
            self.assertEqual(payload["ir_id"], "ir-1")
            self.assertNotIn("goal", payload)
            self.assertNotIn("canonical_ir", payload)

    def test_activation_rejects_noncanonical_generation(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(
                active_continuation,
                "resolve_continuation",
                return_value=self._resolved(index_id="idx-current", ir_id="ir-current"),
            ):
                with self.assertRaisesRegex(ValueError, "non-canonical generation"):
                    active_continuation.activate_continuation(
                        "agentos-core",
                        index_id="idx-stale",
                        ir_id="ir-stale",
                        reason="test",
                        data_root=td,
                    )

    def test_resolve_active_rejects_stale_pointer(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = root / "runtime"
            runtime.mkdir()
            (runtime / "active-continuation.json").write_text(
                json.dumps(
                    {
                        "schema": "agentos.active-continuation/v1",
                        "project_id": "agentos-core",
                        "index_id": "idx-old",
                        "ir_id": "ir-old",
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(
                active_continuation,
                "resolve_continuation",
                return_value=self._resolved(index_id="idx-new", ir_id="ir-new"),
            ):
                with self.assertRaisesRegex(ValueError, "selector is stale"):
                    active_continuation.resolve_active_continuation(data_root=root)

    def test_resolve_active_returns_current_generation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = root / "runtime"
            runtime.mkdir()
            (runtime / "active-continuation.json").write_text(
                json.dumps(
                    {
                        "schema": "agentos.active-continuation/v1",
                        "project_id": "agentos-core",
                        "index_id": "idx-1",
                        "ir_id": "ir-1",
                    }
                ),
                encoding="utf-8",
            )
            resolved = self._resolved()
            with mock.patch.object(
                active_continuation,
                "resolve_continuation",
                return_value=resolved,
            ):
                result = active_continuation.resolve_active_continuation(data_root=root)
            self.assertEqual(result["selector"]["project_id"], "agentos-core")
            self.assertIs(result["resolution"], resolved)


if __name__ == "__main__":
    unittest.main()
