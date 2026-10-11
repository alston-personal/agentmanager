import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'scripts'))
import persona_reply_intent_generator as reply
import persona_post_intent_generator as reasoning
from persona_social_executor import timestamp

DECISION={'position':'playful_only','should_reply':True,'human_required':False,
          'reason':'respond to the actual comment','reply_text':'這名字喊起來會不會太長？'}

class ReplyReasoningTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        for folder in ('pdca','ir','events'): (self.root/folder).mkdir()
        self.write('pdca/state.json',{'persona_id':'mio','cycle':4,'pending_external_actions':[]})
        self.write('ir/current.json',{'ir_id':'ir-4','revision':4,'current_self':{'voice':['自然簡短']}})
        self.write('reply_policy.json',{'default_mode':'autonomous_with_policy'})
        self.write('social_stances.json',{})
        self.write('persona_state.json',{'temporal_behavior':{'reply_latency':{'typical_minutes':[8,45]}}})
        self.now=datetime.now(timezone.utc)
        self.events=[{'type':'post.sent','object_id':'101','text':'你會幫貓取什麼名字？',
                     'timestamp':(self.now-timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%S%z')},
                     self.comment('201')]
        self.write_events()

    def comment(self,rid,**extra):
        return {'type':'reply.observed','object_id':rid,'root_post_id':'101','actor':'external',
                'author_handle':'reader','text':'我會取很長的名字',
                'timestamp':self.now.strftime('%Y-%m-%dT%H:%M:%S%z'),**extra}

    def write(self,path,value): (self.root/path).write_text(json.dumps(value,ensure_ascii=False))
    def read(self,path): return json.loads((self.root/path).read_text())
    def write_events(self):
        (self.root/'events/events.jsonl').write_text(''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in self.events))

    def execute(self,results=None,providers=(True,False,False)):
        results=results if results is not None else [subprocess.CompletedProcess('claude',0,json.dumps(DECISION),'')]
        with patch.object(sys,'argv',['reply','--persona-dir',str(self.root)]), \
             patch.object(reasoning,'discover_executor',return_value=['claude'] if providers[0] else None), \
             patch.object(reasoning,'discover_gemini_executor',return_value='gemini' if providers[1] else None), \
             patch.object(reasoning,'discover_codex_executor',return_value='codex' if providers[2] else None), \
             patch.object(reasoning.subprocess,'run',side_effect=results) as run, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(reply.main(),0)
        state=self.read('pdca/state.json')
        receipt=self.read(state['last_reply_reasoning_receipt']) if state.get('last_reply_reasoning_receipt') else {}
        return json.loads(output.getvalue()),state,receipt,run.call_args_list

    def test_platform_offsets_are_aware_utc_and_naive_is_rejected(self):
        for value in ('2026-10-11T16:11:38+0000','2026-10-12T00:11:38+0800',
                      '2026-10-12T00:11:38+08:00','2026-10-11T16:11:38Z'):
            self.assertEqual(timestamp(value),datetime(2026,10,11,16,11,38,tzinfo=timezone.utc))
        for value in ('2026-10-11T16:11:38','bad',None): self.assertIsNone(timestamp(value))

    def test_old_legacy_screenshot_and_new_unrouteable_comment_do_not_starve_valid_reply(self):
        self.events += [{'type':'reply.observed','timestamp':'2026-09-18T17:05:00+08:00','text':'舊截圖'},
                        self.comment('202',root_post_id='999',timestamp=(self.now+timedelta(minutes=1)).isoformat())]
        self.write_events()
        out,state,receipt,calls=self.execute()
        self.assertEqual(out['status'],'CANDIDATE_CREATED')
        action=state['pending_external_actions'][0]
        self.assertEqual(action['reply_to_id'],'201')
        self.assertEqual(action['root_post_id'],'101')
        self.assertEqual(receipt['selection_skipped'],{'missing_route_ids':1,'missing_root_post':1})
        prompt=calls[0].args[0][-1]
        self.assertIn('"id": "201"',prompt)
        self.assertNotIn('舊截圖',prompt)
        self.assertEqual(action['ir_source_sha256'],receipt['ir_authoring_context']['source_sha256'])
        self.assertEqual(action['reasoning_receipt_ref'],state['last_reply_reasoning_receipt'])
        delay=timestamp(action['not_before'])-self.now
        self.assertGreaterEqual(delay.total_seconds(),8*60)
        self.assertLess(delay.total_seconds(),46*60)

    def test_reply_to_sibling_does_not_mark_whole_thread_answered(self):
        self.events.append({'type':'reply.sent','parent_object_id':'202','root_post_id':'101',
                            'timestamp':(self.now+timedelta(minutes=1)).isoformat()})
        self.write_events()
        self.assertFalse(reply.already_replied(self.events,self.events[1]))
        out,state,_,_=self.execute()
        self.assertEqual(out['status'],'CANDIDATE_CREATED')
        self.assertEqual(state['pending_external_actions'][0]['reply_to_id'],'201')

    def test_exact_parent_send_is_not_repeated_even_if_event_time_is_missing(self):
        self.events.append({'type':'reply.sent','reply_to_id':'201'})
        self.write_events()
        out,_,_,calls=self.execute()
        self.assertEqual(out['status'],'NO_CANDIDATE')
        self.assertEqual(calls,[])

    def test_own_comment_with_no_actor_is_not_replied_to(self):
        self.events[1]['author_handle']='@Mio.Milkcat'
        self.events[1].pop('actor')
        self.write_events()
        out,_,_,calls=self.execute()
        self.assertEqual(out['status'],'NO_CANDIDATE')
        self.assertEqual(calls,[])

    def test_invalid_timestamp_cannot_beat_real_comment(self):
        self.events.append(self.comment('202',timestamp='unknown'))
        self.write_events()
        _,state,receipt,_=self.execute()
        self.assertEqual(state['pending_external_actions'][0]['reply_to_id'],'201')
        self.assertEqual(receipt['selection_skipped']['invalid_timestamp'],1)

    def test_source_alias_events_deduplicate_by_comment_object(self):
        event=self.comment('201')
        event['source_object_id']=event.pop('object_id')
        event['root_id']=event.pop('root_post_id')
        self.events.append(event)
        candidates,_=reply.reply_candidates(self.events,self.read('pdca/state.json'),{'source_sha256':'hash'})
        self.assertEqual(len(candidates),1)

    def test_no_reply_is_durable_and_next_comment_can_progress(self):
        self.events.append(self.comment('202',timestamp=(self.now+timedelta(seconds=1)).isoformat()))
        self.write_events()
        no_reply={**DECISION,'position':'no_reply','should_reply':False,'reply_text':''}
        out,_,receipt,_=self.execute([subprocess.CompletedProcess('claude',0,json.dumps(no_reply),'')])
        self.assertEqual(out['status'],'NO_REPLY')
        self.assertEqual(receipt['reply_id'],'202')
        out,state,_,_=self.execute()
        self.assertEqual(out['status'],'CANDIDATE_CREATED')
        self.assertEqual(state['pending_external_actions'][0]['reply_to_id'],'201')

    def test_human_reserved_decision_never_falls_through_to_send(self):
        human={**DECISION,'human_required':True}
        out,state,receipt,calls=self.execute([subprocess.CompletedProcess('claude',0,json.dumps(human),'')],providers=(True,True,True))
        self.assertEqual(out['status'],'HUMAN_REQUIRED')
        self.assertEqual(state['pending_external_actions'],[])
        self.assertEqual(len(calls),1)
        self.assertEqual(receipt['publication_acceptance'],'NOT_OBSERVED')

    def test_codex_reply_failover_preserves_thread_and_sanitizes_failures(self):
        secret='TOKEN-MUST-NOT-PERSIST'
        out,state,receipt,calls=self.execute([
            subprocess.TimeoutExpired('claude',45,stderr=secret),
            subprocess.CompletedProcess('gemini',1,'',secret+' Unsupported_Client'),
            subprocess.CompletedProcess('codex',0,json.dumps(DECISION),'')],providers=(True,True,True))
        self.assertEqual(out['status'],'CANDIDATE_CREATED')
        action=state['pending_external_actions'][0]
        self.assertEqual(action['reasoning_executor'],'codex_cli')
        self.assertEqual(action['reply_to_id'],'201')
        self.assertEqual([x['status'] for x in receipt['attempts']],['TIMEOUT','NONZERO','PASS'])
        self.assertEqual(receipt['attempts'][1]['failure_class'],'OAUTH_CLIENT_UNSUPPORTED')
        self.assertNotIn(secret,json.dumps(receipt))
        cmd=calls[-1].args[0]
        self.assertIn('read-only',cmd)
        self.assertIn('--ephemeral',cmd)

    def test_invalid_boolean_does_not_authorize_send_and_valid_provider_can_recover(self):
        out,state,receipt,_=self.execute([
            subprocess.CompletedProcess('claude',0,json.dumps({**DECISION,'should_reply':'false'}),''),
            subprocess.CompletedProcess('gemini',0,json.dumps({'response':json.dumps(DECISION)}),'')],providers=(True,True,False))
        self.assertEqual(out['status'],'CANDIDATE_CREATED')
        self.assertEqual(state['pending_external_actions'][0]['reasoning_executor'],'gemini_cli')
        self.assertEqual(receipt['attempts'][0]['status'],'INVALID_OUTPUT')

    def test_all_providers_fail_holds_comment_without_template_or_terminal_decision(self):
        out,state,receipt,_=self.execute([subprocess.TimeoutExpired('claude',45)])
        self.assertEqual(out['status'],'DEFER')
        self.assertEqual(state['pending_external_actions'],[])
        self.assertNotIn('reply_decisions',state)
        self.assertEqual(receipt['reason'],'persona_reasoning_exhausted')

    def test_missing_providers_is_durable_defer(self):
        out,state,receipt,calls=self.execute([],providers=(False,False,False))
        self.assertEqual(out['status'],'DEFER')
        self.assertEqual(receipt['attempts'],[])
        self.assertEqual(state['pending_external_actions'],[])
        self.assertEqual(calls,[])

    def test_ir_change_during_inference_holds_post_and_no_reply_decisions(self):
        for decision in (DECISION,{**DECISION,'should_reply':False}):
            with self.subTest(decision=decision):
                def changed(*args,**kwargs):
                    self.write('ir/current.json',{'ir_id':'new-ir','value':decision['should_reply']})
                    return subprocess.CompletedProcess('claude',0,json.dumps(decision),'')
                out,state,receipt,_=self.execute(changed)
                self.assertEqual(out['reason'],'current_ir_changed')
                self.assertEqual(state['pending_external_actions'],[])
                self.assertNotIn('reply_decisions',state)
                self.assertEqual(receipt['reason'],'current_ir_changed')

    def test_pending_reply_is_not_duplicated(self):
        action={'capability':'social.reply.send','status':'candidate','reply_to_id':'201'}
        self.write('pdca/state.json',{'persona_id':'mio','cycle':4,'pending_external_actions':[action]})
        out,state,_,calls=self.execute()
        self.assertEqual(out['status'],'SKIP')
        self.assertEqual(state['pending_external_actions'],[action])
        self.assertEqual(calls,[])

    def test_full_unfinished_queue_is_not_truncated(self):
        pending=[{'action_id':str(i),'capability':'other','status':'candidate'} for i in range(12)]
        self.write('pdca/state.json',{'persona_id':'mio','cycle':4,'pending_external_actions':pending})
        out,state,_,calls=self.execute()
        self.assertEqual(out['reason'],'pending_capacity')
        self.assertEqual(state['pending_external_actions'],pending)
        self.assertEqual(calls,[])

    def test_blocked_and_pending_external_actions_are_not_eviction_candidates(self):
        pending=[{'action_id':str(i),'capability':'other','status':'blocked' if i%2 else 'pending_external'} for i in range(12)]
        self.write('pdca/state.json',{'persona_id':'mio','cycle':4,'pending_external_actions':pending})
        out,state,_,calls=self.execute()
        self.assertEqual(out['reason'],'pending_capacity')
        self.assertEqual(state['pending_external_actions'],pending)
        self.assertEqual(calls,[])

    def test_missing_ir_fails_closed_without_provider_or_send(self):
        (self.root/'ir/current.json').unlink()
        out,state,receipt,calls=self.execute()
        self.assertEqual(out['reason'],'current_ir_unavailable')
        self.assertEqual(receipt['status'],'DEFER')
        self.assertEqual(state['pending_external_actions'],[])
        self.assertEqual(calls,[])

    def test_unsafe_reply_text_does_not_become_send_candidate(self):
        bad={**DECISION,'reply_text':'https://example.invalid/private'}
        out,state,receipt,_=self.execute([subprocess.CompletedProcess('claude',0,json.dumps(bad),'')])
        self.assertEqual(out['reason'],'reply_text_guard_failed')
        self.assertEqual(receipt['status'],'DEFER')
        self.assertEqual(state['pending_external_actions'],[])

    def test_changed_ir_permits_fresh_review_of_prior_no_reply(self):
        decision={**DECISION,'should_reply':False,'reply_text':''}
        self.execute([subprocess.CompletedProcess('claude',0,json.dumps(decision),'')])
        self.write('ir/current.json',{'ir_id':'ir-5','current_self':{'voice':['新的立場']}})
        out,state,_,_=self.execute()
        self.assertEqual(out['status'],'CANDIDATE_CREATED')
        self.assertEqual(state['pending_external_actions'][0]['ir_id'],'ir-5')

    def test_completed_entry_only_is_evicted_for_reply_capacity(self):
        pending=[{'action_id':str(i),'capability':'other','status':'candidate' if i else 'completed'} for i in range(12)]
        self.write('pdca/state.json',{'persona_id':'mio','cycle':4,'pending_external_actions':pending})
        out,state,_,_=self.execute()
        self.assertEqual(out['status'],'CANDIDATE_CREATED')
        self.assertEqual(len(state['pending_external_actions']),12)
        self.assertEqual(state['pending_external_actions'][:11],pending[1:])

    def test_all_unrouteable_events_are_reported_and_repeat_is_deduplicated(self):
        self.events=[{'type':'reply.observed','text':'歷史截圖','timestamp':self.now.isoformat()}]
        self.write_events()
        out,state,receipt,calls=self.execute()
        self.assertEqual(out['reason'],'no_routeable_comment')
        self.assertEqual(receipt['selection_skipped'],{'missing_route_ids':1})
        old_ref=state['last_reply_reasoning_receipt']
        _,state,_,_=self.execute()
        self.assertEqual(state['last_reply_reasoning_receipt'],old_ref)
        self.assertEqual(calls,[])

if __name__=='__main__': unittest.main()
