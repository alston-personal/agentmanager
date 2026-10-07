#!/usr/bin/env python3
from __future__ import annotations

import json, os, re, subprocess, sys, tempfile, time
from pathlib import Path
from typing import Any

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agentos_node.antigravity_relay import AntigravityRelayClient
from agentos_node.social.dm_loop_guard import should_auto_reply, record_auto_reply, record_consumed
from agentos_node.social.persona_dm import binding_for

PERSONA="oursong"
PEER="mio.milkcat"
BINDING=binding_for(PERSONA)
ROOT=Path.home()/".local"/"share"/"agentos"/"social"/"threads-web-dm"/BINDING.runtime_key
EVENTS=ROOT/"events.jsonl"
STATE=ROOT/"autonomous-state.json"
IR_PATH=Path("/home/ubuntu/agent-data/personas/oursong_alstonhuang/ir/current.json")
RELAY_ROOT=Path("/home/ubuntu/agent-data/runtime/antigravity-relay")
USERNAME_RE=re.compile(r"^[A-Za-z0-9._]{1,64}$")
SENSITIVE_TERMS=("密碼","password","驗證碼","otp","匯款","付款","合約","契約","法律","醫療","診斷","投票","選舉","政黨","候選人")

def load_json(path:Path,default):
    try:
        v=json.loads(path.read_text(encoding="utf-8"))
        return v if isinstance(v,dict) else default
    except Exception:
        return default

def save_json(path:Path,payload:dict[str,Any]):
    path.parent.mkdir(parents=True,exist_ok=True)
    os.chmod(path.parent,0o700)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    os.chmod(tmp,0o600); tmp.replace(path); os.chmod(path,0o600)

def events()->list[dict[str,Any]]:
    if not EVENTS.exists(): return []
    out=[]
    for raw in EVENTS.read_text(encoding="utf-8").splitlines()[-200:]:
        try:d=json.loads(raw)
        except Exception:continue
        if isinstance(d,dict):out.append(d)
    return out

def decide(text:str)->dict[str,Any]:
    low=text.lower()
    if any(term.lower() in low for term in SENSITIVE_TERMS):
        return {"decision":"no_reply","text":None,"decision_source":"safety_gate"}

    ir=load_json(IR_PATH,{})
    if ir.get("schema")!="agentos.persona-ir/v1":
        return {"decision":"no_reply","text":None,"decision_source":"ir_unavailable"}

    prompt=f"""You are deciding one PRIVATE Threads DM reply for @oursong_alstonhuang to @mio.milkcat.
Return JSON only.

Persona IR:
{json.dumps(ir,ensure_ascii=False)}

Inbound DM:
{json.dumps({"sender":PEER,"message":text},ensure_ascii=False)}

Rules:
- Decide reply or no_reply first. Silence is valid.
- Traditional Chinese, concise, direct, observational, mildly playful.
- Never invent real-world experiences, private facts, payments, contracts, identity claims, credentials, medical/legal advice, or political persuasion.
- Do not reveal internal AgentOS implementation.
- This is a peer-to-peer persona conversation, not customer support.
- Keep reply under 120 Chinese characters.
- Do not ask multiple questions.
- Do not echo the inbound text verbatim.
- If uncertain or context is weak, choose no_reply.

Schema:
{{"decision":"reply"|"no_reply","text":"..."|null}}
"""
    try:
        client=AntigravityRelayClient(RELAY_ROOT)
        cap=client.submit(
            project_id="oursong-persona-dm",
            canonical_ir={"goal":"Produce one bounded Oursong DM decision.","constraints":["persona IR primary","private-safe","no sensitive commitments"]},
            instruction=prompt,
            workspace="/home/ubuntu/agentmanager",
        )
        for _ in range(45):
            receipt=client.receipt(cap["capsule_id"])
            if receipt:
                if receipt.get("ok") is not True:
                    return {"decision":"no_reply","text":None,"decision_source":"relay_failed"}
                raw=str(receipt.get("stdout") or "")
                decoder=json.JSONDecoder()
                for i,ch in enumerate(raw):
                    if ch!="{": continue
                    try:obj,_=decoder.raw_decode(raw[i:])
                    except Exception:continue
                    if isinstance(obj,dict) and obj.get("decision") in {"reply","no_reply"}:
                        body=str(obj.get("text") or "").strip()
                        if obj["decision"]=="reply" and body and len(body)<=500:
                            return {"decision":"reply","text":body,"decision_source":"relay"}
                        return {"decision":"no_reply","text":None,"decision_source":"relay"}
                return {"decision":"no_reply","text":None,"decision_source":"invalid_json"}
            time.sleep(2)
    except Exception:
        return {"decision":"no_reply","text":None,"decision_source":"relay_exception"}
    return {"decision":"no_reply","text":None,"decision_source":"relay_timeout"}

