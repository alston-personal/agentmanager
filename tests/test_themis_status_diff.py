#!/usr/bin/env python3
"""
單元測試：忒彌斯 Themis 狀態盤點與時序差異比對引擎
Tests for Themis State Inventory & Delta Diff Engine
"""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import json

from scripts.themis_status_diff import (
    scan_projects,
    compute_delta,
    format_markdown_report,
)
from agent_core.base_pdca import get_worker, ThemisCommandWorker


class TestThemisStatusDiff(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.mock_data = Path(self.temp_dir.name)
        self.projects_dir = self.mock_data / "projects"
        self.projects_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_scan_projects_empty(self):
        p_map, summary = scan_projects(self.mock_data)
        self.assertEqual(summary["total_projects"], 0)
        self.assertEqual(summary["total_open"], 0)

    def test_scan_projects_with_todos_and_ac(self):
        proj_a = self.projects_dir / "project-alpha"
        proj_a.mkdir()
        status_a = proj_a / "STATUS.md"
        status_a.write_text(
            "# Status\n"
            "- [ ] Task 1 without AC\n"
            "- [ ] Task 2 with [AC: Must pass 100% tests]\n"
            "- [x] Task 3 closed\n",
            encoding="utf-8"
        )

        p_map, summary = scan_projects(self.mock_data)
        self.assertEqual(summary["total_projects"], 1)
        self.assertEqual(summary["documented_projects"], 1)
        self.assertEqual(summary["total_open"], 2)
        self.assertEqual(summary["total_closed"], 1)
        self.assertEqual(summary["total_with_ac"], 1)
        self.assertEqual(p_map["project-alpha"]["ac_count"], 1)

    def test_compute_delta_without_baseline(self):
        curr = {
            "schema": "agentos.inventory-snapshot/v1",
            "timestamp": "2026-11-09T12:00:00+08:00",
            "git": {"commit_sha": "abcdef123456", "branch": "main", "is_clean": True},
            "projects_summary": {"total_projects": 1, "total_open": 2, "total_closed": 1, "total_with_ac": 0},
            "projects": {},
            "atlas": {"latest_cycle": 10},
        }
        delta = compute_delta(None, curr)
        self.assertFalse(delta["has_baseline"])
        self.assertIn("首次", delta["message"])

    def test_compute_delta_with_progression(self):
        base = {
            "schema": "agentos.inventory-snapshot/v1",
            "timestamp": "2026-11-09T10:00:00+08:00",
            "git": {"commit_sha": "111111111111", "branch": "main", "is_clean": True},
            "projects_summary": {"total_projects": 1, "total_open": 5, "total_closed": 10, "total_with_ac": 1},
            "projects": {
                "proj-1": {"has_status": True, "open_count": 5, "closed_count": 10, "ac_count": 1}
            },
            "atlas": {"latest_cycle": 100},
        }

        curr = {
            "schema": "agentos.inventory-snapshot/v1",
            "timestamp": "2026-11-09T11:00:00+08:00",
            "git": {"commit_sha": "222222222222", "branch": "main", "is_clean": True},
            "projects_summary": {"total_projects": 2, "total_open": 4, "total_closed": 12, "total_with_ac": 2},
            "projects": {
                "proj-1": {"has_status": True, "open_count": 3, "closed_count": 12, "ac_count": 2},
                "proj-2": {"has_status": True, "open_count": 1, "closed_count": 0, "ac_count": 0},
            },
            "atlas": {"latest_cycle": 105},
        }

        delta = compute_delta(base, curr)
        self.assertTrue(delta["has_baseline"])
        self.assertTrue(delta["git_delta"]["changed"])
        self.assertEqual(delta["git_delta"]["old_sha"], "11111111")
        self.assertEqual(delta["git_delta"]["new_sha"], "22222222")

        # 專案 Delta
        self.assertEqual(delta["project_delta"]["new_projects"], ["proj-2"])

        # 任務 Delta
        self.assertEqual(delta["todo_delta"]["open_delta"], -1)
        self.assertEqual(delta["todo_delta"]["closed_delta"], 2)
        self.assertEqual(delta["todo_delta"]["ac_delta"], 1)

        # Atlas 週期 Delta
        self.assertEqual(delta["atlas_delta"]["cycle_delta"], 5)

        # 驗證 Markdown 生成無崩潰
        md = format_markdown_report(curr, delta)
        self.assertIn("proj-2", md)
        self.assertIn("11111111", md)
        self.assertIn("22222222", md)

    def test_worker_registration(self):
        worker = get_worker("themis")
        self.assertIsInstance(worker, ThemisCommandWorker)
        self.assertEqual(worker.role_slug, "governance-themis-command-steward")


if __name__ == "__main__":
    unittest.main()
