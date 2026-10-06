#!/usr/bin/env python3
from __future__ import annotations
import base64, json, os, socket, struct, time, urllib.request
from urllib.parse import urlsplit

TARGET="oursong_alstonhuang"
MESSAGE="聽說你那邊最近很會發文？等你的 DM 接好，我們再來看看誰比較會吐槽。"
STAGE="module"

def _json_get(url: str):
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.load(r)

class _WS:
    def __init__(self, url: str):
        u=urlsplit(url)
        if u.scheme!="ws":
            raise RuntimeError("only ws:// supported")
        self.sock=socket.create_connection((u.hostname,u.port or 80),timeout=30)
        key=base64.b64encode(os.urandom(16)).decode()
        path=u.path+(("?"+u.query) if u.query else "")
        req=(f"GET {path} HTTP/1.1\r\nHost: {u.hostname}:{u.port or 80}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(req.encode("ascii"))
        head=b""
        while b"\r\n\r\n" not in head and len(head)<65536:
            ch=self.sock.recv(4096)
            if not ch:
                break
            head+=ch
        if not head.startswith(b"HTTP/1.1 101"):
            raise RuntimeError("cdp websocket handshake failed")
    def _read_exact(self,n):
        out=b""
        while len(out)<n:
            ch=self.sock.recv(n-len(out))
            if not ch:
                raise RuntimeError("cdp websocket closed")
            out+=ch
        return out
    def send_text(self,text):
        p=text.encode(); m=os.urandom(4); n=len(p); h=bytearray([0x81])
        if n<126: h.append(0x80|n)
        elif n<65536: h.append(0x80|126); h.extend(struct.pack("!H",n))
        else: h.append(0x80|127); h.extend(struct.pack("!Q",n))
        self.sock.sendall(bytes(h)+m+bytes(b^m[i%4] for i,b in enumerate(p)))
    def recv_text(self):
        while True:
            b1,b2=self._read_exact(2); op=b1&0x0F; n=b2&0x7F
            if n==126: n=struct.unpack("!H",self._read_exact(2))[0]
            elif n==127: n=struct.unpack("!Q",self._read_exact(8))[0]
            mask=self._read_exact(4) if (b2&0x80) else None
            p=self._read_exact(n)
            if mask: p=bytes(b^mask[i%4] for i,b in enumerate(p))
            if op==1: return p.decode("utf-8","replace")
            if op==8: raise RuntimeError("closed")
    def close(self):
        try: self.sock.close()
        except Exception: pass

def _call(ws,method,params,cid):
    ws.send_text(json.dumps({"id":cid,"method":method,"params":params},separators=(",",":")))
    while True:
        m=json.loads(ws.recv_text())
        if m.get("id")!=cid:
            continue
        if "error" in m:
            raise RuntimeError(method+" failed")
        return m.get("result") or {}

def _eval(ws,expr,cid):
    result=_call(ws,"Runtime.evaluate",{"expression":expr,"returnByValue":True,"awaitPromise":True},cid)
    value=result.get("result") or {}
    if value.get("exceptionDetails"):
        raise RuntimeError("Runtime.evaluate exception")
    return value.get("value")

def _threads_tab():
    tabs=_json_get("http://127.0.0.1:9222/json/list")
    candidates=[t for t in tabs if "threads.com" in str(t.get("url") or "") and t.get("webSocketDebuggerUrl")]
    if not candidates:
        raise RuntimeError("no Threads tab")
    candidates.sort(key=lambda t: 0 if "/messages" in str(t.get("url") or "") else 1)
    return candidates[0]

def main() -> int:
    global STAGE
    STAGE="cdp_list"
    tab=_threads_tab()
    STAGE="cdp_ws"
    ws=_WS(str(tab["webSocketDebuggerUrl"]))
    try:
        STAGE="messages_goto"
        current=str(tab.get("url") or "")
        if "/messages" not in current:
            _call(ws,"Page.navigate",{"url":"https://www.threads.com/messages"},1)
            ws.close()
            time.sleep(10)
            STAGE="cdp_reconnect"
            tab=_threads_tab()
            ws=_WS(str(tab["webSocketDebuggerUrl"]))
        else:
            time.sleep(1)
        STAGE="login_check"
        state=_eval(ws,'(()=>({url:location.href,body:(document.body?.innerText||"").slice(0,1200)}))()',2) or {}
        url=str((state or {}).get("url") or "").lower()
        if "/login" in url or "accountscenter" in url:
            print("mio_dm_oursong_acceptance=LOGIN_REQUIRED")
            return 4

        STAGE="conversation_find"
        clicked=_eval(ws,'''(()=>{const target='''+json.dumps(TARGET)+''';const els=[...document.querySelectorAll('a,button,[role="button"],[role="link"]')];const e=els.find(x=>((x.innerText||"").trim()).includes(target));if(!e)return "NOT_FOUND";e.click();return "CLICKED";})()''',3)
        if clicked!="CLICKED":
            print("mio_dm_oursong_acceptance=NO_CONVERSATION")
            return 5
        time.sleep(2)

        STAGE="readback_precheck"
        already=_eval(ws,'(()=>((document.querySelector("main")?.innerText||document.body.innerText||"").includes('+json.dumps(MESSAGE)+')?"FOUND":"MISSING"))()',4)
        if already=="FOUND":
            print("mio_dm_oursong_acceptance=PASS")
            print("mio_dm_oursong_send=ALREADY_PRESENT")
            print("mio_dm_oursong_readback=PASS")
            return 0

        STAGE="composer_fill"
        send_result=_eval(ws,'''(()=>{const text='''+json.dumps(MESSAGE)+''';const box=[...document.querySelectorAll('textarea,[contenteditable="true"]')].find(x=>{const r=x.getBoundingClientRect();return r.width>0&&r.height>0});if(!box)return "NO_COMPOSER";box.focus();if(box.tagName==="TEXTAREA"){const set=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,"value").set;set.call(box,text);box.dispatchEvent(new Event("input",{bubbles:true}));}else{document.execCommand("selectAll",false,null);document.execCommand("insertText",false,text);box.dispatchEvent(new InputEvent("input",{bubbles:true,inputType:"insertText",data:text}));}const buttons=[...document.querySelectorAll('button,[role="button"]')];const send=buttons.find(x=>/^(Send|傳送)$/i.test((x.innerText||x.getAttribute("aria-label")||"").trim()));if(send){send.click();return "SENT_BUTTON";}box.dispatchEvent(new KeyboardEvent("keydown",{key:"Enter",code:"Enter",keyCode:13,which:13,bubbles:true}));box.dispatchEvent(new KeyboardEvent("keypress",{key:"Enter",code:"Enter",keyCode:13,which:13,bubbles:true}));box.dispatchEvent(new KeyboardEvent("keyup",{key:"Enter",code:"Enter",keyCode:13,which:13,bubbles:true}));return "SENT_ENTER";})()''',5)
        if send_result=="NO_COMPOSER":
            print("mio_dm_oursong_acceptance=NO_COMPOSER")
            return 6

        STAGE="readback"
        time.sleep(3)
        verify=_eval(ws,'(()=>((document.querySelector("main")?.innerText||document.body.innerText||"").includes('+json.dumps(MESSAGE)+')?"FOUND":"MISSING"))()',6)
        if verify!="FOUND":
            print("mio_dm_oursong_acceptance=UNVERIFIED")
            return 7
        print("mio_dm_oursong_acceptance=PASS")
        print("mio_dm_oursong_send=PASS")
        print("mio_dm_oursong_readback=PASS")
        return 0
    finally:
        ws.close()

if __name__=="__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print("mio_dm_oursong_stage="+str(STAGE or "unknown"))
        print("mio_dm_oursong_acceptance=ERROR_"+type(exc).__name__.upper())
        raise SystemExit(8)
