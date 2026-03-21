"""
agent_core/renderer.py
Output rendering layer for Agent OS.

Actions produce ActionResult objects. The renderer decides HOW to display them
based on the channel (terminal, telegram, etc.).
This keeps formatting concerns completely out of action business logic.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_core.registry import ActionResult


# ANSI colours for terminal output
_BOLD = "\033[1m"
_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_RESET = "\033[0m"


def render_terminal(result: "ActionResult", verbose: bool = False) -> str:
    """Render an ActionResult for terminal (stdout)."""
    lines = []

    if not result.success:
        lines.append(f"{_RED}❌ Command failed (exit {result.exit_code}){_RESET}")

    if result.warnings:
        for w in result.warnings:
            lines.append(f"{_YELLOW}⚠️  {w}{_RESET}")

    lines.append(result.output)

    if verbose and result.data:
        import json
        lines.append("\n--- debug payload ---")
        lines.append(json.dumps(result.data, indent=2, ensure_ascii=False, default=str))

    return "\n".join(lines)


def render_telegram(result: "ActionResult") -> str:
    """
    Render an ActionResult as a Telegram-safe message (no ANSI, markdown OK).
    Truncates at Telegram's 4096-char limit.
    """
    MAX_LEN = 4000  # leave room for status prefix

    prefix = "✅" if result.success else "❌"
    body = result.output

    if result.warnings:
        body = "\n".join(f"⚠️ {w}" for w in result.warnings) + "\n\n" + body

    message = f"{prefix} {body}"
    if len(message) > MAX_LEN:
        message = message[:MAX_LEN] + "\n…(truncated)"
    return message


def send_telegram(text: str) -> bool:
    """
    Send a message to the configured Telegram channel.
    Returns True on success, False on failure (non-fatal).
    Lazy-imports requests to avoid blocking on module load.
    """
    try:
        import requests
    except ImportError:
        return False

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHANNEL_ID")
    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
        return resp.status_code == 200
    except Exception:
        return False


def render_project_table(projects: list) -> str:
    """
    Render a list of ProjectRecord objects as a markdown table.
    Used by /status action.
    """
    HEALTH_ICON = {"fresh": "🟢", "stale": "🟡", "unknown": "⚪"}

    lines = [
        "| Project | Sector | P | Phase | Status | Health |",
        "| :--- | :---: | :---: | :---: | :--- | :---: |",
    ]
    for p in projects:
        icon = HEALTH_ICON.get(p.health.freshness, "⚪")
        lines.append(
            f"| **{p.project_id}** | {p.sector} | {p.priority} "
            f"| {p.phase} | {p.status} | {icon} {p.health.freshness} |"
        )
    return "\n".join(lines)
