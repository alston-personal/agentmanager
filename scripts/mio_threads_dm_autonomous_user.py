#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, subprocess, sys, tempfile
from pathlib import Path
from typing import Any

from scripts.mio_persona_dm_decision_user import decide
from agentos_node.social.dm_loop_guard import should_auto_reply, record_auto_reply, record_consumed
from agentos_node.social.persona_dm import binding_for

ROOT=Path(os.environ.get("AGENTOS_THREADS_WEB_DM_ROOT") or (Path.home()/".local"/"share"/"agentos"/"social"/"threads-web-dm"))
EVENTS=ROOT/"events.jsonl"
STATE=ROOT/"autonomous-state.json"
DATA_REPO=Path("/home/ubuntu/agent-data")
REL_DIR="personas/sunlake-milkcat/relationships/threads"
USERNAME_RE=re.compile(r"^[A-Za-z0-9._]{1,64}$")
BINDING=binding_for("mio")

def load_json(path:Path, default):
    try:
        v=json.loads(path.read_text(encoding="utf-8"))
        return v if isinstance(v,dict) else default
    except (FileNotFoundError,ValueError,TypeError):
        return default

def save_json(path:Path,payload:dict[str,Any]):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    os.chmod(tmp,0o600); tmp.replace(path); os.chmod(path,0o600)

def relationship(username:str)->dict[str,Any]:
    p=subprocess.run(["git","-C",str(DATA_REPO),"show","origin/main:"+REL_DIR+"/"+username+".json"],
                     text=True,capture_output=True,timeout=4,check=False)
    if p.returncode or not p.stdout:
        return {}
    try:
        d=json.loads(p.stdout); return d if isinstance(d,dict) else {}
    except Exception:
        return {}

def events():
    if not EVENTS.exists():
        return []
    out=[]
    for raw in EVENTS.read_text(encoding="utf-8").splitlines()[-200:]:
        try:
            d=json.loads(raw)
        except Exception:
            continue
        if isinstance(d,dict):
            out.append(d)
    return out

def main()->int:
    if os.geteuid()!=1001:
        print("mio_dm_autonomous=WRONG_USER"); return 2
    state=load_json(STATE,{"schema":"agentos.mio-dm-autonomous-state/v2","processed_ids":[],"loop_by_peer":{}})
    processed=set(str(x) for x in state.get("processed_ids") or [])
    loop_by_peer=state.get("loop_by_peer") if isinstance(state.get("loop_by_peer"),dict) else {}
    candidates=[]
    for e in events():
        mid=str(e.get("message_id") or "")
        user=str(e.get("actor_username") or "").lstrip("@")
        text=str(e.get("text") or "").strip()
        if mid in processed or e.get("direction")!="inbound":
            continue
        if not USERNAME_RE.fullmatch(user) or not text:
            continue
        candidates.append((e,user,text))
    if not candidates:
        print("mio_dm_autonomous=PASS")
        print("mio_dm_autonomous_pending=0")
        return 0

    e,user,text=candidates[-1]
    peer_state=loop_by_peer.get(user) if isinstance(loop_by_peer.get(user),dict) else {}
    guard=should_auto_reply(
        event=e,
        state=peer_state,
        own_account=BINDING.account,
        peer_account=user,
        max_auto_hops=BINDING.max_auto_hops,
        cooldown_seconds=BINDING.cooldown_seconds,
        hop_window_seconds=600,
    )
    if not guard.allow:
        peer_state=record_consumed(event=e,state=peer_state,fingerprint=guard.fingerprint)
        loop_by_peer[user]=peer_state
        processed.add(str(e.get("message_id") or ""))
        state={"schema":"agentos.mio-dm-autonomous-state/v2","processed_ids":sorted(processed)[-5000:],"loop_by_peer":loop_by_peer}
        save_json(STATE,state)
        print("mio_dm_autonomous=PASS")
        print("mio_dm_autonomous_guard="+guard.reason)
        print("mio_dm_autonomous_pending=0")
        return 0

    rel=relationship(user)
    dm={
        "platform":"threads","account":"mio.milkcat","sender":user,
        "message":text,"context_scope":"inbox_preview",
        "relationship_status":str(rel.get("relationship_stage") or "unknown_new_interaction"),
        "relationship_context":{
            "relationship_stage":rel.get("relationship_stage"),
            "familiarity":rel.get("familiarity"),
            "trust_level":rel.get("trust_level"),
            "interaction_counts":rel.get("interaction_counts") or {},
            "known_topics":rel.get("known_topics") or [],
            "last_inbound":rel.get("last_inbound"),
            "last_outbound":rel.get("last_outbound"),
            "last_decision":rel.get("last_decision"),
        },
    }
    decision=decide(dm)
    result=str(decision.get("decision") or "invalid")
    print("mio_dm_autonomous_target="+user)
    print("mio_dm_autonomous_guard="+guard.reason)
    print("mio_dm_autonomous_decision="+result)
    if result=="reply":
        with tempfile.NamedTemporaryFile("w",encoding="utf-8",suffix=".json",delete=False) as fh:
            json.dump(decision,fh,ensure_ascii=False)
            path=fh.name
        env=dict(os.environ)
        env["AGENTOS_DM_PERSONA"]="mio"
        env["AGENTOS_DM_DECISION_PATH"]=path
        env["AGENTOS_DM_TARGET"]=user
        cp=subprocess.run([sys.executable,str(Path(__file__).with_name("send_threads_dm_from_decision_user.py"))],
                          env=env,text=True,capture_output=True,timeout=140,check=False)
        for line in (cp.stdout or "").splitlines():
            if line.startswith(("persona_dm_send=","persona_dm_send_readback=")):
                print(line)
        try: os.unlink(path)
        except OSError: pass
        if cp.returncode!=0:
            print("mio_dm_autonomous=SEND_FAILED")
            return 1
        peer_state=record_auto_reply(event=e,state=peer_state,fingerprint=guard.fingerprint,now_epoch=__import__("time").time())
        print("mio_dm_autonomous_readback=PASS")
    elif result=="no_reply":
        peer_state=record_consumed(event=e,state=peer_state,fingerprint=guard.fingerprint)
    else:
        print("mio_dm_autonomous=INVALID_DECISION")
        return 1

    loop_by_peer[user]=peer_state
    processed.add(str(e.get("message_id") or ""))
    state={"schema":"agentos.mio-dm-autonomous-state/v2","processed_ids":sorted(processed)[-5000:],"loop_by_peer":loop_by_peer}
    save_json(STATE,state)
    print("mio_dm_autonomous=PASS")
    print("mio_dm_autonomous_pending=1")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
