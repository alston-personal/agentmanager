"""Offline image-lane acceptance: bytes/review binding and one-write recovery."""
import contextlib
import copy
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS=Path(__file__).resolve().parents[1]/"scripts"
sys.path.insert(0,str(SCRIPTS))
import persona_media_asset as assets
import persona_social_executor as social
import persona_media_request_worker as worker
import persona_image_generate_flux as generator


class MediaLane(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/"persona"
        self.root.mkdir()
        self.drafts=Path(self.temp.name)/"drafts"
        self.drafts.mkdir()
        self.host=Path(self.temp.name)/"host"
        self.journal=Path(self.temp.name)/"journal"
        self.env_patch=patch.dict(os.environ,{"AGENTOS_MIO_MEDIA_OUTPUT_DIR":str(self.drafts),
            "AGENTOS_MIO_PUBLIC_MEDIA_DIR":str(self.host),"AGENTOS_PERSONA_WRITE_JOURNAL_DIR":str(self.journal)})
        self.env_patch.start(); self.addCleanup(self.env_patch.stop)
        self.action={"action_id":"image-test-01","status":"candidate","capability":"social.post.publish",
                     "primary_text":"想像中的窗邊片刻。","media_intent":{"mode":"generate"}}
        self.state={"status":"RUNNING","energy_current":5,"persona_id":"mio",
                    "pending_external_actions":[self.action]}
        self.write("pdca/state.json",self.state)
        self.write("persona_state.json",{"autonomy":{"routine_posts":"autonomous_with_policy"}})
        self.write("pdca/config.json",{"enabled":True})
        self.write("visual_anchor_spec.json",{"face_blueprint":{"schema":"agentos.persona-face-blueprint/v2.1"}})
        self.write("visual_content_policy.json",{"version":3})
        self.write("reference_pack.json",{"status":"approved","approved_reference_ids":["reference-v2.1"],
                   "canonical_asset":{"sha256":"a"*64,"reference_id":"reference-v2.1"}})
        self.write("world_library/catalog.json",{"entries":[{"id":"scene-test","lifecycle":"usable","source":{"rights":"original_description_only"}}]})
        self.write("wardrobe/catalog.json",{"items":[{"item_id":"top-test","state":"approved",
            "rights":{"product_image_use":"owner_authorized","evidence_ref":"owner-receipt"}}]})
        self.image=self.drafts/"image.jpg"
        self.data=b"\xff\xd8\xff"+b"fixture-reviewed-image"*10
        self.image.write_bytes(self.data)
        self.sha=assets.digest(self.data)
        features={name:{"status":"pass","evidence":["independent review fixture"]}
                  for name in ("face_shape","eye_shape","brows","hair_flow","right_eye_beauty_mark","upper_right_canine")}
        self.manifest={"schema":"milkcat.image-manifest/v2","action_id":self.action["action_id"],
            "caption_sha256":assets.caption_digest(self.action),"image_sha256":self.sha,"image_path":str(self.image),
            "media_selection_sha256":assets.selection_digest(self.action),
            "image_alt_text":"窗邊的澪之情境圖", "reference_image_sha256":"a"*64,
            "identity_blueprint":{"blueprint_version":"2.1","reference_pack_status":"approved",
                "camera_mirror_state":"not_mirrored","features":features},
            "checks":{name:{"status":"pass","evidence":["review-fixture"]} for name in (*assets.REVIEW_GATES,"identity")},
            "publication":{"allowed":True},"provenance":{"source_ref":"draft-fixture",
                "rights_evidence_ref":"rights-fixture","commercial_state":"organic_no_brand",
                "world_ids":["scene-test"],"wardrobe_ids":["top-test"]}}
        for name,ref in (("visual_policy","visual_content_policy.json"),("visual_anchor","visual_anchor_spec.json"),
                         ("reference_pack","reference_pack.json"),("world_catalog","world_library/catalog.json"),
                         ("wardrobe_catalog","wardrobe/catalog.json")):
            self.manifest[name+"_sha256"]=assets.digest((self.root/ref).read_bytes())
        self.review=self.write("pdca/media_reviews/image-test-01.json",self.manifest)
        self.out=self.root/"pdca/social_receipts/test.json"
        self.base={"schema":"agentos.social-request/v1","platform":"threads","product_id":"galaxy",
                   "account_binding_id":"binding-123","target_account_id":"123"}
        (self.root/"events").mkdir()
        (self.root/"events/events.jsonl").write_text("")
        self.calls=[]
        self.row={"id":"987","text":self.action["primary_text"],"media_type":"IMAGE","image_visible":True,
                  "permalink":"https://www.threads.com/@mio.milkcat/post/test"}

    def write(self,ref,value):
        path=self.root/ref; path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value,ensure_ascii=False)); return path

    def public(self,url,sha):
        self.assertEqual(sha,self.sha)
        self.assertEqual(url,assets.PUBLIC_BASE+self.sha+".jpg")
        self.assertEqual((self.host/(self.sha+".jpg")).read_bytes(),self.data)
        return self.data

    def ready(self):
        with patch.object(assets,"read_public_image",self.public):
            receipt=assets.prepare_asset(self.root,self.action,self.review,self.host)
        self.write("pdca/media_receipts/asset.json",receipt)
        self.action["media_intent"].update(status="validated",asset_receipt_ref="pdca/media_receipts/asset.json")
        return receipt

    def adapter(self,path,request,headers,timeout=20):
        self.calls.append((path,copy.deepcopy(request)))
        if path=="/internal/v1/social/acceptances":
            self.assertEqual(request["image_url"],assets.PUBLIC_BASE+self.sha+".jpg")
            return 201,{"acceptance_id":"accepted"}
        if path=="/v1/social/publish":
            self.assertEqual(request["operation"],"publish")
            self.assertEqual(timeout,100)
            return 200,{"ok":True,"platform_object_id":"987","operation":"publish",
                "target_account_id":"123","account_binding_id":"binding-123","completed_at":"2026-10-11T02:00:00Z"}
        if path=="/v1/social/status":
            return 200,{"ok":True,"result":{"items":[self.row] if self.row else []}}
        raise AssertionError(path)

    def execute(self,adapter=None):
        with patch.object(assets,"read_public_image",self.public),patch.object(social,"post",adapter or self.adapter):
            return social.image_write(self.root,self.state,self.action,self.out,"mio.milkcat",self.base,
                                      {"X-AgentOS-Product-Key":"test"},"control","2026-10-11T02:00:01Z",8)

    def test_review_to_real_image_request_and_exact_id_readback(self):
        self.ready(); receipt=self.execute()
        self.assertTrue(receipt["ok"])
        self.assertEqual(receipt["media_readback_status"],"PASS")
        self.assertEqual(self.action["status"],"completed")
        self.assertEqual(self.state["energy_current"],-3)
        self.assertEqual(self.action["provider_object_id"],"987")
        event=json.loads((self.root/"events/events.jsonl").read_text())
        self.assertEqual(event["source_object_id"],"987")
        self.assertEqual(event["media_type"],"IMAGE")
        self.assertNotIn("reply_to_id",self.calls[1][1])

    def test_readback_delay_retries_only_reads_and_debits_once_even_at_negative_energy(self):
        self.ready(); row=self.row; self.row=None
        self.assertEqual(self.execute()["status"],"AWAITING_READBACK")
        self.assertEqual(self.state["energy_current"],-3)
        self.row=row
        self.assertEqual(self.execute()["status"],"EXECUTED")
        self.assertEqual(self.state["energy_current"],-3)
        self.assertEqual(sum(path=="/v1/social/publish" for path,_ in self.calls),1)

    def test_unknown_timeout_never_republishes_after_state_clone_is_lost(self):
        self.ready(); old_state=copy.deepcopy(self.state)
        def timeout(path,*args,**kwargs):
            if path=="/v1/social/publish": raise TimeoutError("private-provider-text")
            return self.adapter(path,*args,**kwargs)
        receipt=self.execute(timeout)
        self.assertEqual(receipt["status"],"WRITE_OUTCOME_UNKNOWN")
        self.assertIsNone(receipt["write_performed"])
        self.state=old_state; self.action=self.state["pending_external_actions"][0]
        self.calls=[]
        self.assertEqual(self.execute()["status"],"WRITE_OUTCOME_UNKNOWN")
        self.assertEqual(self.calls,[])
        self.assertNotIn("private-provider-text",self.out.read_text())

    def test_provider_receipt_must_bind_success_operation_account_and_object(self):
        self.ready()
        for field,value in (("ok",False),("platform_object_id",""),("operation","reply"),
                            ("target_account_id","foreign"),("account_binding_id","foreign")):
            with self.subTest(field=field):
                for path in self.journal.glob("*.json"): path.unlink()
                self.action["status"]="candidate"
                def malformed(path,*args,**kwargs):
                    code,r=self.adapter(path,*args,**kwargs)
                    if path=="/v1/social/publish": r[field]=value
                    return code,r
                self.assertEqual(self.execute(malformed)["status"],"WRITE_OUTCOME_UNKNOWN")
                self.assertEqual(self.state["energy_current"],5)
        self.assertEqual((self.root/"events/events.jsonl").read_text(),"")

    def test_known_write_survives_lost_git_push_and_emits_one_event(self):
        self.ready(); old_state=copy.deepcopy(self.state); row=self.row; self.row=None
        self.execute()
        self.state=old_state; self.action=self.state["pending_external_actions"][0]; self.row=row
        self.assertEqual(self.execute()["status"],"EXECUTED")
        self.assertEqual(self.state["energy_current"],-3)
        self.execute()
        self.assertEqual(len((self.root/"events/events.jsonl").read_text().splitlines()),1)
        self.assertEqual(sum(path=="/v1/social/publish" for path,_ in self.calls),1)

    def test_wrong_id_text_media_or_visibility_never_completes(self):
        self.ready()
        for field,value in (("id","999"),("text","wrong"),("media_type","TEXT_POST"),("image_visible",False)):
            original=self.row[field]; self.row[field]=value
            with self.subTest(field=field): self.assertEqual(self.execute()["status"],"AWAITING_READBACK")
            self.row[field]=original
        self.assertEqual((self.root/"events/events.jsonl").read_text(),"")
        self.assertEqual(sum(path=="/v1/social/publish" for path,_ in self.calls),1)

    def test_unreviewed_draft_cannot_send_or_silently_fall_back_to_text(self):
        self.assertEqual(self.execute()["status"],"BLOCKED")
        self.assertEqual(self.calls,[])

    def test_changed_intent_after_dispatch_is_blocked(self):
        self.ready(); self.row=None; self.execute()
        self.action["primary_text"]="changed"
        self.calls=[]
        self.assertEqual(self.execute()["result"],"IMAGE_WRITE_INTENT_CHANGED")
        self.assertEqual(self.calls,[])

    def test_receipt_for_another_action_or_modified_caption_is_rejected(self):
        self.ready()
        for key,value in (("action_id","another-action"),("primary_text","modified-caption")):
            original=self.action[key]; self.action[key]=value
            with self.subTest(key=key):
                with self.assertRaises(ValueError): assets.resolve_asset(self.root,self.action)
            self.action[key]=original

    def test_changed_image_choice_or_prompt_invalidates_review(self):
        self.ready(); self.action["media_intent"]["prompt"]="different scene"
        with self.assertRaises(ValueError): assets.resolve_asset(self.root,self.action)

    def test_policy_digest_change_invalidates_previously_reviewed_image(self):
        self.ready(); self.write("visual_content_policy.json",{"version":4})
        self.assertEqual(self.execute()["status"],"BLOCKED")
        self.assertEqual(self.calls,[])

    def test_edited_review_or_served_image_is_rejected(self):
        self.ready(); self.manifest["image_alt_text"]="modified"
        self.write("pdca/media_reviews/image-test-01.json",self.manifest)
        with self.assertRaises(ValueError): assets.resolve_asset(self.root,self.action)

    def test_missing_review_gate_and_unapproved_reference_are_rejected(self):
        for kind in ("checks","reference_image_sha256"):
            m=copy.deepcopy(self.manifest)
            if kind=="checks": m["checks"]["caption_fact_check"]["status"]="pending"
            else: m[kind]="b"*64
            with self.subTest(kind=kind):
                with self.assertRaises(ValueError): assets.review_manifest(self.root,self.action,m)

    def test_candidate_wardrobe_and_world_cannot_be_promoted_by_pass_labels(self):
        for ref,key,collection in (("wardrobe/catalog.json","state","items"),("world_library/catalog.json","lifecycle","entries")):
            old=json.loads((self.root/ref).read_text()); changed=copy.deepcopy(old)
            changed[collection][0][key]="candidate"; self.write(ref,changed)
            m=copy.deepcopy(self.manifest)
            m[("wardrobe_catalog" if collection=="items" else "world_catalog")+"_sha256"]=assets.digest((self.root/ref).read_bytes())
            with self.subTest(collection=collection):
                with self.assertRaises(ValueError): assets.review_manifest(self.root,self.action,m)
            self.write(ref,old)

    def test_reference_escape_and_draft_escape_are_rejected(self):
        with self.assertRaises(ValueError): assets.within(self.root,"../outside.json")
        self.manifest["image_path"]=str(Path(self.temp.name)/"outside.jpg")
        self.write("pdca/media_reviews/image-test-01.json",self.manifest)
        with self.assertRaises(ValueError): assets.prepare_asset(self.root,self.action,self.review,self.host)

    def test_worker_resumes_generated_unverified_only_with_real_review(self):
        self.write("pdca/media_requests/image-test-01.json",{"schema":"agentos.persona-media-request/v1",
                   "action_id":"image-test-01","mode":"generate","status":"generated_unverified"})
        with patch.object(assets,"read_public_image",self.public),contextlib.redirect_stdout(io.StringIO()):
            worker.process(self.root); worker.process(self.root)
        state=json.loads((self.root/"pdca/state.json").read_text())
        self.assertEqual(state["pending_external_actions"][0]["media_intent"]["status"],"validated")
        self.assertEqual(state["pending_external_actions"][0]["status"],"candidate")
        self.assertEqual(self.calls,[])

    def test_public_url_cannot_point_at_arbitrary_host(self):
        with self.assertRaises(ValueError): assets.read_public_image("https://example.org/image.jpg",self.sha)

    def test_public_digest_type_and_redirect_are_checked_against_exact_bytes(self):
        url=assets.PUBLIC_BASE+self.sha+".jpg"
        for data,kind,final in ((b"corrupted","image/jpeg",url),(self.data,"text/html",url),
                                (self.data,"image/jpeg","https://other.example/image.jpg")):
            response=io.BytesIO(data)
            response.status=200; response.headers={"Content-Type":kind}; response.geturl=lambda:final
            with self.subTest(kind=kind,final=final),patch.object(assets.urllib.request,"urlopen",return_value=response):
                with self.assertRaises(ValueError): assets.read_public_image(url,self.sha)

    def test_private_write_journal_permissions_survive_all_updates(self):
        self.ready(); self.execute()
        path=next(self.journal.glob("*.json"))
        self.assertEqual(path.stat().st_mode&0o777,0o600)
        self.assertEqual(self.journal.stat().st_mode&0o777,0o700)

    def test_generator_requires_approved_reference_bytes_before_provider_invocation(self):
        source=self.drafts/"reference.jpg"; source.write_bytes(self.data)
        pack={"status":"approved","approved_reference_ids":["reference-v2.1"],
              "canonical_asset":{"sha256":self.sha,"reference_id":"reference-v2.1"}}
        with patch.dict(os.environ,{"AGENTOS_MIO_REFERENCE_IMAGE":str(source)}):
            self.assertEqual(generator.canonical_reference({"canonical_reference_pack":pack}),self.data)
            source.write_bytes(b"wrong public avatar")
            with self.assertRaisesRegex(ValueError,"digest_mismatch"):
                generator.generate({"action_id":"test","mode":"generate","generation_prompt":"scene",
                                    "canonical_reference_pack":pack},self.drafts)
        with patch.dict(os.environ,{"AGENTOS_MIO_REFERENCE_IMAGE":""}):
            with self.assertRaisesRegex(ValueError,"unavailable"):
                generator.canonical_reference({"canonical_reference_pack":pack})

    def test_main_dispatches_image_lane_and_reconciles_in_progress(self):
        self.ready(); row=self.row; self.row=None
        self.write("pdca/state.json",self.state)
        env=self.root/"runtime.env"
        env.write_text('AGENTOS_SOCIAL_PRODUCTS_JSON={"galaxy":{"api_key":"test"}}\nAGENTOS_SOCIAL_CONTROL_TOKEN=control\n')
        creds=self.write("creds.json",{"bindings":{"binding-123":{"platform":"threads","product_id":"galaxy",
            "username":"mio.milkcat","provider_account_id":"123","auth_profile":"persona"}}})
        with patch.object(social,"ENV",env),patch.object(social,"CREDS",creds),patch.object(social,"post",self.adapter),\
             patch.object(assets,"read_public_image",self.public),patch.object(sys,"argv",["social","--persona-dir",str(self.root),"--receipt-out",str(self.out)]),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(social.main(),0)
            self.row=row
            self.assertEqual(social.main(),0)
        self.assertEqual(json.loads(self.out.read_text())["media_readback_status"],"PASS")
        self.assertEqual(sum(path=="/v1/social/publish" for path,_ in self.calls),1)

    def test_text_and_reply_keep_top_level_provider_id_and_reply_parent(self):
        env=self.root/"runtime.env"
        env.write_text('AGENTOS_SOCIAL_PRODUCTS_JSON={"galaxy":{"api_key":"test"}}\nAGENTOS_SOCIAL_CONTROL_TOKEN=control\n')
        creds=self.write("creds.json",{"bindings":{"binding-123":{"platform":"threads","product_id":"galaxy",
            "username":"mio.milkcat","provider_account_id":"123","auth_profile":"persona"}}})
        for cap,endpoint in (("social.post.publish","/v1/social/publish"),("social.reply.send","/v1/social/reply")):
            self.action.update(status="candidate",capability=cap,media_intent={},reply_to_id="456",root_post_id="789")
            self.state["energy_current"]=30
            self.write("pdca/state.json",self.state)
            (self.root/"events/events.jsonl").write_text("")
            def adapter(path,payload,headers):
                if path=="/internal/v1/social/acceptances": return 201,{"acceptance_id":"accepted"}
                self.assertEqual(path,endpoint)
                if cap=="social.reply.send": self.assertEqual(payload["reply_to_id"],"456")
                else: self.assertNotIn("reply_to_id",payload)
                return 200,{"ok":True,"platform_object_id":"987","result":{}}
            with self.subTest(cap=cap),patch.object(social,"ENV",env),patch.object(social,"CREDS",creds),\
                 patch.object(social,"post",adapter),patch.object(sys,"argv",["social","--persona-dir",str(self.root),"--receipt-out",str(self.out)]),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(social.main(),0)
            event=json.loads((self.root/"events/events.jsonl").read_text())
            self.assertEqual(event["source_object_id"],"987")
            self.assertEqual(event["parent_object_id"],"456" if cap=="social.reply.send" else None)
            self.assertEqual(event["root_post_id"],"789" if cap=="social.reply.send" else "987")


if __name__=="__main__": unittest.main()
