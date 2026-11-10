import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from scripts import gaia_intake_probe


class GaiaRunnerProbeTest(unittest.TestCase):
    def test_runner_window_intent_registered_as_read_only(self):
        from agent_core.runner_window import resolve_intent
        from agentos_node import bootstrap_control as bc
        from agentos_node.bootstrap_scheduler import policy_for
        intent, params = resolve_intent(
            "agentos.gaia", "intake.inspect", source_commit="a" * 40, payload={})
        self.assertEqual(intent.action, bc.ACTION_GAIA_INTAKE_INSPECT)
        self.assertIn(intent.action, bc.ALLOWED_ACTIONS)
        self.assertEqual(params, {"source_commit": "a" * 40})
        self.assertEqual(policy_for(intent.action).role, "control")
        self.assertEqual(intent.allowed_payload_keys, frozenset())
        with self.assertRaises(ValueError):
            resolve_intent("agentos.gaia", "intake.inspect",
                           source_commit="a" * 40, payload={"command": "create"})

    @patch("scripts.gaia_proposal_intake.examine")
    @patch("agentos_node.bootstrap_control._run_canonical_script")
    def test_oracle_handler_uses_installed_code_not_remote_script(self, run, examine):
        from agentos_node import bootstrap_control as bc
        examine.return_value = {
            "review": {
                "schema": "agentos.gaia-review/v1",
                "decision": {"disposition": "NEEDS_EVIDENCE", "canonical_parent": None},
            }
        }
        receipt = bc._execute(bc.ACTION_GAIA_INTAKE_INSPECT, "a" * 40)
        self.assertTrue(receipt["ok"])
        self.assertEqual(receipt["gaia_intake"]["disposition"], "NEEDS_EVIDENCE")
        self.assertFalse(receipt["gaia_intake"]["execution_authorized"])
        self.assertFalse(receipt["gaia_intake"]["creation_authorized"])
        self.assertEqual(receipt["source_commit"], "a" * 40)
        run.assert_not_called()
        examine.assert_called_once()

    def test_probe_is_bounded_and_reports_non_authority(self):
        review = {
            "schema": "agentos.gaia-review/v1",
            "content_hash": "a" * 64,
            "decision": {"disposition": "NEEDS_EVIDENCE", "canonical_parent": None},
        }
        with patch.object(gaia_intake_probe, "examine", return_value={"review": review}) as examine:
            output = io.StringIO()
            with redirect_stdout(output):
                status = gaia_intake_probe.main()
        self.assertEqual(status, 0)
        self.assertEqual(examine.call_args.args[0], {
            "title": "Personal Device Secretary", "kind": "project",
            "related_asset_ids": ["project://mobile-node"],
        })
        self.assertIn("gaia_intake_probe=PASS", output.getvalue())
        self.assertIn("gaia_intake_execution_authorized=false", output.getvalue())
        self.assertIn("gaia_intake_creation_authorized=false", output.getvalue())
        self.assertNotIn("work_item_registered", output.getvalue())


if __name__ == "__main__":
    unittest.main()
