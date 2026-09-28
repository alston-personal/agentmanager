from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import venv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCHEMA='agentos.client-runtime-converge/v1'
REPO='alston-personal/agentmanager'
SOURCE_REF='core/integration'
LABEL='org.milkcat.agentos.thin-client'
GUARD_LABEL='org.milkcat.agentos.ota-guard'

def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')

def _root() -> Path:
    return Path.home()/'Library'/'Application Support'/'AgentOS'

def _prov_path() -> Path:
    return Path.home()/'.local'/'share'/'agentos'/'runtime-provenance.json'

def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp=path.with_name(path.name+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    os.replace(tmp,path)

def _load(path: Path) -> dict[str, Any] | None:
    try:
        value=json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value,dict) else None
    except (OSError,json.JSONDecodeError):
        return None

def _kick(label: str) -> None:
    uid=str(os.getuid())
    subprocess.run(['launchctl','kickstart','-k',f'gui/{uid}/{label}'],capture_output=True,text=True,timeout=15,check=False)

def _stable_launcher(root: Path) -> Path:
    path=root/'agentos-client'
    body='''#!/bin/bash
set -e
ROOT="$HOME/Library/Application Support/AgentOS"
PY=$(python3 -c 'import json,os; p=os.path.expanduser("~/Library/Application Support/AgentOS/current.json"); d=json.load(open(p)); print(d["python"])')
exec "$PY" -m agentos_node.client_cli "$@"
'''
    tmp=path.with_name(path.name+'.next')
    tmp.write_text(body,encoding='utf-8')
    tmp.chmod(0o700)
    os.replace(tmp,path)
    return path

def _install_guard(root: Path) -> None:
    guard=root/'ota-guard.py'
    guard.write_text('''from __future__ import annotations
import json,os,subprocess
from datetime import datetime,timezone
from pathlib import Path
root=Path.home()/"Library"/"Application Support"/"AgentOS"
cur=root/"current.json"; lkg=root/"last-known-good.json"
try: c=json.loads(cur.read_text())
except Exception: raise SystemExit(0)
if c.get("status")!="awaiting-controller-acceptance": raise SystemExit(0)
try: deadline=datetime.fromisoformat(str(c["rollback_deadline"]).replace("Z","+00:00"))
except Exception: raise SystemExit(2)
if datetime.now(timezone.utc)<deadline: raise SystemExit(0)
try: previous=json.loads(lkg.read_text())
except Exception: raise SystemExit(3)
tmp=cur.with_name(cur.name+".tmp"); tmp.write_text(json.dumps(previous,indent=2,sort_keys=True)+"\\n"); os.replace(tmp,cur)
prov=Path.home()/".local"/"share"/"agentos"/"runtime-provenance.json"; prov.parent.mkdir(parents=True,exist_ok=True)
p=prov.with_name(prov.name+".tmp"); p.write_text(json.dumps({"schema":"agentos.thin-client-runtime/v0.1","source_ref":previous.get("source_ref"),"source_commit":previous.get("source_commit"),"status":"rollback-restored"},indent=2,sort_keys=True)+"\\n"); os.replace(p,prov)
uid=str(os.getuid()); subprocess.run(["launchctl","kickstart","-k",f"gui/{uid}/org.milkcat.agentos.thin-client"],check=False)
''',encoding='utf-8')
    guard.chmod(0o700)
    plist=Path.home()/'Library'/'LaunchAgents'/(GUARD_LABEL+'.plist')
    plist.parent.mkdir(parents=True,exist_ok=True)
    plist.write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>{GUARD_LABEL}</string>
