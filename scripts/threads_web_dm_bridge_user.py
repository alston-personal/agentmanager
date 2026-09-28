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


def extract_text(page) -> list[DirectMessageEvent]:
    # Web UI fallback: use visible conversation list/message regions only.
    # Never inspect cookies/localStorage and never serialize DOM wholesale.
    rows=page.locator('[role="main"] [role="link"], [role="main"] a').all()
    events=[]
    for row in rows[:100]:
        try:
            text=(row.inner_text(timeout=500) or "").strip()
            href=row.get_attribute("href") or ""
        except Exception:
            continue
        if not text or "/messages" not in href:
            continue
        conversation_id=stable_id(href)
        # The list row itself is evidence that a conversation exists. Message
        # bodies are read after opening each conversation below.
        try:
            row.click(timeout=1200)
            page.wait_for_timeout(500)
        except Exception:
            continue
        message_nodes=page.locator('[role="main"] [dir="auto"]')
        count=min(message_nodes.count(),120)
        for i in range(count):
            try:
                body=(message_nodes.nth(i).inner_text(timeout=300) or "").strip()
            except Exception:
                continue
            if not body or len(body)>12000:
                continue
            # Avoid obvious navigation labels and duplicate container text.
            if body in {"Messages","Requests","New message","Search"}:
                continue
            mid=stable_id(conversation_id,body,str(i))
            events.append(DirectMessageEvent(
                platform="threads",
                account_id="mio.milkcat",
                conversation_id=conversation_id,
                message_id=mid,
                actor_id=None,
                actor_username=None,
                text=body,
                timestamp=None,
                direction="unknown",
            ))
    return events


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--account",default="mio.milkcat")
    ap.add_argument("--headed",action="store_true")
    ap.add_argument("--login-only",action="store_true")
    ap.add_argument("--channel",default=os.environ.get("AGENTOS_WEB_DM_BROWSER_CHANNEL") or ("chrome" if sys.platform=="darwin" else None))
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
            browser_type=p.chromium
            launch_args={"headless":not args.headed,"viewport":{"width":1280,"height":900}}
            if args.channel:
                launch_args["channel"]=args.channel
            context=browser_type.launch_persistent_context(str(PROFILE),**launch_args)
            page=context.pages[0] if context.pages else context.new_page()
            page.goto(INBOX_URL,wait_until="domcontentloaded",timeout=30000)
            page.wait_for_timeout(1500)
            url=page.url
            if "login" in url or "accountscenter" in url:
                print("threads_web_dm_bridge=LOGIN_REQUIRED")
                context.close()
                return 4
            if args.login_only:
                print("threads_web_dm_bridge=SESSION_READY")
                context.close()
                return 0

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
    return 0


if __name__=="__main__":
    raise SystemExit(main())
