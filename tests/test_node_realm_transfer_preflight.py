"""Static fail-closed preflight contracts for staged Node Realm migration.

These tests do not constitute a real Windows/ONE transfer receipt.
"""
from pathlib import Path
import unittest

SRC = (Path(__file__).resolve().parents[1] / "scripts" / "bootstrap_clean_windows_node.ps1").read_text(encoding="utf-8")


class StagedTransferPreflightTests(unittest.TestCase):
    def test_custom_enrolled_node_id_read_before_computername_fallback(self):
        self.assertLess(
            SRC.index("$NodeId = [string]$existingBinding.node_id"),
            SRC.index("$NodeId = $env:COMPUTERNAME.ToLowerInvariant()")
        )
        self.assertIn("SwitchRealm requires an existing Node enrollment.", SRC)

    def test_target_realm_must_be_explicit(self):
        self.assertIn("if ($SwitchRealm -and [string]::IsNullOrWhiteSpace($RealmId))", SRC)
        self.assertIn("SwitchRealm requires an explicit target RealmId.", SRC)
        self.assertIn("SwitchRealm target matches current Realm; no transfer staged.", SRC)

    def test_no_unverified_cutover(self):
        self.assertIn("--stage-only", SRC)
        self.assertIn("agentos_active_binding=PRESERVED", SRC)
        self.assertIn("NOT_AUTHORIZED_UNTIL_SUPERVISOR_ROLLBACK_VERIFIED", SRC)
        self.assertNotIn("Copy-Item -LiteralPath $stagedConfig -Destination $originalConfig", SRC)


if __name__ == "__main__":
    unittest.main()
