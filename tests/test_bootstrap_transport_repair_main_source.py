"""The existing Bootstrap Control transport repair must not route to legacy integration."""
import unittest
from unittest.mock import patch

from agentos_node import bootstrap_control


class TransportRepairCanonicalSourceTest(unittest.TestCase):
    def test_exact_source_repair_uses_main_not_integration(self):
        source = "a" * 40
        with patch.object(bootstrap_control, "_run_canonical_script", return_value={"ok": True}) as call:
            result = bootstrap_control._execute(bootstrap_control.ACTION_REPAIR_TRANSPORT, source)
        self.assertEqual(result, {"ok": True})
        call.assert_called_once_with(
            "scripts/repair_antigravity_relay_user.sh",
            timeout=180,
            source_commit=source,
            env_extra={"AGENTOS_ACTION_SPOOL_PREPROVISIONED": "1", "AGENTOS_REF": "main"},
        )

    def test_unpinned_repair_cannot_default_to_integration(self):
        with patch.object(bootstrap_control, "_run_canonical_script", return_value={"ok": True}) as call:
            bootstrap_control._execute(bootstrap_control.ACTION_REPAIR_TRANSPORT, None)
        self.assertEqual(call.call_args.kwargs["env_extra"]["AGENTOS_REF"], "main")
        self.assertIsNone(call.call_args.kwargs["source_commit"])

    def test_existing_repair_script_enforces_exact_sha_and_realm_separation(self):
        from pathlib import Path
        script = (Path(__file__).resolve().parents[1] / "scripts" /
                  "repair_antigravity_relay_user.sh").read_text(encoding="utf-8")
        self.assertIn('git -C "$REPO" merge-base --is-ancestor "$SOURCE_COMMIT" "$SOURCE_REF_HEAD"', script)
        self.assertIn('realm_fabric_mutation=NONE', script)
        self.assertNotIn("systemctl --user restart agentos-realm-fabric.service", script)


if __name__ == "__main__":
    unittest.main()
