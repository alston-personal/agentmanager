from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from agentos_node.antigravity_relay_worker import AntigravityRelayWorker, discover_executor


class AntigravityRelayWorkerTests(unittest.TestCase):
    def test_stranded_processing_is_never_auto_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "inbox").mkdir(parents=True)
            (root / "processing").mkdir()
            (root / "receipts").mkdir()
            stranded = root / "processing" / "relay-old.json"
            stranded.write_text(json.dumps({"schema": "agentos.antigravity-relay/v1"}), encoding="utf-8")
            worker = AntigravityRelayWorker(root, executor=["/bin/true"])
            self.assertIsNone(worker._next_capsule())
            self.assertTrue(stranded.exists())

    def test_inbox_capsule_is_selected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "inbox").mkdir(parents=True)
            (root / "processing").mkdir()
            (root / "receipts").mkdir()
            capsule = root / "inbox" / "relay-new.json"
            capsule.write_text("{}", encoding="utf-8")
            worker = AntigravityRelayWorker(root, executor=["/bin/true"])
            self.assertEqual(worker._next_capsule(), capsule)

    def test_executor_timeout_terminates_process_group(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            worker = AntigravityRelayWorker(
                Path(td) / "relay",
                executor=[sys.executable, "-c", "import time; time.sleep(60)"],
                timeout=0.1,
            )
            started = time.monotonic()
            result = worker._run_executor({"canonical_ir": {}, "instruction": "noop"}, Path(td))
            elapsed = time.monotonic() - started
            self.assertTrue(result["timed_out"])
            self.assertEqual(result["returncode"], 124)
            self.assertLess(elapsed, 5.0)


    def test_claude_discovery_preserves_ubuntu_oauth_identity(self) -> None:
        fake_binary = Path("/home/ubuntu/.antigravity-ide-server/extensions/anthropic.claude-code-2.1.251-linux-arm64/resources/native-binary/claude")
        with patch.dict("agentos_node.antigravity_relay_worker.os.environ", {"AGENTOS_ANTIGRAVITY_EXECUTOR": str(fake_binary)}, clear=False), \
             patch.object(Path, "is_file", return_value=True), \
             patch("agentos_node.antigravity_relay_worker.os.access", return_value=True):
            provider, executor = discover_executor("claude")
        self.assertEqual(provider, "claude")
        self.assertIsNotNone(executor)
        self.assertEqual(executor[0], str(fake_binary))
        self.assertIn("--print", executor)
        self.assertIn("--output-format", executor)
        self.assertIn("--effort", executor)
        self.assertNotIn("--bare", executor)

    def test_claude_executor_argv_stays_noninteractive_without_bare(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            worker = AntigravityRelayWorker(
                workspace / "relay",
                provider="claude",
                executor=["/tmp/claude", "--print", "--output-format", "text", "--effort", "low"],
            )
            argv = worker._executor_argv(
                {"canonical_ir": {"goal": "probe"}, "instruction": "Return exactly PASS"},
                workspace,
            )
            self.assertEqual(argv[0], "/tmp/claude")
            self.assertIn("--print", argv)
            self.assertNotIn("--bare", argv)
            self.assertIn("Return exactly PASS", argv[-1])

    def test_agy_provider_uses_fixed_agentos_cli_path(self) -> None:
        fake_home = Path("/home/ubuntu")
        with patch("agentos_node.antigravity_relay_worker.Path.home", return_value=fake_home), \
             patch.object(Path, "is_file", return_value=True), \
             patch("agentos_node.antigravity_relay_worker.os.access", return_value=True):
            provider, executor = discover_executor("agy")
        self.assertEqual(provider, "agy")
        self.assertEqual(executor, ["/home/ubuntu/.local/bin/agy"])

    def test_unknown_provider_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported Antigravity executor provider"):
            discover_executor("shell")

    def test_agy_argv_is_structured_not_shell_text(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            worker = AntigravityRelayWorker(
                workspace / "relay",
                provider="agy",
                executor=["/home/ubuntu/.local/bin/agy"],
            )
            argv = worker._executor_argv(
                {"canonical_ir": {"goal": "probe"}, "instruction": "Return exactly PASS"},
                workspace,
            )
            self.assertEqual(argv[0:2], ["/home/ubuntu/.local/bin/agy", "run"])
            self.assertIn("--task", argv)
            self.assertIn("--workspace", argv)
            self.assertEqual(argv[-1], str(workspace))
            self.assertNotIn("sh", argv)
            self.assertNotIn("bash", argv)


if __name__ == "__main__":
    unittest.main()
