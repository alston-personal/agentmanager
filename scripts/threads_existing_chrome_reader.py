#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import socket
import struct
import time
import urllib.request
from urllib.parse import urlsplit


def _json_get(url: str):
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.load(response)


class _WS:
    def __init__(self, url: str):
        u = urlsplit(url)
        if u.scheme != "ws":
            raise RuntimeError("only ws:// CDP endpoints are supported")
        self.sock = socket.create_connection((u.hostname, u.port or 80), timeout=8)
        key = base64.b64encode(os.urandom(16)).decode()
        path = u.path + (("?" + u.query) if u.query else "")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {u.hostname}:{u.port or 80}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(request.encode("ascii"))
        head = b""
        while b"\r\n\r\n" not in head and len(head) < 65536:
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            head += chunk
        if not head.startswith(b"HTTP/1.1 101"):
            raise RuntimeError("cdp websocket handshake failed")

    def _read_exact(self, n: int) -> bytes:
        out = b""
        while len(out) < n:
            chunk = self.sock.recv(n - len(out))
            if not chunk:
                raise RuntimeError("cdp websocket closed")
            out += chunk
        return out

    def send_text(self, text: str) -> None:
        payload = text.encode("utf-8")
        mask = os.urandom(4)
        n = len(payload)
        header = bytearray([0x81])
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", n))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", n))
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def recv_text(self) -> str:
        while True:
            b1, b2 = self._read_exact(2)
            opcode = b1 & 0x0F
            masked = bool(b2 & 0x80)
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack("!H", self._read_exact(2))[0]
            elif n == 127:
                n = struct.unpack("!Q", self._read_exact(8))[0]
            mask = self._read_exact(4) if masked else None
            payload = self._read_exact(n)
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if opcode == 0x1:
                return payload.decode("utf-8", errors="replace")
            if opcode == 0x8:
                raise RuntimeError("cdp websocket closed")
            if opcode == 0x9:
                self._send_pong(payload)

    def _send_pong(self, payload: bytes) -> None:
        mask = os.urandom(4)
        n = len(payload)
        header = bytearray([0x8A, 0x80 | n])
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def close(self) -> None:
        try:
            self.sock.close()
        except Exception:
            pass


def _threads_tab():
    tabs = _json_get("http://127.0.0.1:9222/json/list")
    candidates = [
        t for t in tabs
        if "/messages" in str(t.get("url") or "")
        and "threads.com" in str(t.get("url") or "")
        and t.get("webSocketDebuggerUrl")
    ]
    if not candidates:
        raise RuntimeError("Threads Messages tab not found")
    return candidates[0]


def _eval(ws: _WS, expression: str, call_id: int):
    payload = {
        "id": call_id,
        "method": "Runtime.evaluate",
        "params": {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
        },
    }
    ws.send_text(json.dumps(payload, separators=(",", ":")))
    while True:
        msg = json.loads(ws.recv_text())
        if msg.get("id") != call_id:
            continue
        if "error" in msg:
            raise RuntimeError("CDP Runtime.evaluate failed")
        result = (((msg.get("result") or {}).get("result") or {}).get("value"))
        return result


def inspect_threads_tabs() -> dict:
    tabs = _json_get("http://127.0.0.1:9222/json/list")
    found = []
    for tab in tabs:
        url = str(tab.get("url") or "")
        if "threads.com" in url and "/messages" in url:
            found.append({"title": str(tab.get("title") or "")[:500], "url": url[:2000]})
    return {"threads_tabs": found, "count": len(found), "transport": "chrome-cdp"}


def read_visible_threads_messages(max_chars: int = 30000, username: str | None = None) -> dict:
    limit = max(1000, min(int(max_chars), 30000))
    tab = _threads_tab()
    ws = _WS(str(tab["webSocketDebuggerUrl"]))
    try:
        if username:
            click_expr = """(()=>{const q=%s;const els=[...document.querySelectorAll('a,button,div[role=button]')];const e=els.find(x=>((x.innerText||'').trim()).includes(q));if(!e)return 'NOT_FOUND';e.click();return 'CLICKED';})()""" % json.dumps(username)
            clicked = _eval(ws, click_expr, 1)
            if clicked != "CLICKED":
                return {"found": False, "url": str(tab.get("url") or "")[:2000], "visible_text": "", "conversation": username, "reason": "conversation_not_found", "transport": "chrome-cdp"}
            time.sleep(2)
        read_expr = f"(()=>{{const m=document.querySelector('main');const s=(m?m.innerText:document.body.innerText)||'';return s.slice(0,{limit});}})()"
        text = str(_eval(ws, read_expr, 2) or "")
        current_url = str(_eval(ws, "location.href", 3) or tab.get("url") or "")
        return {
            "found": bool(text),
            "url": current_url[:2000],
            "visible_text": text[:limit],
            "conversation": username,
            "transport": "chrome-cdp",
        }
    finally:
        ws.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--read", action="store_true")
    ap.add_argument("--conversation")
    ap.add_argument("--max-chars", type=int, default=30000)
    args = ap.parse_args()
    result = read_visible_threads_messages(args.max_chars, args.conversation) if args.read else inspect_threads_tabs()
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
