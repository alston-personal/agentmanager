"""Run the real social shell lane against offline adapters and fake Git/gh."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "scripts/run_persona_social_actions_user.sh"


class SocialMediaIsolation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.fixture = self.root / "fixture"
        self.persona = self.fixture / "personas/sunlake-milkcat"
        (self.persona / "pdca").mkdir(parents=True)
        (self.persona / "events").mkdir()
        (self.persona / "pdca/state.json").write_text(json.dumps({"status": "RUNNING", "cycle": 195}))
        (self.persona / "events/events.jsonl").write_text("")
        self.capture = self.root / "persisted"
        self.trace = self.root / "trace.jsonl"
        self.env = dict(os.environ, PATH=str(self.bin) + ":" + os.environ["PATH"],
            MIO_TEST_FIXTURE=str(self.fixture), MIO_TEST_CAPTURE=str(self.capture), MIO_TEST_TRACE=str(self.trace))
        self.program("id", "print('1001')")
        self.program("flock", "pass")
        self.program("gh", """
import os,shutil,sys
if sys.argv[1:3]==['repo','clone']:
    shutil.copytree(os.environ['MIO_TEST_FIXTURE'],sys.argv[4],dirs_exist_ok=True)
""")
        self.program("git", """
import json,os,shutil,sys
from pathlib import Path
args=sys.argv[1:]
with open(os.environ['MIO_TEST_TRACE'],'a') as stream:
    stream.write(json.dumps({'git':args})+'\\n')
if args==['diff','--cached','--quiet']:
    raise SystemExit(1)
if args and args[0]=='commit':
    shutil.copytree(Path.cwd()/'personas/sunlake-milkcat',os.environ['MIO_TEST_CAPTURE'],dirs_exist_ok=True)
""")
        self.env["AGENTOS_PERSONA_SOCIAL_EXECUTOR"] = str(self.script("observe", """
import argparse,json
from pathlib import Path
ap=argparse.ArgumentParser(); ap.add_argument('--persona-dir'); ap.add_argument('--username'); ap.add_argument('--receipt-out')
a=ap.parse_args(); root=Path(a.persona_dir)
Path(a.receipt_out).write_text(json.dumps({'status':'EXECUTED','ok':True,'capability':'social.threads.observe','write_performed':False}))
with (root/'events/events.jsonl').open('a') as stream:
    stream.write(json.dumps({'type':'reply.observed','summary':'offline observation'})+'\\n')
"""))
        for name, variable in (("reply", "AGENTOS_PERSONA_REPLY_INTENT_GENERATOR"),
                               ("post", "AGENTOS_PERSONA_POST_INTENT_GENERATOR")):
            self.env[variable] = str(self.script(name, """
import json,os,sys
with open(os.environ['MIO_TEST_TRACE'],'a') as stream:
    stream.write(json.dumps({'cognition':sys.argv[0]})+'\\n')
"""))
        self.env["AGENTOS_PERSONA_GROWTH_METRICS"] = str(self.script("metrics", """
