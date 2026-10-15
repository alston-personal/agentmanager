import hashlib
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

WORKFLOW=Path(__file__).resolve().parents[1]/'.github/workflows/persona-pdca-heartbeat.yml'
SOURCE=WORKFLOW.read_text().split("python3 - <<'PY_RUNTIME'\n",1)[1].split('          PY_RUNTIME',1)[0]
SOURCE='\n'.join(line[10:] for line in SOURCE.splitlines())

class PersonaRuntimeInspectionTests(unittest.TestCase):
    def setUp(self):
        self.scope={'__name__':'offline_fixture'}
        exec(compile(SOURCE,str(WORKFLOW),'exec'),self.scope)
        self.calls=[]
        self.units='LoadState=loaded\nActiveState=active\nSubState=waiting\nResult=success\nExecMainStatus=0\nExecMainStartTimestamp=Mon 2026-10-12 07:25:00 CST\nLastTriggerUSec=Mon 2026-10-12 07:25:00 CST\n'
        self.journal=[]

    def run_command(self,command,**kwargs):
        self.calls.append((command,kwargs))
        text=self.units if command[0]=='systemctl' else '\n'.join(json.dumps(x) for x in self.journal)
        return subprocess.CompletedProcess(command,0,text,'PRIVATE-STDERR')

    def inspect(self,runner=None,uid=1001,host='instance-20260129-0852',missing_hash=False):
        with patch.object(subprocess,'run',side_effect=runner or self.run_command), \
             patch.object(self.scope['os'],'getuid',return_value=uid), \
             patch.object(self.scope['socket'],'gethostname',return_value=host), \
             patch.object(Path,'read_bytes',side_effect=OSError if missing_hash else None,
                          return_value=b'installed-source'):
            return self.scope['inspect']()

    def test_fixed_read_only_units_and_bounded_journals_are_used(self):
        report=self.inspect()
        self.assertEqual(report['schema'],'agentos.execution-receipt/v1')
        self.assertEqual(report['authority']['kind'],'runtime_node')
        self.assertEqual(report['status'],'completed')
        self.assertEqual(len(report['units']),4)
        self.assertEqual(len(self.calls),7)
        for command,kwargs in self.calls:
            self.assertIsInstance(command,list)
            self.assertFalse(kwargs.get('shell',False))
            self.assertEqual(kwargs['timeout'],10)
            self.assertEqual(kwargs['env']['LC_ALL'],'C')
            if command[0]=='systemctl':
                self.assertEqual(command[1:3],['--user','show'])
                self.assertIn(command[3],report['units'])
            else:
                self.assertEqual(command[0],'journalctl')
                self.assertEqual(command[command.index('-n')+1],'200')
                self.assertIn('--output=json',command)
        self.assertIn('2026-10-11 22:15:00 UTC',self.calls[4][0])
        self.assertIn('2026-10-11 22:40:00 UTC',self.calls[4][0])
        self.assertEqual(report['source_sha256']['core_runner'],hashlib.sha256(b'installed-source').hexdigest())

    def test_historical_lock_timeout_is_preserved_with_utc_time_only(self):
        self.journal=[{'MESSAGE':'persona_pdca_runtime=LOCK_TIMEOUT secret=DO-NOT-PUBLISH',
                       '__REALTIME_TIMESTAMP':'1791757620000000','_CMDLINE':'PRIVATE-COMMAND'},
                      {'MESSAGE':'private prompt and TOKEN-SECRET','__REALTIME_TIMESTAMP':'1791757620000000'}]
        report=self.inspect()
        markers=report['journals']['core_incident_1730']['markers']
        self.assertEqual(len(markers),1)
        self.assertEqual(markers[0]['value'],'LOCK_TIMEOUT')
        self.assertRegex(markers[0]['timestamp'],r'T.*Z$')
        serialized=json.dumps(report)
        for value in ('DO-NOT-PUBLISH','TOKEN-SECRET','PRIVATE-COMMAND','private prompt','PRIVATE-STDERR'):
            self.assertNotIn(value,serialized)

    def test_unknown_unit_fields_and_invalid_known_values_are_not_exposed(self):
        self.units+='Environment=PRIVATE-TOKEN\nExecStart=PRIVATE-COMMAND\nSubState=TOKEN-SECRET\nExecMainExitTimestamp=PRIVATE-PATH\n'
        report=self.inspect()
        self.assertEqual(report['status'],'partial')
        props=report['units']['agentos-persona-pdca-heartbeat.service']['properties']
        self.assertNotIn('Environment',props)
        self.assertNotIn('SubState',props)
        self.assertNotIn('ExecMainExitTimestamp',props)
        self.assertNotIn('PRIVATE',json.dumps(report))

    def test_failed_core_status_is_observed_without_claiming_functional_health(self):
        self.units=self.units.replace('ActiveState=active','ActiveState=failed').replace('Result=success','Result=exit-code').replace('ExecMainStatus=0','ExecMainStatus=1')
        report=self.inspect()
        core=report['units']['agentos-persona-pdca-heartbeat.service']['properties']
        self.assertEqual(core['ActiveState'],'failed')
        self.assertEqual(core['Result'],'exit-code')
        self.assertEqual(core['ExecMainStatus'],1)
        self.assertEqual(report['functional_acceptance'],'NOT_EVALUATED')
        self.assertFalse(report['publication_allowed'])

    def test_read_failure_is_partial_and_raw_output_is_discarded(self):
        def fail(command,**kwargs):
            return subprocess.CompletedProcess(command,1,'PRIVATE-STDOUT','PRIVATE-STDERR')
        report=self.inspect(fail)
        self.assertEqual(report['status'],'partial')
        self.assertEqual(report['units']['agentos-persona-pdca-heartbeat.service']['read_status'],'READ_FAILED')
        self.assertNotIn('PRIVATE',json.dumps(report))

    def test_timeout_and_missing_binary_have_stable_classification(self):
        for error,status in ((subprocess.TimeoutExpired('private-command',10,output='SECRET',stderr='SECRET'),'READ_TIMEOUT'),
                             (OSError('SECRET'),'READ_UNAVAILABLE')):
            with self.subTest(status=status):
                def fail(command,**kwargs): raise error
                report=self.inspect(fail)
                self.assertEqual(report['status'],'partial')
                self.assertEqual(report['units']['agentos-persona-pdca-heartbeat.service']['read_status'],status)
                self.assertNotIn('SECRET',json.dumps(report))

    def test_malformed_journal_is_partial_and_keeps_valid_markers(self):
        def rows(command,**kwargs):
            result=self.run_command(command,**kwargs)
            if command[0]=='journalctl':
                result.stdout='not-json\n'+json.dumps({'MESSAGE':'persona_pdca_runtime=LOCK_TIMEOUT','__REALTIME_TIMESTAMP':'1791757620000000'})
            return result
        report=self.inspect(rows)
        journal=report['journals']['core_incident_1730']
        self.assertEqual(report['status'],'partial')
        self.assertEqual(journal['read_status'],'PARTIAL_PARSE')
        self.assertEqual(journal['malformed_rows'],1)
        self.assertEqual(len(journal['markers']),1)

    def test_empty_journal_is_not_evidence_of_no_contention_or_healthy_activity(self):
        report=self.inspect()
        journal=report['journals']['core_incident_1730']
        self.assertEqual(journal['observed_rows'],0)
        self.assertEqual(journal['coverage'],'BOUNDED_NOT_EXHAUSTIVE')
        self.assertEqual(report['functional_acceptance'],'NOT_EVALUATED')

    def test_empty_unit_properties_cannot_be_complete_evidence(self):
        self.units=''
        report=self.inspect()
        self.assertEqual(report['status'],'partial')
        core=report['units']['agentos-persona-pdca-heartbeat.service']
        self.assertEqual(core['read_status'],'MISSING_PROPERTIES')
        self.assertIn('ActiveState',core['missing_properties'])

    def test_incorrect_node_or_uid_never_claims_production_authority(self):
        for uid,host in ((0,'instance-20260129-0852'),(1001,'sandbox')):
            with self.subTest(uid=uid,host=host):
                report=self.inspect(uid=uid,host=host)
                self.assertEqual(report['environment'],'offline')
                self.assertEqual(report['authority']['kind'],'offline_fixture')
                self.assertFalse(report['authority']['sandbox_fallback_allowed'])

    def test_missing_installed_sources_do_not_fabricate_hashes(self):
        report=self.inspect(missing_hash=True)
        self.assertEqual(report['status'],'partial')
        self.assertTrue(all(value is None for value in report['source_sha256'].values()))

    def test_unusable_journal_timestamp_does_not_escape_or_crash(self):
        self.journal=[{'MESSAGE':'persona_pdca_runtime=LOCK_TIMEOUT','__REALTIME_TIMESTAMP':value}
                      for value in ('PRIVATE','99999999999999999999')]
        report=self.inspect()
        self.assertEqual(report['journals']['core_incident_1730']['markers'],[])
        self.assertEqual(report['journals']['core_incident_1730']['invalid_marker_timestamps'],2)
        self.assertEqual(report['status'],'partial')

if __name__=='__main__': unittest.main()
