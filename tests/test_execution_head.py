from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.execution_head import arbitrate_heads, collect_execution_head, discover_version
from scripts.update_projects_pulse import _status_observed_at


class ExecutionHeadTests(unittest.TestCase):
    def test_discovers_extension_manifest_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "extension" / "manifest.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({"version": "1.0.59"}), encoding="utf-8")
            version, source = discover_version(root)
            self.assertEqual(version, "1.0.59")
            self.assertEqual(source, "extension/manifest.json")

    def test_collects_local_git_head_and_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            workspace = base / "repo"
            project_dir = base / "project"
            workspace.mkdir()
            project_dir.mkdir()
            subprocess.run(["git", "init", "-b", "develop"], cwd=workspace, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "agentos@example.invalid"], cwd=workspace, check=True)
            subprocess.run(["git", "config", "user.name", "AgentOS Test"], cwd=workspace, check=True)
            manifest = workspace / "extension" / "manifest.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({"version": "1.0.59"}), encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=workspace, check=True)
            subprocess.run(["git", "commit", "-m", "test head"], cwd=workspace, check=True, capture_output=True)
            subprocess.run(["git", "tag", "v1.0.55"], cwd=workspace, check=True)
            (project_dir / "project.yaml").write_text(
                f"project_id: metashield-protocol\nactual_code_path: {workspace}\n",
                encoding="utf-8",
            )

            head = collect_execution_head("metashield-protocol", project_dir, node="test-node")
            self.assertIsNone(head.error)
            self.assertEqual(head.branch, "develop")
            self.assertEqual(head.version, "1.0.59")
            self.assertEqual(head.latest_tag, "v1.0.55")
            self.assertEqual(head.node, "test-node")
            self.assertFalse(head.dirty)
            self.assertTrue(head.local_head)

    def test_fresh_local_execution_wins_over_remote_drift(self):
        now = datetime(2026, 8, 28, 1, 30, tzinfo=timezone.utc)
        local = {
            "source": "local-git",
            "node": "oracle",
            "local_head": "0b37627",
            "version": "1.0.59",
            "ahead": 40,
            "latest_tag": "v1.0.55",
            "observed_at": (now - timedelta(seconds=30)).isoformat(),
            "confidence": 1.0,
        }
        remote = {
            "source": "remote-git",
            "node": "github",
            "remote_head": "e71e85c",
            "version": "1.0.36",
            "observed_at": (now - timedelta(seconds=20)).isoformat(),
            "confidence": 1.0,
        }
        result = arbitrate_heads([remote, local], now=now)
        self.assertEqual(result["winner"]["source"], "local-git")
        self.assertEqual(result["winner"]["version"], "1.0.59")
        self.assertEqual(result["winner"]["ahead"], 40)
        self.assertEqual(len(result["conflicts"]), 1)

    def test_fresh_remote_wins_when_local_receipt_is_stale(self):
        now = datetime(2026, 8, 28, 1, 30, tzinfo=timezone.utc)
        local = {
            "source": "local-git",
            "local_head": "local",
            "version": "2.0.0",
            "observed_at": (now - timedelta(minutes=10)).isoformat(),
        }
        remote = {
            "source": "remote-git",
            "remote_head": "remote",
            "version": "1.9.0",
            "observed_at": (now - timedelta(seconds=30)).isoformat(),
        }
        result = arbitrate_heads([local, remote], now=now)
        self.assertEqual(result["winner"]["source"], "remote-git")

    def test_failed_fresh_local_evidence_cannot_win(self):
        now = datetime(2026, 8, 28, 1, 30, tzinfo=timezone.utc)
        failed_local = {
            "source": "local-git",
            "error": "workspace_not_found",
            "observed_at": (now - timedelta(seconds=1)).isoformat(),
            "confidence": 0.0,
        }
        remote = {
            "source": "remote-git",
            "remote_head": "remote",
            "version": "1.0.36",
            "observed_at": (now - timedelta(seconds=20)).isoformat(),
        }
        result = arbitrate_heads([failed_local, remote], now=now)
        self.assertEqual(result["winner"]["source"], "remote-git")
        self.assertEqual(len(result["invalid_evidence"]), 1)

    def test_persisted_receipt_survives_missing_workspace_and_stale_status(self):
        now = datetime(2026, 8, 28, 2, 0, tzinfo=timezone.utc)
        failed_local = {
            "source": "local-git",
            "error": "workspace_not_found",
            "observed_at": (now - timedelta(seconds=1)).isoformat(),
            "confidence": 0.0,
        }
        persisted = {
            "source": "execution-receipt",
            "local_head": "0b37627",
            "version": "1.0.59",
            "observed_at": (now - timedelta(hours=1)).isoformat(),
            "confidence": 0.95,
        }
        stale_status = {
            "source": "status-md",
            "status": "v1.0.20 released",
            "observed_at": "2026-08-20T02:25:00+00:00",
            "confidence": 1.0,
        }
        result = arbitrate_heads([failed_local, stale_status, persisted], now=now)
        self.assertEqual(result["winner"]["source"], "execution-receipt")
        self.assertEqual(result["winner"]["version"], "1.0.59")

    def test_status_semantic_timestamp_beats_checkout_mtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "STATUS.md"
            path.write_text("status", encoding="utf-8")
            observed = _status_observed_at(path, {"last_updated": "2026-08-20 10:25"})
            self.assertTrue(observed.startswith("2026-08-20T10:25:00"))

    def test_operator_bootstrap_receipt_is_valid_execution_evidence(self):
        now = datetime(2026, 8, 28, 2, 0, tzinfo=timezone.utc)
        bootstrap = {
            "source": "execution-receipt",
            "receipt_kind": "operator-confirmed-bootstrap",
            "verification_state": "pending-node-attestation",
            "local_head": "0b37627",
            "version": "1.0.59",
            "latest_tag": "v1.0.55",
            "ahead": 40,
            "observed_at": (now - timedelta(minutes=10)).isoformat(),
            "confidence": 0.95,
        }
        stale_status = {
            "source": "status-md",
            "status": "v1.0.20 released",
            "observed_at": "2026-08-20T02:25:00+00:00",
        }
        result = arbitrate_heads([stale_status, bootstrap], now=now)
        self.assertEqual(result["winner"]["receipt_kind"], "operator-confirmed-bootstrap")
        self.assertEqual(result["winner"]["version"], "1.0.59")


if __name__ == "__main__":
    unittest.main()
