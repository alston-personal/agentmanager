#!/usr/bin/env python3
from __future__ import annotations

import json, os, re, sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agentos_node.social.persona_dm import binding_for, account_from_profile_hrefs

TARGET_RE=re.compile(r"^[A-Za-z0-9._]{1,64}$")
INBOX="https://www.threads.com/messages"

def main()->int:
    persona=str(os.environ.get("AGENTOS_DM_PERSONA") or "").strip().lower()
    target=str(os.environ.get("AGENTOS_DM_TARGET") or "").strip().lstrip("@")
    decision_path=Path(os.environ.get("AGENTOS_DM_DECISION_PATH") or "")
    if persona not in {"mio","oursong"} or not TARGET_RE.fullmatch(target) or not decision_path.is_file():
        print("persona_dm_send=INVALID_INPUT"); return 2
    binding=binding_for(persona)
    try:
        decision=json.loads(decision_path.read_text(encoding="utf-8"))
    except Exception:
        print("persona_dm_send=INVALID_DECISION"); return 2
    if str(decision.get("decision") or "")!="reply":
        print("persona_dm_send=NO_REPLY"); return 0
    body=str(decision.get("text") or "").strip()
    if not body or len(body)>500 or any(ord(ch)<32 and ch not in "\n\t" for ch in body):
        print("persona_dm_send=INVALID_BODY"); return 2

    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        print("persona_dm_send=PLAYWRIGHT_UNAVAILABLE"); return 3

    with sync_playwright() as p:
        browser=p.chromium.connect_over_cdp(binding.cdp_url,timeout=5000)
        if not browser.contexts:
            print("persona_dm_send=NO_CONTEXT"); return 4
        ctx=browser.contexts[0]
        page=ctx.new_page()
        try:
            page.goto(INBOX,wait_until="domcontentloaded",timeout=30000)
            page.wait_for_timeout(1500)
            parsed=urlparse(page.url)
            path=(parsed.path or "").lower(); host=(parsed.hostname or "").lower()
            if path=="/login" or path.startswith("/login/") or "accountscenter" in host:
                print("persona_dm_send=LOGIN_REQUIRED"); return 4

            profile_hrefs=page.locator(
                'a[href][aria-label*="profile" i], '
                'a[href][title*="profile" i], '
                'a[href]:has(svg[aria-label*="profile" i]), '
                '[role="navigation"] a[href^="/@"], nav a[href^="/@"]'
            )
            hrefs=[]
            try:
                for i in range(min(profile_hrefs.count(),20)):
                    href=profile_hrefs.nth(i).get_attribute("href") or ""
                    if href: hrefs.append(href)
            except Exception:
                pass
            observed=account_from_profile_hrefs(hrefs)
            if observed!=binding.account:
                print("persona_dm_send=IDENTITY_FAIL"); return 5

            found=False
            for loc in (page.get_by_text(target,exact=False),page.locator(f"text={target}")):
                try:
                    if loc.count()>0 and loc.first.is_visible():
                        loc.first.click(timeout=5000); found=True; break
                except Exception:
                    pass
            if not found:
                print("persona_dm_send=CONVERSATION_NOT_FOUND"); return 6

            page.wait_for_timeout(1500)
            if body in (page.locator("body").inner_text(timeout=5000) or ""):
                print("persona_dm_send=PASS")
                print("persona_dm_send_readback=ALREADY_PRESENT")
                return 0

            box=None
            for sel in ('textarea','[contenteditable="true"]'):
                loc=page.locator(sel)
                for i in range(loc.count()-1,-1,-1):
                    item=loc.nth(i)
                    try:
                        if item.is_visible(): box=item; break
                    except Exception:
                        pass
                if box is not None: break
            if box is None:
                print("persona_dm_send=NO_COMPOSER"); return 7

            box.click()
            try:
                if box.evaluate("(e)=>e.tagName==='TEXTAREA'"): box.fill(body)
                else: box.press_sequentially(body,delay=5)
            except Exception:
                box.press_sequentially(body,delay=5)

            sent=False
            for label in ("Send","傳送"):
                try:
                    btn=page.get_by_role("button",name=re.compile("^"+re.escape(label)+"$",re.I))
                    if btn.count()>0 and btn.last.is_visible():
                        btn.last.click(timeout=5000); sent=True; break
                except Exception:
                    pass
            if not sent: box.press("Enter")
            page.wait_for_timeout(2200)
            if body not in (page.locator("body").inner_text(timeout=5000) or ""):
                print("persona_dm_send=UNVERIFIED"); return 8
            print("persona_dm_send=PASS")
            print("persona_dm_send_readback=PASS")
            return 0
        finally:
            page.close()

if __name__=="__main__":
    raise SystemExit(main())
