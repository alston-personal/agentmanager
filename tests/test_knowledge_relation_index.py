"""Tests for agent_core.knowledge_relation_index (KG-LINK-01, KG-LINK-02)."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from agent_core.knowledge_relation_index import (
    GRAPH_SCHEMA,
    rebuild_relation_index,
    recall_for_task,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestKnowledgeRelationIndex(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_root = Path(self._tmp.name)

        # Seed immutable raw data fixtures
        (self.data_root / "projects" / "zeus-writer").mkdir(parents=True)
        self.zeus_status = self.data_root / "projects" / "zeus-writer" / "STATUS.md"
        self.zeus_status.write_text(
            "# Project Status: zeus-writer\n- [ ] 建置文章審批後台與選段反白標記註解元件\n",
            encoding="utf-8",
        )

        (self.data_root / "projects" / "persona-engine").mkdir(parents=True)
        self.pe_status = self.data_root / "projects" / "persona-engine" / "STATUS.md"
        self.pe_status.write_text(
            "# Project Status: persona-engine\n- [x] 實作 Character IR 與 fork_persona\n",
            encoding="utf-8",
        )

        (self.data_root / "personas" / "system-atlas").mkdir(parents=True)
        self.guard_file = self.data_root / "personas" / "system-atlas" / "pitfalls_guardrails.md"
        self.guard_file.write_text(
            "# Guardrails\n\n"
            "### 8. 公開網址交付前必須實測 HTTP 200\n"
            "- 修改 Nginx 後必須用 curl 實測 HTTP 200，避免 403。\n",
            encoding="utf-8",
        )

        self.exp_file = self.data_root / "personas" / "system-atlas" / "consolidated_experiences.jsonl"
        self.exp_file.write_text(
            json.dumps(
                {
                    "card_id": "exp-001",
                    "title": "vopc5750 Issue Draft HTML 預覽反白註解",
                    "summary": "Issue Draft 審查支援選段反白註解大幅提升修改精準度",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_rebuild_keeps_raw_data_immutable_and_creates_raw_refs(self) -> None:
        before = {
            "zeus": _sha256(self.zeus_status),
            "pe": _sha256(self.pe_status),
            "guard": _sha256(self.guard_file),
            "exp": _sha256(self.exp_file),
        }

        graph = rebuild_relation_index(self.data_root)
        self.assertEqual(graph["schema"], GRAPH_SCHEMA)
        self.assertEqual(graph["data_root_policy"], "raw_data_immutable_index_rebuildable")
        self.assertGreaterEqual(graph["stats"]["node_count"], 5)
        self.assertGreaterEqual(graph["stats"]["edge_count"], 4)

        # Every node must carry a raw_ref pointer back to raw data.
        for node in graph["nodes"]:
            self.assertTrue(node["raw_ref"])

        # Raw data files must remain byte-for-byte identical.
        after = {
            "zeus": _sha256(self.zeus_status),
            "pe": _sha256(self.pe_status),
            "guard": _sha256(self.guard_file),
            "exp": _sha256(self.exp_file),
        }
        self.assertEqual(before, after)

    def test_recall_before_act_surfaces_cross_project_lessons_and_guardrails(self) -> None:
        rebuild_relation_index(self.data_root)

        # Recall for a new web deployment task should surface Nginx HTTP 200 guardrail.
        web_hits = recall_for_task(
            self.data_root,
            project="zeus-writer",
            query_text="部署文章審批後台 Nginx 路由並避免 403",
        )
        self.assertTrue(any(h["kind"] == "guardrail" and "HTTP 200" in h["title"] for h in web_hits))
        self.assertTrue(all(h["raw_ref"] for h in web_hits))

        # Recall for inline annotation task should link across zeus-writer and Issue Draft experience.
        anno_hits = recall_for_task(
            self.data_root,
            project="redmine-qa",
            query_text="實作選段反白標記註解功能",
        )
        ids = {h["id"] for h in anno_hits}
        self.assertIn("project:zeus-writer", ids)
        self.assertTrue(any(h["kind"] == "experience" for h in anno_hits))


if __name__ == "__main__":
    unittest.main()
