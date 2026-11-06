#!/usr/bin/env python3
"""AgentOS Multi-Agent Channel Router.

Inspired by OpenMausBot's multi-bot channel routing and Jev decision primitives.
Allows human operators and external agents (ChatGPT, Gemini, Mobile) to communicate
with specialized AgentOS roles using natural language and `@role` mentions:

Examples:
  python3 scripts/agentos_channel.py "@paw report current progress"
  python3 scripts/agentos_channel.py "@cartographer verify world model"
  python3 scripts/agentos_channel.py "@atlas index project codebase"
  python3 scripts/agentos_channel.py "Check system health and pending approvals"
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

AGENTMANAGER_ROOT = Path("/home/ubuntu/agentmanager")
if str(AGENTMANAGER_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENTMANAGER_ROOT))

from scripts.agentos_remote_control import execute_oracle_local, submit_task

ROLE_MENTIONS = {
    "paw": "system.paw",
    "the-paw": "system.paw",
    "claw": "system.claw",
    "the-claw": "system.claw",
    "cartographer": "system.cartographer",
    "atlas": "system.atlas",
    "mnemosyne": "system.mnemosyne",
    "supervisor": "core.supervisor",
    "zeus": "system.zeus_writer",
    "zeus_writer": "system.zeus_writer",
    "venus": "system.venus_aesthetic",
    "iris": "system.iris_dns",
    "iris_dns": "system.iris_dns",
    "eunomia": "system.eunomia_port",
    "thales": "system.thales_academic",
    "chronicler": "system.chronicler",
    "arbiter": "system.arbiter",
    "atlast": "system.atlast",
}

KEYWORD_ROUTING = [
    (re.compile(r"\b(review|audit|inspect|verify|claw)\b", re.I), "system.claw"),
    (re.compile(r"\b(world model|resource|cartographer|topology)\b", re.I), "system.cartographer"),
    (re.compile(r"\b(index|search|atlas|find)\b", re.I), "system.atlas"),
    (re.compile(r"\b(memory|archive|history|mnemosyne)\b", re.I), "system.mnemosyne"),
    (re.compile(r"\b(write|novel|chapter|publish|zeus)\b", re.I), "system.zeus_writer"),
    (re.compile(r"\b(dns|nginx|domain|port|ssl|network|iris)\b", re.I), "system.iris_dns"),
    (re.compile(r"\b(supervisor|wake|daemon|queue)\b", re.I), "core.supervisor"),
]


def resolve_target(prompt: str) -> tuple[str, str, str]:
    """Parse prompt for @mentions or keyword intent to determine target role and clean goal."""
    # 1. Check for @mention
    mention_match = re.search(r"@([a-zA-Z0-9_\-]+)", prompt)
    if mention_match:
        tag = mention_match.group(1).lower()
        if tag in ROLE_MENTIONS:
            capability = ROLE_MENTIONS[tag]
            role_name = tag.replace("-", " ").title()
            clean_goal = prompt.replace(mention_match.group(0), "").strip()
            return role_name, capability, clean_goal

    # 2. Keyword fallback routing
    for pattern, cap in KEYWORD_ROUTING:
        if pattern.search(prompt):
            role_slug = cap.replace("system.", "").replace("core.", "")
            return role_slug.replace("_", " ").title(), cap, prompt.strip()

    # 3. Default to The Paw (Engineering Execution)
    return "The Paw", "system.paw", prompt.strip()


def dispatch_channel_message(prompt: str, *, local: bool = True) -> dict[str, Any]:
    role_name, capability, clean_goal = resolve_target(prompt)
    if not clean_goal:
        clean_goal = f"Status check and sync by {role_name}"

    print(f"\n💬 [AgentOS Channel] Routing to: {role_name} ({capability})")
    print(f"🎯 Goal: \"{clean_goal}\"")

    if local:
        receipt = execute_oracle_local(clean_goal, capability=capability)
        return {
            "channel": "general",
            "role": role_name,
            "capability": capability,
            "goal": clean_goal,
            "receipt": receipt,
        }
    else:
        res = submit_task(clean_goal, capability=capability)
        return {
            "channel": "general",
            "role": role_name,
            "capability": capability,
            "goal": clean_goal,
            "task": res.get("task"),
        }


def main():
    parser = argparse.ArgumentParser(description="AgentOS Multi-Agent Channel Router")
    parser.add_argument("prompt", nargs="?", help="Prompt to dispatch (e.g. '@paw check queue')")
    parser.add_argument("--remote", action="store_true", help="Submit asynchronously to Gateway instead of local execution")
    args = parser.parse_args()

    if not args.prompt:
        print("Usage: python3 scripts/agentos_channel.py \"<prompt with optional @role>\"")
        print("Examples:")
        print("  python3 scripts/agentos_channel.py \"@cartographer audit resources\"")
        print("  python3 scripts/agentos_channel.py \"@paw run verification\"")
        sys.exit(0)

    res = dispatch_channel_message(args.prompt, local=not args.remote)
    print("\n📬 Channel Response:")
    if "receipt" in res:
        receipt = res["receipt"]
        print(f"Role: {res['role']} | Executor: {receipt.get('executor_id')} | Status: {receipt.get('status')}")
        print(f"Receipt ID: {receipt.get('receipt_id')}")
        findings = receipt.get("findings", [])
        if findings:
            print("Findings:")
            for f in findings:
                print(f"  • {f}")
    elif "task" in res:
        task = res["task"]
        task_id = task.get("taskId") or task.get("id")
        task_status = task.get("status") or task.get("state")
        print(f"Role: {res['role']} | Task ID: {task_id} | State: {task_status}")


if __name__ == "__main__":
    main()
