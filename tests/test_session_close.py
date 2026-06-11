from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from agent_core.session_lifecycle import close_session


class SessionCloseTests(unittest.TestCase):
    def test_close_session_writes_record_and_compact_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            project_root = base / "project"
            data_root = base / "agent-data"
            project_root.mkdir(parents=True, exist_ok=True)
            short_term = data_root / "projects" / "project" / "memory" / "SHORT_TERM.md"
            status = data_root / "projects" / "project" / "STATUS.md"
            short_term.parent.mkdir(parents=True, exist_ok=True)
            short_term.write_text(
                "# Short Term\n\n## Pending Tasks\n- [ ] Ship the refactor\n- [ ] Verify report output\n\n## Blockers\n- Waiting on service install validation\n\n## Next Steps\n- Validate smoke tests\n",
                encoding="utf-8",
            )
            status.write_text(
                "---\npriority: 5\ncategory: management\n---\n\n# Project Status\n\n## 📍 Summary\n| Metric | Value |\n| :--- | :--- |\n| **Last Status** | 🟡 In progress |\n| **Last Updated** | 2026-06-10 00:00:00 |\n\n## 🪵 Activity Log (Latest on Top)\n<!-- LOG_START -->\n",
                encoding="utf-8",
            )

            result = close_session(project_root=project_root, data_root=data_root, agent_name="TestAgent")

            self.assertTrue(result.record_path.exists())
            self.assertEqual(result.record["project"], "project")
            self.assertIn("session_id", result.record)
            self.assertIn("started_at", result.record)
            self.assertIn("ended_at", result.record)
            self.assertIn("summary", result.record)
            self.assertIn("files_touched", result.record)
            self.assertIn("pending_tasks", result.record)
            self.assertIn("blockers", result.record)
            self.assertIn("next_steps", result.record)
            self.assertIn("branch", result.record)
            self.assertIn("uncommitted_files", result.record)
            self.assertIsInstance(result.record["files_touched"], list)
            self.assertTrue((data_root / "memory" / "session_sync.md").exists())
            self.assertIn("Session Handoff", (data_root / "memory" / "session_sync.md").read_text(encoding="utf-8"))
            self.assertIn("Session Close", (data_root / "projects" / "project" / "memory" / "SHORT_TERM.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
