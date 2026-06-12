from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from agent_core.session_lifecycle import close_session
from agentos_host.adapter import AgentOSContextAdapter


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

            adapter = AgentOSContextAdapter(project_root=project_root, data_root=data_root)
            result = close_session(context_provider=adapter, project_root=project_root, data_root=data_root, agent_name="TestAgent")

            self.assertTrue(Path(result.record_uri).exists())
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

    def test_in_memory_context_provider(self) -> None:
        from runtime_core.memory_provider import InMemoryContextProvider
        
        provider = InMemoryContextProvider(
            project_id="mem-project",
            summary="In-memory test summary",
            pending_tasks=["Task 1", "Task 2"],
            blockers=["Blocker A"],
            next_steps=["Step Z"]
        )
        
        result = close_session(context_provider=provider, agent_name="MemoryAgent")
        
        self.assertEqual(result.record["project"], "mem-project")
        self.assertEqual(result.record["summary"], "In-memory test summary")
        self.assertEqual(result.record["pending_tasks"], ["Task 1", "Task 2"])
        self.assertEqual(result.record["blockers"], ["Blocker A"])
        self.assertEqual(result.record["next_steps"], ["Step Z"])
        self.assertEqual(result.record["agent"], "MemoryAgent")
        self.assertTrue(result.record_uri.startswith("memory://"))
        self.assertEqual(len(provider.closed_sessions), 1)
        self.assertEqual(provider.closed_sessions[0].session_id, result.session_id)

    def test_import_boundaries(self) -> None:
        # Import core modules
        import runtime_core.models as models
        import runtime_core.interfaces as interfaces
        import agent_core.session_lifecycle as lifecycle
        import agentos_host.adapter as adapter
        
        self.assertIsNotNone(models)
        self.assertIsNotNone(interfaces)
        self.assertIsNotNone(lifecycle)
        self.assertIsNotNone(adapter)


if __name__ == "__main__":
    unittest.main()
