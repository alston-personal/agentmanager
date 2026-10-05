from __future__ import annotations

import json
from pathlib import Path
import sys
import os
import tempfile
import time
import unittest
from unittest.mock import patch

from agentos_node.antigravity_relay_worker import AntigravityRelayWorker, discover_executor


class AntigravityRelayWorkerTests(unittest.TestCase):
    def test_stranded_processing_is_quarantined_and_never_auto_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "inbox").mkdir(parents=True)
            (root / "processing").mkdir()
            (root / "receipts").mkdir()
            stranded = root / "processing" / "relay-old.json"
            stranded.write_text(
                json.dumps({
                    "schema": "agentos.antigravity-relay/v1",
                    "capsule_id": "relay-old",
                    "created_at": "2026-01-01T00:00:00Z",
                }),
                encoding="utf-8",
            )
            old = time.time() - 1200
            os.utime(stranded, (old, old))
            worker = AntigravityRelayWorker(root, executor=["/bin/true"])
            with patch("agentos_node.antigravity_relay._shared_gid", return_value=os.getgid()):
                self.assertEqual(worker.reconcile_stranded_processing(stale_after=600), 1)
            self.assertIsNone(worker._next_capsule())
            self.assertFalse(stranded.exists())
            self.assertTrue((root / "quarantine" / "relay-old.json").exists())
            receipt = json.loads((root / "receipts" / "relay-old.json").read_text(encoding="utf-8"))
            self.assertFalse(receipt["ok"])
            self.assertEqual(receipt["classification"], "UNKNOWN_SIDE_EFFECT")
            self.assertIn("automatic replay disabled", receipt["error"])

    def test_peer_owned_stale_spool_can_be_quarantined_by_parent_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "inbox").mkdir(parents=True)
            (root / "processing").mkdir()
            (root / "receipts").mkdir()
            stranded = root / "processing" / "relay-peer.json"
            stranded.write_text(json.dumps({
                "schema": "agentos.antigravity-relay/v1",
                "capsule_id": "relay-peer",
                "created_at": "2026-01-01T00:00:00Z",
            }), encoding="utf-8")
            old = time.time() - 1200
            os.utime(stranded, (old, old))
            worker = AntigravityRelayWorker(root, executor=["/bin/true"])
            with patch("agentos_node.antigravity_relay._shared_gid", return_value=os.getgid()), \
                 patch("agentos_node.antigravity_relay_worker.os.access", return_value=False):
                self.assertEqual(worker.reconcile_stranded_processing(stale_after=600), 1)
            self.assertTrue((root / "processing").is_dir())
            self.assertFalse(any((root / "processing").glob("relay-*.json")))
            quarantined = list((root / "quarantine").glob("processing-spool-*/relay-peer.json"))
            self.assertEqual(len(quarantined), 1)
            receipt = json.loads((root / "receipts" / "relay-peer.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["classification"], "UNKNOWN_SIDE_EFFECT")

    def test_directory_quarantine_refuses_when_fresh_processing_exists(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "inbox").mkdir(parents=True)
            (root / "processing").mkdir()
            (root / "receipts").mkdir()
            stale = root / "processing" / "relay-stale.json"
            fresh = root / "processing" / "relay-fresh.json"
            stale.write_text(json.dumps({"capsule_id": "relay-stale"}), encoding="utf-8")
            fresh.write_text(json.dumps({"capsule_id": "relay-fresh"}), encoding="utf-8")
            old = time.time() - 1200
            os.utime(stale, (old, old))
            worker = AntigravityRelayWorker(root, executor=["/bin/true"])
            with patch("agentos_node.antigravity_relay._shared_gid", return_value=os.getgid()), \
                 patch("agentos_node.antigravity_relay_worker.os.access", return_value=False):
                with self.assertRaises(PermissionError):
                    worker.reconcile_stranded_processing(stale_after=600)
            self.assertTrue(stale.exists())
            self.assertTrue(fresh.exists())

    def test_fresh_processing_is_not_quarantined(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "inbox").mkdir(parents=True)
            (root / "processing").mkdir()
            (root / "receipts").mkdir()
            processing = root / "processing" / "relay-live.json"
            processing.write_text(
                json.dumps({"schema": "agentos.antigravity-relay/v1", "capsule_id": "relay-live"}),
                encoding="utf-8",
            )
            worker = AntigravityRelayWorker(root, executor=["/bin/true"])
            with patch("agentos_node.antigravity_relay._shared_gid", return_value=os.getgid()):
                self.assertEqual(worker.reconcile_stranded_processing(stale_after=600), 0)
            self.assertTrue(processing.exists())
            self.assertFalse((root / "receipts" / "relay-live.json").exists())

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

    def test_gemini_provider_uses_fixed_ubuntu_cli_path(self) -> None:
        fake_home = Path("/home/ubuntu")
        with patch("agentos_node.antigravity_relay_worker.Path.home", return_value=fake_home), \
             patch.object(Path, "is_file", return_value=True), \
             patch("agentos_node.antigravity_relay_worker.os.access", return_value=True):
            provider, executor = discover_executor("gemini")
        self.assertEqual(provider, "gemini")
        self.assertEqual(executor, ["/home/ubuntu/.local/bin/gemini"])

    def test_gemini_argv_uses_headless_auto_edit_without_shell_text(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            worker = AntigravityRelayWorker(
                workspace / "relay",
                provider="gemini",
                executor=["/home/ubuntu/.local/bin/gemini"],
            )
            argv = worker._executor_argv(
                {"canonical_ir": {"goal": "probe"}, "instruction": "Make the bounded edit"},
                workspace,
            )
            self.assertEqual(argv[0], "/home/ubuntu/.local/bin/gemini")
            self.assertIn("--approval-mode", argv)
            self.assertEqual(argv[argv.index("--approval-mode") + 1], "auto_edit")
            self.assertIn("-p", argv)
            self.assertNotIn("sh", argv)
            self.assertNotIn("bash", argv)

    def test_trusted_provider_hint_selects_gemini_with_headless_argv(self) -> None:
        with tempfile.TemporaryDirectory() as td, \
             patch("agentos_node.antigravity_relay_worker.discover_executor", return_value=("gemini", ["/bin/echo"])):
            workspace = Path(td)
            worker = AntigravityRelayWorker(workspace / "relay", executor=["/bin/false"], provider="agy")
            result = worker._run_executor(
                {
                    "canonical_ir": {"goal": "probe"},
                    "instruction": "Return exactly PASS",
                    "executor_hint": "provider:gemini",
                },
                workspace,
            )
        self.assertEqual(result["provider"], "gemini")
        self.assertEqual(result["executor"], "/bin/echo")
        self.assertEqual(result["returncode"], 0)
        self.assertIn("--approval-mode auto_edit", result["stdout"])
        self.assertIn("--output-format text -p", result["stdout"])

    def test_trusted_provider_hint_selects_claude_without_caller_argv(self) -> None:
        with tempfile.TemporaryDirectory() as td, \
             patch("agentos_node.antigravity_relay_worker.discover_executor", return_value=("claude", ["/bin/true"])):
            workspace = Path(td)
            worker = AntigravityRelayWorker(workspace / "relay", executor=["/bin/false"], provider="agy")
            result = worker._run_executor(
                {
                    "canonical_ir": {"goal": "probe"},
                    "instruction": "Return exactly PASS",
                    "executor_hint": "provider:claude",
                },
                workspace,
            )
        self.assertEqual(result["provider"], "claude")
        self.assertEqual(result["executor"], "/bin/true")
        self.assertEqual(result["returncode"], 0)

    def test_non_provider_hint_cannot_select_an_executor(self) -> None:
        with tempfile.TemporaryDirectory() as td, \
             patch("agentos_node.antigravity_relay_worker.discover_executor") as discover:
            workspace = Path(td)
            worker = AntigravityRelayWorker(workspace / "relay", executor=["/bin/true"], provider="claude")
            result = worker._run_executor(
                {
                    "canonical_ir": {"goal": "probe"},
                    "instruction": "Return exactly PASS",
                    "executor_hint": "caller-supplied-random-provider",
                },
                workspace,
            )
        discover.assert_not_called()
        self.assertEqual(result["provider"], "claude")
        self.assertEqual(result["returncode"], 0)

    def test_unknown_provider_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported Antigravity executor provider"):
            discover_executor("shell")

    def test_codex_argv_maps_semantic_operation_to_fixed_sandbox(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            worker = AntigravityRelayWorker(
                workspace / "relay",
                provider="codex",
                executor=["/home/ubuntu/.local/bin/codex"],
            )
            read_only = worker._executor_argv(
                {
                    "canonical_ir": {"operation": "agent.chat"},
                    "instruction": "Return exactly READY",
                },
                workspace,
            )
            self.assertEqual(read_only[0], "/home/ubuntu/.local/bin/codex")
            self.assertIn("exec", read_only)
            self.assertEqual(read_only[read_only.index("--sandbox") + 1], "read-only")
            self.assertEqual(read_only[read_only.index("-a") + 1], "never")
            self.assertIn("--ephemeral", read_only)
            self.assertEqual(read_only[read_only.index("-C") + 1], str(workspace))

            writable = worker._executor_argv(
                {
                    "canonical_ir": {"operation": "code.edit"},
                    "instruction": "Make the bounded change",
                },
                workspace,
            )
            self.assertEqual(writable[writable.index("--sandbox") + 1], "workspace-write")

    def test_codex_argv_rejects_missing_semantic_operation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            worker = AntigravityRelayWorker(
                workspace / "relay",
                provider="codex",
                executor=["/home/ubuntu/.local/bin/codex"],
            )
            with self.assertRaisesRegex(ValueError, "operation is not allowlisted"):
                worker._executor_argv(
                    {"canonical_ir": {}, "instruction": "noop"},
                    workspace,
                )

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
