# PR rerun trigger 2: fixed governed Action Relay bootstrap validation
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentos_node.action_relay import ActionRelayClient, ActionRelayWorker, ACTIONS


class ActionRelayTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name) / "relay"

    def tearDown(self):
        self.td.cleanup()

    @patch("agentos_node.action_relay._share", lambda *args, **kwargs: None)
    def test_rejects_arbitrary_action(self):
        client = ActionRelayClient(self.root)
        with self.assertRaises(ValueError):
            client.submit("shell.exec", {"command": "rm -rf /"})

    @patch("agentos_node.action_relay._share", lambda *args, **kwargs: None)
    def test_capsule_contains_no_command_field(self):
        client = ActionRelayClient(self.root)
        capsule = client.submit("layoutlab.api.restart", {})
        self.assertEqual(capsule["action"], "layoutlab.api.restart")
        self.assertNotIn("command", capsule)
        self.assertFalse(capsule["authority"]["arbitrary_shell"])

    @patch("agentos_node.action_relay._share", lambda *args, **kwargs: None)
    def test_worker_dispatches_only_registered_handler(self):
        client = ActionRelayClient(self.root)
        capsule = client.submit("layoutlab.api.restart", {})
        with patch.dict(ACTIONS, {"layoutlab.api.restart": lambda params: {"ok": True, "marker": "called"}}, clear=True):
            receipt = ActionRelayWorker(self.root).process_one()
        self.assertTrue(receipt["ok"])
        self.assertEqual(receipt["marker"], "called")
        self.assertEqual(receipt["capsule_id"], capsule["capsule_id"])

    @patch("agentos_node.action_relay._share", lambda *args, **kwargs: None)
    def test_digest_tampering_is_rejected(self):
        client = ActionRelayClient(self.root)
        capsule = client.submit("layoutlab.api.restart", {})
        path = self.root / "inbox" / f"{capsule['capsule_id']}.json"
        data = json.loads(path.read_text())
        data["params"] = {"service": "other"}
        path.write_text(json.dumps(data))
        receipt = ActionRelayWorker(self.root).process_one()
        self.assertFalse(receipt["ok"])
        self.assertIn("digest mismatch", receipt["error"])


if __name__ == "__main__":
    unittest.main()
