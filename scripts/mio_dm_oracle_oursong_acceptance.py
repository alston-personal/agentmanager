#!/usr/bin/env python3
from __future__ import annotations
import json, re, sys, time
from playwright.sync_api import sync_playwright

TARGET="oursong_alstonhuang"
MESSAGE="聽說你那邊最近很會發文？等你的 DM 接好，我們再來看看誰比較會吐槽。"
CDP="http://127.0.0.1:9222"

def main() -> int:
    with sync_playwright() as p:
        browser=p.chromium.connect_over_cdp(CDP,timeout=7000)
        if not browser.contexts:
            print("mio_dm_oursong_acceptance=NO_CONTEXT")
            return 3
        ctx=browser.contexts[0]
        page=ctx.new_page()
        try:
            page.goto("https://www.threads.com/messages",wait_until="domcontentloaded",timeout=30000)
            page.wait_for_timeout(2500)
            low=page.url.lower()
            if "/login" in low or "accountscenter" in low:
                print("mio_dm_oursong_acceptance=LOGIN_REQUIRED")
                return 4

            found=False
            for loc in [
                page.get_by_text(TARGET, exact=False),
                page.locator(f'text={TARGET}'),
            ]:
                try:
                    if loc.count() > 0:
                        loc.first.click(timeout=3000)
                        found=True
                        break
                except Exception:
                    pass

            if not found:
                print("mio_dm_oursong_acceptance=NO_CONVERSATION")
                return 5

            page.wait_for_timeout(1800)
            body=page.locator("body").inner_text(timeout=3000)
            if MESSAGE in body:
                print("mio_dm_oursong_acceptance=PASS")
                print("mio_dm_oursong_send=ALREADY_PRESENT")
                print("mio_dm_oursong_readback=PASS")
                return 0

            box=None
            selectors=['textarea','[contenteditable="true"]']
            for sel in selectors:
                loc=page.locator(sel)
                try:
                    if loc.count() > 0 and loc.last.is_visible():
                        box=loc.last
                        break
                except Exception:
                    pass
            if box is None:
                print("mio_dm_oursong_acceptance=NO_COMPOSER")
                return 6

            box.click()
            box.fill(MESSAGE) if box.evaluate("(e)=>e.tagName==='TEXTAREA'") else box.press_sequentially(MESSAGE,delay=5)

            sent=False
            for label in ["Send","傳送"]:
                try:
                    btn=page.get_by_role("button",name=re.compile(f"^{label}$",re.I))
                    if btn.count()>0 and btn.last.is_visible():
                        btn.last.click(timeout=3000)
                        sent=True
                        break
                except Exception:
                    pass
            if not sent:
                box.press("Enter")

            page.wait_for_timeout(2500)
            verify=page.locator("body").inner_text(timeout=3000)
            if MESSAGE not in verify:
                print("mio_dm_oursong_acceptance=UNVERIFIED")
                return 7
            print("mio_dm_oursong_acceptance=PASS")
            print("mio_dm_oursong_send=PASS")
            print("mio_dm_oursong_readback=PASS")
            return 0
        finally:
            page.close()

if __name__=="__main__":
    raise SystemExit(main())
