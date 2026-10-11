"""Image review accepts observed evidence, never simulated runtime readiness."""
import contextlib
import copy
import io
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import persona_media_review as review
import persona_media_asset as assets
import persona_media_request_worker as worker
from tests import test_persona_media_publish as publish_tests


class VisualReview(unittest.TestCase):
    def setUp(self):
        self.f=publish_tests.MediaLane(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.root=self.f.root; self.action=self.f.action
        self.action["media_intent"].update(world_ids=["scene-test"],wardrobe_ids=["top-test"])
        self.f.write("pdca/state.json",self.f.state)
        self.f.review.unlink()
        self.reference=self.f.drafts/"reference.jpg"
        self.reference.write_bytes(b"\xff\xd8\xff"+b"canonical reference fixture"*6)
        pack=assets.load(self.root/"reference_pack.json")
        pack["canonical_asset"]["sha256"]=assets.digest(self.reference.read_bytes())
        self.f.write("reference_pack.json",pack)
        self.f.write("world_library/policy.json",{"block_on_missing":True})
        self.cli=self.f.drafts/"codex"; self.cli.write_bytes(b"cli-fixture")
        self.request={"action_id":self.action["action_id"],"mode":"generate","status":"generated_unverified",
                      "receipt_ref":"pdca/media_receipts/generated.json"}
        self.f.write("pdca/media_requests/image-test-01.json",self.request)
        self.generation={"status":"GENERATED_UNVERIFIED","action_id":self.action["action_id"],
                         "image_path":str(self.f.image),"image_sha256":self.f.sha,
                         "caption_sha256":assets.caption_digest(self.action),
                         "media_selection_sha256":assets.selection_digest(self.action),
                         "reference_image_sha256":pack["canonical_asset"]["sha256"]}
        self.f.write(self.request["receipt_ref"],self.generation)
        self.value={"image_seen":True,"face_visible":True,"camera_mirror_state":"not_mirrored",
                    "features":{x:{"status":"pass","evidence":["specific fixture observation"]} for x in review.FEATURES},
                    "checks":{x:{"status":"pass","evidence":["independent fixture evidence"]} for x in review.GATES},
                    "visible_wardrobe_ids":["top-test"],"unlisted_wearables":False,"image_alt_text":"澪窗邊情境草稿"}
        self.env=patch.dict(os.environ,{"AGENTOS_MIO_REFERENCE_IMAGE":str(self.reference),
            "AGENTOS_MIO_VISUAL_REVIEW":"codex_cli","AGENTOS_MIO_IMAGE_EXECUTOR":str(self.cli),
            "AGENTOS_MIO_IMAGE_EXECUTOR_PYTHON":sys.executable})
        self.env.start(); self.addCleanup(self.env.stop)
        self.discover=patch.object(review,"discover_codex_executor",return_value=str(self.cli))
        self.discover.start(); self.addCleanup(self.discover.stop)

    def run_review(self,value=None,side_effect=None):
        with patch.object(review,"invoke",return_value=value if value is not None else self.value,side_effect=side_effect) as invoke:
            changed=review.review_one(self.root,self.action,self.request)
        receipt=assets.load(self.root/"pdca/media_review_receipts/image-test-01.json")
        return changed,receipt,invoke

    def test_success_binds_exact_inputs_and_reuses_existing_validator(self):
        changed,r,invoke=self.run_review()
        self.assertTrue(changed); self.assertEqual(r["status"],"REVIEW_PASSED")
        self.assertFalse(r["publication_allowed"])
        args=invoke.call_args.args
        self.assertEqual(args[2],self.f.data); self.assertEqual(args[3],self.reference.read_bytes())
        manifest=assets.load(self.f.review)
        self.assertEqual(manifest["media_selection_sha256"],assets.selection_digest(self.action))
        self.assertEqual(manifest["provenance"]["wardrobe_ids"],["top-test"])
        assets.validate_review(self.root,self.action,self.f.review)

    def test_generated_draft_review_enters_existing_host_lane(self):
        with patch.object(review,"invoke",return_value=self.value),patch.object(assets,"read_public_image",self.f.public),contextlib.redirect_stdout(io.StringIO()):
            worker.process(self.root)
        state=assets.load(self.root/"pdca/state.json")
        self.assertEqual(state["pending_external_actions"][0]["media_intent"]["status"],"validated")
        self.assertEqual(assets.load(self.root/"pdca/media_requests/image-test-01.json")["status"],"asset_validated")

    def test_unchanged_inputs_call_provider_once(self):
        self.run_review()
        changed,_,invoke=self.run_review()
        self.assertFalse(changed); invoke.assert_not_called()

    def test_unapproved_world_never_calls_model_or_creates_manifest(self):
        world=assets.load(self.root/"world_library/catalog.json"); world["entries"][0]["lifecycle"]="candidate"
        self.f.write("world_library/catalog.json",world)
        _,r,invoke=self.run_review()
        self.assertEqual(r["reason"],"MEDIA_WORLD_SOURCE_NOT_USABLE")
        invoke.assert_not_called(); self.assertFalse(self.f.review.exists())

    def test_unverified_wardrobe_never_calls_model(self):
        wardrobe=assets.load(self.root/"wardrobe/catalog.json"); wardrobe["items"][0]["rights"]["product_image_use"]="unverified"
        self.f.write("wardrobe/catalog.json",wardrobe)
        _,r,invoke=self.run_review()
        self.assertEqual(r["reason"],"MEDIA_WARDROBE_RIGHTS_UNVERIFIED"); invoke.assert_not_called()

    def test_identity_and_unseen_image_never_pass(self):
        for key,value in (("image_seen",False),("face_visible",False),("unlisted_wearables",True),("camera_mirror_state","unknown"),("visible_wardrobe_ids",[])):
            with self.subTest(key=key):
                data=copy.deepcopy(self.value); data[key]=value
                with self.assertRaises(ValueError): review.checked_output(data,{"wardrobe_ids":["top-test"]})
        for feature in review.FEATURES:
            data=copy.deepcopy(self.value); data["features"][feature]["status"]="pending"
            with self.assertRaises(ValueError): review.checked_output(data,{"wardrobe_ids":["top-test"]})

    def test_closed_mouth_canine_requires_evidence(self):
        self.value["features"]["upper_right_canine"]["status"]="not_visible"
        review.checked_output(self.value,{"wardrobe_ids":["top-test"]})
        self.value["features"]["upper_right_canine"]["evidence"]=[]
        with self.assertRaises(ValueError): review.checked_output(self.value,{"wardrobe_ids":["top-test"]})

    def test_boolean_strings_and_bare_pass_are_rejected(self):
        for field in ("image_seen","face_visible","unlisted_wearables"):
            data=copy.deepcopy(self.value); data[field]="true"
            with self.assertRaises(ValueError): review.checked_output(data,{"wardrobe_ids":["top-test"]})
        self.value["checks"]["caption_fact_check"]["evidence"]=[]
        with self.assertRaises(ValueError): review.checked_output(self.value,{"wardrobe_ids":["top-test"]})

    def test_timeout_is_sanitized_and_not_retried_without_changed_inputs(self):
        _,r,_=self.run_review(side_effect=subprocess.TimeoutExpired("private prompt",60,stderr="secret"))
        self.assertEqual(r["reason"],"MEDIA_REVIEW_TIMEOUT")
        _,_,invoke=self.run_review(); invoke.assert_not_called()
        self.assertNotIn("secret",json.dumps(r)); self.assertFalse(self.f.review.exists())

    def test_digest_reference_and_path_fail_before_provider(self):
        self.reference.write_bytes(b"wrong")
        _,r,invoke=self.run_review()
        self.assertEqual(r["reason"],"canonical_reference_digest_mismatch"); invoke.assert_not_called()

    def test_generation_receipt_binding_rejects_rewritten_caption(self):
        self.action["primary_text"]="不同的文字"
        _,r,invoke=self.run_review()
        self.assertEqual(r["reason"],"MEDIA_GENERATION_INTENT_CHANGED"); invoke.assert_not_called()

    def test_policy_or_draft_change_during_review_rejects_stale_evidence(self):
        def change(*args):
            self.f.write("visual_content_policy.json",{"version":999})
            return self.value
        _,r,_=self.run_review(side_effect=change)
        self.assertEqual(r["reason"],"MEDIA_REVIEW_INPUT_CHANGED"); self.assertFalse(self.f.review.exists())

    def test_policy_revision_allows_fresh_review_after_prior_hold(self):
        self.run_review(side_effect=ValueError("private-token-output"))
        self.f.write("visual_content_policy.json",{"version":4})
        _,r,invoke=self.run_review()
        self.assertEqual(r["status"],"REVIEW_PASSED"); invoke.assert_called_once()

    def test_negative_energy_or_disabled_authority_does_not_invoke(self):
        for energy in (0,-1):
            self.f.state["energy_current"]=energy; self.f.write("pdca/state.json",self.f.state)
            with patch.object(review,"review_one") as run:
                self.assertEqual(review.process_reviews(self.root),0); run.assert_not_called()
        self.f.state["energy_current"]=5; self.f.write("pdca/state.json",self.f.state)
        self.f.write("pdca/config.json",{"enabled":False})
        with patch.object(review,"review_one") as run:
            self.assertEqual(review.process_reviews(self.root),0); run.assert_not_called()

    def test_readiness_records_configuration_not_provider_acceptance(self):
        review.persist_readiness(self.root)
        path=self.root/"pdca/media_readiness.json"; before=path.read_bytes()
        r=assets.load(path)
        self.assertEqual(r["status"],"CONFIGURED_NOT_ACCEPTED")
        self.assertEqual(r["provider_acceptance"],"NOT_OBSERVED"); self.assertFalse(r["publication_allowed"])
        self.assertNotIn(str(self.reference),path.read_text())
        review.persist_readiness(self.root); self.assertEqual(path.read_bytes(),before)
        self.reference.write_bytes(b"wrong")
        review.persist_readiness(self.root); self.assertEqual(assets.load(path)["status"],"BLOCKED")

    def test_codex_recipe_attaches_two_exact_images_in_isolated_workspace(self):
        def run(argv,**kwargs):
            self.assertEqual(kwargs["timeout"],60); self.assertEqual(kwargs["stdin"],subprocess.DEVNULL)
            self.assertIn("read-only",argv); self.assertIn("never",argv); self.assertIn("--ephemeral",argv)
            image_paths=[Path(argv[i+1]) for i,x in enumerate(argv) if x=="--image"]
            self.assertEqual([x.read_bytes() for x in image_paths],[self.f.data,self.reference.read_bytes()])
            home=Path(kwargs["env"]["CODEX_HOME"])
            self.assertIn("shell_tool = false",(home/"config.toml").read_text())
            Path(argv[argv.index("--output-last-message")+1]).write_text(json.dumps(self.value))
            return subprocess.CompletedProcess(argv,0,"","")
        with patch.object(subprocess,"run",side_effect=run):
            self.assertEqual(review.invoke(str(self.cli),"review",self.f.data,self.reference.read_bytes(),".jpg"),self.value)

    def test_source_selection_ids_are_part_of_intent_digest(self):
        before=assets.selection_digest(self.action)
        self.action["media_intent"]["wardrobe_ids"]=["different"]
        self.assertNotEqual(assets.selection_digest(self.action),before)

    def test_unknown_or_pending_image_receipt_survives_runner_reporting(self):
        source=(Path(worker.__file__).with_name("run_persona_social_actions_user.sh")).read_text()
        code=re.search(r'python3 - "\$SOCIAL_RECEIPT" "\$METRICS_STATUS" "\$METRICS_CHANGED" <<\'PY\'\n(.*?)\nPY',source,re.S).group(1)
        for status,write,expected in (("AWAITING_READBACK",True,"PENDING_READBACK"),("WRITE_OUTCOME_UNKNOWN",None,"WRITE_OUTCOME_UNKNOWN")):
            path=self.f.write("pdca/social_receipts/runtime.json",{"status":status,"write_performed":write,"ok":False})
            result=subprocess.run([sys.executable,"-",str(path),"NO_CHANGE","0"],input=code,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn("persona_social_action_runtime="+expected,result.stdout)
            if write is None: self.assertIn("persona_social_action_write=unknown",result.stdout)


if __name__=="__main__": unittest.main()
