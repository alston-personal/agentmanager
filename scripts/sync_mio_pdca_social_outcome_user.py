#!/usr/bin/env python3
from __future__ import annotations
import fcntl, json, os, re, shutil, subprocess, sys, tempfile, time
from datetime import datetime, timezone
from pathlib import Path

DATA_REPO=Path('/home/ubuntu/agent-data')
DATA_HTTPS='https://github.com/alston-personal/my-agent-data.git'
GIT_CREDENTIAL='credential.helper=!gh auth git-credential'
OUTCOME=Path('/home/ubuntu/agent-data/runtime/social/persona/sunlake-milkcat/pdca-outcome.json')
STATE_REL=Path('personas/sunlake-milkcat/pdca/state.json')
EVENTS_REL=Path('personas/sunlake-milkcat/events/events.jsonl')

def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')

def run(args,cwd=None,check=True):
    env=os.environ.copy(); env.pop('GH_TOKEN',None); env.pop('GITHUB_TOKEN',None)
    p=subprocess.run(args,cwd=str(cwd or DATA_REPO),text=True,capture_output=True,timeout=60,check=False,env=env)
    if check and p.returncode:
        raise RuntimeError('git_operation_failed')
    return p

def main():
    if os.geteuid()!=1001 or os.environ.get('USER') not in (None,'','ubuntu'):
        print('mio_pdca_outcome_sync=WRONG_USER'); return 2
    if not OUTCOME.is_file():
        print('mio_pdca_outcome_sync=NO_OUTCOME'); return 0
    try:
        outcome=json.loads(OUTCOME.read_text(encoding='utf-8'))
    except (OSError,ValueError,TypeError):
        print('mio_pdca_outcome_sync=BAD_OUTCOME'); return 3
    if outcome.get('schema')!='agentos.persona-pdca-social-outcome/v1':
        print('mio_pdca_outcome_sync=BAD_SCHEMA'); return 3
    action_id=str(outcome.get('action_id') or '')
    cycle=int(outcome.get('cycle') or 0)
    capability=str(outcome.get('capability') or '')
    status=str(outcome.get('status') or '')
    result=str(outcome.get('result') or '')
    if (not re.fullmatch(r'mio-pdca-c[0-9]+-social-reply-review',action_id)
            or cycle<1 or capability!='social.reply.review'
            or status not in {'in_progress','completed','deferred'}
            or not result):
        print('mio_pdca_outcome_sync=INVALID_SCOPE'); return 4

    lock=open('/tmp/agentos-mio-persona-data-git.lock','a+')
    fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
    fetched=False
    for _ in range(3):
        p=run(['git','-c',GIT_CREDENTIAL,'fetch',DATA_HTTPS,
               '+refs/heads/main:refs/remotes/origin/main'],check=False)
        if p.returncode==0:
            fetched=True; break
        time.sleep(1)
    if not fetched:
        print('mio_pdca_outcome_sync=FETCH_FAILED'); return 5

    root=Path(tempfile.mkdtemp(prefix='mio-pdca-outcome-')); work=root/'work'
    try:
        run(['git','worktree','add','--detach',str(work),'origin/main'])
        state_path=work/STATE_REL; events_path=work/EVENTS_REL
        state=json.loads(state_path.read_text(encoding='utf-8'))
        if state.get('schema')!='agentos.persona-pdca-state/v1':
            print('mio_pdca_outcome_sync=STATE_SCHEMA_MISMATCH'); return 6
        pending=state.get('pending_external_actions')
        if not isinstance(pending,list):
            pending=[]
        target=None
        for item in reversed(pending):
            if not isinstance(item,dict): continue
            if item.get('action_id')==action_id:
                target=item; break
            if (not item.get('action_id') and item.get('capability')==capability
                    and item.get('status') in ('candidate','in_progress')):
                target=item; break
        if target is None:
            print('mio_pdca_outcome_sync=NO_MATCHING_ACTION'); return 0

        previous=json.dumps(target.get('last_outcome') or {},sort_keys=True,ensure_ascii=False)
        safe_outcome={
            'schema':outcome['schema'],'action_id':action_id,'cycle':cycle,
            'capability':capability,'observed_at':str(outcome.get('observed_at') or now()),
            'status':status,'result':result[:80],
            'reviewed_count':max(0,int(outcome.get('reviewed_count') or 0)),
        }
        platform_object_id=str(outcome.get('platform_object_id') or '')
        if platform_object_id and re.fullmatch(r'[0-9]{8,30}',platform_object_id):
            safe_outcome['platform_object_id']=platform_object_id
        target['action_id']=action_id
        target['cycle']=cycle
        target['execution_status']=status
        target['last_outcome']=safe_outcome
        if status=='completed':
            target['status']='completed'
            target['completed_at']=safe_outcome['observed_at']
        else:
            # Keep candidate while work is scheduled/deferred so the PDCA tick
            # does not create a duplicate capability intent.
            target['status']='candidate'

        state['pending_external_actions']=pending[-12:]
        state['last_external_outcome']=safe_outcome
        changed=(previous!=json.dumps(safe_outcome,sort_keys=True,ensure_ascii=False))

        event_added=False
        if status=='completed':
            event_id='pdca-external-'+action_id+'-'+result
            seen=False
            for raw in events_path.read_text(encoding='utf-8').splitlines():
                try: row=json.loads(raw)
                except Exception: continue
                if str(row.get('event_id') or row.get('id') or '')==event_id:
                    seen=True; break
            if not seen:
                event={
                    'schema':'agentos.persona-event/v1',
                    'event_id':event_id,
                    'timestamp':safe_outcome['observed_at'],
                    'observed_at':now(),
                    'type':'pdca.external_action.completed',
                    'actor':'sunlake-milkcat-ai-001',
                    'source':'AgentOS Persona PDCA Social bridge',
                    'execution_origin':'agentos_social_runtime',
                    'summary':f"PDCA cycle {cycle} social.reply.review completed: {result}",
                    'pdca_action_id':action_id,
                    'pdca_cycle':cycle,
                    'result':result,
                }
                if 'platform_object_id' in safe_outcome:
                    event['object_id']=safe_outcome['platform_object_id']
                    event['platform']='threads'
                with events_path.open('a',encoding='utf-8') as fh:
                    fh.write(json.dumps(event,ensure_ascii=False,separators=(',',':'))+'\n')
                event_added=True

        state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        run(['git','add',STATE_REL.as_posix(),EVENTS_REL.as_posix()],cwd=work)
        if run(['git','diff','--cached','--quiet'],cwd=work,check=False).returncode==0:
            print('mio_pdca_outcome_sync=NO_CHANGE'); return 0
        run(['git','-c','user.name=AgentOS Persona PDCA Social',
             '-c','user.email=agentos-persona-pdca-social@users.noreply.github.com',
             'commit','-m',f'chore(mio): sync PDCA social outcome cycle {cycle}'],cwd=work)
        pushed=run(['git','-c',GIT_CREDENTIAL,'push',DATA_HTTPS,'HEAD:main'],cwd=work,check=False)
        if pushed.returncode:
            print('mio_pdca_outcome_sync=PUSH_FAILED'); return 7
        head=run(['git','rev-parse','HEAD'],cwd=work).stdout.strip()
        if re.fullmatch(r'[0-9a-f]{40}',head):
            run(['git','update-ref','refs/remotes/origin/main',head],cwd=DATA_REPO,check=False)
        print('mio_pdca_outcome_sync=PASS')
        print('mio_pdca_outcome_status='+status)
        print('mio_pdca_outcome_result='+re.sub(r'[^a-zA-Z0-9_\-]','',result)[:80])
        print('mio_pdca_outcome_event_added='+str(event_added).lower())
        return 0
    finally:
        try: run(['git','worktree','remove','--force',str(work)],check=False)
        except Exception: pass
        shutil.rmtree(root,ignore_errors=True)

if __name__=='__main__':
    raise SystemExit(main())
