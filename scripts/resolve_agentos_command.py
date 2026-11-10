#!/usr/bin/env python3
"""Resolve registered AgentOS slash commands into ONE intents.

Client-side compiler, not an executor: no arbitrary local subprocess or
caller-defined executable. ONE must independently authorize and route.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

REGISTRY=Path(__file__).resolve().parents[1]/".agentos"/"commands"
SCHEMA="agentos.realm-command/v0.1"
INTENT_SCHEMA="agentos.command-intent/v1"
NAME_PATTERN=re.compile(r"/[a-z][a-z0-9-]{0,63}\Z")

def resolve_command(command: str, *, registry: Path=REGISTRY) -> dict:
    if not isinstance(command,str) or not NAME_PATTERN.fullmatch(command):
        raise ValueError("COMMAND_NAME_INVALID")
    path=registry/(command[1:]+".json")
    if not path.is_file() or path.is_symlink():
        raise ValueError("COMMAND_NOT_REGISTERED")
    record=json.loads(path.read_text(encoding="utf-8"))
    if (record.get("schema")!=SCHEMA or record.get("command")!=command
            or not isinstance(record.get("action"),str)
            or not re.fullmatch(r"[a-z][a-z0-9._-]{0,95}",record["action"])):
        raise ValueError("COMMAND_REGISTRY_INVALID")
    # Runner is descriptive metadata; never send user-specified argv to ONE.
    return {
        "schema":INTENT_SCHEMA,
        "command":command,
        "action":record["action"],
        "steward":record.get("steward"),
        "source_registry":".agentos/commands/"+path.name,
        "dispatch":{
            "schema":"agentos.runner-window-dispatch/v1",
            "capability":"agentos.command",
            "operation":"invoke",
            "payload":{"command":command,"command_action":record["action"]}
        },
        "authority":"ONE_CAPABILITY_AND_RUNTIME_AUTHORIZATION_REQUIRED"
    }

def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("command",help="registered slash command, e.g. /status-diff")
    args=parser.parse_args()
    print(json.dumps(resolve_command(args.command),ensure_ascii=False,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
