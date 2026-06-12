from __future__ import annotations

import os
import tempfile
from pathlib import Path
import unittest
from unittest import mock

from agent_core.memory_router import resolve_memory_route


class MemoryRouterTests(unittest.TestCase):
    def test_resolves_project_from_cwd_markers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            project_root = base / "youtube-ai-manager"
            data_root = base / "agent-data"
            project_data_root = data_root / "projects" / project_root.name
            project_data_root.joinpath("memory").mkdir(parents=True, exist_ok=True)
            project_root.mkdir(parents=True, exist_ok=True)
            (project_data_root / "STATUS.md").write_text("status", encoding="utf-8")
            status_link = project_root / "STATUS.md"
            memory_link = project_root / "memory"
            status_link.symlink_to(project_data_root / "STATUS.md")
            memory_link.symlink_to(project_data_root / "memory", target_is_directory=True)

            route = resolve_memory_route(cwd=project_root, data_root=data_root)

            self.assertEqual(route.project_root, project_root.resolve())
            self.assertEqual(route.project_name, "youtube-ai-manager")
            self.assertEqual(route.short_term_path, project_data_root / "memory" / "SHORT_TERM.md")
            self.assertEqual(route.session_sync_path, data_root / "memory" / "session_sync.md")

    def test_context_env_override_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            active_root = base / "agentmanager"
            override_root = base / "youtube-ai-manager"
            data_root = base / "agent-data"
            for root in (active_root, override_root):
                project_data_root = data_root / "projects" / root.name
                project_data_root.joinpath("memory").mkdir(parents=True, exist_ok=True)
                root.mkdir(parents=True, exist_ok=True)
                (project_data_root / "STATUS.md").write_text("status", encoding="utf-8")
                (root / "STATUS.md").symlink_to(project_data_root / "STATUS.md")
                (root / "memory").symlink_to(project_data_root / "memory", target_is_directory=True)

            with mock.patch.dict(
                os.environ,
                {"AGENT_CONTEXT_PROJECT_ROOT": str(override_root), "AGENT_DATA_ROOT": str(data_root)},
                clear=False,
            ):
                route = resolve_memory_route(cwd=active_root)

            self.assertEqual(route.project_root, override_root.resolve())
            self.assertEqual(route.project_name, "youtube-ai-manager")

    def test_agent_project_root_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            active_root = base / "agentmanager"
            override_root = base / "openclaw"
            data_root = base / "agent-data"
            
            for root in (active_root, override_root):
                project_data_root = data_root / "projects" / root.name
                project_data_root.joinpath("memory").mkdir(parents=True, exist_ok=True)
                root.mkdir(parents=True, exist_ok=True)
                (root / ".agent").touch()

            with mock.patch.dict(
                os.environ,
                {"AGENT_PROJECT_ROOT": str(override_root), "AGENT_DATA_ROOT": str(data_root)},
                clear=False,
            ):
                # Using a directory with NO project markers.
                # Should fallback to AGENT_PROJECT_ROOT.
                empty_cwd = base / "empty"
                empty_cwd.mkdir()
                route = resolve_memory_route(cwd=empty_cwd)

            self.assertEqual(route.project_root, override_root.resolve())
            self.assertEqual(route.project_name, "openclaw")
            
    def test_cwd_project_marker_inference_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            data_root = base / "agent-data"
            project_a = base / "project_a"
            project_b = base / "project_b"
            
            for root in (project_a, project_b):
                root.mkdir()
                (root / ".agent").touch()
                
            nested_a = project_a / "src" / "deep"
            nested_a.mkdir(parents=True)
            
            # Even if we are deep inside project_a, it should infer project_a
            route_a = resolve_memory_route(cwd=nested_a, data_root=data_root)
            self.assertEqual(route_a.project_root, project_a.resolve())
            self.assertEqual(route_a.short_term_path, data_root / "projects" / "project_a" / "memory" / "SHORT_TERM.md")
            
            # Calling from project_b
            route_b = resolve_memory_route(cwd=project_b, data_root=data_root)
            self.assertEqual(route_b.project_root, project_b.resolve())
            self.assertEqual(route_b.short_term_path, data_root / "projects" / "project_b" / "memory" / "SHORT_TERM.md")
            
            # session_sync should be shared
            self.assertEqual(route_a.session_sync_path, route_b.session_sync_path)
            self.assertEqual(route_a.session_sync_path, data_root / "memory" / "session_sync.md")


if __name__ == "__main__":
    unittest.main()
