import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "persona_post_reasoning", REPO / "scripts/persona_post_intent_generator.py"
)
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)

DECISION = {"should_post": True, "human_required": False,
            "reason": "verified context", "post_text": "今天想試試哪個小改變？"}


class PostReasoningTests(unittest.TestCase):
    def run_generator(self, results, *, liveness=False, claude=True, gemini=True, codex=False):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for directory in ("pdca", "events", "ir"):
                (root / directory).mkdir()
            now = datetime.now(timezone.utc).isoformat()
            state = {"cycle": 1, "energy_current": 80,
                     "pending_external_actions": [{"action_id": "consider-1",
                         "capability": "social.post.consider", "status": "candidate",
                         "liveness_pressure": liveness}]}
            for filename, value in (
                ("pdca/state.json", state), ("ir/current.json", {"ir_id": "test-ir"}),
                ("persona_state.json", {}), ("pdca/config.json", {"growth_mode": {"enabled": True}})
            ):
                (root / filename).write_text(json.dumps(value), encoding="utf-8")
            (root / "events/events.jsonl").write_text(
                json.dumps({"type": "post.sent", "timestamp": now}) + "\n", encoding="utf-8"
            )
            with patch.object(sys, "argv", ["generator", "--persona-dir", str(root)]), \
                 patch.object(generator, "discover_executor", return_value=["claude"] if claude else None), \
                 patch.object(generator, "discover_gemini_executor", return_value="gemini" if gemini else None), \
                 patch.object(generator, "discover_codex_executor", return_value="codex" if codex else None), \
                 patch.object(generator.subprocess, "run", side_effect=results) as run, \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(generator.main(), 0)
            state = json.loads((root / "pdca/state.json").read_text())
            receipt = json.loads((root / state["last_post_reasoning_receipt"]).read_text())
            actions = [x for x in state["pending_external_actions"] if x["capability"] == "social.post.publish"]
            return json.loads(output.getvalue()), state, receipt, actions, run.call_args_list

    def test_gemini_success_is_linked_to_actual_provider_after_claude_timeout(self):
        output, state, receipt, actions, calls = self.run_generator([
            subprocess.TimeoutExpired("claude", 45),
            subprocess.CompletedProcess("gemini", 0, json.dumps({"response": json.dumps(DECISION)}), "")
        ])
        self.assertEqual(output["status"], "CANDIDATE_CREATED")
        self.assertEqual(receipt["status"], "PASS")
        self.assertFalse(receipt["fallback_used"])
        self.assertEqual(actions[0]["reasoning_executor"], "gemini_cli")
        self.assertEqual(actions[0]["reasoning_receipt_ref"], state["last_post_reasoning_receipt"])
        self.assertEqual([x["status"] for x in receipt["attempts"]], ["TIMEOUT", "PASS"])
        self.assertEqual([x.kwargs["timeout"] for x in calls], [45, 60])
        self.assertTrue(all(x.kwargs["stdin"] == subprocess.DEVNULL for x in calls))
        self.assertTrue(all(x["elapsed_ms"] >= 0 for x in receipt["attempts"]))
        self.assertEqual(receipt["generator_sha256"], generator.hashlib.sha256(Path(generator.__file__).read_bytes()).hexdigest())

    def test_claude_success_does_not_invoke_gemini(self):
        _, _, receipt, actions, calls = self.run_generator([
            subprocess.CompletedProcess("claude", 0, json.dumps(DECISION), "")
        ])
        self.assertEqual(len(calls), 1)
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(actions[0]["reasoning_executor"], "antigravity_claude")

    def test_codex_can_author_after_both_existing_providers_fail(self):
        def execute(argv, **kwargs):
            if argv[0] == "claude":
                raise subprocess.TimeoutExpired("claude", 45)
            if argv[0] == "gemini":
                return subprocess.CompletedProcess(argv, 1, "", "unsupported_client")
            self.assertEqual(argv[0], "codex")
            self.assertIn("--ephemeral", argv)
            self.assertEqual(argv[argv.index("--sandbox") + 1], "read-only")
            cli_home = Path(kwargs["env"]["CODEX_HOME"])
            settings = (cli_home / "config.toml").read_text()
            self.assertIn("shell_tool = false", settings)
            self.assertIn("apps = false", settings)
            self.assertNotIn("mcp_servers", settings)
            Path(argv[argv.index("--output-last-message") + 1]).write_text(json.dumps(DECISION))
            return subprocess.CompletedProcess(argv, 0, "progress logs are not the answer", "")
        _, _, receipt, actions, calls = self.run_generator(execute, codex=True)
        self.assertEqual([x["status"] for x in receipt["attempts"]], ["TIMEOUT", "NONZERO", "PASS"])
        self.assertEqual(receipt["status"], "PASS")
        self.assertFalse(receipt["fallback_used"])
        self.assertEqual(actions[0]["reasoning_executor"], "codex_cli")
        self.assertEqual(len(calls), 3)

    def test_codex_failure_remains_deferred_or_truthful_fallback(self):
        for liveness in (False, True):
            with self.subTest(liveness=liveness):
                _, _, receipt, actions, _ = self.run_generator([
                    subprocess.CompletedProcess("codex", 1, "", "authentication required private-secret")
                ], claude=False, gemini=False, codex=True, liveness=liveness)
                self.assertEqual(receipt["attempts"][0]["failure_class"], "AUTH_REQUIRED")
                self.assertEqual(receipt["status"], "FALLBACK" if liveness else "DEFER")
                self.assertNotIn("private-secret", json.dumps(receipt))
                if actions:
                    self.assertEqual(actions[0]["reasoning_executor"], "safe_liveness_fallback")

    def test_unsupported_oauth_defers_without_publishing_or_leaking_error(self):
        secret = "private-prompt-and-credential-12345"
        output, _, receipt, actions, _ = self.run_generator([
            subprocess.TimeoutExpired("claude", 45),
            subprocess.CompletedProcess("gemini", 1, json.dumps({"error": {
                "type": "IneligibleTierError", "message": "migrate to Antigravity " + secret}}), "")
        ])
        self.assertEqual(output["status"], "DEFER")
        self.assertEqual(actions, [])
        self.assertEqual(receipt["attempts"][1]["failure_class"], "OAUTH_CLIENT_UNSUPPORTED")
        self.assertNotIn(secret, json.dumps([receipt, output]))

    def test_liveness_fallback_is_never_labeled_as_model_success(self):
        _, _, receipt, actions, _ = self.run_generator([
            subprocess.TimeoutExpired("claude", 45),
            subprocess.CompletedProcess("gemini", 1, "", "quota exceeded")
        ], liveness=True)
        self.assertEqual(receipt["status"], "FALLBACK")
        self.assertTrue(receipt["fallback_used"])
        self.assertEqual(actions[0]["reasoning_executor"], "safe_liveness_fallback")
        self.assertTrue(actions[0]["requires_real_adapter_receipt"])
        self.assertEqual(actions[0]["status"], "candidate")
        self.assertEqual(receipt["attempts"][1]["failure_class"], "RATE_LIMITED")

    def test_malformed_decision_is_not_a_pass_or_publication(self):
        for malformed in ([], False, {**DECISION, "should_post": "false"}, {**DECISION, "human_required": None}):
            with self.subTest(malformed=malformed):
                _, _, receipt, actions, _ = self.run_generator([
                    subprocess.CompletedProcess("claude", 0, json.dumps(malformed), "")
                ], gemini=False)
                self.assertEqual(receipt["status"], "DEFER")
                self.assertEqual(receipt["attempts"][0]["status"], "INVALID_OUTPUT")
                self.assertEqual(actions, [])

    def test_explicit_no_post_remains_no_post(self):
        output, state, receipt, actions, _ = self.run_generator([
            subprocess.CompletedProcess("claude", 0, json.dumps({**DECISION, "should_post": False, "post_text": ""}), "")
        ], liveness=True)
        self.assertEqual(output["status"], "NO_POST")
        self.assertEqual(state["pending_external_actions"][0]["decision"], "no_post")
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(actions, [])

    def test_missing_executors_emit_durable_unavailable_receipt(self):
        output, _, receipt, actions, calls = self.run_generator([], claude=False, gemini=False)
        self.assertEqual(output["status"], "DEFER")
        self.assertEqual(receipt["status"], "UNAVAILABLE")
        self.assertEqual(receipt["attempts"], [])
        self.assertEqual(actions, [])
        self.assertEqual(calls, [])

    def test_launch_error_is_classified_without_raw_exception(self):
        _, _, receipt, actions, _ = self.run_generator([OSError("private error")], gemini=False)
        self.assertEqual(receipt["attempts"][0]["failure_class"], "UNAVAILABLE")
        self.assertNotIn("private error", json.dumps(receipt))
        self.assertEqual(actions, [])

    def test_classification_signatures_and_unknown_remain_bounded(self):
        examples = {"Unknown argument: skip-trust": "CLI_CONTRACT",
                    "401 Unauthorized": "AUTH_REQUIRED", "ENOTFOUND host": "NETWORK",
                    "FatalConfigError": "CONFIG_ERROR", "workspace trust required": "WORKSPACE_TRUST_REQUIRED",
                    "EBADENGINE": "NODE_INCOMPATIBLE", "hook failed": "HOOK_ERROR",
                    "MCP connection failed": "MCP_ERROR", "opaque private error": "UNKNOWN_NONZERO"}
        for error, expected in examples.items():
            self.assertEqual(generator.failure_class(error), expected)
        self.assertEqual(generator.failure_class("", json.dumps({"response": "quota and login"})), "UNKNOWN_NONZERO")

    def test_timeout_keeps_timeout_status_with_safe_hint(self):
        error = subprocess.TimeoutExpired("claude", 45, stderr=b"authentication required: private-secret")
        attempt = generator.reasoning_attempt("claude", time.monotonic(), "TIMEOUT", error=error)
        self.assertEqual(attempt["failure_class"], "TIMEOUT")
        self.assertEqual(attempt["failure_hint"], "AUTH_REQUIRED")
        self.assertNotIn("private-secret", json.dumps(attempt))


if __name__ == "__main__":
    unittest.main()
