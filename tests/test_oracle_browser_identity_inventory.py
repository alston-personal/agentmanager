"""Contract tests for read-only browser inventory (#1735)."""
import importlib.util
from pathlib import Path
from unittest.mock import patch
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "oracle_browser_identity_inventory.py"
spec = importlib.util.spec_from_file_location("oracle_browser_identity_inventory", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class InventoryTests(unittest.TestCase):
    def test_profile_identifier_does_not_expose_path(self):
        path = "/home/ubuntu/private/chromium-profile"
        identity = module.profile_id(path)
        self.assertEqual(len(identity), 16)
        self.assertNotIn("ubuntu", identity)
        self.assertEqual(identity, module.profile_id(path))

    def test_cross_port_shared_profile_is_flagged(self):
        def processes(port):
            return [{"pid": port, "profile_id": "sameprofile", "profile_explicit": True}]
        with patch.object(module, "browser_processes", side_effect=processes), patch.object(
            module, "targets", return_value={"state": "CDP_READY", "page_hosts": []}
        ):
            result = module.inventory()
        self.assertEqual(result["classification"], "REVIEW_REQUIRED")
        self.assertEqual(result["shared_profile_ids"], ["sameprofile"])
        self.assertFalse(result["account_identity_verified"])

    def test_distinct_profiles_still_do_not_prove_login(self):
        with patch.object(module, "browser_processes", side_effect=lambda port: [
            {"pid": port, "profile_id": str(port), "profile_explicit": True}
        ]), patch.object(module, "targets", return_value={
            "state": "CDP_READY", "page_hosts": ["threads.net"]
        }):
            result = module.inventory()
        self.assertEqual(result["classification"], "UNVERIFIED")
        self.assertFalse(result["account_identity_verified"])


if __name__ == "__main__":
    unittest.main()
