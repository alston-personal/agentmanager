"""Contract tests for read-only browser inventory (#1735)."""
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
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

    def test_launch_hints_do_not_change_identity_verdict(self):
        fake = {"debugging_port_flag": 1, "debugging_pipe_flag": 0,
                "profile_flag": 1, "browser_processes": 2,
                "proxy_like_processes": 1, "unknown_process_argv": 0}
        with patch.object(module, "browser_processes", return_value=[]), patch.object(
            module, "targets", return_value={"state": "CDP_READY", "page_hosts": []}
        ), patch.object(module, "cdp_launch_hints", return_value=fake), patch.object(
            module, "process_visibility", return_value={
                "pid_entries": 2, "cmdline_readable": 2,
                "cmdline_permission_denied": 0, "cmdline_other_errors": 0,
                "chromium_like_processes": 2
            }
        ):
            result = module.inventory()
        self.assertEqual(result["cdp_launch_hints"], fake)
        self.assertFalse(result["account_identity_verified"])
        self.assertEqual(result["classification"], "UNVERIFIED")


    def test_socket_owner_profile_is_opaque_and_specific_to_owner(self):
        with TemporaryDirectory() as dirname:
            root = Path(dirname)
            owner = root / "1234"
            owner.mkdir()
            owner.joinpath("cmdline").write_bytes(
                b"/usr/bin/chromium\0--user-data-dir=/private/oursong-profile\0")
            result = module.socket_owner_profile_evidence(owner)
            self.assertEqual(result["state"], "EXPLICIT_PROFILE")
            self.assertEqual(len(result["profile_id"]), 16)
            self.assertNotIn("/private", str(result))
            owner.joinpath("cmdline").write_bytes(b"/usr/bin/chromium\0")
            self.assertEqual(module.socket_owner_profile_evidence(owner)["state"],
                             "PROFILE_ARG_ABSENT")

    def test_listener_owner_classification_is_sanitized(self):
        with TemporaryDirectory() as dirname:
            root = Path(dirname)
            (root / "net").mkdir()
            (root / "net/tcp").write_text(
                "sl local_address rem_address st tx_queue rx_queue tr tm->when retrnsmt uid timeout inode\n"
                "0: 0100007F:2407 00000000:0000 0A 0:0 00:0 0 1000 0 98765\n"
            )
            pid = root / "1234"
            (pid / "fd").mkdir(parents=True)
            (pid / "comm").write_text("chromium\n")
            (pid / "fd/3").symlink_to("socket:[98765]")
            result = module.socket_ownership(root, (9223, 9224))
        record = result["records"][9223]
        self.assertEqual(record["state"], "LISTENER_OWNER_OBSERVED")
        self.assertEqual(record["owner_categories"], ["BROWSER"])
        self.assertEqual(record["owner_process_count"], 1)
        self.assertNotIn("98765", str(result))
        self.assertNotIn("1234", str(result))
        self.assertEqual(result["records"][9224]["state"], "NO_LISTENER_FOUND")

    def test_unmapped_listener_does_not_claim_account(self):
        with TemporaryDirectory() as dirname:
            root = Path(dirname)
            (root / "net").mkdir()
            (root / "net/tcp").write_text(
                "header\n0: 0100007F:2406 00000000:0000 0A 0:0 00:0 0 1000 0 99\n"
            )
            result = module.socket_ownership(root, (9222,))
        self.assertEqual(result["records"][9222]["state"], "LISTENER_OWNER_UNRESOLVED")
        self.assertNotIn("account_identity_verified", result)

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
