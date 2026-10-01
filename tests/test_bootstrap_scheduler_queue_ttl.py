from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from agentos_node import bootstrap_control as bc
from agentos_node.bootstrap_scheduler import _claim, _recover_inflight, policy_for


def old_timestamp(seconds: int) -> str:
    return (
        datetime.now(timezone.utc) - timedelta(seconds=seconds)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class InteractiveQueueTtlTests(unittest.TestCase):
    def test_threads_login_handoff_has_bounded_queue_lifetime(self) -> None:
        policy = policy_for(bc.ACTION_START_THREADS_WEB_DM_LOGIN)
        self.assertEqual(policy.role, "gui")
        self.assertEqual(policy.queue_ttl_seconds, 90)

    def test_expired_login_handoff_becomes_failure_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bootstrap_root = root / "bootstrap"
            data_root = root / "data"
            with patch.dict(
                os.environ,
                {
                    "AGENTOS_BOOTSTRAP_ROOT": str(bootstrap_root),
                    "AGENT_DATA_ROOT": str(data_root),
                },
                clear=False,
            ):
                requests, receipts, rejected = bc._ensure(bootstrap_root)
                request_id = "expired-login-handoff"
                payload = {
                    "schema": bc.SCHEMA,
                    "request_id": request_id,
                    "action": bc.ACTION_START_THREADS_WEB_DM_LOGIN,
                    "created_at": old_timestamp(180),
                    "params": {"source_commit": "a" * 40},
                }
                request_path = requests / f"{request_id}.request.json"
                request_path.write_text(json.dumps(payload), encoding="utf-8")

                claimed = _claim("gui", "oracle-gui")

                self.assertIsNone(claimed)
                self.assertFalse(request_path.exists())
                self.assertTrue((rejected / request_path.name).exists())
                receipt = json.loads(
                    (receipts / f"{request_id}.json").read_text(encoding="utf-8")
                )
                self.assertFalse(receipt["ok"])
                self.assertEqual(receipt["failure_class"], "queue_expired")
                self.assertEqual(receipt["scheduler"]["queue_ttl_seconds"], 90)


    def test_restart_recovery_expires_stale_inflight_login_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bootstrap_root = root / "bootstrap"
            data_root = root / "data"
            with patch.dict(
                os.environ,
                {
                    "AGENTOS_BOOTSTRAP_ROOT": str(bootstrap_root),
                    "AGENT_DATA_ROOT": str(data_root),
                },
                clear=False,
            ):
                _requests, receipts, rejected = bc._ensure(bootstrap_root)
                request_id = "stale-inflight-login"
                payload = {
                    "schema": bc.SCHEMA,
                    "request_id": request_id,
                    "action": bc.ACTION_START_THREADS_WEB_DM_LOGIN,
                    "created_at": old_timestamp(180),
                    "params": {"source_commit": "c" * 40},
                }
                inflight = bootstrap_root / "inflight" / "oracle-gui"
                inflight.mkdir(parents=True, exist_ok=True)
                request_path = inflight / f"{request_id}.request.json"
                request_path.write_text(json.dumps(payload), encoding="utf-8")

                result = _recover_inflight("gui", "oracle-gui")

                self.assertEqual(result["stale"], 1)
                self.assertFalse(request_path.exists())
                self.assertTrue((rejected / request_path.name).exists())
                receipt = json.loads(
                    (receipts / f"{request_id}.json").read_text(encoding="utf-8")
                )
                self.assertEqual(receipt["failure_class"], "queue_expired")

    def test_normal_gui_probe_keeps_global_freshness_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bootstrap_root = root / "bootstrap"
            data_root = root / "data"
            with patch.dict(
                os.environ,
                {
                    "AGENTOS_BOOTSTRAP_ROOT": str(bootstrap_root),
                    "AGENT_DATA_ROOT": str(data_root),
                },
                clear=False,
            ):
                requests, _receipts, _rejected = bc._ensure(bootstrap_root)
                request_id = "normal-gui-probe"
                payload = {
                    "schema": bc.SCHEMA,
                    "request_id": request_id,
                    "action": bc.ACTION_PROBE_THREADS_WEB_DM,
                    "created_at": old_timestamp(180),
                    "params": {"source_commit": "b" * 40},
                }
                request_path = requests / f"{request_id}.request.json"
                request_path.write_text(json.dumps(payload), encoding="utf-8")

                claimed = _claim("gui", "oracle-gui")

                self.assertIsNotNone(claimed)
                claimed_path, claimed_payload = claimed
                self.assertEqual(claimed_payload["request_id"], request_id)
                self.assertTrue(claimed_path.exists())


if __name__ == "__main__":
    unittest.main()
