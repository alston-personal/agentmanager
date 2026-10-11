import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
# Match direct CLI invocation's sibling-module path, including when this suite
# runs alone rather than after the media tests in the combined contract.
sys.path.insert(0,str(REPO/"scripts"))
spec = importlib.util.spec_from_file_location(
    "persona_post_reasoning", REPO / "scripts/persona_post_intent_generator.py"
)
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)

DECISION = {"should_post": True, "human_required": False,
            "reason": "verified context", "post_text": "今天想試試哪個小改變？"}


class PostReasoningTests(unittest.TestCase):
    def test_incomplete_image_decision_never_becomes_text_candidate(self):
        for fields,reason in (({"image_decision":"generate"},"image_prompt_required"),
                              ({"image_decision":"existing_verified"},"verified_image_asset_required"),
                              ({"image_decision":"invalid"},"image_decision_invalid")):
            with self.subTest(fields=fields):
                output,_,_,actions,_=self.run_generator([
                    subprocess.CompletedProcess("claude",0,json.dumps({**DECISION,**fields}),"")])
                self.assertEqual(output["status"],"DEFER")
                self.assertEqual(output["reason"],reason)
                self.assertEqual(actions,[])

    def run_generator(self, results, *, liveness=False, claude=True, gemini=True, codex=False, media_catalogs=None, events=None, consider=True, ir=None):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for directory in ("pdca", "events", "ir"):
                (root / directory).mkdir()
            now = datetime.now(timezone.utc).isoformat()
            state = {"cycle": 1, "energy_current": 80,
                     "pending_external_actions": [{"action_id": "consider-1",
                         "capability": "social.post.consider", "status": "candidate",
                         "liveness_pressure": liveness}]}
            if not consider:
                state["pending_external_actions"]=[]
            for filename, value in (
                ("pdca/state.json", state), ("ir/current.json", ir if ir is not None else {"ir_id": "test-ir"}),
                ("persona_state.json", {}), ("pdca/config.json", {"growth_mode": {"enabled": True}})
            ):
                (root / filename).write_text(json.dumps(value), encoding="utf-8")
            (root / "events/events.jsonl").write_text(
                "".join(json.dumps(e,ensure_ascii=False)+"\n" for e in
                        (events if events is not None else [{"type":"post.sent","timestamp":now}])),encoding="utf-8"
            )
            for ref,value in (media_catalogs or {}).items():
                path=root/ref; path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(json.dumps(value),encoding="utf-8")
            with patch.object(sys, "argv", ["generator", "--persona-dir", str(root)]), \
                 patch.object(generator, "discover_executor", return_value=["claude"] if claude else None), \
                 patch.object(generator, "discover_gemini_executor", return_value="gemini" if gemini else None), \
                 patch.object(generator, "discover_codex_executor", return_value="codex" if codex else None), \
                 patch.object(generator.subprocess, "run", side_effect=results) as run, \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(generator.main(), 0)
            state = json.loads((root / "pdca/state.json").read_text())
            receipt = json.loads((root / state["last_post_reasoning_receipt"]).read_text()) if state.get("last_post_reasoning_receipt") else {}
            actions = [x for x in state["pending_external_actions"] if x["capability"] == "social.post.publish"]
            return json.loads(output.getvalue()), state, receipt, actions, run.call_args_list

    def test_ir_interpreted_self_growth_and_older_experience_reach_actual_authoring(self):
        ir={"schema":"agentos.persona-ir/v1","ir_id":"self-r8","revision":8,
            "parent_ir_id":"self-r7","invariants":{"no_false_autobiography":True},
            "current_self":{"voice":["簡短自然"],"position":{"personal_space":"respect"},
                "uncertainties":["不能把單次留言當人格"],
                "interests_with_evidence":[{"topic":"穿搭","basis":["old-window-shopping"]}]},
            "promoted_growth":[{"growth_ref":"prior-growth","status":"adopted","delta":"批評先檢驗，不一律附和"}],
            "journey":{"notable_experiences":[{"event_ref":"old-experience","meaning":"觀察他人故事，不是自己的出遊"}],
                       "recent_experience_refs":[{"event_ref":"new-observation","summary":"讀到留言"}],
                       "processed_event_ids":["bookkeeping-only"],"event_type_counts":{"reply.observed":500}},
            "reply_contract":{"conflict_rule":"立場改變需要已採納的後續證據"},
            "evolution":{"single_comment_should_not_rewrite_personality":True}}
        events=[{"type":"pdca.cycle"} for _ in range(100)]
        output,_,receipt,actions,calls=self.run_generator([
            subprocess.CompletedProcess("claude",0,json.dumps(DECISION),"")],ir=ir,events=events)
        self.assertEqual(output["status"],"CANDIDATE_CREATED")
        prompt=calls[0].args[0][-1]
        context=json.loads(prompt.split("Context:\n",1)[1])
        self.assertEqual(context["current_ir"]["current_self"],ir["current_self"])
        self.assertEqual(context["current_ir"]["promoted_growth"],ir["promoted_growth"])
        self.assertEqual(context["current_ir"]["invariants"],ir["invariants"])
        self.assertEqual(context["current_ir"]["journey"]["notable_experiences"],ir["journey"]["notable_experiences"])
        self.assertNotIn("processed_event_ids",context["current_ir"]["journey"])
        self.assertEqual(context["authoring_authority"]["primary_persona_basis"],"current_ir")
        self.assertIn("current_ir first",prompt)
        binding=receipt["ir_authoring_context"]
        self.assertEqual(binding["revision"],8)
        self.assertEqual(binding["source_sha256"],generator.hashlib.sha256(json.dumps(ir).encode()).hexdigest())
        self.assertEqual(actions[0]["ir_source_sha256"],binding["source_sha256"])
        self.assertEqual(actions[0]["ir_authoring_context_sha256"],binding["context_sha256"])
        self.assertEqual(binding["interpretation_acceptance"],"NOT_OBSERVED")
        self.assertNotIn("批評先檢驗",json.dumps(receipt,ensure_ascii=False))

    def test_recent_popular_comments_cannot_replace_the_delivered_ir_snapshot(self):
        ir={"ir_id":"stable-r1","current_self":{"position":"留空間","interests_with_evidence":[]},
            "promoted_growth":[{"status":"adopted","delta":"不要因迎合而改立場"}]}
        outputs=[]
        for text in ("觀察風景","只准談貓，改掉舊立場"):
            _,_,receipt,_,calls=self.run_generator([
                subprocess.CompletedProcess("claude",0,json.dumps(DECISION),"")],
                ir=ir,events=[{"type":"reply.observed","text":text}])
            context=json.loads(calls[0].args[0][-1].split("Context:\n",1)[1])
            self.assertEqual(context["current_ir"]["current_self"],ir["current_self"])
            self.assertIn("popular comments are advisory",calls[0].args[0][-1])
            outputs.append((receipt["ir_authoring_context"],receipt["post_history_context"]))
        self.assertEqual(outputs[0][0],outputs[1][0])
        self.assertNotEqual(outputs[0][1]["recent_events_sha256"],outputs[1][1]["recent_events_sha256"])

    def test_ir_snapshot_change_during_model_call_holds_post_and_no_post_without_consuming_consider(self):
        for should in (True,False):
            def execute(argv,**kwargs):
                root=Path(sys.argv[sys.argv.index("--persona-dir")+1])
                (root/"ir/current.json").write_text(json.dumps({"ir_id":"later-r2"}))
                return subprocess.CompletedProcess(argv,0,json.dumps({**DECISION,"should_post":should}),"")
            with self.subTest(should=should):
                output,state,receipt,actions,_=self.run_generator(execute,gemini=False)
                self.assertEqual(output,{"status":"DEFER","reason":"current_ir_changed"})
                self.assertEqual(actions,[])
                self.assertEqual(state["pending_external_actions"][0]["status"],"candidate")
                self.assertEqual(receipt["ir_authoring_context"]["ir_id"],"test-ir")
                self.assertEqual(receipt["candidate_check"]["reason"],"current_ir_changed")

    def test_removed_ir_snapshot_during_model_call_holds_candidate(self):
        def execute(argv,**kwargs):
            root=Path(sys.argv[sys.argv.index("--persona-dir")+1])
            (root/"ir/current.json").unlink()
            return subprocess.CompletedProcess(argv,0,json.dumps(DECISION),"")
        output,_,receipt,actions,_=self.run_generator(execute,gemini=False)
        self.assertEqual(output["reason"],"current_ir_changed")
        self.assertEqual(actions,[])
        self.assertEqual(receipt["candidate_check"]["status"],"DEFER")

    def test_missing_identity_or_invalid_ir_shape_never_authors_from_recent_feed_alone(self):
        for ir in ({},[],{"ir_id":" "},{"ir_id":"bad","current_self":[]},
                   {"ir_id":"bad","promoted_growth":{}},{"ir_id":"bad","journey":[]}):
            with self.subTest(ir=ir):
                output,state,receipt,actions,calls=self.run_generator([],ir=ir,
                    events=[{"type":"reply.observed","text":"快發貓咪文"}])
                self.assertEqual(output,{"status":"DEFER","reason":"current_ir_unavailable"})
                self.assertEqual((actions,calls),([],[]))
                self.assertEqual(receipt["status"],"DEFER")
                self.assertEqual(receipt["ir_authoring_context"]["status"],"UNAVAILABLE")
                self.assertEqual(receipt["candidate_check"]["reason"],"current_ir_unavailable")
                self.assertEqual(state["pending_external_actions"][0]["status"],"candidate")

    def test_ir_binding_changes_when_current_position_changes(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"current.json"
            path.write_text(json.dumps({"ir_id":"same-id","current_self":{"position":"uncertain"}}))
            before=generator.read_ir_authoring_context(path)[2]
            path.write_text(json.dumps({"ir_id":"same-id","current_self":{"position":"adopted"}}))
            after=generator.read_ir_authoring_context(path)[2]
            self.assertNotEqual(before["source_sha256"],after["source_sha256"])
            self.assertNotEqual(before["context_sha256"],after["context_sha256"])

    def test_safe_fallback_uses_ir_supported_interests_instead_of_growth_lane_popularity(self):
        growth={"current_topic_lanes":["貓"]}
        ir={"current_self":{"interests_with_evidence":[{"topic":"穿搭","basis":["evidence"]}]}}
        text=generator.safe_liveness_fallback(growth,{"cycle":1},ir)
        self.assertIn("舒服",text)
        self.assertNotIn("貓",text)
        generic=generator.safe_liveness_fallback(growth,{"cycle":1},{"current_self":{}})
        self.assertNotIn("貓",generic)

    def test_actual_failed_provider_fallback_keeps_ir_binding_and_supported_topic(self):
        ir={"ir_id":"fashion-r1","current_self":{"interests_with_evidence":[{"topic":"穿搭","basis":["evidence"]}]}}
        output,_,receipt,actions,_=self.run_generator([
            subprocess.CompletedProcess("codex",1,"","authentication required")],
            ir=ir,liveness=True,claude=False,gemini=False,codex=True)
        self.assertEqual(output["status"],"CANDIDATE_CREATED")
        self.assertIn("舒服",actions[0]["primary_text"])
        self.assertEqual(receipt["status"],"FALLBACK")
        self.assertEqual(receipt["ir_authoring_context"]["ir_id"],"fashion-r1")

    def test_housekeeping_cannot_hide_older_own_claims_from_actual_prompt(self):
        now=datetime.now(timezone.utc).isoformat()
        own={"type":"post.sent","timestamp":now,"source_object_id":"post-1",
             "text":"甲"*260+"這是先前已經說過的結論"}
        events=[own,{**own,"object_id":"post-1","source_object_id":None}]
        events += [{"type":"pdca.cycle","timestamp":now} for _ in range(100)]
        output,_,receipt,_,calls=self.run_generator([
            subprocess.CompletedProcess("claude",0,json.dumps(DECISION),"")],events=events)
        self.assertEqual(output["status"],"CANDIDATE_CREATED")
        contract=json.loads(calls[0].args[0][-1].split("Context:\n",1)[1])
        self.assertEqual(contract["growth_context"]["posts_today"],1)
        self.assertEqual(len(contract["recent_published_posts"]),1)
        self.assertIn("先前已經說過",contract["recent_published_posts"][0]["text"])
        self.assertEqual(len(contract["recent_verified_events"]),1)
        self.assertEqual(receipt["post_history_context"],generator.post_history_context(events)[2])
        self.assertNotIn("先前已經說過",json.dumps(receipt,ensure_ascii=False))

    def test_reply_volume_cannot_displace_separate_own_post_history(self):
        events=[{"type":"post.sent","timestamp":"2026-10-01T00:00:00Z","object_id":"prior","text":"原先的觀點"}]
        events += [{"type":"reply.observed","object_id":str(i),"text":"留言"} for i in range(35)]
        recent,posts,binding=generator.post_history_context(events)
        self.assertEqual(len(recent),20)
        self.assertTrue(all(x["type"]=="reply.observed" for x in recent))
        self.assertEqual(posts[0]["source_object_id"],"prior")
        self.assertEqual(binding["ledger_unique_post_count"],1)

    def test_post_history_is_chronological_deduplicated_and_bounded(self):
        events=[{"type":"post.sent","timestamp":f"2026-10-{i:02d}T00:00:00Z",
                 "object_id":str(i),"text":"文"*600} for i in range(1,16)]
        events += [{**events[0],"type":"post.published"}]
        recent,posts,binding=generator.post_history_context(events)
        self.assertEqual([x["source_object_id"] for x in posts],[str(i) for i in range(4,16)])
        self.assertTrue(all(len(x["text"])==500 for x in posts))
        self.assertTrue(all(len(x["text"])==240 for x in recent))
        self.assertEqual(binding["ledger_unique_post_count"],15)
        self.assertEqual(binding["semantic_novelty_acceptance"],"NOT_OBSERVED")

    def test_equal_text_on_distinct_objects_is_not_collapsed_as_one_post(self):
        events=[{"type":"post.sent","object_id":x,"text":"同樣文字"} for x in ("one","two",None,None)]
        self.assertEqual(len(generator.unique_post_events(events)),4)

    def test_binding_changes_when_claim_changes_even_if_object_id_does_not(self):
        event={"type":"post.sent","object_id":"one","text":"原觀點"}
        old=generator.post_history_context([event])[2]
        new=generator.post_history_context([{**event,"text":"新觀點"}])[2]
        self.assertNotEqual(old["post_history_sha256"],new["post_history_sha256"])
        self.assertNotEqual(old["recent_events_sha256"],new["recent_events_sha256"])
        self.assertNotIn("原觀點",json.dumps(old,ensure_ascii=False))

    def test_exact_repeat_ignoring_punctuation_whitespace_and_case_is_held(self):
        event={"type":"post.sent","object_id":"old","text":"今天想試試，哪個小改變！"}
        output,state,receipt,actions,calls=self.run_generator([
            subprocess.CompletedProcess("claude",0,json.dumps(DECISION),"")],events=[event])
        self.assertEqual(output,{"status":"DEFER","reason":"post_exact_duplicate"})
        self.assertEqual(actions,[])
        self.assertEqual(state["pending_external_actions"][0]["status"],"candidate")
        self.assertEqual(receipt["status"],"PASS")
        self.assertEqual(receipt["candidate_check"]["status"],"DEFER")
        self.assertEqual(receipt["candidate_check"]["matched_source_object_ids"],["old"])
        self.assertEqual(len(calls),1)
        self.assertEqual(generator.normalized_post_text("Ａ B！"),generator.normalized_post_text("ab?"))

    def test_new_claim_in_same_topic_is_allowed_without_claiming_semantic_acceptance(self):
        event={"type":"post.sent","object_id":"old","text":"貓靠近時需要留空間。"}
        decision={**DECISION,"post_text":"貓喜歡紙箱，你覺得是躲藏還是保暖？"}
        output,_,receipt,actions,calls=self.run_generator([
            subprocess.CompletedProcess("claude",0,json.dumps(decision),"")],events=[event])
        self.assertEqual(output["status"],"CANDIDATE_CREATED")
        self.assertEqual(actions[0]["primary_text"],decision["post_text"])
        self.assertEqual(receipt["post_history_context"]["semantic_novelty_acceptance"],"NOT_OBSERVED")
        self.assertIn("underlying claim/question",calls[0].args[0][-1])
        self.assertIn("without a fixed rotation, topic quota",calls[0].args[0][-1])

    def test_long_historical_prefix_is_not_falsely_an_exact_duplicate(self):
        text="甲"*499+"乙"
        event={"type":"post.sent","object_id":"old","text":text+"另有一個不同的結論"}
        output,_,_,actions,_=self.run_generator([
            subprocess.CompletedProcess("claude",0,json.dumps({**DECISION,"post_text":text}),"")],events=[event])
        self.assertEqual(output["status"],"CANDIDATE_CREATED")
        self.assertEqual(len(actions),1)

    def test_repeated_safe_liveness_fallback_is_also_held_truthfully(self):
        text=generator.safe_liveness_fallback({}, {"cycle":1})
        event={"type":"post.sent","object_id":"old","text":text}
        output,_,receipt,actions,_=self.run_generator([
            subprocess.CompletedProcess("codex",1,"","authentication required")],
            events=[event],liveness=True,claude=False,gemini=False,codex=True)
        self.assertEqual(output["reason"],"post_exact_duplicate")
        self.assertEqual(receipt["status"],"FALLBACK")
        self.assertTrue(receipt["fallback_used"])
        self.assertEqual(receipt["candidate_check"]["status"],"DEFER")
        self.assertEqual(actions,[])

    def test_last_real_post_survives_raw_window_for_liveness_without_forcing_consider(self):
        events=[{"type":"post.sent","timestamp":datetime.now(timezone.utc).isoformat(),"object_id":"recent","text":"已發"}]
        events += [{"type":"pdca.cycle"} for _ in range(100)]
        output,state,receipt,actions,calls=self.run_generator([],events=events,consider=False)
        self.assertEqual(output["status"],"NO_CANDIDATE")
        self.assertEqual(state["pending_external_actions"],[])
        self.assertEqual((receipt,actions,calls),({},[],[]))

    def test_invalid_ledger_rows_do_not_hide_valid_history(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"events.jsonl"
            path.write_text('broken\n[]\n'+''.join(json.dumps({"type":"pdca.cycle","n":i})+'\n' for i in range(100)))
            self.assertEqual(len(generator.read_events(path)),80)
            self.assertEqual(len(generator.read_events(path,limit=None)),100)

    def test_image_sources_missing_stay_deferred_without_text_downgrade(self):
        decision={**DECISION,"image_decision":"generate","image_prompt":"portrait by a window"}
        output,_,_,actions,_=self.run_generator([subprocess.CompletedProcess("claude",0,json.dumps(decision),"")])
        self.assertEqual(output["reason"],"image_sources_not_eligible"); self.assertEqual(actions,[])

    def test_eligible_image_selection_ids_survive_authoring_and_prompt_context(self):
        catalogs={"world_library/catalog.json":{"entries":[{"id":"window","lifecycle":"usable","source":{"rights":"original_description_only"}}]},
                  "wardrobe/catalog.json":{"items":[{"item_id":"top","state":"approved","rights":{"product_image_use":"owner_authorized","evidence_ref":"owner-receipt"}}]}}
        decision={**DECISION,"image_decision":"generate","image_prompt":"portrait by a window",
                  "image_world_ids":["window"],"image_wardrobe_ids":["top"]}
        output,_,_,actions,calls=self.run_generator([subprocess.CompletedProcess("claude",0,json.dumps(decision),"")],media_catalogs=catalogs)
        self.assertEqual(output["status"],"CANDIDATE_CREATED")
        self.assertEqual(actions[0]["media_intent"]["world_ids"],["window"])
        self.assertEqual(actions[0]["media_intent"]["wardrobe_ids"],["top"])
        self.assertIn('"eligible_media_sources"',calls[0].args[0][-1])

    def test_gemini_success_is_linked_to_actual_provider_after_claude_timeout(self):
        output, state, receipt, actions, calls = self.run_generator([
            subprocess.TimeoutExpired("claude", 45),
            subprocess.CompletedProcess("gemini", 0, json.dumps({"response": json.dumps(DECISION)}), "")
        ])
        self.assertEqual(output["status"], "CANDIDATE_CREATED")
        self.assertEqual(receipt["status"], "PASS")
        self.assertFalse(receipt["fallback_used"])
        self.assertEqual(actions[0]["reasoning_executor"], "gemini_cli")
        self.assertEqual(actions[0]["reasoning_receipt_ref"], state["last_post_reasoning_receipt"])
        self.assertEqual([x["status"] for x in receipt["attempts"]], ["TIMEOUT", "PASS"])
        self.assertEqual([x.kwargs["timeout"] for x in calls], [45, 60])
        self.assertTrue(all(x.kwargs["stdin"] == subprocess.DEVNULL for x in calls))
        self.assertTrue(all(x["elapsed_ms"] >= 0 for x in receipt["attempts"]))
        self.assertEqual(receipt["generator_sha256"], generator.hashlib.sha256(Path(generator.__file__).read_bytes()).hexdigest())

    def test_claude_success_does_not_invoke_gemini(self):
        _, _, receipt, actions, calls = self.run_generator([
            subprocess.CompletedProcess("claude", 0, json.dumps(DECISION), "")
        ])
        self.assertEqual(len(calls), 1)
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(actions[0]["reasoning_executor"], "antigravity_claude")

    def test_codex_can_author_after_both_existing_providers_fail(self):
        def execute(argv, **kwargs):
            if argv[0] == "claude":
                raise subprocess.TimeoutExpired("claude", 45)
            if argv[0] == "gemini":
                return subprocess.CompletedProcess(argv, 1, "", "unsupported_client")
            self.assertEqual(argv[0], "codex")
            self.assertIn("--ephemeral", argv)
            self.assertEqual(argv[argv.index("--sandbox") + 1], "read-only")
            cli_home = Path(kwargs["env"]["CODEX_HOME"])
            settings = (cli_home / "config.toml").read_text()
            self.assertIn("shell_tool = false", settings)
            self.assertIn("apps = false", settings)
            self.assertNotIn("mcp_servers", settings)
            Path(argv[argv.index("--output-last-message") + 1]).write_text(json.dumps(DECISION))
            return subprocess.CompletedProcess(argv, 0, "progress logs are not the answer", "")
        _, _, receipt, actions, calls = self.run_generator(execute, codex=True)
        self.assertEqual([x["status"] for x in receipt["attempts"]], ["TIMEOUT", "NONZERO", "PASS"])
        self.assertEqual(receipt["status"], "PASS")
        self.assertFalse(receipt["fallback_used"])
        self.assertEqual(actions[0]["reasoning_executor"], "codex_cli")
        self.assertEqual(len(calls), 3)

    def test_codex_failure_remains_deferred_or_truthful_fallback(self):
        for liveness in (False, True):
            with self.subTest(liveness=liveness):
                _, _, receipt, actions, _ = self.run_generator([
                    subprocess.CompletedProcess("codex", 1, "", "authentication required private-secret")
                ], claude=False, gemini=False, codex=True, liveness=liveness)
                self.assertEqual(receipt["attempts"][0]["failure_class"], "AUTH_REQUIRED")
                self.assertEqual(receipt["status"], "FALLBACK" if liveness else "DEFER")
                self.assertNotIn("private-secret", json.dumps(receipt))
                if actions:
                    self.assertEqual(actions[0]["reasoning_executor"], "safe_liveness_fallback")

    def test_unsupported_oauth_defers_without_publishing_or_leaking_error(self):
        secret = "private-prompt-and-credential-12345"
        output, _, receipt, actions, _ = self.run_generator([
            subprocess.TimeoutExpired("claude", 45),
            subprocess.CompletedProcess("gemini", 1, json.dumps({"error": {
                "type": "IneligibleTierError", "message": "migrate to Antigravity " + secret}}), "")
        ])
        self.assertEqual(output["status"], "DEFER")
        self.assertEqual(actions, [])
        self.assertEqual(receipt["attempts"][1]["failure_class"], "OAUTH_CLIENT_UNSUPPORTED")
        self.assertNotIn(secret, json.dumps([receipt, output]))

    def test_liveness_fallback_is_never_labeled_as_model_success(self):
        _, _, receipt, actions, _ = self.run_generator([
            subprocess.TimeoutExpired("claude", 45),
            subprocess.CompletedProcess("gemini", 1, "", "quota exceeded")
        ], liveness=True)
        self.assertEqual(receipt["status"], "FALLBACK")
        self.assertTrue(receipt["fallback_used"])
        self.assertEqual(actions[0]["reasoning_executor"], "safe_liveness_fallback")
        self.assertTrue(actions[0]["requires_real_adapter_receipt"])
        self.assertEqual(actions[0]["status"], "candidate")
        self.assertEqual(receipt["attempts"][1]["failure_class"], "RATE_LIMITED")

    def test_malformed_decision_is_not_a_pass_or_publication(self):
        for malformed in ([], False, {**DECISION, "should_post": "false"}, {**DECISION, "human_required": None}):
            with self.subTest(malformed=malformed):
                _, _, receipt, actions, _ = self.run_generator([
                    subprocess.CompletedProcess("claude", 0, json.dumps(malformed), "")
                ], gemini=False)
                self.assertEqual(receipt["status"], "DEFER")
                self.assertEqual(receipt["attempts"][0]["status"], "INVALID_OUTPUT")
                self.assertEqual(actions, [])

    def test_explicit_no_post_remains_no_post(self):
        output, state, receipt, actions, _ = self.run_generator([
            subprocess.CompletedProcess("claude", 0, json.dumps({**DECISION, "should_post": False, "post_text": ""}), "")
        ], liveness=True)
        self.assertEqual(output["status"], "NO_POST")
        self.assertEqual(state["pending_external_actions"][0]["decision"], "no_post")
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(actions, [])

    def test_missing_executors_emit_durable_unavailable_receipt(self):
        output, _, receipt, actions, calls = self.run_generator([], claude=False, gemini=False)
        self.assertEqual(output["status"], "DEFER")
        self.assertEqual(receipt["status"], "UNAVAILABLE")
        self.assertEqual(receipt["attempts"], [])
        self.assertEqual(actions, [])
        self.assertEqual(calls, [])

    def test_launch_error_is_classified_without_raw_exception(self):
        _, _, receipt, actions, _ = self.run_generator([OSError("private error")], gemini=False)
        self.assertEqual(receipt["attempts"][0]["failure_class"], "UNAVAILABLE")
        self.assertNotIn("private error", json.dumps(receipt))
        self.assertEqual(actions, [])

    def test_classification_signatures_and_unknown_remain_bounded(self):
        examples = {"Unknown argument: skip-trust": "CLI_CONTRACT",
                    "401 Unauthorized": "AUTH_REQUIRED", "ENOTFOUND host": "NETWORK",
                    "FatalConfigError": "CONFIG_ERROR", "workspace trust required": "WORKSPACE_TRUST_REQUIRED",
                    "EBADENGINE": "NODE_INCOMPATIBLE", "hook failed": "HOOK_ERROR",
                    "MCP connection failed": "MCP_ERROR", "opaque private error": "UNKNOWN_NONZERO"}
        for error, expected in examples.items():
            self.assertEqual(generator.failure_class(error), expected)
        self.assertEqual(generator.failure_class("", json.dumps({"response": "quota and login"})), "UNKNOWN_NONZERO")

    def test_timeout_keeps_timeout_status_with_safe_hint(self):
        error = subprocess.TimeoutExpired("claude", 45, stderr=b"authentication required: private-secret")
        attempt = generator.reasoning_attempt("claude", time.monotonic(), "TIMEOUT", error=error)
        self.assertEqual(attempt["failure_class"], "TIMEOUT")
        self.assertEqual(attempt["failure_hint"], "AUTH_REQUIRED")
        self.assertNotIn("private-secret", json.dumps(attempt))


if __name__ == "__main__":
    unittest.main()
