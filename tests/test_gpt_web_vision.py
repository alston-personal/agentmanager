from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentos_node.gpt_web_vision import build_plan, validate_request


class GptWebVisionTests(unittest.TestCase):
    def test_invoice_request_builds_bounded_plan(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            image = root / "invoice.png"
            image.write_bytes(b"image")
            plan = build_plan({
                "schema": "agentos.gpt-web-vision-request/v0.1",
                "capability": "vision.invoice.extract",
                "image_path": "invoice.png",
            }, workspace=root)
        self.assertEqual(plan["action"], "desktop.plan.execute")
        steps = plan["plan"]["steps"]
        self.assertEqual(steps[0]["action"], "desktop.open_url")
        self.assertEqual(steps[2]["action"], "desktop.image_paste")
        self.assertTrue(plan["gpt_web"]["response_adapter_required"])

    def test_request_rejects_workspace_escape(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "workspace"
            root.mkdir()
            outside = Path(td) / "outside.png"
            outside.write_bytes(b"image")
            with self.assertRaises(PermissionError):
                validate_request({
                    "schema": "agentos.gpt-web-vision-request/v0.1",
                    "capability": "vision.invoice.extract",
                    "image_path": str(outside),
                }, workspace=root)

    def test_request_rejects_unknown_capability(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            image = root / "x.png"
            image.write_bytes(b"image")
            with self.assertRaises(ValueError):
                validate_request({
                    "schema": "agentos.gpt-web-vision-request/v0.1",
                    "capability": "shell.exec",
                    "image_path": "x.png",
                }, workspace=root)


if __name__ == "__main__":
    unittest.main()