import json,sys
from pathlib import Path
Path(sys.argv[sys.argv.index('--receipt-out')+1]).write_text(json.dumps({'status':'NO_CHANGE','changed':0}))
"""))
        self.worker("raise SystemExit(0)")

    def program(self, name, body):
        path = self.bin / name
        path.write_text("#!" + sys.executable + "\n" + body)
        path.chmod(0o755)
        return path

    def script(self, name, body):
        path = self.root / (name + ".py")
        path.write_text(body)
        return path

    def worker(self, body):
        path = self.script("media", body)
        self.env["AGENTOS_PERSONA_MEDIA_WORKER"] = str(path)
        return path

    def run_lane(self):
        return subprocess.run(["bash", str(RUNNER)], env=self.env, cwd=self.root,
                              capture_output=True, text=True, timeout=15)

    def events(self):
        return [json.loads(x) for x in self.trace.read_text().splitlines()] if self.trace.exists() else []

    def persisted(self):
        return json.loads((self.capture / "pdca/media_worker_runtime.json").read_text())

    def assert_other_work_persisted(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        events = self.events()
        self.assertEqual(len([x for x in events if "cognition" in x]), 2)
        self.assertTrue(any(x.get("git", [])[-1:] == ["push"] for x in events))
        self.assertIn("reply.observed", (self.capture / "events/events.jsonl").read_text())
        receipts = list((self.capture / "pdca/social_receipts").glob("*.json"))
        self.assertEqual(len(receipts), 1)
        self.assertEqual(json.loads(receipts[0].read_text())["status"], "EXECUTED")

    def test_media_crash_keeps_observation_and_both_cognition_lanes(self):
        path = self.worker("import sys\nprint('private-provider-output')\nprint('private-error-input',file=sys.stderr)\nraise SystemExit(2)")
        result = self.run_lane()
        self.assert_other_work_persisted(result)
        receipt = self.persisted()
        self.assertEqual(receipt["schema"], "agentos.execution-receipt/v1")
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["reason"], "MEDIA_WORKER_FAILED")
        self.assertEqual(receipt["exit_code"], 2)
        self.assertFalse(receipt["publication_allowed"])
        self.assertEqual(receipt["image_acceptance"], "NOT_OBSERVED")
        self.assertEqual(receipt["authority"]["kind"], "offline_fixture")
        self.assertFalse(receipt["media_failure_blocks_social_lane"])
        import hashlib
        self.assertEqual(receipt["expected"]["worker_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(receipt["expected"]["runner_sha256"], hashlib.sha256(RUNNER.read_bytes()).hexdigest())
        self.assertEqual(receipt["expected"]["social_executor_sha256"],
                         hashlib.sha256(Path(self.env["AGENTOS_PERSONA_SOCIAL_EXECUTOR"]).read_bytes()).hexdigest())
        for value in ("private-provider-output", "private-error-input"):
            self.assertNotIn(value, result.stdout + result.stderr + json.dumps(receipt))
        self.assertFalse(list(self.capture.rglob("*output.log")))

    def test_missing_optional_worker_does_not_stop_existing_activity(self):
        self.env["AGENTOS_PERSONA_MEDIA_WORKER"] = str(self.root / "missing.py")
        result = self.run_lane()
        self.assert_other_work_persisted(result)
        receipt = self.persisted()
        self.assertEqual(receipt["reason"], "MEDIA_WORKER_NOT_INSTALLED")
        self.assertEqual(receipt["exit_code"], 127)
        self.assertIsNone(receipt["expected"]["worker_sha256"])

    def test_success_is_execution_only_and_unchanged_ticks_do_not_rewrite_receipt(self):
        self.assert_other_work_persisted(self.run_lane())
        first = self.persisted()
        self.assertEqual(first["status"], "completed")
        self.assertFalse(first["publication_allowed"])
        self.assertEqual(first["image_acceptance"], "NOT_OBSERVED")
        (self.persona / "pdca/media_worker_runtime.json").write_text(json.dumps(first))
        self.assertEqual(self.run_lane().returncode, 0)
        self.assertEqual(self.persisted()["checked_at"], first["checked_at"])

    def test_recovery_refreshes_diagnostic_without_promoting_image_or_old_failure(self):
        self.worker("raise SystemExit(1)")
        self.assertEqual(self.run_lane().returncode, 0)
        first = self.persisted()
        (self.persona / "pdca/media_worker_runtime.json").write_text(json.dumps(first))
        self.worker("raise SystemExit(0)")
        self.assertEqual(self.run_lane().returncode, 0)
        after = self.persisted()
        self.assertEqual(after["status"], "completed")
        self.assertIsNone(after["reason"])
        self.assertNotEqual(first["expected"]["worker_sha256"], after["expected"]["worker_sha256"])
        self.assertFalse(after["publication_allowed"])

    def test_malformed_state_still_stops_before_any_adapter_or_cognition(self):
        for value in ("{", "[]"):
            with self.subTest(value=value):
                (self.persona / "pdca/state.json").write_text(value)
                result = self.run_lane()
                self.assertEqual(result.returncode, 3)
                self.assertIn("DEGRADED_STATE", result.stderr)
                self.assertFalse(self.capture.exists())
                self.assertFalse(any("cognition" in x for x in self.events()))

    def test_worker_corrupting_state_stops_before_cognition_or_persistence(self):
        self.worker("""
import sys
from pathlib import Path
(Path(sys.argv[sys.argv.index('--persona-dir')+1])/'pdca/state.json').write_text('{')
raise SystemExit(1)
""")
        result = self.run_lane()
        self.assertEqual(result.returncode, 3)
        self.assertIn("DEGRADED_STATE", result.stderr)
        self.assertFalse(self.capture.exists())
        self.assertFalse(any("cognition" in x for x in self.events()))

    def test_real_worker_malformed_request_cannot_discard_social_observation(self):
        (self.persona / "pdca/media_requests").mkdir()
        (self.persona / "pdca/media_requests/bad.json").write_text("{")
        self.env["AGENTOS_PERSONA_MEDIA_WORKER"] = str(REPO / "scripts/persona_media_request_worker.py")
        self.env["AGENTOS_MIO_VISUAL_REVIEW"] = "off"
        result = self.run_lane()
        self.assert_other_work_persisted(result)
        self.assertEqual(self.persisted()["status"], "failed")
        self.assertFalse((self.capture / "pdca/media_reviews").exists())
        self.assertFalse((self.capture / "pdca/media_receipts").exists())
        self.assertEqual(json.loads((self.capture / "pdca/state.json").read_text())["cycle"], 195)


if __name__ == "__main__":
    unittest.main()
