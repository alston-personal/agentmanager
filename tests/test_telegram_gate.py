from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_core import telegram_gate


class TelegramGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.receipt_file = Path(self.temp_dir.name) / "telegram_receipts.jsonl"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_non_core_node_is_fenced_and_records_receipt(self) -> None:
        with patch.object(telegram_gate, "resolve_current_node_id", return_value="vopc5750"), \
             patch.dict("os.environ", {"AGENTOS_ONE_RUNTIME": "false", "AGENTOS_TELEGRAM_GATEWAY_ENABLED": ""}, clear=False), \
             patch.object(telegram_gate, "RECEIPT_LOG", self.receipt_file), \
             patch("requests.post") as mock_post, \
             patch("requests.get", side_effect=Exception("no local bridge")):
            
            allowed, reason = telegram_gate.is_one_core_runtime()
            self.assertFalse(allowed)
            self.assertIn("non_core_node_fenced", reason)

            result = telegram_gate.send_governed_telegram("Hello from secondary node")
            self.assertFalse(result)
            mock_post.assert_not_called()

            self.assertTrue(self.receipt_file.exists())
            content = self.receipt_file.read_text(encoding="utf-8")
            self.assertIn("non_core_node_fenced:vopc5750", content)
            self.assertIn("Hello from secondary node", content)

    def test_one_core_node_is_authorized(self) -> None:
        with patch.object(telegram_gate, "resolve_current_node_id", return_value="oracle-core-node"), \
             patch.dict("os.environ", {"AGENTOS_ONE_RUNTIME": "true"}, clear=False), \
             patch("requests.post") as mock_post:
            
            # Simulate bridge 200 OK
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            allowed, reason = telegram_gate.is_one_core_runtime()
            self.assertTrue(allowed)
            self.assertIn("core_node_match", reason)

            result = telegram_gate.send_governed_telegram("Hello from core ONE runtime")
            self.assertTrue(result)
            mock_post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
