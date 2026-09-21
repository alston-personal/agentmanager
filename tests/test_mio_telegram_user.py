"""Offline safety tests for Mio's private Telegram transport."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import mio_telegram_user as mio


class MioTelegramBridgeTests(unittest.TestCase):
    def test_module_launch_does_not_import_shadow_script(self):
        # Running scripts/mio_telegram_user.py directly prepends scripts/ and
        # imports scripts/agentos_node.py instead of the agentos_node package.
        repo = Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            [sys.executable, "-m", "scripts.mio_telegram_user", "--help"],
            cwd=repo, text=True, capture_output=True, timeout=10,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Mio private Telegram bridge", completed.stdout)

    def test_safe_diagnostics_never_echo_raw_executor_or_private_chat(self):
        sensitive = "SENSITIVE_PRIVATE_MESSAGE_TOKEN"
        receipt = {
            "provider": "agy", "returncode": 1, "timed_out": False,
            "stdout": sensitive * 4, "stderr": sensitive,
            "error": "RuntimeError: " + sensitive,
        }
        meta = mio.receipt_diagnostic(receipt, "relay-" + "a" * 32)
        self.assertEqual(meta["returncode"], 1)
        self.assertEqual(meta["provider"], "agy")
        self.assertEqual(meta["stdout_chars"], len(sensitive) * 4)
        self.assertNotIn(sensitive, str(meta))
        status = {"reason": "executor_failed", "elapsed_seconds": 12, "meta": meta}
        self.assertNotIn(sensitive, mio.diagnostic_text(status))
        self.assertIn("代碼：1", mio.diagnostic_text(status))

    def test_compact_persona_context_retains_identity_not_entire_ir(self):
        original = {
            "character_core.json": {"character_id": mio.PERSONA_ID, "name": {"display": "澪"},
                                    "immutable_traits": {"values": ["尊重他人"]}},
            "persona_state.json": {"voice": {"tone": "溫和"}, "memory": {"schema": "v1"},
                                   "large_legacy_field": "X" * 20000},
            "reply_policy.json": {"rules": [{"action": "reply directly"}]},
            "recent_persona_events": [{"event_id": "recent", "text": "E" * 2000}],
            "private_telegram_history": [{"role": "owner", "text": "H" * 2000}],
        }
        compact = mio.compact_persona_context(original)
        self.assertEqual(compact["character_id"], mio.PERSONA_ID)
        self.assertEqual(compact["name"], {"display": "澪"})
        self.assertNotIn("large_legacy_field", str(compact))
        self.assertLess(len(str(compact)), 1300)
        self.assertLessEqual(len(compact["private_conversation"][0]["text"]), 300)

    def test_error_hint_is_coarse_and_never_contains_raw_stderr(self):
        self.assertEqual(mio.stderr_category("HTTP 429 resource exhausted"), "quota_or_rate")
        self.assertEqual(mio.stderr_category("connection refused"), "network")
        self.assertEqual(mio.stderr_category("no actionable details"), "unclassified")
        secret = "PRIVATE_ERROR_TOKEN_abc"
        meta = mio.receipt_diagnostic({"provider": "agy", "returncode": 1,
                "stdout": "data", "stderr": "HTTP 429 " + secret}, "relay-" + "a" * 32)
        self.assertEqual(meta["error_hint"], "quota_or_rate")
        self.assertNotIn(secret, str(meta))
        self.assertNotIn(secret, mio.diagnostic_text(
            {"reason": "executor_failed", "elapsed_seconds": 4, "meta": meta}))

    def test_debug_status_reads_only_its_own_exact_capsule(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cid = "relay-" + "a" * 32
            state = root / "last-status.json"
            state.write_text(__import__("json").dumps({
                "reason": "executor_failed", "elapsed_seconds": 4,
                "meta": {"capsule_id": cid, "returncode": 1, "stdout_chars": 14071}
            }))
            receipts = root / "receipts"
            receipts.mkdir()
            (receipts / (cid + ".json")).write_text(__import__("json").dumps({
                "schema": "agentos.antigravity-receipt/v1",
                "capsule_id": cid, "provider": "agy", "returncode": 1,
                "stdout": "SENSITIVE_PROMPT", "stderr": "HTTP 429 PRIVATE_TOKEN", "ok": False
            }))
            with patch.object(mio, "RELAY_ROOT", root), patch.object(
                    mio, "LAST_STATUS_PATH", state):
                status = mio.last_status()
            self.assertEqual(status["meta"]["error_hint"], "quota_or_rate")
            self.assertEqual(status["meta"]["stdout_chars"], len("SENSITIVE_PROMPT"))
            self.assertNotIn("SENSITIVE_PROMPT", str(status))
            self.assertNotIn("PRIVATE_TOKEN", str(status))
            self.assertEqual(status["reason"], "executor_failed")

    def test_debug_is_opt_in_and_persists_outside_persona_git(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "debug.json"
            with patch.object(mio, "DEBUG_PATH", state):
                self.assertFalse(mio.debug_enabled())
                mio.set_debug(True)
                self.assertTrue(mio.debug_enabled())
                self.assertEqual(state.stat().st_mode & 0o777, 0o600)
                mio.set_debug(False)
                self.assertFalse(mio.debug_enabled())

    def test_parse_failure_is_distinct_from_relay_executor_failure(self):
        failure = mio.PersonaReplyError("executor_failed", {"returncode": 1})
        self.assertEqual(failure.reason, "executor_failed")
        with self.assertRaisesRegex(RuntimeError, "mio_reply_missing_or_invalid"):
            mio.parse_persona_reply('{"reply":"hello","request_id":"other"}', "mine")

    def test_verify_only_uses_getme_and_never_steals_polling_updates(self):
        with patch.object(mio.os, "geteuid", return_value=1001), patch.object(
                mio.os.environ, "get", return_value="ubuntu"), patch.object(
                mio, "bot_token", return_value="hidden"), patch.object(
                mio, "verified_bot") as verify, patch.object(
                mio, "telegram") as telegram_request, patch.object(
                mio.sys, "argv", ["mio_telegram_user", "verify"]):
            self.assertEqual(mio.main(), 0)
            verify.assert_called_once_with("hidden")
            telegram_request.assert_not_called()

    def test_start_candidates_only_private_person_and_exact_start(self):
        updates = [
            {"message": {"text": "/start", "from": {"id": 123},
                         "chat": {"id": 123, "type": "private"}}},
            {"message": {"text": "/start", "from": {"id": 999},
                         "chat": {"id": -55, "type": "group"}}},
            {"message": {"text": "hello", "from": {"id": 789},
                         "chat": {"id": 789, "type": "private"}}},
            {"message": {"text": "/start", "from": {"id": 777},
                         "chat": {"id": 123, "type": "private"}}},
        ]
        self.assertEqual(mio.start_candidates(updates), [123])

    def test_owner_must_match_sender_chat_and_private_type(self):
        own = {"from": {"id": 123}, "chat": {"id": 123, "type": "private"}}
        self.assertTrue(mio.is_owner_message(own, 123))
        self.assertFalse(mio.is_owner_message(own, 555))
        self.assertFalse(mio.is_owner_message({
            "from": {"id": 555}, "chat": {"id": 123, "type": "private"}}, 123))
        self.assertFalse(mio.is_owner_message({
            "from": {"id": 123}, "chat": {"id": -55, "type": "group"}}, 123))

    def test_model_reply_must_match_request_id_not_echoed_template(self):
        prompt_echo = '{"reply":"...","request_id":"other"}'
        final = '{"reply":"早安呀 🌱","request_id":"correct"}'
        wrapped = '{"content":"' + final.replace('"', '\\"') + '"}'
        self.assertEqual(
            mio.parse_persona_reply(prompt_echo + "\n" + wrapped, "correct"),
            "早安呀 🌱",
        )
        with self.assertRaisesRegex(RuntimeError, "mio_reply_missing_or_invalid"):
            mio.parse_persona_reply(prompt_echo, "correct")

    def test_pair_does_not_accept_old_start_or_wrong_challenge(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = Path(temp) / "mio-telegram.env"
            original = "MIO_TELEGRAM_BOT_TOKEN=12345:abcdefghijklmnopqrstuvwxyz\n"
            cfg.write_text(original)
            updates = {"result": [
                {"update_id": 10, "message": {"text": "/start", "from": {"id": 33},
                    "chat": {"id": 33, "type": "private"}}},
                {"update_id": 11, "message": {"text": "/start abcdef00", "from": {"id": 33},
                    "chat": {"id": 33, "type": "private"}}},
                {"update_id": 12, "message": {"text": "/start abcdef01", "from": {"id": 77},
                    "chat": {"id": 77, "type": "private"}}},
            ]}
            with patch.object(mio, "ENV_PATH", cfg), patch.object(mio, "telegram",
                return_value=updates), patch.object(mio.time, "monotonic", side_effect=[0, 0, 1]):
                with self.assertRaisesRegex(RuntimeError, "mio_pair_challenge_not_observed"):
                    mio.pair_owner("test-token", challenge="abcdef01", poll_seconds=0)
            self.assertEqual(cfg.read_text(), original)

    def test_pair_requires_matching_private_chat_and_confirmation(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = Path(temp) / "mio-telegram.env"
            original = "MIO_TELEGRAM_BOT_TOKEN=12345:abcdefghijklmnopqrstuvwxyz\n"
            cfg.write_text(original)
            updates = {"result": [
                {"update_id": 10, "message": {"text": "/start abcdef01",
                    "from": {"id": 33}, "chat": {"id": 33, "type": "private"}}},
                {"update_id": 11, "message": {"text": "/start abcdef01",
                    "from": {"id": 44}, "chat": {"id": -12, "type": "group"}}},
                {"update_id": 12, "message": {"text": "/start abcdef01",
                    "from": {"id": 99}, "chat": {"id": 33, "type": "private"}}},
            ]}
            with patch.object(mio, "ENV_PATH", cfg), patch.object(
                    mio, "telegram", return_value=updates):
                with self.assertRaisesRegex(RuntimeError, "mio_pair_cancelled"):
                    mio.pair_owner("test-token", challenge="abcdef01",
                                   confirm=lambda _: "NO")
                self.assertEqual(cfg.read_text(), original)
                mio.pair_owner("test-token", challenge="abcdef01",
                               confirm=lambda _: "YES")
            self.assertEqual(cfg.read_text(), original + "MIO_TELEGRAM_OWNER_ID=33\n")
            self.assertEqual(cfg.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
