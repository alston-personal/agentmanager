#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os,re,subprocess,time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TARGET="oursong_alstonhuang"
OWN_ACCOUNT="mio.milkcat"
STATE=Path("/home/ubuntu/agent-data/runtime/social/persona/sunlake-milkcat/oursong-dm-state.json")
RECEIPT_DIR=Path("/home/ubuntu/agent-data/runtime/social/persona/sunlake-milkcat/dm-receipts")

def load_json(path:Path,default):
    try:
        v=json.loads(path.read_text(encoding="utf-8"))
        return v if isinstance(v,dict) else default
    except Exception:
        return default

def save_json(path:Path,payload:dict[str,Any]):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    os.chmod(tmp,0o600); tmp.replace(path); os.chmod(path,0o600)

def write_receipt(status:str, **extra):
    RECEIPT_DIR.mkdir(parents=True,exist_ok=True)
    now=datetime.now(timezone.utc)
    payload={
        "schema":"agentos.mio-dm-cycle-receipt/v1",
        "created_at":now.isoformat().replace("+00:00","Z"),
        "peer":TARGET,
        "status":status,
        **extra,
    }
    path=RECEIPT_DIR/(now.strftime("%Y%m%dT%H%M%S%fZ")+".json")
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    os.chmod(tmp,0o600); tmp.replace(path); os.chmod(path,0o600)
    return path

def relationship():
    p=subprocess.run(
        ["git","-C","/home/ubuntu/agent-data","show",
         f"origin/main:personas/sunlake-milkcat/relationships/threads/{TARGET}.json"],
        text=True,capture_output=True,check=False,timeout=5
    )
    if p.returncode or not p.stdout:
        return {}
    try:
        d=json.loads(p.stdout); return d if isinstance(d,dict) else {}
    except Exception:
        return {}

