import unittest
import tempfile
import json
from pathlib import Path
from agent_core.ir_relation_index import (
    build_ir_relation_graph,
    project_canonical_ir,
    extract_ir_concepts,
    IR_GRAPH_SCHEMA
)

class TestIRRelationIndex(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_root = Path(self.temp_dir.name)
        self.proj_dir = self.data_root / "projects" / "demo-proj"
        self.cont_dir = self.proj_dir / "continuity"
        self.cont_dir.mkdir(parents=True, exist_ok=True)

        self.mock_ir = {
            "canonical_ir": {
                "project_id": "demo-proj",
                "goal": "建立 Nginx 反向代理與安全憑證 0600 防線",
                "decisions": [
                    "完成 Nginx 路由設定並通過 http 200 驗證",
                    "修訂小說章節矛盾並支援反白註解",
                    "設定 .env 權限為 0600 防止 token 洩漏"
                ],
                "pending_tasks": [
                    "任務 1: 部署 Nginx 站點",
                    "任務 2: 撰寫單元測試"
                ]
            }
        }
        (self.cont_dir / "latest.json").write_text(json.dumps(self.mock_ir), encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_concept_extraction(self):
        concepts = extract_ir_concepts("檢查 nginx 403 錯誤與 curl http 200 連通")
        self.assertIn("web_routing_and_gateway", concepts)

    def test_graph_build(self):
        graph = build_ir_relation_graph(self.data_root)
        self.assertEqual(graph["schema"], IR_GRAPH_SCHEMA)
        self.assertGreater(graph["stats"]["node_count"], 0)
        self.assertGreater(graph["stats"]["edge_count"], 0)

    def test_dynamic_projection_reduces_size(self):
        raw = self.mock_ir["canonical_ir"]
        proj = project_canonical_ir(raw, query_intent="nginx 路由與網路連通", data_root=self.data_root)
        
        self.assertEqual(proj["schema_version"], "agentos.projected-ir/v1")
        self.assertEqual(proj["current_task"], "任務 1: 部署 Nginx 站點")
        self.assertLessEqual(len(proj["recalled_relevant_decisions"]), 3)
        self.assertTrue(any("Nginx" in d for d in proj["recalled_relevant_decisions"]))

if __name__ == "__main__":
    unittest.main()
