"""Media worker smoke tests using isolated persona fixtures, no network or publication."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO=Path(__file__).resolve().parents[1]
WORKER=REPO/"scripts/persona_media_request_worker.py"

class MediaExperienceSmoke(unittest.TestCase):
    def test_unavailable_generation_persists_one_evidence_only(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/"pdca/media_requests").mkdir(parents=True)
            (root/"visual_anchor_spec.json").write_text("{}")
            (root/"visual_content_policy.json").write_text("{}")
            (root/"pdca/state.json").write_text(json.dumps({
                "pending_external_actions":[{
                    "action_id":"smoke-image-001",
                    "capability":"social.post.publish",
                    "status":"candidate",
                    "media_intent":{"mode":"generate","status":"awaiting_asset_and_validation"}
                }]
            }))
            request=root/"pdca/media_requests/smoke-image-001.json"
            request.write_text(json.dumps({
                "schema":"agentos.persona-media-request/v1",
                "action_id":"smoke-image-001",
                "status":"awaiting_media_executor",
                "mode":"generate",
                "generation_prompt":"test only"
            }))
            # Deliberately disable generator to exercise safe failure receipt.
            env={"PATH":"/usr/bin:/bin","AGENTOS_MIO_IMAGE_EXECUTOR":"/missing",
                 "AGENTOS_MIO_IMAGE_EXECUTOR_PYTHON":"/missing",
                 "AGENTOS_MIO_MEDIA_OUTPUT_DIR":str(root/"media")}
            for _ in range(2):
                p=subprocess.run([sys.executable,str(WORKER),"--persona-dir",str(root)],
                                 env=env,capture_output=True,text=True,timeout=15)
                self.assertEqual(p.returncode,0,p.stderr)
            receipt=json.loads((root/"pdca/media_receipts/smoke-image-001.json").read_text())
            self.assertEqual(receipt["status"],"BLOCKED")
            self.assertEqual(receipt["reason"],"CAPABILITY_UNAVAILABLE_IMAGE_GENERATION")
            self.assertFalse(receipt["generated"])
            self.assertFalse(receipt["uploaded"])
            rows=[json.loads(line) for line in (root/"pdca/capability_experience.jsonl").read_text().splitlines()]
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]["outcome"],"FAILED")
            self.assertEqual(rows[0]["evidence_kind"],"runtime_receipt")
            state=json.loads((root/"pdca/state.json").read_text())
            self.assertEqual(state["pending_external_actions"][0]["media_intent"]["status"],"blocked")
            self.assertEqual(state["pending_external_actions"][0]["status"],"candidate")
            self.assertFalse((root/"media").exists())

if __name__=="__main__":
    unittest.main()
