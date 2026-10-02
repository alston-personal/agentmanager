#!/usr/bin/env python3
from __future__ import annotations

import fcntl
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PERSONA_SLUG=os.environ.get('AGENTOS_PERSONA_SLUG','').strip()
PERSONA_ID=os.environ.get('AGENTOS_PERSONA_ID','').strip()
PERSONA_DISPLAY=os.environ.get('AGENTOS_PERSONA_DISPLAY',PERSONA_SLUG).strip() or PERSONA_SLUG
PERSONA_WRITE_PREFIX=os.environ.get('AGENTOS_PERSONA_WRITE_PREFIX',PERSONA_SLUG).strip() or PERSONA_SLUG
DATA_REPO=Path(os.environ.get('AGENTOS_PERSONA_DATA_ROOT','/home/ubuntu/agent-data'))
DATA_REPO_NAME=os.environ.get('AGENTOS_PERSONA_DATA_REPO','alston-personal/my-agent-data').strip()
LOCAL_TZ=ZoneInfo(os.environ.get('AGENTOS_PERSONA_TIMEZONE','Asia/Taipei'))
LOCK=Path('/tmp/agentos-persona-pdca-data-git.lock')

def now():
    return datetime.now(timezone.utc)

def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace('+00:00','Z')

def load_json(path):
    return json.loads(path.read_text(encoding='utf-8'))

def run(args,cwd=None,check=True,timeout=90):
    env=os.environ.copy()
    env.pop('GH_TOKEN',None)
    env.pop('GITHUB_TOKEN',None)
    p=subprocess.run(args,cwd=str(cwd) if cwd else None,text=True,capture_output=True,timeout=timeout,check=False,env=env)
    if check and p.returncode:
        raise RuntimeError('git_operation_failed:'+str(p.returncode))
    return p

def unresolved_reply_review(state):
    for item in reversed(state.get('pending_external_actions') or []):
        if not isinstance(item,dict):
            continue
        if item.get('capability')=='social.reply.review' and item.get('status') in ('candidate','in_progress'):
            return item
    return None

def seed_persona(work):
    source=DATA_REPO/'personas'/PERSONA_SLUG
    target=work/'personas'/PERSONA_SLUG
    required=[
        'character_core.json',
        'persona_state.json',
        'ir/current.json',
        'pdca/config.json',
        'pdca/state.json',
        'events/events.jsonl',
    ]
    for rel in required:
        src=source/rel
        if not src.exists():
            raise RuntimeError('persona_seed_missing:'+rel)
        dst=target/rel
        dst.parent.mkdir(parents=True,exist_ok=True)
        if not dst.exists():
            shutil.copy2(src,dst)
    rel=Path('relationships/README.md')
    src=source/rel
    dst=target/rel
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dst)