def main()->int:
    from scripts.mio_dm_oracle_oursong_acceptance import _json_new,_WS,_eval
    from scripts.threads_web_dm_bridge_user import parse_row
    from scripts.mio_persona_dm_decision_user import decide
    from dm_loop_guard_runtime import should_auto_reply,record_auto_reply,record_consumed

    state=load_json(STATE,{
        "schema":"agentos.persona-dm-loop-state/v1",
        "processed_message_ids":[],
        "processed_fingerprints":[],
        "auto_hops":0,
        "last_auto_reply_epoch":0,
    })

    tab=None
    last_open_error=None
    for attempt in range(1,4):
        try:
            tab=_json_new("https://www.threads.com/messages")
            break
        except Exception as exc:
            last_open_error=exc
            print(f"mio_oursong_dm_cycle_cdp_open_retry={attempt}")
            if attempt<3:
                time.sleep(attempt*2)
    if not isinstance(tab,dict):
        reason=type(last_open_error).__name__ if last_open_error is not None else "UNKNOWN"
        write_receipt("DEGRADED",reason="CDP_OPEN_FAILED",error_type=reason)
        print("mio_oursong_dm_cycle=CDP_OPEN_FAILED")
        print("mio_oursong_dm_cycle_error_type="+reason)
        return 4
    ws=None
    browser_state=None
    last_session_error=None
    for session_attempt in range(1,4):
        try:
            if session_attempt>1:
                tab=_json_new("https://www.threads.com/messages")
            wsurl=str((tab or {}).get("webSocketDebuggerUrl") or "")
            if not wsurl:
                raise RuntimeError("NO_CDP_TARGET")
            time.sleep(4)
            ws=_WS(wsurl)
            browser_state=_eval(ws,'(()=>({url:location.href}))()',2) or {}
            break
        except Exception as exc:
            last_session_error=exc
            if ws is not None:
                try: ws.close()
                except Exception: pass
            ws=None
            browser_state=None
            print(f"mio_oursong_dm_cycle_cdp_session_retry={session_attempt}")
            if session_attempt<3:
                time.sleep(session_attempt*2)
    if ws is None or browser_state is None:
        reason=type(last_session_error).__name__ if last_session_error is not None else "UNKNOWN"
        write_receipt("DEGRADED",reason="CDP_SESSION_FAILED",error_type=reason)
        print("mio_oursong_dm_cycle=CDP_SESSION_FAILED")
        print("mio_oursong_dm_cycle_error_type="+reason)
        return 4
    try:
        low=str(browser_state.get("url") or "").lower()
        if "/login" in low or "accountscenter" in low:
            write_receipt("AUTH_REQUIRED",reason="LOGIN_REQUIRED"); print("mio_oursong_dm_cycle=LOGIN_REQUIRED"); return 4

        info=_eval(ws,'''(()=>{const target='''+json.dumps(TARGET)+''';const els=[...document.querySelectorAll('a,button,[role="button"],[role="link"],div,span')];let e=els.find(x=>((x.innerText||"").trim())===target);if(!e)e=els.find(x=>((x.innerText||"").trim()).includes(target));if(!e)return null;let n=e,best=null;for(let i=0;i<8&&n;i++,n=n.parentElement){const t=(n.innerText||"").trim();if(t.includes(target)&&t.length<=800&&t.split(/\\n/).filter(Boolean).length>=2)best={text:t};}return best||{text:(e.innerText||"").trim()};})()''',3)
        if not isinstance(info,dict) or not str(info.get("text") or "").strip():
            write_receipt("ALIVE_IDLE",reason="TARGET_NOT_FOUND"); print("mio_oursong_dm_cycle=TARGET_NOT_FOUND"); return 0

        user,preview,direction=parse_row(str(info["text"]))
        if str(user or "").lstrip("@")!=TARGET or not preview:
            write_receipt("DEGRADED",reason="PREVIEW_PARSE_FAILED"); print("mio_oursong_dm_cycle=PREVIEW_PARSE_FAILED"); return 5
        if direction!="inbound":
            write_receipt("ALIVE_IDLE",reason="NO_NEW_INBOUND"); print("mio_oursong_dm_cycle=NO_NEW_INBOUND"); return 0

        mid=hashlib.sha256((TARGET+"\x1f"+preview).encode("utf-8")).hexdigest()[:32]
        event={
            "schema":"agentos.social-conversation-event/v1",
            "platform":"threads",
            "account_id":OWN_ACCOUNT,
            "conversation_id":"mio-oursong",
            "message_id":mid,
            "actor_id":None,
            "actor_username":TARGET,
            "text":preview,
            "timestamp":None,
            "direction":"inbound",
            "source":"oracle_cdp_inbox_preview",
        }
        guard=should_auto_reply(
            event=event,state=state,own_account=OWN_ACCOUNT,peer_account=TARGET,
            max_auto_hops=2,cooldown_seconds=120,hop_window_seconds=600,
        )
        print("mio_oursong_dm_guard="+guard.reason)
        if not guard.allow:
            if guard.reason in {"semantic_duplicate","unexpected_peer","own_message","not_inbound","incomplete_event","cooldown","hop_budget_exhausted"}:
                state=record_consumed(event=event,state=state,fingerprint=guard.fingerprint)
                save_json(STATE,state)
            write_receipt("PASS_NO_ACTION",reason=guard.reason,message_id=mid)
            print("mio_oursong_dm_cycle=PASS_NO_ACTION")
            return 0

        rel=relationship()
        dm={
          "platform":"threads","account":OWN_ACCOUNT,"sender":TARGET,
          "message":preview,"context_scope":"inbox_preview",
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
          }
        }
        decision=decide(dm)
        result=str(decision.get("decision") or "invalid")
        print("mio_oursong_dm_decision="+result)
        print("mio_oursong_dm_consistency="+str(decision.get("consistency_check") or "unknown"))
        if result=="no_reply":
            state=record_consumed(event=event,state=state,fingerprint=guard.fingerprint)
            save_json(STATE,state)
            write_receipt("PASS_NO_REPLY",reason=str(decision.get("reason_category") or "unknown"),message_id=mid)
            print("mio_oursong_dm_cycle=PASS_NO_REPLY")
            return 0
        if result!="reply":
            write_receipt("DEGRADED",reason="INVALID_DECISION",message_id=mid); print("mio_oursong_dm_cycle=INVALID_DECISION"); return 6

        reply=str(decision.get("text") or "").strip()
        if not reply or len(reply)>500:
            write_receipt("DEGRADED",reason="INVALID_REPLY",message_id=mid); print("mio_oursong_dm_cycle=INVALID_REPLY"); return 6

        clicked=_eval(ws,'''(()=>{const target='''+json.dumps(TARGET)+''';const els=[...document.querySelectorAll('a,button,[role="button"],[role="link"],div,span')];const e=els.find(x=>((x.innerText||"").trim())===target)||els.find(x=>((x.innerText||"").trim()).includes(target));if(!e)return "NOT_FOUND";e.click();return "CLICKED";})()''',4)
        if clicked!="CLICKED":
            write_receipt("DEGRADED",reason="CLICK_FAILED",message_id=mid); print("mio_oursong_dm_cycle=CLICK_FAILED"); return 7
        time.sleep(1.5)
        sent=_eval(ws,'''(()=>{const text='''+json.dumps(reply)+''';const box=[...document.querySelectorAll('textarea,[contenteditable="true"]')].find(x=>{const r=x.getBoundingClientRect();return r.width>0&&r.height>0});if(!box)return "NO_COMPOSER";box.focus();if(box.tagName==="TEXTAREA"){const set=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,"value").set;set.call(box,text);box.dispatchEvent(new Event("input",{bubbles:true}));}else{document.execCommand("selectAll",false,null);document.execCommand("insertText",false,text);box.dispatchEvent(new InputEvent("input",{bubbles:true,inputType:"insertText",data:text}));}const buttons=[...document.querySelectorAll('button,[role="button"]')];const send=buttons.find(x=>/^(Send|傳送)$/i.test((x.innerText||x.getAttribute("aria-label")||"").trim()));if(send){send.click();return "SENT_BUTTON";}box.dispatchEvent(new KeyboardEvent("keydown",{key:"Enter",code:"Enter",keyCode:13,which:13,bubbles:true}));box.dispatchEvent(new KeyboardEvent("keyup",{key:"Enter",code:"Enter",keyCode:13,which:13,bubbles:true}));return "SENT_ENTER";})()''',5)
        if sent=="NO_COMPOSER":
            write_receipt("DEGRADED",reason="NO_COMPOSER",message_id=mid); print("mio_oursong_dm_cycle=NO_COMPOSER"); return 7
        time.sleep(2)
        verify=_eval(ws,'(()=>((document.querySelector("main")?.innerText||document.body.innerText||"").includes('+json.dumps(reply)+')?"FOUND":"MISSING"))()',6)
        if verify!="FOUND":
            write_receipt("DEGRADED",reason="SEND_UNVERIFIED",message_id=mid); print("mio_oursong_dm_cycle=SEND_UNVERIFIED"); return 8

        state=record_auto_reply(event=event,state=state,fingerprint=guard.fingerprint,now_epoch=time.time())
        save_json(STATE,state)
        write_receipt("PASS_REPLY",reason=str(decision.get("reason_category") or "unknown"),message_id=mid,readback="PASS")
        print("mio_oursong_dm_cycle=PASS_REPLY")
        print("mio_oursong_dm_readback=PASS")
        return 0
    finally:
        ws.close()

if __name__=="__main__":
    raise SystemExit(main())
