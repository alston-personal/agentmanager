"""Exercise hydration, silence, compaction heuristic and budget without a model."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid


HOOK = Path(__file__).resolve().parents[1] / "scripts/claude_context_injector.sh"


class ClaudeContextInjectorTests(unittest.TestCase):
    def test_session_hydration_silence_budget_and_size_shrink(self):
        session = f"test-{uuid.uuid4().hex}"
        stamp = Path(f"/tmp/agentos-claude-hydrated-{session}.stamp")
        try:
            with tempfile.TemporaryDirectory() as temp:
                transcript = Path(temp) / "transcript.jsonl"
                transcript.write_text("x" * 40000)
                payload = json.dumps({"session_id": session, "transcript_path": str(transcript), "cwd": temp})
                env = dict(os.environ, CLAUDE_PROJECT_DIR=temp, AGENT_DATA_ROOT=temp)

                def run():
                    return subprocess.run(["bash", str(HOOK)], input=payload, text=True,
                                          capture_output=True, env=env, check=True, timeout=10).stdout

                self.assertIn("Single-Shot Session Hydration", run())
                self.assertEqual(run(), "")
                transcript.write_text("x" * 307200)
                self.assertIn("Context Budget Guard", run())
                transcript.write_text("x" * 10000)
                self.assertIn("Single-Shot Session Hydration", run())
                self.assertEqual(run(), "")
        finally:
            stamp.unlink(missing_ok=True)
