import unittest
from unittest.mock import patch

from agentos_node import bootstrap_control as bc


class OursongControlInboxContractTests(unittest.TestCase):
    def test_actions_are_allowlisted_and_exact_commit_scoped(self):
        self.assertIn(bc.ACTION_ACTIVATE_OURSONG_PERSONA, bc.ALLOWED_ACTIONS)
        self.assertIn(bc.ACTION_PROBE_OURSONG_PERSONA, bc.ALLOWED_ACTIONS)

    def test_execute_routes_only_to_fixed_activation_script(self):
        with patch.object(bc, "_run_canonical_script", return_value={"ok": True}) as run:
            out = bc._execute(
                bc.ACTION_ACTIVATE_OURSONG_PERSONA,
                "60d939cdc5cb204f500f3ac13b9be4abe05f49c1",
            )
        self.assertTrue(out["ok"])
        run.assert_called_once_with(
            "scripts/activate_oursong_persona_user.sh",
            timeout=240,
            source_commit="60d939cdc5cb204f500f3ac13b9be4abe05f49c1",
        )

    def test_status_routes_only_to_fixed_probe_script(self):
        with patch.object(bc, "_run_canonical_script", return_value={"ok": True}) as run:
            out = bc._execute(
                bc.ACTION_PROBE_OURSONG_PERSONA,
                "60d939cdc5cb204f500f3ac13b9be4abe05f49c1",
            )
        self.assertTrue(out["ok"])
        run.assert_called_once_with(
            "scripts/probe_oursong_persona_user.sh",
            timeout=60,
            source_commit="60d939cdc5cb204f500f3ac13b9be4abe05f49c1",
        )


if __name__ == "__main__":
    unittest.main()
