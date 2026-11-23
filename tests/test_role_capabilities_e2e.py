"""
AgentOS Role Capabilities E2E Functional Test Suite
執掌: 實體驗證全生態角色宣稱能力 (Capabilities) 是否如預期執行與產出物閉環。
拒絕『無人檢測角色是否正常』的結構性失職。
"""

import unittest
import json
from pathlib import Path

class RoleCapabilitiesE2ETests(unittest.TestCase):
    def setUp(self):
        self.agent_data = Path("/home/ubuntu/agent-data")
        self.repo_root = Path("/home/ubuntu/agentmanager")

    def test_mio_persona_pipeline(self):
        """驗證 Mio 社交探索與生活發布管線合規性"""
        mio_dir = self.agent_data / "personas" / "mio"
        self.assertTrue(mio_dir.is_dir(), "Mio 必須存在實體 Persona 目錄")
        
        # 驗證 PDCA 狀態契約
        state_file = mio_dir / "pdca" / "state.json"
        self.assertTrue(state_file.is_file(), "Mio 必須納入正規 PDCA state.json 治理")
        s_data = json.loads(state_file.read_text(encoding="utf-8"))
        self.assertEqual(s_data.get("role_id"), "persona.mio")
        self.assertEqual(s_data.get("status"), "RUNNING")

        # 驗證圖文發布契約 (若有 approved 貼文，必須嚴格攜帶同名 json 圖片 manifest)
        approved_dir = mio_dir / "approved"
        if approved_dir.is_dir():
            for post_txt in approved_dir.glob("mio-post-*.txt"):
                manifest = post_txt.with_suffix(".json")
                self.assertTrue(
                    manifest.is_file(),
                    f"Mio 待發布貼文 {post_txt.name} 必須具備專屬配圖 manifest (.json)！禁止發布純文字。"
                )

    def test_venus_aesthetic_governance_capabilities(self):
        """驗證維納斯 (Venus) 美學總監治理能力與 Taste Skill 綁定"""
        import yaml
        reg_path = self.repo_root / ".agent" / "roles" / "registry.yaml"
        reg_data = yaml.safe_load(reg_path.read_text(encoding="utf-8"))
        venus = next((r for r in reg_data.get("roles", []) if r.get("id") == "system.aesthetic_director_venus"), None)
        self.assertIsNotNone(venus, "Venus 角色必須存在於 registry.yaml")
        
        # 驗證 primary_skills
        self.assertIn("design-taste-frontend", venus.get("primary_skills", []))
        self.assertIn("web.design_taste.enforce", venus.get("capabilities", []))

    def test_themis_command_diff_capability(self):
        """驗證忒彌斯 (Themis) 時序差分與契約防漂移能力"""
        from scripts.themis_project_diff import run_all_projects_summary_diff
        result, report_md = run_all_projects_summary_diff(self.agent_data)
        self.assertIn("忒彌斯全生態專案島嶼狀態簡報", report_md)
        self.assertIn("島嶼總數", report_md)

if __name__ == "__main__":
    unittest.main()
