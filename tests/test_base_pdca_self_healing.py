import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import tempfile
import json

from agent_core.base_pdca import BasePDCAWorker


class TestBasePDCASelfHealing(unittest.TestCase):
    def test_gui_worker_fallback_and_self_healing_recheck(self):
        with tempfile.TemporaryDirectory() as tmp_data, tempfile.TemporaryDirectory() as tmp_proj:
            data_root = Path(tmp_data)
            proj_root = Path(tmp_proj)

            worker = BasePDCAWorker("the-paw", data_root, proj_root)

            # Mock check to fail on first run, pass on second run
            check_counts = [0]
            target_test_file = proj_root / "tests" / "test_dummy.py"

            def mock_check(plan_data, do_data):
                check_counts[0] += 1
                if target_test_file.exists():
                    return {"verdict": "PASS", "findings": ["✅ target_dummy.py exists"]}
                return {"verdict": "FAIL", "findings": ["❌ test_dummy.py missing"]}

            worker.check = mock_check

            remediation_reply = (
                "需要補齊測試檔案：\n"
                f"```python {target_test_file}\n"
                "def test_ok(): assert True\n"
                "```\n"
            )

            with patch("agent_core.gui_worker_client.query_gui_worker", return_value={"status": "PASS", "provider": "chatgpt-web", "reasoning": remediation_reply}):
                res = worker.run_cycle()

            self.assertEqual(res.check.get("verdict"), "PASS")
            self.assertTrue(res.check.get("self_healed"))
            self.assertTrue(target_test_file.exists())
            self.assertIn("test_ok", target_test_file.read_text())
            self.assertEqual(check_counts[0], 2)


if __name__ == "__main__":
    unittest.main()
