from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_core import spec_steward_o3_cli as cli


class SpecStewardO3CliTests(unittest.TestCase):
    def test_runtime_root_must_be_absolute(self):
        parser = cli.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--runtime-root", "relative/runtime", "bootstrap"])

    def test_bootstrap_is_idempotent_and_never_emits_verified_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = str(Path(tmp).resolve() / "runtime")
            first_out = io.StringIO()
            with patch("sys.stdout", first_out):
                first_code = cli.main(["--runtime-root", root, "bootstrap"])
            second_out = io.StringIO()
            with patch("sys.stdout", second_out):
                second_code = cli.main(["--runtime-root", root, "bootstrap"])
            self.assertEqual(first_code, 0)
            self.assertEqual(second_code, 0)
            first = json.loads(first_out.getvalue())
            second = json.loads(second_out.getvalue())
            self.assertTrue(first["employee_created"])
            self.assertFalse(second["employee_created"])
            self.assertFalse(first["verified_marker_emitted"])
            self.assertFalse(second["verified_marker_emitted"])

    def test_inspect_is_blocked_after_bootstrap_only_and_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "runtime"
            with patch("sys.stdout", io.StringIO()):
                cli.main(["--runtime-root", str(root), "bootstrap"])
            before = {
                str(path.relative_to(root)): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }
            out = io.StringIO()
            with patch("sys.stdout", out):
                code = cli.main(["--runtime-root", str(root), "inspect"])
            after = {
                str(path.relative_to(root)): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(code, 3)
            self.assertEqual(before, after)
            payload = json.loads(out.getvalue())
            self.assertFalse(payload["ready_for_live_marker"])
            self.assertFalse(payload["verified_marker_emitted"])

    def test_cli_has_no_dispatch_deploy_or_main_publish_subcommand(self):
        parser = cli.build_parser()
        subparsers = [action for action in parser._actions if hasattr(action, "choices") and action.choices]
        choices = set()
        for action in subparsers:
            choices.update(action.choices)
        self.assertEqual(choices, {"bootstrap", "inspect"})
        self.assertNotIn("dispatch", choices)
        self.assertNotIn("deploy", choices)
        self.assertNotIn("publish", choices)


if __name__ == "__main__":
    unittest.main()
