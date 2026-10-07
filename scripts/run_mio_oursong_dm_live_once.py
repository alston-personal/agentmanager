#!/usr/bin/env python3
from __future__ import annotations
import json, re, subprocess, sys, time
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
    from playwright.sync_api import sync_playwright
    from scripts.threads_web_dm_bridge_user import parse_row
    from scripts.mio_persona_dm_decision_user import decide

    rel=relation()
    with sync_playwright() as p:
        browser=p.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=5000)
        if not browser.contexts:
            print("mio_dm_live=NO_CONTEXT"); return 4
        ctx=browser.contexts[0]
        page=ctx.new_page()
        try:
            page.goto("https://www.threads.com/messages",wait_until="domcontentloaded",timeout=30000)
            page.wait_for_timeout(1500)
            low=page.url.lower()
            if "/login" in low or "accountscenter" in low:
                print("mio_dm_live=LOGIN_REQUIRED"); return 4

            target_text=page.get_by_text(TARGET,exact=False)
            if target_text.count()==0:
                print("mio_dm_live=TARGET_NOT_FOUND"); return 5
            target_node=target_text.first
            target_row=None
            preview=None
            direction=None

            # Threads may render conversation rows as links, buttons or plain divs.
            # Walk ancestors from the visible username and choose the smallest
            # container that contains enough text to include an inbox preview.
            for level in range(0,7):
                try:
                    node=target_node if level==0 else target_node.locator("xpath=" + "/.."*level)
                    text=(node.inner_text(timeout=500) or "").strip()
                except Exception:
                    continue
                if not text or TARGET not in text:
                    continue
                user,msg,dirn=parse_row(text)
                if str(user or "").lstrip("@")==TARGET and msg:
                    target_row=node
                    preview=msg
                    direction=dirn
                    break

            if target_row is None:
                # Fallback: click the visible target to open the conversation.
                target_row=target_node
            print("mio_dm_live_target="+TARGET)
            print("mio_dm_live_direction="+str(direction or "unknown"))
            if direction!="inbound" or not preview:
                print("mio_dm_live=NO_NEW_INBOUND")
                return 0

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

            target_row.click(timeout=5000)
            page.wait_for_timeout(1200)
            boxes=page.locator('textarea,[contenteditable="true"]')
            box=None
            for i in range(boxes.count()):
                try:
                    if boxes.nth(i).is_visible():
                        box=boxes.nth(i); break
                except Exception:
                    pass
            if box is None:
                print("mio_dm_live=NO_COMPOSER"); return 7

            box.click()
            if (box.evaluate("(e)=>e.tagName") or "").upper()=="TEXTAREA":
                box.fill(reply)
            else:
                box.fill(reply)
            send=None
            for name in ("Send","傳送"):
                loc=page.get_by_role("button",name=re.compile("^"+re.escape(name)+"$",re.I))
                if loc.count() and loc.first.is_visible():
                    send=loc.first; break
            if send is not None:
                send.click(timeout=5000)
            else:
                box.press("Enter")
            page.wait_for_timeout(1800)
            main_text=page.locator("main").inner_text(timeout=5000) or ""
            if reply not in main_text:
                print("mio_dm_live=SEND_UNVERIFIED"); return 8
            print("mio_dm_live=PASS_REPLY")
            print("mio_dm_live_readback=PASS")
            return 0
        finally:
            page.close()

if __name__=="__main__":
    raise SystemExit(main())