def append_jsonl(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a',encoding='utf-8') as fh:
        fh.write(json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n')

def main():
    if os.geteuid()!=1001:
        print('persona_pdca_tick=WRONG_USER')
        return 2
    if not PERSONA_SLUG or not PERSONA_ID:
        print('persona_pdca_tick=IDENTITY_MISSING')
        return 3

    canonical=DATA_REPO/'personas'/PERSONA_SLUG
    config=load_json(canonical/'pdca/config.json')
    state=load_json(canonical/'pdca/state.json')
    persona_state=load_json(canonical/'persona_state.json')
    ir=load_json(canonical/'ir/current.json')

    if config.get('schema')!='agentos.persona-pdca-config/v1' or config.get('enabled') is not True:
        print('persona_pdca_tick=DISABLED')
        return 0
    if state.get('schema')!='agentos.persona-pdca-state/v1' or state.get('status')!='RUNNING':
        print('persona_pdca_tick=STATE_NOT_RUNNING')
        return 4
    if (persona_state.get('autonomy') or {}).get('public_conversation')!='autonomous_with_policy':
        print('persona_pdca_tick=PUBLIC_CONVERSATION_GUARDED')
        return 0

    tick=now()
    heartbeat=max(5,int(config.get('heartbeat_minutes') or 60))
    last_raw=state.get('last_tick_at')
    if int(state.get('cycle') or 0)>0 and last_raw:
        try:
            last=datetime.fromisoformat(str(last_raw).replace('Z','+00:00'))
            if (tick-last).total_seconds() < heartbeat*60:
                print('persona_pdca_tick=NOT_DUE')
                return 0
        except (ValueError,TypeError):
            pass

    cycle=int(state.get('cycle') or 0)+1
    energy=max(0.0,float(state.get('energy_current') if state.get('energy_current') is not None else ((persona_state.get('energy') or {}).get('current') or 72)))
    cost=float((((persona_state.get('energy') or {}).get('action_costs') or {}).get('observe_passive') or 0.2))
    before=energy
    after=max(0.0,before-cost)
    pending=list(state.get('pending_external_actions') or [])
    existing=unresolved_reply_review(state)
    queued=False
    action=None
    if existing is None:
        action={
            'action_id':f'{PERSONA_WRITE_PREFIX}-pdca-c{cycle}-social-reply-review',
            'cycle':cycle,
            'capability':'social.reply.review',
            'status':'candidate',
            'created_at':iso(tick),
            'reason':'review new owned-post public replies through the governed social runtime',
            'policy':'public_conversation=autonomous_with_policy',
            'requires_real_adapter_receipt':True,
        }
        pending.append(action)
        queued=True
    else:
        action=existing

    local=tick.astimezone(LOCAL_TZ)
    receipt_rel=Path('pdca/receipts')/(local.date().isoformat()+'.jsonl')
    activity_rel=Path('pdca/activities')/local.date().isoformat()/f'cycle-{cycle}.json'
    event_rel=Path('events/events.jsonl')
    state_rel=Path('pdca/state.json')

    receipt={
        'schema':'agentos.persona-pdca-receipt/v1',
        'persona_id':PERSONA_ID,
        'cycle':cycle,
        'tick_at':iso(tick),
        'local_time':local.isoformat(),
        'phase':'active',
        'ir_id':str(ir.get('ir_id') or ''),
        'trigger':'oracle_local_timer',
        'plan':{
            'energy':round(before,3),
            'candidates':[{'intent':'observe','weight':1.0}],
            'selected_intent':'observe',
        },
        'do':{
            'action':'observe',
            'status':'pending_external',
            'energy_cost':round(cost,3),
            'capability':'social.reply.review',
            'action_id':str(action.get('action_id') or ''),
        },
        'check':{
            'internal_action_verified':True,
            'external_action_completed':False,
            'energy_before':round(before,3),
            'energy_after':round(after,3),
            'policy_boundary_respected':True,
        },
        'act':{
            'next_focus':'social_feedback',
            'consecutive_noops':0,
            'pending_external_actions':len(pending),
            'external_candidate':action,
        },
        'truth_boundary':{
            'fabricated_external_completion':False,
            'external_receipt_required':True,
        },
    }
    activity={
        'schema':'agentos.persona-activity-receipt/v1',
        'persona_id':PERSONA_ID,
        'cycle':cycle,
        'created_at':iso(tick),
        'intent':'observe',
        'activity':'social_reply_review',
        'result':'delegated_to_social_executor',
        'capability':'social.reply.review',
        'action_id':str(action.get('action_id') or ''),
    }
    event={
        'id':f'pdca-{tick.strftime("%Y%m%d-%H%M%S")}-c{cycle}',
        'type':'pdca.cycle',
        'timestamp':iso(tick),
        'summary':f'PDCA cycle {cycle}: observe social feedback',
        'source':'persona_pdca_runtime',
        'trigger':'oracle_local_timer',
        'receipt_ref':receipt_rel.as_posix(),
        'external_action_completed':False,
    }

    state.update({
        'cycle':cycle,
        'last_tick_at':iso(tick),
        'last_action_at':iso(tick),
        'last_ir_id':str(ir.get('ir_id') or state.get('last_ir_id') or ''),
        'energy_current':round(after,3),
        'consecutive_noops':0,
        'current_focus':'social_feedback',
        'pending_external_actions':pending[-20:],
        'last_receipt':receipt_rel.as_posix(),
        'last_activity_receipt':activity_rel.as_posix(),
        'status':'RUNNING',
    })

    LOCK.touch(exist_ok=True)
    with LOCK.open('a+') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        root=Path(tempfile.mkdtemp(prefix=f'{PERSONA_WRITE_PREFIX}-pdca-tick-'))
        work=root/'repo'
        try:
            if run(['gh','auth','status'],check=False).returncode:
                raise RuntimeError('gh_auth_unavailable')
            run(['gh','auth','setup-git'])
            clone=run(['gh','repo','clone',DATA_REPO_NAME,str(work),'--','--branch','main','--single-branch'],check=False,timeout=120)
            if clone.returncode:
                raise RuntimeError('data_repo_clone_failed')
            seed_persona(work)
            base=work/'personas'/PERSONA_SLUG
            (base/activity_rel).parent.mkdir(parents=True,exist_ok=True)
            (base/activity_rel).write_text(json.dumps(activity,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            append_jsonl(base/receipt_rel,receipt)
            append_jsonl(base/event_rel,event)
            (base/state_rel).write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            run(['git','add',(Path('personas')/PERSONA_SLUG).as_posix()],cwd=work)
            if run(['git','diff','--cached','--quiet'],cwd=work,check=False).returncode==0:
                print('persona_pdca_tick=NO_CHANGE')
                return 0
            run(['git','-c','user.name=agentos-persona-pdca[bot]',
                 '-c','user.email=agentos-persona-pdca[bot]@users.noreply.github.com',
                 'commit','-m',f'persona({PERSONA_SLUG}): persist autonomous PDCA cycle {cycle}'],cwd=work)
            pushed=run(['git','push','origin','HEAD:main'],cwd=work,check=False,timeout=120)
            if pushed.returncode:
                raise RuntimeError('data_repo_push_failed')
            run(['git','fetch','origin','main'],cwd=DATA_REPO,check=False,timeout=60)
        finally:
            shutil.rmtree(root,ignore_errors=True)

    print('persona_pdca_tick=PASS')
    print('persona_pdca_cycle='+str(cycle))
    print('persona_pdca_social_reply_review='+('QUEUED' if queued else 'EXISTING'))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
