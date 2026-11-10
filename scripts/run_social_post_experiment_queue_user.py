#!/usr/bin/env python3
from __future__ import annotations
import json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path('/home/ubuntu/agent-data/runtime/social/post-experiments')
QUEUE=ROOT/'queue'
DONE=ROOT/'completed'
REPO=Path('/home/ubuntu/agentmanager')

def parse_iso(value):
    return datetime.fromisoformat(str(value).replace('Z','+00:00')).astimezone(timezone.utc)

def save(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    os.chmod(tmp,0o600); tmp.replace(path); os.chmod(path,0o600)

def main():
    QUEUE.mkdir(parents=True,exist_ok=True); DONE.mkdir(parents=True,exist_ok=True)
    os.chmod(QUEUE,0o700); os.chmod(DONE,0o700)
    now=datetime.now(timezone.utc)
    checked=0; advanced=0; failed=0
    for path in sorted(QUEUE.glob('*.json')):
        try:
            item=json.loads(path.read_text(encoding='utf-8'))
            published=parse_iso(item['published_at'])
            elapsed=max(0,int((now-published).total_seconds()//60))
            due=item.get('next_elapsed_minutes')
            if due is None or elapsed < int(due):
                continue
            cmd=[
                sys.executable,str(REPO/'scripts/monitor_social_post_experiment_user.py'),
                '--account',str(item['account_username']),
                '--post-id',str(item['post_id']),
                '--experiment-id',str(item['experiment_id']),
                '--elapsed-minutes',str(elapsed),
            ]
            if item.get('hypothesis'):
                cmd += ['--hypothesis',str(item['hypothesis'])]
            for value in item.get('changed_variables') or []:
                cmd += ['--changed-variable',str(value)]
            r=subprocess.run(cmd,cwd=str(REPO),capture_output=True,text=True,timeout=90,check=False)
            checked+=1
            if r.returncode:
                item['last_error']='monitor_nonzero_exit'
                item['last_attempt_at']=now.replace(microsecond=0).isoformat().replace('+00:00','Z')
                save(path,item); failed+=1
                continue
            next_file=ROOT/str(item['account_username']).lstrip('@').lower()/str(item['experiment_id'])/'next.json'
            nxt=json.loads(next_file.read_text(encoding='utf-8'))
            item['last_observed_at']=now.replace(microsecond=0).isoformat().replace('+00:00','Z')
            item['last_elapsed_minutes']=elapsed
            item['next_elapsed_minutes']=nxt.get('next_elapsed_minutes')
            item.pop('last_error',None)
            if nxt.get('complete') or item['next_elapsed_minutes'] is None:
                target=DONE/path.name
                save(target,item)
                path.unlink(missing_ok=True)
            else:
                save(path,item)
            advanced+=1
        except Exception:
            failed+=1
    print('social_experiment_queue=PASS')
    print('social_experiment_queue_checked='+str(checked))
    print('social_experiment_queue_advanced='+str(advanced))
    print('social_experiment_queue_failed='+str(failed))

if __name__=='__main__':
    main()
