#!/usr/bin/env python3
"""
單元測試：全生態輕量網頁統計探針合約驗證
Tests for AgentOS Web Telemetry Probe Contract
"""
import unittest
from pathlib import Path


class TestWebTelemetryContract(unittest.TestCase):
    def test_telemetry_script_exists_and_compliant(self):
        script_path = Path("/home/ubuntu/agentmanager/web/telemetry.js")
        self.assertTrue(script_path.exists(), "telemetry.js must exist")

        content = script_path.read_text(encoding="utf-8")
        # 驗證符合輕量與規範
        self.assertIn("agentos.web-telemetry/v1", content)
        self.assertIn("navigator.sendBeacon", content)
        self.assertIn("doNotTrack", content)
        self.assertNotIn("document.cookie", content, "Must be cookie-free")
        self.assertLess(len(content.encode("utf-8")), 2048, "Probe must be small and lightweight")


if __name__ == "__main__":
    unittest.main()
