from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import platform
from pathlib import Path
from typing import Any

from agentos_node.social.web_dm import DirectMessageEvent, dedupe_new_events


def _root() -> Path:
    return Path(os.environ.get("AGENTOS_THREADS_WEB_DM_ROOT") or (Path.home() / ".local" / "share" / "agentos" / "social" / "threads-web-dm"))


def capability_ready() -> bool:
    if platform.system() != "Darwin":
        return False
    if importlib.util.find_spec("playwright") is None:
        return False
    chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    return chrome.is_file()


def _stable_id(*parts: str) -> str:
    raw = "\x1f".join(str(part or "") for part in parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def _parse_row(text: str) -> tuple[str | None, str | None, str]:
    import re
    username_re = re.compile(r"^[A-Za-z0-9._]{1,64}$")
    age_re = re.compile(r"^(?:\d+[smhdw]|\d+\s*(?:秒|分|分鐘|小時|天|週)|昨天|Yesterday)$", re.I)
    lines = [item.strip() for item in str(text or "").splitlines() if item.strip()]
    username = next((item.lstrip("@") for item in lines if username_re.fullmatch(item.lstrip("@"))), None)
    filtered = [
        item for item in lines
        if item not in {"·", "訊息", "Messages", "收件匣", "Inbox"} and not age_re.fullmatch(item)
    ]
    if username:
        filtered = [item for item in filtered if item.lstrip("@") != username]
    preview = filtered[-1] if filtered else None
    direction = "unknown"
    if preview:
        low = preview.lower()
        if low.startswith("you sent") or preview.startswith("你傳送了") or preview.startswith("你已傳送"):
            direction = "outbound"
        elif username:
            direction = "inbound"
    return username, preview, direction


def _load_state(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, ValueError, OSError):
        return {}


def _save_state(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    os.chmod(path, 0o600)


def read_threads_dm(account: str = "mio.milkcat") -> dict[str, Any]:
    if not capability_ready():
        raise RuntimeError("threads_gui_read_capability_unavailable")

    from playwright.sync_api import sync_playwright

    root = _root()
    profile = root / "browser-profile"
    state_path = root / "state.json"
    events_path = root / "events.jsonl"
    root.mkdir(parents=True, exist_ok=True)
    profile.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    os.chmod(profile, 0o700)

    state = _load_state(state_path)
    seen = {str(item) for item in state.get("seen_message_ids") or []}
    fresh: list[DirectMessageEvent] = []

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(profile),
            channel="chrome",
            headless=True,
            viewport={"width": 1280, "height": 900},
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://www.threads.com/messages", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1500)
            current_url = page.url
            if "login" in current_url or "accountscenter" in current_url:
                return {
                    "threads_gui_read_state": "LOGIN_REQUIRED",
                    "new_events": 0,
                    "inbound_events": 0,
                    "events": [],
                }

            events: list[DirectMessageEvent] = []
            seen_conversations: set[str] = set()
            rows = page.locator('[role="main"] [role="link"], [role="main"] a').all()
            for row in rows[:100]:
                try:
                    text = (row.inner_text(timeout=500) or "").strip()
                    href = row.get_attribute("href") or ""
                except Exception:
                    continue
                if not text or "/messages" not in href:
                    continue
                conversation_id = _stable_id(href)
                if conversation_id in seen_conversations:
                    continue
                seen_conversations.add(conversation_id)
                username, preview, direction = _parse_row(text)
                if not username or not preview or direction == "unknown":
                    continue
                events.append(
                    DirectMessageEvent(
                        platform="threads",
                        account_id=account,
                        conversation_id=conversation_id,
                        message_id=_stable_id(conversation_id, username, preview, direction),
                        actor_id=None,
                        actor_username=username,
                        text=preview,
                        timestamp=None,
                        direction=direction,
                    )
                )

            fresh = dedupe_new_events(events, seen)
            if fresh:
                with events_path.open("a", encoding="utf-8") as handle:
                    for event in fresh:
                        payload = event.to_dict()
                        payload["account_id"] = account
                        handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
                os.chmod(events_path, 0o600)

            seen.update(event.message_id for event in fresh)
            _save_state(
                state_path,
                {
                    "schema": "agentos.threads-web-dm-state/v1",
                    "account": account,
                    "seen_message_ids": sorted(seen)[-5000:],
                    "last_scan_new_count": len(fresh),
                },
            )
        finally:
            context.close()

    return {
        "threads_gui_read_state": "PASS",
        "new_events": len(fresh),
        "inbound_events": sum(1 for item in fresh if item.direction == "inbound"),
        "events": [item.to_dict() for item in fresh],
    }
