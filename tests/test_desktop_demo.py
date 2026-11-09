import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from agentos_node import desktop_demo


class TestDesktopDemo(unittest.TestCase):
    def test_stage_and_stop_preserve_elapsed_and_video_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            root = workspace / "agentos-demo"
            root.mkdir()
            video = root / desktop_demo.VIDEO_NAME
            video.write_bytes(b"demo-video")
            state = {
                "schema": "agentos.desktop-demo/v1",
                "recording": True,
                "label": "AgentOS Demo",
                "stage": "Starting",
                "started_at": "2026-10-01T12:00:00Z",
                "started_epoch": time.time() - 1.0,
                "video_path": str(video),
            }
            (root / desktop_demo.STATE_NAME).write_text(
                json.dumps(state), encoding="utf-8"
            )

            with mock.patch("agentos_node.desktop_demo.platform.system", return_value="Windows"):
                stage = desktop_demo.set_stage(workspace, "Gemini / generating")
                self.assertTrue(stage["demo_recording"])
                self.assertEqual(stage["stage"], "Gemini / generating")
                self.assertGreaterEqual(stage["elapsed_seconds"], 0.9)

                stopped = desktop_demo.stop(workspace, final_stage="Threads / Verified")
                self.assertFalse(stopped["demo_recording"])
                self.assertTrue(stopped["video_exists"])
                self.assertEqual(stopped["video_bytes"], len(b"demo-video"))
                self.assertEqual(stopped["final_stage"], "Threads / Verified")
                self.assertGreaterEqual(stopped["elapsed_seconds"], 0.9)

            final_state = json.loads((root / desktop_demo.STATE_NAME).read_text(encoding="utf-8"))
            self.assertFalse(final_state["recording"])
            self.assertEqual(final_state["stage"], "Threads / Verified")
            self.assertIn("completed_at", final_state)


if __name__ == "__main__":
    unittest.main()
