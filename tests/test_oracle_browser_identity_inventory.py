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

    def test_process_visibility_is_diagnostic_only(self):
        records = [{"state": "CDP_READY", "processes": []}]
        defaults = {"cmdline_permission_denied": 0, "chromium_like_processes": 0}
        self.assertEqual(module.visibility_classification(records, defaults),
                         "CDP_READY_BROWSER_PROCESS_NOT_VISIBLE")
        self.assertEqual(module.visibility_classification(records, {
            **defaults, "cmdline_permission_denied": 4,
        }), "PROCESS_PERMISSION_OR_ISOLATION_POSSIBLE")
        self.assertEqual(module.visibility_classification(records, {
            **defaults, "chromium_like_processes": 2,
        }), "BROWSER_VISIBLE_PORT_MAPPING_UNRESOLVED")
        self.assertEqual(module.visibility_classification(records, {
            **defaults, "proc_scan_error": True,
        }), "PROC_SCAN_UNAVAILABLE")

    def test_inventory_cannot_verify_account_from_visible_browser(self):
        with patch.object(module, "browser_processes", return_value=[]), patch.object(
            module, "targets", return_value={"state": "CDP_READY", "page_hosts": ["www.threads.com"]}
        ), patch.object(module, "process_visibility", return_value={
            "pid_entries": 5, "cmdline_readable": 5, "cmdline_permission_denied": 0,
            "cmdline_other_errors": 0, "chromium_like_processes": 2
        }):
            result = module.inventory()
        self.assertEqual(result["process_visibility_classification"],
                         "BROWSER_VISIBLE_PORT_MAPPING_UNRESOLVED")
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
