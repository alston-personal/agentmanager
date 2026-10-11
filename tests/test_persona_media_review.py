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
            "AGENTOS_MIO_GARMENT_DATA_ROOT":str(self.f.drafts/"wardrobe-store"),
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

    def audit(self, catalog=None):
        return review.wardrobe_source_audit(self.root,catalog or assets.load(self.root/"wardrobe/catalog.json"))

    def garment(self, folder, filename, value, data_root=None):
        path=(data_root or Path(os.environ["AGENTOS_MIO_GARMENT_DATA_ROOT"]))/"projects/dressup-simulator/garments"/folder/filename
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value),encoding="utf-8")
        return path

    def test_wardrobe_hold_reasons_remain_independent_from_registry(self):
        catalog=assets.load(self.root/"wardrobe/catalog.json")
        item=catalog["items"][0]; item["state"]="candidate"; item["rights"]={"product_image_use":"unverified"}
        before=json.dumps(catalog)
        r=self.audit(catalog)
        self.assertEqual(r["authority"]["kind"],"offline_fixture")
        self.assertFalse(r["publication_allowed"])
        row=r["observed"]["catalog_items"][0]
        self.assertFalse(row["publication_source_eligible"])
        self.assertEqual(row["diagnostics"],["CATALOG_STATE_NOT_USABLE","PRODUCT_IMAGE_RIGHTS_UNVERIFIED",
            "RIGHTS_EVIDENCE_MISSING","CANONICAL_GARMENT_LINK_NOT_OBSERVED"])
        self.assertEqual(json.dumps(catalog),before)

    def test_registry_uses_explicit_live_store_not_social_clone(self):
        live=self.f.drafts/"live-store"
        self.garment("seeded","clone.json",{"garmentId":"wrong","characterId":"sunlake-milkcat-ai-001"})
        self.garment("seeded","live.json",{"garmentId":"real","characterId":"sunlake-milkcat-ai-001"},live)
        catalog=assets.load(self.root/"wardrobe/catalog.json"); catalog["items"][0]["garment_id"]="real"
        with patch.dict(os.environ,{"AGENTOS_MIO_GARMENT_DATA_ROOT":str(live)}):
            r=self.audit(catalog)["observed"]["canonical_registry"]
        self.assertEqual(r["active_persona_records_observed"],1)
        self.assertEqual(r["linked_garments_observed"],1)
        self.assertEqual(r["records"][0]["garment_id"],"real")
        self.assertTrue(r["records"][0]["catalog_link_observed"])
        unit=(Path(review.__file__).with_name("install_persona_pdca_timer_user.sh")).read_text()
        self.assertIn("Environment=AGENTOS_MIO_GARMENT_DATA_ROOT=/home/ubuntu/agent-data",unit)

    def test_imported_precedence_scoping_and_legacy_flat_exclusion(self):
        base={"garmentId":"top-real","characterId":"sunlake-milkcat-ai-001"}
        self.garment("seeded","base.json",{**base,"tryOnSource":{"state":"approved"}})
        self.garment("imported","replacement.json",base)
        self.garment("imported","other.json",{"garmentId":"foreign","characterId":"other"})
        self.garment("imported","unscoped.json",{"garmentId":"unscoped"})
        self.garment("","legacy.json",{**base,"garmentId":"flat"})
        r=self.audit()["observed"]["canonical_registry"]
        self.assertEqual(r["status"],"OBSERVED")
        self.assertEqual(r["active_persona_records_observed"],1)
        self.assertEqual(r["declared_isolation_approved_count"],0)
        self.assertEqual((r["unscoped_records"],r["other_persona_records"]),(1,1))
        self.assertEqual(r["unlinked_garments_observed"],1)

    def test_isolation_declaration_never_approves_social_catalog_or_assets(self):
        row={"garmentId":"top-real","characterId":"sunlake-milkcat-ai-001",
             "tryOnSource":{"state":"approved","isolatedImageUrl":"https://private.example/image"},
             "source":{"imageUrl":"https://private.example/source"},"note":"secret-note"}
        path=self.garment("seeded","top.json",row); before=path.read_bytes()
        catalog=assets.load(self.root/"wardrobe/catalog.json"); item=catalog["items"][0]
        item.update(garment_id="top-real",state="candidate"); item["rights"]["product_image_use"]="unverified"
        r=self.audit(catalog); registry=r["observed"]["canonical_registry"]
        self.assertEqual(registry["declared_isolation_approved_count"],1)
        self.assertEqual(registry["isolation_asset_verification"],"NOT_PERFORMED")
        self.assertEqual(registry["records"][0]["isolation_declared_state"],"approved")
        self.assertFalse(registry["records"][0]["product_ir_declared"])
        self.assertFalse(r["observed"]["catalog_items"][0]["publication_source_eligible"])
        self.assertEqual(path.read_bytes(),before)
        self.assertNotIn("private.example",json.dumps(r)); self.assertNotIn("secret-note",json.dumps(r))

    def test_missing_live_directories_do_not_imply_missing_catalog_approval(self):
        with patch.object(review,"invoke") as model:
            review.persist_readiness(self.root)
        r=assets.load(self.root/"pdca/media_readiness.json")
        self.assertEqual(r["eligible_wardrobe_count"],1)
        self.assertEqual(r["status"],"CONFIGURED_NOT_ACCEPTED")
        audit=r["wardrobe_source_audit"]
        self.assertEqual(audit["observed"]["canonical_registry"]["status"],"DIRECTORIES_ABSENT")
        self.assertEqual(audit["checked_at"],r["observed_at"])
        self.assertFalse(audit["publication_allowed"]); model.assert_not_called()

    def test_missing_configuration_never_scans_persona_clone_or_parent(self):
        with patch.dict(os.environ,{},clear=True),patch.object(os,"scandir") as scan:
            r=self.audit()["observed"]["canonical_registry"]
        self.assertEqual(r["status"],"NOT_CONFIGURED")
        self.assertEqual(r["issues"],["SOURCE_NOT_CONFIGURED"]); scan.assert_not_called()

    def test_registry_change_refreshes_readiness_without_hourly_noise(self):
        path=self.garment("seeded","top.json",{"garmentId":"top-real","characterId":"sunlake-milkcat-ai-001"})
        review.persist_readiness(self.root)
        report=self.root/"pdca/media_readiness.json"; before=report.read_bytes()
        review.persist_readiness(self.root); self.assertEqual(report.read_bytes(),before)
        row=json.loads(path.read_text()); row["tryOnSource"]={"state":"approved"}
        path.write_text(json.dumps(row))
        review.persist_readiness(self.root); self.assertNotEqual(report.read_bytes(),before)

    def test_symlink_source_and_symlink_file_are_not_followed(self):
        live=self.f.drafts/"live-store"
        path=self.garment("seeded","top.json",{"garmentId":"top-real","characterId":"sunlake-milkcat-ai-001"},live)
        path.unlink(); path.symlink_to(self.reference)
        with patch.dict(os.environ,{"AGENTOS_MIO_GARMENT_DATA_ROOT":str(live)}):
            r=self.audit()["observed"]["canonical_registry"]
            self.assertEqual(r["status"],"PARTIAL"); self.assertIn("INVALID_RECORD",r["issues"])
        alias=self.f.drafts/"alias"; alias.symlink_to(live,target_is_directory=True)
        with patch.dict(os.environ,{"AGENTOS_MIO_GARMENT_DATA_ROOT":str(alias)}):
            r=self.audit()["observed"]["canonical_registry"]
            self.assertIn("SOURCE_UNREADABLE",r["issues"])

    def test_bad_oversized_and_nonregular_records_are_partial_not_empty_success(self):
        path=self.garment("seeded","oversized.json",{})
        path.write_bytes(b"x"*131073)
        bad=self.garment("seeded","bad.json",{}); bad.write_text("private-invalid-data")
        fifo=path.parent/"fifo.json"; os.mkfifo(fifo)
        r=self.audit()["observed"]["canonical_registry"]
        self.assertEqual(r["status"],"PARTIAL"); self.assertEqual(r["issues"],["INVALID_RECORD"])
        self.assertNotIn("private-invalid-data",json.dumps(r))

    def test_directory_limit_and_duplicate_ids_cannot_claim_complete_scan(self):
        for i in range(129):
            self.garment("seeded",f"{i:03d}.json",{"garmentId":"duplicate","characterId":"sunlake-milkcat-ai-001"})
        r=self.audit()["observed"]["canonical_registry"]
        self.assertEqual(r["status"],"PARTIAL")
        self.assertIn("SOURCE_LIMIT",r["issues"]); self.assertIn("DUPLICATE_GARMENT_ID",r["issues"])
        self.assertEqual(r["active_persona_records_observed"],1)

    def test_catalog_diagnostics_are_bounded_and_names_never_create_links(self):
        self.garment("seeded","top.json",{"garmentId":"top-test","characterId":"sunlake-milkcat-ai-001"})
        item=assets.load(self.root/"wardrobe/catalog.json")["items"][0]
        catalog={"items":[{**item,"item_id":f"item-{i}"} for i in range(25)]}
        r=self.audit(catalog)["observed"]
        self.assertEqual(len(r["catalog_items"]),24); self.assertTrue(r["catalog_items_truncated"])
        self.assertEqual(r["catalog_item_count"],25)
        self.assertEqual(r["canonical_registry"]["linked_garments_observed"],0)

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
