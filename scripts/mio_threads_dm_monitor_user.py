#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from agent_core.realm_fabric import RealmFabricStore
from scripts.mio_persona_dm_decision_user import decide

DATA_REPO=Path('/home/ubuntu/agent-data')
REL_DIR='personas/sunlake-milkcat/relationships/threads'
STATE=Path('/home/ubuntu/agent-data/runtime/social/persona/sunlake-milkcat/dm-monitor-state.json')
PENDING=Path('/home/ubuntu/agent-data/runtime/social/persona/sunlake-milkcat/dm-pending.json')
NODE_ID='mbpr'
USERNAME_RE=re.compile(r'^[A-Za-z0-9._]{1,64}$')

def load_json(path:Path, default):
    try: return json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError,ValueError,TypeError): return default

def save_json(path:Path, payload:dict[str,Any]):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    os.chmod(tmp,0o600); tmp.replace(path); os.chmod(path,0o600)

def node_read_inbox() -> str:
    js="(()=>{const m=document.querySelector('main');return (m?m.innerText:document.body.innerText)||'';})()"
    osa='''on run argv
set jsRead to item 1 of argv
tell application "Google Chrome"
activate
set t to active tab of front window
set u to URL of t
if u does not start with "https://www.threads.com/messages" and u does not start with "https://threads.com/messages" then
set URL of t to "https://www.threads.com/messages"
delay 2
end if
return execute t javascript jsRead
end tell
end run'''
    code=(
        "import subprocess; "
        "p=subprocess.run(['/usr/bin/osascript','-e',"+repr(osa)+",'--',"+repr(js)+"],"
        "text=True,capture_output=True,timeout=20); "
        "print(p.stdout,end=''); raise SystemExit(p.returncode)"
    )
    tid='mio-dm-monitor-'+str(int(time.time()*1000))
    store=RealmFabricStore()
    store.queue_task(NODE_ID,{
        'schema':'agentos.node-task/v0.1','task_id':tid,'action':'shell.exec',
        'executable':'python3','argv':['-c',code],
        'cwd':'/Users/tengweihuang/AgentOS','timeout_seconds':30,'cognition_ids_used':[],
    })
    for _ in range(45):
        r=store.get_receipt(tid)
        if r:
            if r.get('ok') is not True or int(r.get('returncode') or 0)!=0:
                raise RuntimeError('mio_dm_monitor_browser_read_failed')
            return str(r.get('stdout') or '')
        time.sleep(1)
    raise TimeoutError('mio_dm_monitor_browser_receipt_timeout')

def parse_inbox(text:str) -> list[dict[str,str]]:
    lines=[x.strip() for x in text.splitlines() if x.strip()]
    rows=[]
    for i,line in enumerate(lines):
        if line!='·' or i<2 or i+1>=len(lines): continue
        user,preview,age=lines[i-2],lines[i-1],lines[i+1]
        if not USERNAME_RE.fullmatch(user): continue
        if not preview or preview in {'訊息','收件匣','陌生訊息'}: continue
        rows.append({'username':user,'preview':preview,'age':age})
    out=[]; seen=set()
    for row in rows:
        if row['username'] in seen: continue
        seen.add(row['username']); out.append(row)
    return out

def relationship(username:str) -> dict[str,Any]:
    rel=f'{REL_DIR}/{username}.json'
    p=subprocess.run(
        ['git','-C',str(DATA_REPO),'show','origin/main:'+rel],
        text=True,capture_output=True,timeout=4,check=False
    )
    if p.returncode or not p.stdout: return {}
    try:
        d=json.loads(p.stdout)
        return d if isinstance(d,dict) else {}
    except (ValueError,TypeError):
        return {}

def input_for(row:dict[str,str], rel:dict[str,Any]) -> dict[str,Any]:
    return {
        'platform':'threads',
        'account':'mio.milkcat',
        'sender':row['username'],
        'message':row['preview'],
        'context_scope':'inbox_preview',
        'relationship_status':str(rel.get('relationship_stage') or 'unknown_new_interaction'),
        'relationship_context':{
            'relationship_stage':rel.get('relationship_stage'),
            'familiarity':rel.get('familiarity'),
            'trust_level':rel.get('trust_level'),
            'interaction_counts':rel.get('interaction_counts') or {},
            'known_topics':rel.get('known_topics') or [],
            'last_inbound':rel.get('last_inbound'),
            'last_outbound':rel.get('last_outbound'),
            'last_decision':rel.get('last_decision'),
        },
    }

def main() -> int:
    if os.geteuid()!=1001 or os.environ.get('USER') not in (None,'','ubuntu'):
        print('mio_dm_monitor=WRONG_USER'); return 2
    state=load_json(STATE,{'schema':'agentos.mio-dm-monitor-state/v1','processed':{}})
    processed=state.setdefault('processed',{})
    rows=parse_inbox(node_read_inbox())
    candidate=None
    for row in rows:
        preview=row['preview']
        if preview.startswith('你傳送了') or preview.lower().startswith('you sent'):
            continue
        rel=relationship(row['username'])
        last_in=str((rel.get('last_inbound') or {}).get('text') or '')
        last_out=str((rel.get('last_outbound') or {}).get('text') or '')
        fp=hashlib.sha256((row['username']+'\0'+preview).encode()).hexdigest()
        if preview in {last_in,last_out} or processed.get(row['username'])==fp:
            continue
        candidate=(row,rel,fp)
        break
    if candidate is None:
        PENDING.unlink(missing_ok=True)
        print('mio_dm_monitor=PASS')
        print('mio_dm_monitor_inbox_count='+str(len(rows)))
        print('mio_dm_monitor_new=0')
        return 0
    row,rel,fp=candidate
    decision=decide(input_for(row,rel))
    payload={
        'schema':'agentos.mio-dm-pending/v1',
        'target':row['username'],
        'inbound_preview':row['preview'],
        'inbound_fingerprint':fp,
        'relationship_stage':str(rel.get('relationship_stage') or 'unknown_new_interaction'),
        'decision':decision,
        'created_at_unix':int(time.time()),
    }
    save_json(PENDING,payload)
    print('mio_dm_monitor=PASS')
    print('mio_dm_monitor_inbox_count='+str(len(rows)))
    print('mio_dm_monitor_new=1')
    print('mio_dm_monitor_decision='+str(decision.get('decision') or 'invalid'))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
