#!/usr/bin/env python3
from __future__ import annotations
import json, os, subprocess, sys, tempfile, shutil, fcntl, time
from datetime import datetime, timezone
from pathlib import Path

DATA_REPO=Path(os.environ.get("AGENTOS_PERSONA_DATA_ROOT","/home/ubuntu/agent-data"))
DATA_HTTPS="https://github.com/alston-personal/my-agent-data.git"
GIT_CREDENTIAL="credential.helper=!gh auth git-credential"

def run(args,cwd=None,check=True):
    env=os.environ.copy(); env.pop("GH_TOKEN",None); env.pop("GITHUB_TOKEN",None)
    p=subprocess.run(args,cwd=str(cwd or DATA_REPO),text=True,capture_output=True,timeout=60,check=False,env=env)
    if check and p.returncode: raise RuntimeError("git_operation_failed")
    return p

def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def active_personas(root):
    base=root/"personas"
    if not base.is_dir(): return []
    out=[]
    for d in sorted(base.iterdir()):
        cfg=d/"pdca/config.json"; state=d/"pdca/state.json"
        if not cfg.is_file() or not state.is_file(): continue
        try:
            c=load(cfg); s=load(state)
        except Exception: continue
        if c.get("schema")!="agentos.persona-pdca-config/v1" or not c.get("enabled"): continue
        if s.get("schema")!="agentos.persona-pdca-state/v1" or s.get("status")!="RUNNING": continue
        out.append((d,c,s))
    return out

def main():
    if os.geteuid()!=1001:
        print("persona_pdca_heartbeat=WRONG_USER",file=sys.stderr); return 2
    if not (DATA_REPO/".git").exists():
        print("persona_pdca_heartbeat=DATA_REPO_MISSING",file=sys.stderr); return 3
    lock=open("/tmp/agentos-persona-data-git.lock","a+"); fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
    fetched=False
    for _ in range(3):
        p=run(["git","-c",GIT_CREDENTIAL,"fetch",DATA_HTTPS,"+refs/heads/main:refs/remotes/origin/main"],check=False)
        if p.returncode==0: fetched=True; break
        time.sleep(1)
    if not fetched:
        print("persona_pdca_heartbeat=FETCH_FAILED",file=sys.stderr); return 4
    tmp=Path(tempfile.mkdtemp(prefix="agentos-persona-heartbeat-")); work=tmp/"work"
    try:
        run(["git","worktree","add","--detach",str(work),"origin/main"])
        personas=active_personas(work)
        if not personas:
            print("persona_pdca_heartbeat=NO_ACTIVE_PERSONAS"); return 0
        stamp=now(); changed=[]
        for d,c,s in personas:
            cycle=int(s.get("cycle") or 0)+1
            s["cycle"]=cycle; s["last_tick_at"]=stamp
            s["current_focus"]="heartbeat"
            # A heartbeat is a wake-up/decision opportunity, not proof of an external action.
            # Preserve pending actions; downstream governed runtimes decide/execute them.
            (d/"pdca/state.json").write_text(json.dumps(s,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            changed.append((d.name,str(s.get("persona_id") or ""),cycle))
        for d,_,_ in personas: run(["git","add",str((d/"pdca/state.json").relative_to(work))],cwd=work)
        run(["git","-c","user.name=AgentOS Persona Heartbeat","-c","user.email=agentos-persona-heartbeat@users.noreply.github.com","commit","-m","chore(persona): advance active persona heartbeats"],cwd=work)
        p=run(["git","-c",GIT_CREDENTIAL,"push",DATA_HTTPS,"HEAD:main"],cwd=work,check=False)
        if p.returncode:
            print("persona_pdca_heartbeat=PUSH_FAILED",file=sys.stderr); return 5
        print("persona_pdca_heartbeat=PASS")
        print("persona_pdca_heartbeat_at="+stamp)
        for slug,pid,cycle in changed:
            print(f"persona_pdca_tick={slug}:{pid}:{cycle}")
        return 0
    finally:
        try: run(["git","worktree","remove","--force",str(work)],check=False)
        except Exception: pass
        shutil.rmtree(tmp,ignore_errors=True)

if __name__=="__main__": raise SystemExit(main())