<key>ProgramArguments</key><array><string>{sys.executable}</string><string>{guard}</string></array>
<key>StartInterval</key><integer>30</integer>
<key>RunAtLoad</key><true/>
</dict></plist>''',encoding='utf-8')
    uid=str(os.getuid())
    subprocess.run(['launchctl','bootout',f'gui/{uid}',str(plist)],capture_output=True,text=True,check=False)
    subprocess.run(['launchctl','bootstrap',f'gui/{uid}',str(plist)],capture_output=True,text=True,timeout=15,check=False)

def _validate_task(task: dict[str, Any]) -> tuple[str,str]:
    phase=str(task.get('phase') or '')
    commit=str(task.get('source_commit') or '')
    if phase not in {'stage','accept','rollback'}: raise ValueError('invalid converge phase')
    if not re.fullmatch(r'[0-9a-f]{40}',commit): raise ValueError('invalid source_commit')
    return phase,commit

def execute_client_runtime_converge(task: dict[str, Any]) -> dict[str, Any]:
    phase,commit=_validate_task(task)
    if platform.system()!='Darwin': raise RuntimeError('client runtime converge currently supports Darwin')
    root=_root(); root.mkdir(parents=True,exist_ok=True)
    current_path=root/'current.json'; lkg_path=root/'last-known-good.json'
    current=_load(current_path)

    if phase=='accept':
        if not current or current.get('status')!='awaiting-controller-acceptance' or current.get('source_commit')!=commit:
            raise RuntimeError('candidate is not awaiting acceptance')
        current['status']='active-accepted'; current['accepted_at']=_utc()
        _write_json(current_path,current); _write_json(lkg_path,current)
        return {'runtime_converge':{'status':'accepted','source_commit':commit}}

    if phase=='rollback':
        lkg=_load(lkg_path)
        if not lkg: raise RuntimeError('last-known-good missing')
        _write_json(current_path,lkg)
        _write_json(_prov_path(),{'schema':'agentos.thin-client-runtime/v0.1','source_ref':lkg.get('source_ref'),'source_commit':lkg.get('source_commit'),'status':'rollback-restored'})
        _kick(LABEL)
        return {'runtime_converge':{'status':'rolled-back','source_commit':lkg.get('source_commit')}}

    versions=root/'versions'; candidate=versions/commit; py=candidate/'venv'/'bin'/'python'
    if not py.exists():
        candidate.mkdir(parents=True,exist_ok=True)
        venv.EnvBuilder(with_pip=True,clear=True).create(candidate/'venv')
        p=subprocess.run([str(py),'-m','pip','install','-q','--upgrade',f'git+https://github.com/{REPO}.git@{commit}'],capture_output=True,text=True,timeout=240,check=False)
        if p.returncode!=0: raise RuntimeError('candidate install failed: '+p.stderr[-1000:])
    check=subprocess.run([str(py),'-c','import agentos_node.client_cli,agentos_node.thin_client; print("candidate_import=PASS")'],capture_output=True,text=True,timeout=30,check=False)
    if check.returncode!=0 or 'candidate_import=PASS' not in check.stdout: raise RuntimeError('candidate import failed')

    if not current:
        legacy_py=root/'venv'/'bin'/'python'
        if not legacy_py.exists(): raise RuntimeError('legacy runtime missing')
        current={'schema':SCHEMA,'source_ref':'bootstrap-lkg','source_commit':'unknown','python':str(legacy_py),'status':'active-accepted','installed_at':_utc()}
        _write_json(current_path,current)
    _write_json(lkg_path,current)
    _stable_launcher(root); _install_guard(root)
    pending={'schema':SCHEMA,'source_ref':SOURCE_REF,'source_commit':commit,'python':str(py),'status':'awaiting-controller-acceptance','installed_at':_utc(),'rollback_deadline':(datetime.now(timezone.utc)+timedelta(minutes=3)).replace(microsecond=0).isoformat().replace('+00:00','Z')}
    _write_json(current_path,pending)
    _write_json(_prov_path(),{'schema':'agentos.thin-client-runtime/v0.1','source_ref':SOURCE_REF,'source_commit':commit,'status':'activating'})
    _kick(LABEL)
    return {'runtime_converge':{'status':'awaiting-controller-acceptance','source_commit':commit,'previous_commit':current.get('source_commit')}}
