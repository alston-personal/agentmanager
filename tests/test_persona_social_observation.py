import importlib.util
import json
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, REPO / 'scripts' / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class ObservationContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.social = module('persona_social_executor')
        self.tick = module('persona_pdca_tick')
        for directory in ('pdca', 'events', 'ir'):
            (self.root / directory).mkdir()
        self.action = {'action_id': 'mio-pdca-c10-social-observe', 'cycle': 10,
                       'capability': 'social.threads.observe', 'status': 'candidate'}
        self.state = {'status': 'RUNNING', 'cycle': 10, 'energy_current': 72,
                      'pending_external_actions': [self.action]}
        self.write('pdca/state.json', self.state)
        self.write('pdca/config.json', {'enabled': True, 'timezone': 'Asia/Taipei',
                                      'persona_id': 'mio'})
        self.write('persona_state.json', {'energy': {'current': 72},
                                        'autonomy': {'public_conversation': 'autonomous_with_policy'}})
        self.write('ir/current.json', {'ir_id': 'test-ir'})
        (self.root / 'events/events.jsonl').write_text('')
        self.env = self.root / 'env'
        self.env.write_text('AGENTOS_SOCIAL_PRODUCTS_JSON=' + json.dumps(
            {'galaxy': {'api_key': 'private-product-key'}}))
        self.creds = self.root / 'creds.json'
        self.creds.write_text(json.dumps({'bindings': {'galaxy:threads:persona:123': {
            'product_id': 'galaxy', 'platform': 'threads', 'username': 'mio.milkcat',
            'auth_profile': 'persona', 'provider_account_id': '123'}}}))
        self.out = self.root / 'pdca/social_receipts/test.json'
        self.calls = []
        self.posts = [{'id': '101', 'has_replies': False}]
        self.replies = []
        self.now = datetime.now(timezone.utc)

    def write(self, path, value):
        (self.root / path).write_text(json.dumps(value))

    def read(self, path):
        return json.loads((self.root / path).read_text())

    def adapter(self, path, payload, headers):
        self.assertEqual(path, '/v1/social/status')
        self.assertIn(payload['operation'], ('post.read', 'replies.read'))
        self.calls.append(payload)
        return 200, {'ok': True, 'receipt_id': 'provider-receipt', 'result': {
            'items': self.posts if payload['operation'] == 'post.read' else self.replies}}

    def execute(self, adapter=None):
        with patch.object(self.social, 'ENV', self.env), patch.object(self.social, 'CREDS', self.creds), \
             patch.object(self.social, 'post', adapter or self.adapter), \
             patch.object(sys, 'argv', ['social', '--persona-dir', str(self.root),
                                      '--receipt-out', str(self.out)]):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(self.social.main(), 0)
        return json.loads(self.out.read_text())

    def reply(self, rid='201', **extra):
        return {'id': rid, 'username': 'reader', 'text': '測試留言',
                'timestamp': (self.now - timedelta(minutes=5)).isoformat(), **extra}

    def creative_tick(self, state=None, phase='afternoon', config=None, selected='content_ideation'):
        self.write('pdca/state.json',state or {**self.state,'pending_external_actions':[]})
        if config is not None: self.write('pdca/config.json',config)
        with patch.object(self.tick,'local_phase',return_value=phase), \
             patch.object(self.tick.random.Random,'choices',return_value=[selected]), \
             patch.object(sys,'argv',['tick','--persona-dir',str(self.root),
                                     '--receipt-out',str(self.root/'tick.json')]):
            with contextlib.redirect_stdout(io.StringIO()): self.assertEqual(self.tick.main(),0)
        return self.read('tick.json')

    def test_due_read_keeps_creative_choice_and_both_intents(self):
        receipt=self.creative_tick()
        self.assertEqual(receipt['plan']['selected_intent'],'content_ideation')
        self.assertEqual(receipt['do']['status'],'completed_internal')
        self.assertTrue(receipt['plan']['social_observation']['due'])
        pending=self.read('pdca/state.json')['pending_external_actions']
        self.assertEqual([x['capability'] for x in pending],
                         ['social.post.consider','social.threads.observe'])
        self.assertEqual(receipt['act']['observation_candidate']['cycle'],11)
        self.assertFalse(receipt['check']['external_action_completed'])
        self.assertAlmostEqual(receipt['check']['energy_after'],68.8)

    def test_successful_read_is_scheduled_before_next_heartbeat_would_expire(self):
        state={**self.state,'pending_external_actions':[], 'last_social_observation':{
            'read_status':'PASS','receipt_ref':'pdca/social_receipts/pass.json',
            'observed_at':(self.now-timedelta(minutes=10)).isoformat()}}
        plan=self.tick.social_observation_plan({'heartbeat_minutes':60},state,'afternoon',72,self.now)
        self.assertTrue(plan['due'])
        plan=self.tick.social_observation_plan({'heartbeat_minutes':60,
            'social_observation':{'max_age_minutes':120}},state,'afternoon',72,self.now)
        self.assertFalse(plan['due'])
        self.assertEqual(plan['reason'],'successful_read_fresh')

    def test_due_planning_respects_recovery_and_periodic_policy(self):
        for phase,energy in [('sleep',72),('rest',72),('afternoon',14)]:
            with self.subTest(phase=phase,energy=energy):
                plan=self.tick.social_observation_plan({},self.state,phase,energy,self.now)
                self.assertEqual(plan['reason'],'recovery_window')
                self.assertFalse(plan['due'])
        for interval in [None,False,0,-1,'60',float('nan'),float('inf')]:
            with self.subTest(interval=interval):
                plan=self.tick.social_observation_plan({'social_observation':{'max_age_minutes':interval}},
                    self.state,'afternoon',72,self.now)
                self.assertEqual(plan['reason'],'invalid_observation_policy')
        plan=self.tick.social_observation_plan({'social_observation':{'enabled':False}},
            self.state,'afternoon',72,self.now)
        self.assertEqual(plan['reason'],'periodic_observation_disabled')

    def test_existing_read_or_blocked_incident_prevents_supplemental_duplicate(self):
        for status in ['candidate','in_progress','blocked']:
            with self.subTest(status=status):
                state={**self.state,'pending_external_actions':[{**self.action,'status':status}]}
                receipt=self.creative_tick(state)
                reads=[x for x in self.read('pdca/state.json')['pending_external_actions']
                       if x['capability']=='social.threads.observe']
                self.assertEqual(len(reads),1)
                self.assertFalse(receipt['plan']['social_observation']['due'])

    def test_future_naive_failed_or_unproven_summary_does_not_suppress_read(self):
        for summary in [
            {'read_status':'PASS','receipt_ref':'pass','observed_at':(self.now+timedelta(hours=1)).isoformat()},
            {'read_status':'PASS','receipt_ref':'pass','observed_at':self.now.replace(tzinfo=None).isoformat()},
            {'read_status':'FAILED','receipt_ref':'failed','observed_at':self.now.isoformat()},
            {'read_status':'PASS','observed_at':self.now.isoformat()}]:
            with self.subTest(summary=summary):
                state={**self.state,'pending_external_actions':[],'last_social_observation':summary}
                self.assertTrue(self.tick.social_observation_plan({},state,'afternoon',72,self.now)['due'])

    def test_due_observation_precedes_write(self):
        writes=[{'action_id':f'write-{i}','cycle':10,'capability':'social.post.publish',
                 'status':'candidate','primary_text':'not sent'} for i in range(3)]
        self.creative_tick({**self.state,'pending_external_actions':writes})
        pending=self.read('pdca/state.json')['pending_external_actions']
        self.assertEqual(len(pending),5)
        self.assertEqual(pending[-1]['capability'],'social.threads.observe')
        result=self.execute()
        self.assertEqual(result['capability'],'social.threads.observe')
        self.assertFalse(result['write_performed'])
        self.assertTrue(all(x['operation'] in ('post.read','replies.read') for x in self.calls))

    def test_full_live_queue_is_not_evicted_for_observation(self):
        pending=[{'action_id':f'write-{i}','cycle':10,'capability':'social.post.publish',
                  'status':'candidate'} for i in range(12)]
        receipt=self.creative_tick({**self.state,'pending_external_actions':pending},selected='reflect')
        self.assertEqual(self.read('pdca/state.json')['pending_external_actions'],pending)
        self.assertEqual(receipt['plan']['social_observation']['reason'],'pending_capacity')
        self.assertFalse(receipt['plan']['social_observation']['queued'])
        self.assertNotIn('social_observation_energy_cost',receipt['do'])
        pending[0]['status']='completed'
        receipt=self.creative_tick({**self.state,'pending_external_actions':pending},selected='reflect')
        saved=self.read('pdca/state.json')['pending_external_actions']
        self.assertEqual([x['action_id'] for x in saved[:-1]],
                         [x['action_id'] for x in pending[1:]])
        self.assertTrue(receipt['plan']['social_observation']['queued'])

    def test_tick_queues_read_and_internal_executor_delegates(self):
        with patch.object(self.tick, 'local_phase', return_value='idle'), \
             patch.object(self.tick.random.Random, 'choices', return_value=['observe']), \
             patch.object(sys, 'argv', ['tick', '--persona-dir', str(self.root),
                                      '--receipt-out', str(self.root / 'tick.json')]):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(self.tick.main(), 0)
        receipt = self.read('tick.json')
        self.assertEqual(receipt['do']['status'], 'pending_external')
        self.assertFalse(receipt['check']['internal_action_verified'])
        self.assertFalse(receipt['check']['external_action_completed'])
        self.assertEqual(len(self.read('pdca/state.json')['pending_external_actions']), 1)
        internal = module('persona_internal_activity_executor')
        with patch.object(sys, 'argv', ['internal', '--persona-dir', str(self.root)]):
            with contextlib.redirect_stdout(io.StringIO()):
                internal.main()
        events = [json.loads(row) for row in (self.root / 'events/events.jsonl').read_text().splitlines()]
        self.assertEqual(events[-1]['type'], 'pdca.activity.delegated')

    def test_no_reply_pass_requires_real_reads_including_false_indicator(self):
        receipt = self.execute()
        self.assertEqual([x['operation'] for x in self.calls], ['post.read', 'replies.read'])
        self.assertEqual(receipt['result'], 'NO_NEW_REPLIES')
        self.assertEqual(receipt['read_status'], 'PASS')
        state = self.read('pdca/state.json')
        self.assertEqual(state['pending_external_actions'][0]['status'], 'completed')
        self.assertEqual(receipt['cycle'], 10)
        self.assertEqual(receipt['action_id'], self.action['action_id'])
        self.assertEqual(receipt['fresh_replies'], 0)
        self.assertFalse(receipt['write_performed'])

    def test_new_comment_creates_review_and_second_observe_does_not_duplicate(self):
        self.replies = [self.reply()]
        first = self.execute()
        self.assertEqual(first['fresh_replies'], 1)
        state = self.read('pdca/state.json')
        review = state['pending_external_actions'][1]
        self.assertEqual(review['capability'], 'social.reply.review')
        self.assertEqual(review['reply_ids'], ['201'])
        self.assertEqual(review['observation_receipt_ref'], 'pdca/social_receipts/test.json')
        state['pending_external_actions'][0]['status'] = 'candidate'
        self.write('pdca/state.json', state)
        self.assertEqual(self.execute()['fresh_replies'], 0)
        self.assertEqual(len((self.root / 'events/events.jsonl').read_text().splitlines()), 1)
        self.assertEqual(len(self.read('pdca/state.json')['pending_external_actions']), 2)

    def test_self_old_future_and_invalid_timestamp_replies_are_not_new_candidates(self):
        self.replies = [self.reply('201', is_reply_owned_by_me=True),
                        self.reply('202', username='mio.milkcat'),
                        self.reply('203', timestamp=(self.now - timedelta(days=3)).isoformat()),
                        self.reply('204', timestamp='malformed'),
                        self.reply('205', timestamp=(self.now + timedelta(days=1)).isoformat())]
        self.assertEqual(self.execute()['fresh_replies'], 0)
        self.assertEqual((self.root / 'events/events.jsonl').read_text(), '')

    def test_partial_read_failure_does_not_advance_cursor_or_emit_comment(self):
        self.posts = [{'id': '101'}, {'id': '102'}]
        self.replies = [self.reply()]
        def failure(path, payload, headers):
            if payload.get('object_id') == '102':
                return 500, {'ok': False, 'error': 'private-product-key'}
            return self.adapter(path, payload, headers)
        receipt = self.execute(failure)
        self.assertEqual(receipt['status'], 'BLOCKED')
        self.assertFalse(receipt['source_receipts_verified'])
        state = self.read('pdca/state.json')
        self.assertNotIn('social_observation_cursor', state)
        self.assertEqual(state['status'], 'RUNNING')
        self.assertEqual((self.root / 'events/events.jsonl').read_text(), '')
        incidents = list((self.root / 'pdca/incidents').glob('*.json'))
        self.assertEqual(len(incidents), 1)
        self.assertEqual(json.loads(incidents[0].read_text())['status'], 'open')
        self.assertNotIn('private-product-key', self.out.read_text() + incidents[0].read_text())

    def test_malformed_success_envelope_is_blocked(self):
        self.assertEqual(self.execute(lambda *args: (200, {'ok': True, 'result': {}}))['status'], 'BLOCKED')

    def test_missing_explicit_ok_is_blocked(self):
        self.assertEqual(self.execute(lambda *args: (200, {'result': {'items': []}}))['status'], 'BLOCKED')

    def test_runtime_timeout_is_blocked_without_advancing_cursor(self):
        def timeout(*args):
            raise TimeoutError('private-product-key')
        self.assertEqual(self.execute(timeout)['status'], 'BLOCKED')
        self.assertNotIn('social_observation_cursor', self.read('pdca/state.json'))

    def test_configuration_failure_produces_sanitized_blocked_receipt(self):
        self.env.unlink()
        self.assertEqual(self.execute()['status'], 'BLOCKED')
        self.assertEqual(self.calls, [])

    def test_disabled_pdca_never_reads(self):
        self.write('pdca/config.json', {'enabled': False})
        self.assertEqual(self.execute()['status'], 'BLOCKED')
        self.assertEqual(self.calls, [])

    def test_binding_rejects_other_product_and_ambiguous_accounts(self):
        creds = json.loads(self.creds.read_text())
        row = dict(next(iter(creds['bindings'].values())))
        row['product_id'] = 'content-publish'
        self.assertEqual(self.social.find_binding({'bindings': {'foreign': row}}, 'mio.milkcat'), (None, None))
        row['product_id'] = 'galaxy'
        row['provider_account_id'] = '456'
        creds['bindings']['second'] = row
        self.assertEqual(self.social.find_binding(creds, 'mio.milkcat'), (None, None))

    def test_social_runner_persists_blocked_read_when_metrics_fails(self):
        fixture=self.root/'fixture'
        persona=fixture/'personas/sunlake-milkcat'
        (persona/'pdca').mkdir(parents=True)
        (persona/'events').mkdir()
        (persona/'pdca/state.json').write_text('{}')
        (persona/'events/events.jsonl').write_text('')
        fakebin=self.root/'fakebin'
        fakebin.mkdir()
        def stub(name, code):
            path=fakebin/name
            path.write_text('#!/usr/bin/env python3\n'+code)
            path.chmod(0o755)
            return str(path)
        stub('id','print("1001")\n')
        stub('flock','')
        stub('gh',"import os,sys,shutil\nif sys.argv[1:3]==['repo','clone']: shutil.copytree(os.environ['MIO_TEST_FIXTURE'],sys.argv[4],dirs_exist_ok=True)\n")
        stub('git',"import os,sys,shutil\nif sys.argv[1:4]==['diff','--cached','--quiet']: sys.exit(1)\nif 'push' in sys.argv: shutil.copytree(os.getcwd(),os.environ['MIO_TEST_PUSHED'])\n")
        executor=stub('social.py',"import json,sys\nfrom pathlib import Path\na=sys.argv; root=Path(a[a.index('--persona-dir')+1]); out=Path(a[a.index('--receipt-out')+1]); out.write_text(json.dumps({'ok':False,'status':'BLOCKED','capability':'social.threads.observe'})); (root/'pdca/incidents').mkdir(); (root/'pdca/incidents/test.json').write_text('{\"status\":\"open\"}')\n")
        noop=stub('noop.py','')
        metrics=stub('metrics.py','raise SystemExit(1)\n')
        pushed=self.root/'pushed'
        env={**os.environ,'PATH':str(fakebin)+os.pathsep+os.environ['PATH'],
             'AGENTOS_PERSONA_SOCIAL_EXECUTOR':executor,
             'AGENTOS_PERSONA_REPLY_INTENT_GENERATOR':noop,
             'AGENTOS_PERSONA_POST_INTENT_GENERATOR':noop,
             'AGENTOS_PERSONA_GROWTH_METRICS':metrics,
             'MIO_TEST_FIXTURE':str(fixture),'MIO_TEST_PUSHED':str(pushed)}
        result=subprocess.run(['bash',str(REPO/'scripts/run_persona_social_actions_user.sh')],
                              env=env,text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('persona_social_action_runtime=BLOCKED',result.stdout)
        saved=pushed/'personas/sunlake-milkcat/pdca'
        self.assertEqual(len(list((saved/'social_receipts').glob('*.json'))),1)
        self.assertTrue((saved/'incidents/test.json').exists())
        self.assertEqual(json.loads(next((saved/'growth_metrics').glob('*.json')).read_text())['status'],'ERROR')

    def test_public_projection_exposes_counts_without_reply_text_or_secrets(self):
        self.replies = [self.reply()]
        self.execute()
        publisher = module('publish_mio_public_activity')
        out = self.root / 'public.json'
        with patch.object(sys, 'argv', ['publisher', '--persona-dir', str(self.root), '--output', str(out)]):
            with contextlib.redirect_stdout(io.StringIO()):
                publisher.main()
        data = json.loads(out.read_text())
        self.assertEqual(data['social_observation']['read_status'], 'PASS')
        self.assertEqual(data['social_observation']['fresh_replies'], 1)
        self.assertNotIn('測試留言', out.read_text())
        self.assertNotIn('private-product-key', out.read_text())


if __name__ == '__main__':
    unittest.main()
