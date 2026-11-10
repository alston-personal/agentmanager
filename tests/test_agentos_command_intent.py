import json
import tempfile
import unittest
from pathlib import Path
from scripts.resolve_agentos_command import resolve_command

class CommandIntentTests(unittest.TestCase):
    def test_status_diff_resolves_registered_action(self):
        result=resolve_command("/status-diff")
        self.assertEqual(result["action"],"themis.inventory.diff")
        self.assertEqual(result["dispatch"]["capability"],"agentos.command")
        self.assertEqual(result["dispatch"]["operation"],"invoke")
        self.assertEqual(result["dispatch"]["payload"]["command"],"/status-diff")
        self.assertEqual(result["authority"],"ONE_CAPABILITY_AND_RUNTIME_AUTHORIZATION_REQUIRED")
        self.assertNotIn("runner",result["dispatch"]["payload"])
        self.assertNotIn("node_id",result["dispatch"]["payload"])

    def test_reject_unknown_and_injection(self):
        for command in ("/unknown-command-123","/status-diff;id","../status-diff",
                        "/status-diff something","/STATUS-DIFF"):
            with self.assertRaises(ValueError):
                resolve_command(command)

    def test_mismatched_or_invalid_registry_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/"status-diff.json").write_text(json.dumps({
                "schema":"agentos.realm-command/v0.1",
                "command":"/other",
                "action":"themis.inventory.diff",
                "runner":"sh -c dangerous"}))
            with self.assertRaises(ValueError):
                resolve_command("/status-diff",registry=root)
            (root/"status-diff.json").write_text(json.dumps({
                "schema":"agentos.realm-command/v0.1",
                "command":"/status-diff",
                "action":"evil;run",
                "runner":"sh -c dangerous"}))
            with self.assertRaises(ValueError):
                resolve_command("/status-diff",registry=root)

if __name__=="__main__":
    unittest.main()