def main()->int:
    if os.geteuid()!=1001:
        print("oursong_dm_autonomous=WRONG_USER"); return 2
    state=load_json(STATE,{"schema":"agentos.persona-dm-loop-state/v1"})
    pending=[]
    for event in events():
        user=str(event.get("actor_username") or "").lstrip("@")
        text=str(event.get("text") or "").strip()
        if not USERNAME_RE.fullmatch(user) or not text:
            continue
        mid=str(event.get("message_id") or "")
        if mid and mid in set(str(x) for x in state.get("processed_message_ids") or []):
            continue
        pending.append((event,user,text))

    if not pending:
        print("oursong_dm_autonomous=PASS")
        print("oursong_dm_autonomous_pending=0")
        return 0

    event,user,text=pending[-1]
    guard=should_auto_reply(
        event=event,
        state=state,
        own_account=BINDING.account,
        peer_account=PEER,
        max_auto_hops=BINDING.max_auto_hops,
        cooldown_seconds=BINDING.cooldown_seconds,
        hop_window_seconds=600,
    )
    if not guard.allow:
        if guard.reason in {"cooldown","hop_budget_exhausted","semantic_duplicate","unexpected_peer","own_message","not_inbound","incomplete_event"}:
            state=record_consumed(event=event,state=state,fingerprint=guard.fingerprint)
            save_json(STATE,state)
        print("oursong_dm_autonomous=PASS")
        print("oursong_dm_autonomous_guard="+guard.reason)
        print("oursong_dm_autonomous_pending=0")
        return 0
    decision=decide(text)
    result=str(decision.get("decision") or "no_reply")
    print("oursong_dm_autonomous_guard="+guard.reason)
    print("oursong_dm_autonomous_decision="+result)
    print("oursong_dm_autonomous_decision_source="+str(decision.get("decision_source") or "unknown"))

    if result=="reply":
        with tempfile.NamedTemporaryFile("w",encoding="utf-8",suffix=".json",delete=False) as fh:
            json.dump(decision,fh,ensure_ascii=False)
            path=fh.name
        env=dict(os.environ)
        env["AGENTOS_DM_PERSONA"]=PERSONA
        env["AGENTOS_DM_TARGET"]=user
        env["AGENTOS_DM_DECISION_PATH"]=path
        cp=subprocess.run(
            [sys.executable,str(Path(__file__).with_name("send_threads_dm_from_decision_user.py"))],
            env=env,text=True,capture_output=True,timeout=120,check=False,
        )
        for line in (cp.stdout or "").splitlines():
            if line.startswith(("persona_dm_send=","persona_dm_send_readback=")):
                print(line)
        try:os.unlink(path)
        except OSError:pass
        if cp.returncode!=0:
            print("oursong_dm_autonomous=SEND_FAILED")
            return 1
        state=record_auto_reply(
            event=event,
            state=state,
            fingerprint=guard.fingerprint,
            now_epoch=time.time(),
        )
    else:
        state=record_consumed(event=event,state=state,fingerprint=guard.fingerprint)

    save_json(STATE,state)
    print("oursong_dm_autonomous=PASS")
    print("oursong_dm_autonomous_pending=1")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
