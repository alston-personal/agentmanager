"""Offline safety tests for Mio's private Telegram transport."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import mio_telegram_user as mio


class MioTelegramBridgeTests(unittest.TestCase):
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

    def test_pair_requires_exactly_one_private_start(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = Path(temp) / "mio-telegram.env"
            cfg.write_text("MIO_TELEGRAM_BOT_TOKEN=12345:abcdefghijklmnopqrstuvwxyz\n")
            with patch.object(mio, "ENV_PATH", cfg), patch.object(mio, "telegram", return_value={
                "result": [{"message": {"text": "/start", "from": {"id": 33},
                                        "chat": {"id": 33, "type": "private"}}},
                           {"message": {"text": "/start", "from": {"id": 44},
                                        "chat": {"id": 44, "type": "private"}}}]
            }):
                with self.assertRaisesRegex(RuntimeError, "requires_exactly_one"):
                    mio.pair_owner("test-token", confirm=lambda _: "YES")
            self.assertNotIn("MIO_TELEGRAM_OWNER_ID", cfg.read_text())

    def test_pair_is_explicit_and_does_not_replace_token(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = Path(temp) / "mio-telegram.env"
            original = "MIO_TELEGRAM_BOT_TOKEN=12345:abcdefghijklmnopqrstuvwxyz\n"
            cfg.write_text(original)
            with patch.object(mio, "ENV_PATH", cfg), patch.object(mio, "telegram", return_value={
                "result": [{"message": {"text": "/start", "from": {"id": 33},
                                        "chat": {"id": 33, "type": "private"}}}]
            }):
                with self.assertRaisesRegex(RuntimeError, "mio_pair_cancelled"):
                    mio.pair_owner("test-token", confirm=lambda _: "NO")
                self.assertEqual(cfg.read_text(), original)
                mio.pair_owner("test-token", confirm=lambda _: "YES")
            self.assertEqual(cfg.read_text(), original + "MIO_TELEGRAM_OWNER_ID=33\n")
            self.assertEqual(cfg.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
