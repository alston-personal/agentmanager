from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from agent_core.base_pdca import (
    BasePDCAWorker,
    ClawAuditorWorker,
    CangxuanEditorWorker,
    GeekCultivatorWorker,
    get_worker,
)


class BasePDCATests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="agentos-test-base-pdca-"))
        self.data_root = self.tmp / "agent-data"
        self.project_root = self.tmp / "agentmanager"
        self.data_root.mkdir(parents=True)
        self.project_root.mkdir(parents=True)

        # Create mock .env in project_root
        env_file = self.project_root / ".env"
        env_file.write_text("SECRET=mock\n", encoding="utf-8")
        env_file.chmod(0o600)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_generic_worker_lifecycle(self) -> None:
        worker = BasePDCAWorker("test-role", data_root=self.data_root, project_root=self.project_root)
        self.assertTrue(worker.config_file.is_file())
        self.assertTrue(worker.state_file.is_file())

        res = worker.run_cycle()
        self.assertEqual(res.cycle, 1)
        self.assertEqual(res.check["verdict"], "PASS")

        # Verify state advanced
        state = json.loads(worker.state_file.read_text())
        self.assertEqual(state["cycle"], 2)
        self.assertEqual(len(state["recent_activities"]), 1)

        # Second cycle
        res2 = worker.run_cycle()
        self.assertEqual(res2.cycle, 2)
        state2 = json.loads(worker.state_file.read_text())
        self.assertEqual(state2["cycle"], 3)
        self.assertEqual(len(state2["recent_activities"]), 2)

    def test_claw_auditor_worker(self) -> None:
        claw = ClawAuditorWorker(data_root=self.data_root, project_root=self.project_root)
        res = claw.run_cycle()
        self.assertEqual(res.role_id, "sector.the-claw")
        self.assertEqual(res.check["verdict"], "PASS")
        self.assertTrue(any(".env" in f for f in res.check["findings"]))

    def test_cangxuan_editor_worker(self) -> None:
        # Mock novel directory
        novel_dir = self.tmp / "novel"
        novel_dir.mkdir(parents=True)
        ch_file = novel_dir / "01_第一章_天道初開.md"
        ch_file.write_text("道可道，非常道。" * 500, encoding="utf-8")  # > 3000 chars

        cang = CangxuanEditorWorker(data_root=self.data_root, project_root=self.project_root)
        cang.novel_dir = novel_dir
        res = cang.run_cycle()

        self.assertEqual(res.role_id, "sector.tiandao-cangxuan")
        self.assertEqual(res.check["verdict"], "PASS")
        self.assertTrue(res.do["char_count"] >= 3000)
        self.assertEqual(len(res.do["leaked_terms"]), 0)

    def test_cangxuan_editor_catches_jargon_leak(self) -> None:
        novel_dir = self.tmp / "novel"
        novel_dir.mkdir(parents=True)
        ch_file = novel_dir / "02_第二章_天機外洩.md"
        # Inject leak: Token and Backoff
        ch_file.write_text("此法陣之 Token 節流與 Backoff 機制。" * 200, encoding="utf-8")

        cang = CangxuanEditorWorker(data_root=self.data_root, project_root=self.project_root)
        cang.novel_dir = novel_dir
        res = cang.run_cycle()

        self.assertEqual(res.check["verdict"], "FAIL")
        self.assertTrue(len(res.do["leaked_terms"]) > 0)

    def test_worker_factory(self) -> None:
        claw = get_worker("the-claw")
        self.assertIsInstance(claw, ClawAuditorWorker)

        cang = get_worker("cangxuan")
        self.assertIsInstance(cang, CangxuanEditorWorker)

        geek = get_worker("geek")
        self.assertIsInstance(geek, GeekCultivatorWorker)

        atlas = get_worker("atlast")
        self.assertEqual(atlas.role_slug, "system-atlas")

        cerberus = get_worker("cerberus")
        self.assertEqual(cerberus.role_slug, "system-quality-sentinel")

        hermes = get_worker("hermes")
        self.assertEqual(hermes.role_slug, "system-gateway-steward")


if __name__ == "__main__":
    unittest.main()

