from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentos_node.gpt_web_vision import build_harvest_task, build_plan, parse_harvest_receipt, parse_response_text, validate_request


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
        self.assertTrue(plan["gpt_web"]["request_id"].startswith("agentos-gpt-web-"))
        self.assertIn(plan["gpt_web"]["request_id"], steps[3]["text"])

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


class GptWebVisionResponseTests(unittest.TestCase):
    def test_harvest_task_is_scoped_to_request_and_session(self):
        task = build_harvest_task(session_id="chatgpt-session-1", request_id="invoice:req:12345678")
        self.assertEqual(task["action"], "agent.context.harvest")
        self.assertEqual(task["provider"], "gpt-web")
        self.assertEqual(task["session_id"], "chatgpt-session-1")
        self.assertEqual(task["payload"]["selector"], "assistant.response_by_request_id")
        self.assertEqual(task["payload"]["request_id"], "invoice:req:12345678")

    def test_response_parser_requires_raw_correlated_json(self):
        payload = parse_response_text(
            '{"agentos_request_id":"invoice:req:12345678","total_amount":50}',
            request_id="invoice:req:12345678",
        )
        self.assertEqual(payload["total_amount"], 50)
        with self.assertRaises(ValueError):
            parse_response_text(
                'json: {"agentos_request_id":"invoice:req:12345678"}',
                request_id="invoice:req:12345678",
            )
        with self.assertRaises(ValueError):
            parse_response_text(
                '{"agentos_request_id":"different"}',
                request_id="invoice:req:12345678",
            )

    def test_harvest_receipt_requires_matching_request(self):
        receipt = {
            "schema": "agentos.session-receipt/v0.1",
            "request_id": "session-harvest-1",
            "session_id": "chatgpt-session-1",
            "result": {
                "request_id": "invoice:req:12345678",
                "assistant_text": '{"agentos_request_id":"invoice:req:12345678","total_amount":50}',
            },
        }
        parsed = parse_harvest_receipt(receipt, request_id="invoice:req:12345678")
        self.assertEqual(parsed["payload"]["total_amount"], 50)
        receipt["result"]["request_id"] = "other"
        with self.assertRaises(ValueError):
            parse_harvest_receipt(receipt, request_id="invoice:req:12345678")
