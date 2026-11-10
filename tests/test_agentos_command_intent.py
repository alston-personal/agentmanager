import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from scripts.resolve_agentos_command import resolve_command

class CommandIntentTests(unittest.TestCase):
    def test_status_diff_resolves_registered_action(self):
        result=resolve_command("/status-diff")
        self.assertEqual(result["action"],"themis.inventory.diff")
        self.assertEqual(result["dispatch"]["capability"],"agentos.command")
        self.assertEqual(result["dispatch"]["operation"],"invoke")
        self.assertEqual(result["dispatch"]["payload"]["command"],"/status-diff")
        self.assertEqual(result["dispatch"]["payload"]["command_action"],"themis.inventory.diff")
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


    def test_one_router_rejects_unregistered_command_and_disallows_runner_paths(self):
        from agent_core.runner_window import resolve_intent
        from agentos_node import bootstrap_control as bc
        intent, params=resolve_intent("agentos.command","invoke",
            source_commit="a"*40,
            payload={"command":"/status-diff","command_action":"themis.inventory.diff"})
        self.assertEqual(intent.action,bc.ACTION_COMMAND_INVOKE)
        self.assertEqual(params["command"],"/status-diff")
        self.assertEqual(params["command_action"],"themis.inventory.diff")
        with self.assertRaises(ValueError):
            resolve_intent("agentos.command","invoke",source_commit="a"*40,
                           payload={"command":"/status-diff","command_action":"themis.inventory.diff",
                                    "runner":"sh -c whoami"})

    def test_runtime_executes_installed_themis_only(self):
        from agentos_node import bootstrap_control as bc
        good={"command":"/status-diff","command_action":"themis.inventory.diff"}
        fake={"schema":"agentos.inventory-diff-receipt/v1","steward":"governance.themis_command_steward",
              "current":{"projects_summary":{"total_projects":1},"git":{"commit_sha":"a"*40},"atlas":{}},
              "delta":{"has_baseline":False}}
        with patch("scripts.themis_status_diff.run_inventory_diff",return_value=(fake,"report")) as mock:
            result=bc._execute(bc.ACTION_COMMAND_INVOKE,"a"*40,params=good)
            self.assertTrue(result["ok"])
            self.assertEqual(result["receipt"]["report_markdown"],"report")
            mock.assert_called_once_with(save=True)
        with self.assertRaises(ValueError):
            bc._execute(bc.ACTION_COMMAND_INVOKE,"a"*40,
                        params={"command":"/evil","command_action":"themis.inventory.diff"})

if __name__=="__main__":
    unittest.main()
