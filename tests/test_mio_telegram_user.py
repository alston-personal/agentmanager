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
