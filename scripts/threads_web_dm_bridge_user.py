#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from agentos_node.social.web_dm import DirectMessageEvent, dedupe_new_events

ROOT=Path(os.environ.get("AGENTOS_THREADS_WEB_DM_ROOT") or (Path.home()/".local"/"share"/"agentos"/"social"/"threads-web-dm"))
PROFILE=ROOT/"browser-profile"
STATE=ROOT/"state.json"
EVENTS=ROOT/"events.jsonl"
INBOX_URL="https://www.threads.com/messages"
USERNAME_RE=re.compile(r"^[A-Za-z0-9._]{1,64}$")
AGE_RE=re.compile(r"^(?:\d+[smhdw]|\d+\s*(?:秒|分|分鐘|小時|天|週)|昨天|Yesterday)$",re.I)

def load_state() -> dict[str, Any]:
    try:
        value=json.loads(STATE.read_text(encoding="utf-8"))
        return value if isinstance(value,dict) else {}
    except (FileNotFoundError,ValueError):
        return {}

def save_state(value: dict[str, Any]) -> None:
    ROOT.mkdir(parents=True,exist_ok=True)
    os.chmod(ROOT,0o700)
    tmp=STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    os.chmod(tmp,0o600); tmp.replace(STATE); os.chmod(STATE,0o600)

def stable_id(*parts: str) -> str:
    raw="\x1f".join(str(p or "") for p in parts).encode()
    return hashlib.sha256(raw).hexdigest()[:32]

def parse_row(text:str) -> tuple[str|None,str|None,str]:
    lines=[x.strip() for x in str(text or "").splitlines() if x.strip()]
    username=next((x.lstrip("@") for x in lines if USERNAME_RE.fullmatch(x.lstrip("@"))),None)
    filtered=[x for x in lines if x not in {"·","訊息","Messages","收件匣","Inbox"} and not AGE_RE.fullmatch(x)]
    if username:
        filtered=[x for x in filtered if x.lstrip("@")!=username]
    preview=filtered[-1] if filtered else None
    direction="unknown"
    if preview:
        low=preview.lower()
        if low.startswith("you sent") or preview.startswith("你傳送了") or preview.startswith("你已傳送"):
            direction="outbound"
        elif username:
            direction="inbound"
    return username,preview,direction

def extract_text(page) -> list[DirectMessageEvent]:
    rows=page.locator('[role="main"] [role="link"], [role="main"] a').all()
    events=[]
    seen_conversations=set()
    for row in rows[:100]:
        try:
            text=(row.inner_text(timeout=500) or "").strip()
            href=row.get_attribute("href") or ""
        except Exception:
            continue
        if not text or "/messages" not in href:
            continue
        conversation_id=stable_id(href)
        if conversation_id in seen_conversations:
            continue
        seen_conversations.add(conversation_id)
        username,preview,direction=parse_row(text)
        if not username or not preview or direction=="unknown":
            continue
        mid=stable_id(conversation_id,username,preview,direction)
        events.append(DirectMessageEvent(
            platform="threads",
            account_id="mio.milkcat",
            conversation_id=conversation_id,
            message_id=mid,
            actor_id=None,
            actor_username=username,
            text=preview,
            timestamp=None,
            direction=direction,
        ))
    return events

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--account",default="mio.milkcat")
    ap.add_argument("--headed",action="store_true")
    ap.add_argument("--login-only",action="store_true")
    ap.add_argument("--channel",default=os.environ.get("AGENTOS_WEB_DM_BROWSER_CHANNEL") or ("chrome" if sys.platform=="darwin" else None))
    ap.add_argument("--wait-for-login-seconds",type=int,default=0)
    args=ap.parse_args()

    ROOT.mkdir(parents=True,exist_ok=True); PROFILE.mkdir(parents=True,exist_ok=True)
    os.chmod(ROOT,0o700); os.chmod(PROFILE,0o700)
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        print("threads_web_dm_bridge=PLAYWRIGHT_UNAVAILABLE")
        return 3

    state=load_state()
    seen=set(str(x) for x in state.get("seen_message_ids") or [])
    try:
        with sync_playwright() as p:
            launch_args={"headless":not args.headed,"viewport":{"width":1280,"height":900}}
            if args.channel:
                launch_args["channel"]=args.channel
            context=p.chromium.launch_persistent_context(str(PROFILE),**launch_args)
            page=context.pages[0] if context.pages else context.new_page()
            page.goto(INBOX_URL,wait_until="domcontentloaded",timeout=30000)
            page.wait_for_timeout(1500)
            url=page.url
            if "login" in url or "accountscenter" in url:
                if args.headed and args.wait_for_login_seconds > 0:
                    remaining=max(0,args.wait_for_login_seconds)
                    while remaining > 0:
                        page.wait_for_timeout(1000)
                        remaining-=1
                        url=page.url
                        if "login" not in url and "accountscenter" not in url:
                            break
                    if "login" in url or "accountscenter" in url:
                        print("threads_web_dm_bridge=LOGIN_REQUIRED")
                        context.close(); return 4
                else:
                    print("threads_web_dm_bridge=LOGIN_REQUIRED")
                    context.close(); return 4
            if args.login_only:
                print("threads_web_dm_bridge=SESSION_READY")
                context.close(); return 0

            events=extract_text(page)
            fresh=dedupe_new_events(events,seen)
            if fresh:
                with EVENTS.open("a",encoding="utf-8") as fh:
                    for event in fresh:
                        payload=event.to_dict()
                        payload["account_id"]=args.account
                        fh.write(json.dumps(payload,ensure_ascii=False,separators=(",",":"))+"\n")
                os.chmod(EVENTS,0o600)
            seen.update(e.message_id for e in fresh)
            state={
                "schema":"agentos.threads-web-dm-state/v1",
                "account":args.account,
                "seen_message_ids":sorted(seen)[-5000:],
                "last_scan_new_count":len(fresh),
            }
            save_state(state)
            context.close()
    except Exception as exc:
        print("threads_web_dm_bridge=ERROR")
        print("threads_web_dm_error_type="+type(exc).__name__)
        return 6

    print("threads_web_dm_bridge=PASS")
    print("threads_web_dm_new_events="+str(len(fresh)))
    print("threads_web_dm_inbound_events="+str(sum(1 for x in fresh if x.direction=="inbound")))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
