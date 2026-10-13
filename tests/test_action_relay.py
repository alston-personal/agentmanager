# CI trigger: governed Action Relay bootstrap validation
import json
import os
import stat
from types import SimpleNamespace
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentos_node.action_relay import ActionRelayClient, ActionRelayWorker, ACTIONS, _verify_continuation_capsule_owner


class ActionRelayTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name) / "relay"

    def tearDown(self):
        self.td.cleanup()

    def test_continuation_capsule_rejects_group_member_other_than_node_owner(self):
        capsule = self.root.parent / "candidate.json"
        capsule.write_text("{}")
        capsule.chmod(0o660)
        with patch("agentos_node.action_relay.pwd.getpwnam", return_value=SimpleNamespace(pw_uid=os.getuid()+1)), \
             patch("agentos_node.action_relay.grp.getgrnam", return_value=SimpleNamespace(gr_gid=os.getgid())):
            with self.assertRaises(PermissionError):
                _verify_continuation_capsule_owner(capsule)

    def test_continuation_capsule_accepts_correct_unix_owner_and_mode(self):
        capsule = self.root.parent / "candidate.json"
        capsule.write_text("{}")
        capsule.chmod(0o660)
        with patch("agentos_node.action_relay.pwd.getpwnam", return_value=SimpleNamespace(pw_uid=os.getuid())), \
             patch("agentos_node.action_relay.grp.getgrnam", return_value=SimpleNamespace(gr_gid=os.getgid())):
            _verify_continuation_capsule_owner(capsule)

    @patch("agentos_node.action_relay._share", lambda *args, **kwargs: None)
    def test_continuation_owner_denial_prevents_handler_side_effect(self):
        client = ActionRelayClient(self.root)
        capsule = client.submit("agentos.project.publish_continuation", {"project_id": "agentos-core"})
        called = []
        with patch("agentos_node.action_relay._verify_continuation_capsule_owner",
                   side_effect=PermissionError("untrusted owner")), \
             patch.dict(ACTIONS, {"agentos.project.publish_continuation":
                                  lambda params: called.append(params) or {"ok": True}}):
            receipt = ActionRelayWorker(self.root).process_one()
        self.assertFalse(receipt["ok"])
        self.assertIn("untrusted owner", receipt["error"])
        self.assertEqual(called, [])
        self.assertEqual(receipt["capsule_id"], capsule["capsule_id"])

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

    def test_legacy_site_sync_build_fails_closed_after_studio_web_authority_move(self):
        result = ACTIONS["site.sync_build"]({"site": "studio.milkcat.org"})
        self.assertFalse(result["ok"])
        self.assertTrue(result["blocked"])
        self.assertEqual(result["reason"], "legacy_zeus_writer_site_authority_retired")
        self.assertEqual(result["canonical_source_repository"], "alston-personal/studio-web")

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
