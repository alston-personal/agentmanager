#!/usr/bin/env python3
from __future__ import annotations
import json,re,subprocess,time
from pathlib import Path

TARGET="oursong_alstonhuang"

def relation():
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

def main():
    from scripts.mio_dm_oracle_oursong_acceptance import _json_new,_WS,_eval
    from scripts.threads_web_dm_bridge_user import parse_row
    from scripts.mio_persona_dm_decision_user import decide

    tab=_json_new("https://www.threads.com/messages")
    wsurl=str(tab.get("webSocketDebuggerUrl") or "")
    if not wsurl:
        print("mio_dm_live=NO_CDP_TARGET"); return 4
    time.sleep(7)
    ws=_WS(wsurl)
    try:
        state=_eval(ws,'(()=>({url:location.href,body:(document.body?.innerText||"").slice(0,1200)}))()',2) or {}
        low=str(state.get("url") or "").lower()
        if "/login" in low or "accountscenter" in low:
            print("mio_dm_live=LOGIN_REQUIRED"); return 4

        info=_eval(ws,'''(()=>{const target='''+json.dumps(TARGET)+''';const els=[...document.querySelectorAll('a,button,[role="button"],[role="link"],div,span')];let e=els.find(x=>((x.innerText||"").trim())===target);if(!e)e=els.find(x=>((x.innerText||"").trim()).includes(target));if(!e)return null;let n=e,best=null;for(let i=0;i<8&&n;i++,n=n.parentElement){const t=(n.innerText||"").trim();if(t.includes(target)&&t.length<=800&&t.split(/\\n/).filter(Boolean).length>=2)best={text:t};}return best||{text:(e.innerText||"").trim()};})()''',3)
        if not isinstance(info,dict) or not str(info.get("text") or "").strip():
            print("mio_dm_live=TARGET_NOT_FOUND"); return 5

        user,preview,direction=parse_row(str(info["text"]))
        if str(user or "").lstrip("@")!=TARGET or not preview:
            print("mio_dm_live=PREVIEW_PARSE_FAILED"); return 5
        print("mio_dm_live_target="+TARGET)
        print("mio_dm_live_direction="+str(direction or "unknown"))
        if direction!="inbound":
            print("mio_dm_live=NO_NEW_INBOUND"); return 0

        rel=relation()
        dm={
          "platform":"threads","account":"mio.milkcat","sender":TARGET,
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
        print("mio_dm_live_decision="+result)
        print("mio_dm_live_consistency="+str(decision.get("consistency_check") or "unknown"))
        print("mio_dm_live_reason="+str(decision.get("reason_category") or "unknown"))
        if result=="no_reply":
            print("mio_dm_live=PASS_NO_REPLY"); return 0
        if result!="reply":
            print("mio_dm_live=INVALID_DECISION"); return 6
        reply=str(decision.get("text") or "").strip()
        if not reply or len(reply)>500:
            print("mio_dm_live=INVALID_REPLY"); return 6

        clicked=_eval(ws,'''(()=>{const target='''+json.dumps(TARGET)+''';const els=[...document.querySelectorAll('a,button,[role="button"],[role="link"],div,span')];const e=els.find(x=>((x.innerText||"").trim())===target)||els.find(x=>((x.innerText||"").trim()).includes(target));if(!e)return "NOT_FOUND";e.click();return "CLICKED";})()''',4)
        if clicked!="CLICKED":
            print("mio_dm_live=CLICK_FAILED"); return 7
        time.sleep(1.5)

        sent=_eval(ws,'''(()=>{const text='''+json.dumps(reply)+''';const box=[...document.querySelectorAll('textarea,[contenteditable="true"]')].find(x=>{const r=x.getBoundingClientRect();return r.width>0&&r.height>0});if(!box)return "NO_COMPOSER";box.focus();if(box.tagName==="TEXTAREA"){const set=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,"value").set;set.call(box,text);box.dispatchEvent(new Event("input",{bubbles:true}));}else{document.execCommand("selectAll",false,null);document.execCommand("insertText",false,text);box.dispatchEvent(new InputEvent("input",{bubbles:true,inputType:"insertText",data:text}));}const buttons=[...document.querySelectorAll('button,[role="button"]')];const send=buttons.find(x=>/^(Send|傳送)$/i.test((x.innerText||x.getAttribute("aria-label")||"").trim()));if(send){send.click();return "SENT_BUTTON";}box.dispatchEvent(new KeyboardEvent("keydown",{key:"Enter",code:"Enter",keyCode:13,which:13,bubbles:true}));box.dispatchEvent(new KeyboardEvent("keyup",{key:"Enter",code:"Enter",keyCode:13,which:13,bubbles:true}));return "SENT_ENTER";})()''',5)
        if sent=="NO_COMPOSER":
            print("mio_dm_live=NO_COMPOSER"); return 7
        time.sleep(2)
        verify=_eval(ws,'(()=>((document.querySelector("main")?.innerText||document.body.innerText||"").includes('+json.dumps(reply)+')?"FOUND":"MISSING"))()',6)
        if verify!="FOUND":
            print("mio_dm_live=SEND_UNVERIFIED"); return 8
        print("mio_dm_live=PASS_REPLY")
        print("mio_dm_live_readback=PASS")
        return 0
    finally:
        ws.close()

if __name__=="__main__":
    raise SystemExit(main())
