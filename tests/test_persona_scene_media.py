"""Offline scene-only proofs; no live image providers, hosting or publication."""
import contextlib
import copy
import io
import json
import sys
import subprocess
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import persona_media_asset as assets
import persona_media_review as review
import persona_media_request_worker as worker
import persona_image_generate_flux as flux
from tests import test_persona_media_review as portrait
from tests import test_persona_post_reasoning as author


class SceneMedia(unittest.TestCase):
    def setUp(self):
        self.f=portrait.VisualReview(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.root=self.f.root; self.action=self.f.action
        self.action["media_intent"].update(subject_mode="scene_only",wardrobe_ids=[])
        self.f.f.write("visual_content_policy.json",{"version":4,"scene_only_images":{"enabled":True}})
        self.f.f.write("wardrobe/catalog.json",{"items":[]})
        self.f.f.write("pdca/state.json",self.f.f.state)
        self.f.request["subject_mode"]="scene_only"
        self.f.f.write("pdca/media_requests/image-test-01.json",self.f.request)
        self.f.generation.update(subject_mode="scene_only",identity_reference_used=False,
                                media_selection_sha256=assets.selection_digest(self.action))
        self.f.f.write(self.f.request["receipt_ref"],self.f.generation)
        self.value={"image_seen":True,"people_visible":False,"face_visible":False,
                    "visible_wardrobe_ids":[],"unlisted_wearables":False,"image_alt_text":"想像中的窗邊桌面。",
                    "checks":{x:{"status":"pass","evidence":["specific independent scene observation"]}
                              for x in (*assets.REVIEW_GATES,"no_people","visual_quality")}}

    def run_review(self, value=None, side_effect=None):
        return self.f.run_review(self.value if value is None else value,side_effect)

    def test_scene_review_uses_one_image_and_no_identity_claim(self):
        _,r,invoke=self.run_review()
        self.assertEqual(r["status"],"REVIEW_PASSED")
        self.assertIsNone(invoke.call_args.args[3])
        self.assertIn("ONLY attached image",invoke.call_args.args[1])
        manifest=assets.load(self.f.f.review)
        self.assertNotIn("identity_blueprint",manifest)
        self.assertEqual(manifest["subject_mode"],"scene_only")
        assets.validate_review(self.root,self.action,self.f.f.review)

    def test_scene_reuses_host_publish_exact_readback_and_energy_journal(self):
        with patch.object(review,"invoke",return_value=self.value),patch.object(assets,"read_public_image",self.f.f.public),contextlib.redirect_stdout(io.StringIO()):
            worker.process(self.root)
        state=assets.load(self.root/"pdca/state.json")
        self.assertEqual(state["pending_external_actions"][0]["media_intent"]["status"],"validated")
        self.f.f.state=state; self.f.f.action=state["pending_external_actions"][0]
        r=self.f.f.execute()
        self.assertEqual(r["media_readback_status"],"PASS")
        self.assertEqual(state["energy_current"],-3)
        self.assertEqual(sum(p=="/v1/social/publish" for p,_ in self.f.f.calls),1)

    def test_scene_policy_absent_or_nonboolean_never_calls_reviewer(self):
        for flag in (None,False,"true",1):
            self.f.f.write("visual_content_policy.json",{"scene_only_images":{"enabled":flag}})
            _,r,invoke=self.run_review()
            self.assertEqual(r["reason"],"MEDIA_SCENE_POLICY_NOT_ENABLED")
            invoke.assert_not_called()

    def test_people_and_boolean_strings_never_pass_scene_review(self):
        for field,invalid in (("people_visible",True),("people_visible","false"),("face_visible",True),
                              ("face_visible",0),("image_seen","true"),("unlisted_wearables",True),
                              ("visible_wardrobe_ids",["top-test"])):
            with self.subTest(field=field,invalid=invalid):
                value=copy.deepcopy(self.value); value[field]=invalid
                with self.assertRaises(ValueError):
                    review.checked_output(value,{"subject_mode":"scene_only","wardrobe_ids":[]})

    def test_scene_requires_all_content_checks_and_absence_evidence(self):
        for name in (*assets.REVIEW_GATES,"no_people","visual_quality"):
            for change in ({"status":"pending","evidence":["uncertain"]},{"status":"pass","evidence":[]}):
                value=copy.deepcopy(self.value); value["checks"][name]=change
                with self.assertRaises(ValueError):
                    review.checked_output(value,{"subject_mode":"scene_only","wardrobe_ids":[]})

    def test_scene_cannot_select_even_approved_wardrobe(self):
        self.action["media_intent"]["wardrobe_ids"]=["top-test"]
        _,r,invoke=self.run_review()
        self.assertEqual(r["reason"],"MEDIA_SCENE_WARDROBE_NOT_ALLOWED"); invoke.assert_not_called()

    def test_source_eligibility_still_blocks_before_review(self):
        self.f.f.write("world_library/catalog.json",{"entries":[{"id":"scene-test","lifecycle":"candidate"}]})
        _,r,invoke=self.run_review()
        self.assertEqual(r["reason"],"MEDIA_WORLD_SOURCE_NOT_USABLE"); invoke.assert_not_called()

    def test_portrait_generation_receipt_cannot_be_relabelled_scene(self):
        for field,value in (("subject_mode","mio_portrait"),("identity_reference_used",True)):
            generation=copy.deepcopy(self.f.generation); generation[field]=value
            self.f.f.write(self.f.request["receipt_ref"],generation)
            _,r,invoke=self.run_review()
            self.assertEqual(r["status"],"BLOCKED"); invoke.assert_not_called()

    def test_revoke_policy_during_review_blocks_manifest(self):
        def revoke(*args):
            self.f.f.write("visual_content_policy.json",{"scene_only_images":{"enabled":False}})
            return self.value
        _,r,_=self.run_review(side_effect=revoke)
        self.assertEqual(r["reason"],"MEDIA_REVIEW_INPUT_CHANGED")
        self.assertFalse(self.f.f.review.exists())

    def test_policy_revocation_after_review_blocks_host_and_publish(self):
        self.run_review()
        self.f.f.write("visual_content_policy.json",{"scene_only_images":{"enabled":False}})
        with patch.object(assets,"read_public_image") as host:
            with self.assertRaises(ValueError):
                assets.prepare_asset(self.root,self.action,self.f.f.review,self.f.f.host)
            host.assert_not_called()

    def test_subject_change_invalidates_review_and_asset_digest(self):
        self.run_review()
        before=assets.selection_digest(self.action)
        self.action["media_intent"]["subject_mode"]="mio_portrait"
        self.assertNotEqual(before,assets.selection_digest(self.action))
        with self.assertRaises(ValueError): assets.validate_review(self.root,self.action,self.f.f.review)

    def test_identity_blueprint_cannot_be_added_to_scene_evidence(self):
        self.run_review()
        manifest=assets.load(self.f.f.review); manifest["identity_blueprint"]={"blueprint_version":"2.1"}
        with self.assertRaises(ValueError): assets.review_manifest(self.root,self.action,manifest)

    def test_scene_cli_cannot_be_used_without_explicit_flag(self):
        self.run_review()
        command=[sys.executable,str(Path(review.__file__).with_name("validate_mio_visual_manifest.py")),
                 "--manifest",str(self.f.f.review),"--visual-anchor",str(self.root/"visual_anchor_spec.json")]
        self.assertNotEqual(subprocess.run(command,capture_output=True).returncode,0)
        self.assertEqual(subprocess.run([*command,"--scene-only"],capture_output=True).returncode,0)
        self.assertNotEqual(subprocess.run([*command,"--scene-only","--photo-like-face"],capture_output=True).returncode,0)

    def test_unknown_subject_mode_never_downgrades_identity(self):
        self.action["media_intent"]["subject_mode"]="scene"
        _,r,invoke=self.run_review()
        self.assertEqual(r["reason"],"MEDIA_SUBJECT_MODE_INVALID"); invoke.assert_not_called()

    def test_repeated_review_is_idempotent(self):
        self.run_review(); changed,_,invoke=self.run_review()
        self.assertFalse(changed); invoke.assert_not_called()

    def test_isolated_reviewer_cli_receives_only_scene_bytes(self):
        def run(command, **kwargs):
            self.assertEqual(command.count("--image"),1)
            image=Path(command[command.index("--image")+1])
            self.assertEqual(image.read_bytes(),self.f.f.data)
            self.assertFalse((image.parent/"approved-reference.jpg").exists())
            answer=Path(command[command.index("--output-last-message")+1])
            answer.write_text(json.dumps(self.value))
            self.assertEqual(kwargs["timeout"],60)
            return subprocess.CompletedProcess(command,0,"","")
        with patch.object(review.subprocess,"run",side_effect=run):
            value=review.invoke(str(self.f.cli),"scene review",self.f.f.data,None,".jpg")
        self.assertEqual(value,self.value)

    def test_worker_preserves_subject_and_neutral_input_receipt(self):
        request=copy.deepcopy(self.f.request); request["status"]="awaiting_media_executor"
        self.f.f.write("pdca/media_requests/image-test-01.json",request)
        def run(command, **kwargs):
            sent=assets.load(Path(command[command.index("--request")+1]))
            self.assertEqual(sent["subject_mode"],"scene_only")
            self.assertEqual(sent["content_assembly"]["wardrobe"],[])
            generated={**self.f.generation,"generation_input_sha256":"b"*64}
            Path(command[command.index("--receipt")+1]).write_text(json.dumps(generated))
            return subprocess.CompletedProcess(command,0,"","")
        with patch.object(worker.subprocess,"run",side_effect=run),contextlib.redirect_stdout(io.StringIO()):
            worker.process(self.root)
        generated=assets.load(self.root/"pdca/media_receipts/image-test-01.json")
        self.assertEqual(generated["subject_mode"],"scene_only")
        self.assertIs(generated["identity_reference_used"],False)
        self.assertEqual(generated["generation_input_sha256"],"b"*64)

    def test_generation_uses_neutral_canvas_instead_of_canonical_image(self):
        reference=self.f.reference.read_bytes()
        request={"action_id":"scene-generation","mode":"generate","subject_mode":"scene_only",
                 "generation_prompt":"fictional desk", "canonical_reference_pack":assets.load(self.root/"reference_pack.json"),
                 "visual_content_policy":{"scene_only_images":{"enabled":True}},
                 "content_assembly":{"world":[{"id":"scene-test"}],"wardrobe":[]}}
        class ImageFixture:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def verify(self): pass
            def convert(self,*args): return self
            def save(self,path,**kwargs): Path(path).write_bytes(b"fixture neutral or output bytes"*10)
        inputs=[]
        def predict(**kwargs):
            source=Path(kwargs["input_image"]); inputs.append(source.read_bytes())
            self.assertEqual(source.name,"neutral.png")
            self.assertNotEqual(source.read_bytes(),reference)
            self.assertIn("No people",kwargs["prompt"])
            return str(self.f.f.image)
        pil=SimpleNamespace(Image=SimpleNamespace(new=lambda *a:ImageFixture(),open=lambda *a:ImageFixture()))
        gradio=SimpleNamespace(Client=lambda *a,**kw:SimpleNamespace(predict=predict),handle_file=lambda p:p)
        with patch.dict(sys.modules,{"PIL":pil,"gradio_client":gradio}):
            generated=flux.generate(request,self.f.f.drafts)
        self.assertEqual(generated["status"],"GENERATED_UNVERIFIED")
        self.assertIs(generated["identity_reference_used"],False)
        self.assertFalse(generated["identity_verified"])
        self.assertFalse(generated["publication_allowed"])
        self.assertEqual(generated["generation_input_sha256"],assets.digest(inputs[0]))

    def test_generation_policy_hold_precedes_provider_import(self):
        request={"action_id":"scene-generation","mode":"generate","subject_mode":"scene_only",
                 "generation_prompt":"desk","canonical_reference_pack":assets.load(self.root/"reference_pack.json")}
        with self.assertRaisesRegex(ValueError,"MEDIA_SCENE_POLICY_NOT_ENABLED"):
            flux.generate(request,self.f.f.drafts)

    def test_readiness_distinguishes_support_policy_and_real_image_acceptance(self):
        review.persist_readiness(self.root)
        path=self.root/"pdca/media_readiness.json"; r=assets.load(path)
        self.assertEqual(r["enabled_subject_modes"],["mio_portrait","scene_only"])
        self.assertEqual(r["eligible_wardrobe_count"],0)
        self.assertEqual(r["autonomous_image_acceptance"],"NOT_OBSERVED")
        self.assertEqual(r["image_generator_sha256"],assets.digest(Path(flux.__file__).read_bytes()))
        self.f.f.write("visual_content_policy.json",{"scene_only_images":{"enabled":False}})
        review.persist_readiness(self.root)
        self.assertEqual(assets.load(path)["enabled_subject_modes"],["mio_portrait"])


class SceneAuthoring(unittest.TestCase):
    def run_author(self, enabled, wardrobe_ids=()):
        catalogs={"visual_content_policy.json":{"scene_only_images":{"enabled":enabled}},
                  "world_library/catalog.json":{"entries":[{"id":"desk","lifecycle":"usable","source":{"rights":"original_description_only"}}]},
                  "wardrobe/catalog.json":{"items":[]}}
        decision={**author.DECISION,"image_decision":"generate","image_subject_mode":"scene_only",
                  "image_prompt":"想像的無人窗邊桌面","image_world_ids":["desk"],"image_wardrobe_ids":list(wardrobe_ids)}
        return author.PostReasoningTests().run_generator([subprocess.CompletedProcess("claude",0,json.dumps(decision),"")],media_catalogs=catalogs)

    def test_authoring_preserves_subject_without_identity_claim_or_wardrobe(self):
        out,_,_,actions,calls=self.run_author(True)
        self.assertEqual(out["status"],"CANDIDATE_CREATED")
        self.assertEqual(actions[0]["media_intent"]["subject_mode"],"scene_only")
        self.assertFalse(actions[0]["media_intent"]["canonical_identity_required"])
        self.assertEqual(actions[0]["media_intent"]["wardrobe_ids"],[])
        self.assertIn('"image_subject_modes": ["mio_portrait", "scene_only"]',calls[0].args[0][-1])

    def test_unauthorized_scene_never_creates_text_or_image_candidate(self):
        for flag in (False,"true",1):
            out,_,_,actions,_=self.run_author(flag)
            self.assertEqual(out["reason"],"image_subject_not_authorized"); self.assertEqual(actions,[])

    def test_scene_wardrobe_selection_is_held(self):
        out,_,_,actions,_=self.run_author(True,["anything"])
        self.assertEqual(out["status"],"DEFER"); self.assertEqual(actions,[])


if __name__=="__main__": unittest.main()
