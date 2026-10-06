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
from urllib.parse import urlparse

from agentos_node.social.web_dm import DirectMessageEvent, dedupe_new_events
from agentos_node.social.persona_dm import binding_for, account_from_profile_hrefs

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

def extract_text(page, account: str) -> list[DirectMessageEvent]:
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
            account_id=account,
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
    ap.add_argument("--persona",choices=("mio","oursong"),default="mio")
    ap.add_argument("--headed",action="store_true")
    ap.add_argument("--login-only",action="store_true")
    ap.add_argument("--channel",default=os.environ.get("AGENTOS_WEB_DM_BROWSER_CHANNEL") or ("chrome" if sys.platform=="darwin" else None))
    ap.add_argument("--wait-for-login-seconds",type=int,default=0)
    ap.add_argument("--oursong-acceptance",action="store_true")
    args=ap.parse_args()
    binding=binding_for(args.persona)
    account=binding.account
    global ROOT, PROFILE, STATE, EVENTS
    ROOT=Path(os.environ.get("AGENTOS_THREADS_WEB_DM_ROOT") or (Path.home()/".local"/"share"/"agentos"/"social"/"threads-web-dm"/binding.runtime_key))
    PROFILE=ROOT/"browser-profile"; STATE=ROOT/"state.json"; EVENTS=ROOT/"events.jsonl"

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
            browser=None
            context=None
            page=None
            owns_context=False
            transport="persistent_profile"
            cdp_url=os.environ.get("AGENTOS_WEB_DM_CDP_URL") or (binding.cdp_url if sys.platform!="darwin" else "")
            if cdp_url:
                try:
                    browser=p.chromium.connect_over_cdp(cdp_url,timeout=5000)
                    if browser.contexts:
                        context=browser.contexts[0]
                        page=context.new_page()
                        transport="gui_worker_cdp"
                except Exception:
                    browser=None
                    context=None
                    page=None
            if page is None:
                launch_args={"headless":not args.headed,"viewport":{"width":1280,"height":900}}
                if args.channel:
                    launch_args["channel"]=args.channel
                context=p.chromium.launch_persistent_context(str(PROFILE),**launch_args)
                page=context.pages[0] if context.pages else context.new_page()
                owns_context=True
            page.goto(INBOX_URL,wait_until="domcontentloaded",timeout=30000)
            page.wait_for_timeout(1500)
            url=page.url
            parsed=urlparse(url)
            path=(parsed.path or "").lower()
            host=(parsed.hostname or "").lower()
            login_required=(path == "/login" or path.startswith("/login/") or "accountscenter" in host)
            if login_required:
                if args.headed and args.wait_for_login_seconds > 0:
                    remaining=max(0,args.wait_for_login_seconds)
                    while remaining > 0:
                        page.wait_for_timeout(1000)
                        remaining-=1
                        url=page.url
                        parsed=urlparse(url)
                        path=(parsed.path or "").lower()
                        host=(parsed.hostname or "").lower()
                        if not (path == "/login" or path.startswith("/login/") or "accountscenter" in host):
                            break
                    parsed=urlparse(url)
                    path=(parsed.path or "").lower()
                    host=(parsed.hostname or "").lower()
                    if path == "/login" or path.startswith("/login/") or "accountscenter" in host:
                        print("threads_web_dm_bridge=LOGIN_REQUIRED")
                        if owns_context:
                            context.close()
                        else:
                            page.close()
                        return 4
                else:
                    print("threads_web_dm_bridge=LOGIN_REQUIRED")
                    if args.oursong_acceptance:
                        print("mio_dm_oursong_stage=login_check")
                        print("mio_dm_oursong_acceptance=LOGIN_REQUIRED")
                    if owns_context:
                        context.close()
                    else:
                        page.close()
                    return 4
            profile_hrefs = page.locator('a[href][aria-label*="profile" i], a[href][title*="profile" i], a[href][aria-label*="個人檔案"], a[href][title*="個人檔案"]')
            hrefs=[]
            try:
                for i in range(min(profile_hrefs.count(),20)):
                    href=profile_hrefs.nth(i).get_attribute("href") or ""
                    if href:
                        hrefs.append(href)
            except Exception:
                hrefs=[]
            observed_account=account_from_profile_hrefs(hrefs)
            if observed_account != account:
                print("threads_web_dm_identity=FAIL")
                print("threads_web_dm_expected_account="+account)
                print("threads_web_dm_observed_account="+(observed_account or "UNKNOWN"))
                if owns_context:
                    context.close()
                else:
                    page.close()
                return 9
            print("threads_web_dm_identity=PASS")
            print("threads_web_dm_account="+account)

            if args.login_only:
                print("threads_web_dm_bridge=SESSION_READY")
                print("threads_web_dm_transport="+transport)
                if owns_context:
                    context.close()
                else:
                    page.close()
                return 0

            if args.oursong_acceptance:
                if transport != "gui_worker_cdp":
                    print("mio_dm_oursong_stage=cdp_attach")
                    print("mio_dm_oursong_acceptance=CDP_REQUIRED")
                    if owns_context:
                        context.close()
                    else:
                        page.close()
                    return 8
                target="oursong_alstonhuang"
                message="聽說你那邊最近很會發文？等你的 DM 接好，我們再來看看誰比較會吐槽。"
                print("mio_dm_oursong_stage=conversation_find")
                found=False
                candidates=[
                    page.get_by_text(target, exact=False),
                    page.locator(f"text={target}"),
                ]
                for loc in candidates:
                    try:
                        if loc.count()>0 and loc.first.is_visible():
                            loc.first.click(timeout=5000)
                            found=True
                            break
                    except Exception:
                        pass
                if not found:
                    print("mio_dm_oursong_stage=conversation_create")
                    opened=False
                    safe_controls=[
                        'a[href*="/messages/new"]',
                        'a[href*="/messages/compose"]',
                        'button[aria-label*="message" i]',
                        '[role="button"][aria-label*="message" i]',
                        'button[aria-label*="chat" i]',
                        '[role="button"][aria-label*="chat" i]',
                        'button[aria-label*="compose" i]',
                        '[role="button"][aria-label*="compose" i]',
                        'button[aria-label*="訊息"]',
                        '[role="button"][aria-label*="訊息"]',
                        'button[aria-label*="聊天"]',
                        '[role="button"][aria-label*="聊天"]',
                    ]
                    for sel in safe_controls:
                        try:
                            loc=page.locator(sel)
                            if loc.count()>0 and loc.first.is_visible():
                                loc.first.click(timeout=5000)
                                opened=True
                                break
                        except Exception:
                            pass
                    if not opened:
                        icon_selectors=[
                            'svg[aria-label*="message" i]',
                            'svg[aria-label*="chat" i]',
                            'svg[aria-label*="compose" i]',
                            'svg[aria-label*="new" i]',
                            'svg[aria-label*="訊息"]',
                            'svg[aria-label*="聊天"]',
                            '[title*="message" i]',
                            '[title*="chat" i]',
                            '[title*="compose" i]',
                            '[title*="new" i]',
                            '[title*="訊息"]',
                            '[title*="聊天"]',
                        ]
                        for sel in icon_selectors:
                            try:
                                icon=page.locator(sel)
                                if icon.count()>0 and icon.first.is_visible():
                                    parent=icon.first.locator('xpath=ancestor-or-self::button[1] | ancestor-or-self::*[@role="button"][1]')
                                    if parent.count()>0 and parent.first.is_visible():
                                        parent.first.click(timeout=5000)
                                        opened=True
                                        break
                            except Exception:
                                pass
                    if not opened:
                        for label in ("New message","New Message","Start chat","Compose","新訊息","建立新訊息","開始聊天","新增聊天"):
                            try:
                                btn=page.get_by_role("button",name=re.compile(re.escape(label),re.I))
                                if btn.count()>0 and btn.first.is_visible():
                                    btn.first.click(timeout=5000)
                                    opened=True
                                    break
                            except Exception:
                                pass
                    if not opened:
                        for label in ("New message","New Message","Start chat","Compose","新訊息","建立新訊息","開始聊天","新增聊天"):
                            try:
                                loc=page.get_by_text(label,exact=False)
                                if loc.count()>0 and loc.first.is_visible():
                                    loc.first.click(timeout=5000)
                                    opened=True
                                    break
                            except Exception:
                                pass
                    if not opened:
                        for compose_url in ("https://www.threads.com/messages/new","https://www.threads.com/messages/compose"):
                            try:
                                page.goto(compose_url,wait_until="domcontentloaded",timeout=15000)
                                page.wait_for_timeout(1200)
                                visible_input=False
                                for sel in ('input[type="text"]','input[type="search"]','input'):
                                    loc=page.locator(sel)
                                    try:
                                        if any(loc.nth(i).is_visible() for i in range(loc.count())):
                                            visible_input=True
                                            break
                                    except Exception:
                                        pass
                                if visible_input:
                                    opened=True
                                    break
                            except Exception:
                                pass
                    if not opened:
                        print("mio_dm_oursong_acceptance=NO_NEW_MESSAGE_CONTROL")
                        if owns_context:
                            context.close()
                        else:
                            page.close()
                        return 5

                    page.wait_for_timeout(1000)
                    search=None
                    for sel in ('input[type="text"]','input[type="search"]','input'):
                        loc=page.locator(sel)
                        try:
                            for i in range(loc.count()):
                                item=loc.nth(i)
                                if item.is_visible():
                                    search=item
                                    break
                        except Exception:
                            pass
                        if search is not None:
                            break
                    if search is None:
                        print("mio_dm_oursong_acceptance=NO_RECIPIENT_SEARCH")
                        if owns_context:
                            context.close()
                        else:
                            page.close()
                        return 5

                    search.click()
                    search.fill(target)
                    page.wait_for_timeout(1500)

                    selected=False
                    for loc in [
                        page.get_by_text(target, exact=False),
                        page.locator(f"text={target}"),
                    ]:
                        try:
                            if loc.count()>0 and loc.first.is_visible():
                                loc.first.click(timeout=5000)
                                selected=True
                                break
                        except Exception:
                            pass
                    if not selected:
                        print("mio_dm_oursong_acceptance=RECIPIENT_NOT_FOUND")
                        if owns_context:
                            context.close()
                        else:
                            page.close()
                        return 5

                    page.wait_for_timeout(800)
                    advanced=False
                    for label in ("Chat","Next","Done","開始聊天","下一步","完成"):
                        try:
                            btn=page.get_by_role("button",name=re.compile("^"+re.escape(label)+"$",re.I))
                            if btn.count()>0 and btn.last.is_visible():
                                btn.last.click(timeout=5000)
                                advanced=True
                                break
                        except Exception:
                            pass
                    page.wait_for_timeout(1500)

                page.wait_for_timeout(1800)
                body=page.locator("body").inner_text(timeout=5000)
                if message in body:
                    print("mio_dm_oursong_acceptance=PASS")
                    print("mio_dm_oursong_send=ALREADY_PRESENT")
                    print("mio_dm_oursong_readback=PASS")
                    if owns_context:
                        context.close()
                    else:
                        page.close()
                    return 0
                print("mio_dm_oursong_stage=composer_find")
                box=None
                for sel in ('textarea','[contenteditable="true"]'):
                    loc=page.locator(sel)
                    try:
                        for i in range(loc.count()-1,-1,-1):
                            item=loc.nth(i)
                            if item.is_visible():
                                box=item
                                break
                    except Exception:
                        pass
                    if box is not None:
                        break
                if box is None:
                    print("mio_dm_oursong_acceptance=NO_COMPOSER")
                    if owns_context:
                        context.close()
                    else:
                        page.close()
                    return 6
                print("mio_dm_oursong_stage=send")
                box.click()
                try:
                    if box.evaluate("(e)=>e.tagName==='TEXTAREA'"):
                        box.fill(message)
                    else:
                        box.press_sequentially(message,delay=5)
                except Exception:
                    box.press_sequentially(message,delay=5)
                sent=False
                for label in ("Send","傳送"):
                    try:
                        btn=page.get_by_role("button",name=re.compile("^"+re.escape(label)+"$",re.I))
                        if btn.count()>0 and btn.last.is_visible():
                            btn.last.click(timeout=5000)
                            sent=True
                            break
                    except Exception:
                        pass
                if not sent:
                    box.press("Enter")
                print("mio_dm_oursong_stage=readback")
                page.wait_for_timeout(2500)
                verify=page.locator("body").inner_text(timeout=5000)
                if message not in verify:
                    print("mio_dm_oursong_acceptance=UNVERIFIED")
                    if owns_context:
                        context.close()
                    else:
                        page.close()
                    return 7
                print("mio_dm_oursong_acceptance=PASS")
                print("mio_dm_oursong_send=PASS")
                print("mio_dm_oursong_readback=PASS")
                if owns_context:
                    context.close()
                else:
                    page.close()
                return 0

            events=extract_text(page, account)
            fresh=dedupe_new_events(events,seen)
            if fresh:
                with EVENTS.open("a",encoding="utf-8") as fh:
                    for event in fresh:
                        payload=event.to_dict()
                        payload["account_id"]=account
                        fh.write(json.dumps(payload,ensure_ascii=False,separators=(",",":"))+"\n")
                os.chmod(EVENTS,0o600)
            seen.update(e.message_id for e in fresh)
            state={
                "schema":"agentos.threads-web-dm-state/v1",
                "account":account,
                "seen_message_ids":sorted(seen)[-5000:],
                "last_scan_new_count":len(fresh),
            }
            save_state(state)
            if owns_context:
                context.close()
            else:
                page.close()
    except Exception as exc:
        print("threads_web_dm_bridge=ERROR")
        print("threads_web_dm_error_type="+type(exc).__name__)
        return 6

    print("threads_web_dm_bridge=PASS")
    print("threads_web_dm_transport="+transport)
    print("threads_web_dm_new_events="+str(len(fresh)))
    print("threads_web_dm_inbound_events="+str(sum(1 for x in fresh if x.direction=="inbound")))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
