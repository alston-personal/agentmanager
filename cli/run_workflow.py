#!/usr/bin/env python3
"""
cli/run_workflow.py — Thin CLI entrypoint for Agent OS.

This file has ONE job: parse the command and dispatch to the registry.
All business logic lives in actions/*.py.
All formatting lives in agent_core/renderer.py.

Usage:
    python3 cli/run_workflow.py <command> [args...] [--flag value]

Examples:
    python3 cli/run_workflow.py status
    python3 cli/run_workflow.py report --project openclaw --summary "Fixed auth"
    python3 cli/run_workflow.py ecosystem-report
    python3 cli/run_workflow.py list
"""
import sys
import os

# Ensure the project root is on the path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from agent_core.config import load_env
load_env()

from agent_core.context import RuntimeContext
from agent_core.errors import AgentOSError
from agent_core.renderer import render_terminal

# Import all action modules so they self-register with the registry
import actions.status           # noqa: F401
import actions.report           # noqa: F401
import actions.ecosystem_report # noqa: F401
import actions.snapshot         # noqa: F401

from agent_core.registry import registry


def main() -> int:
    args = sys.argv[1:]

    # --- Handle built-ins that don't go through the registry ---
    if not args or args[0] in ("-h", "--help"):
        _print_help()
        return 0

    if args[0] == "list":
        for meta in sorted(registry.list_commands(), key=lambda m: m.name):
            aliases = f" ({', '.join('/' + a for a in meta.aliases)})" if meta.aliases else ""
            print(f"  /{meta.name:<20} {meta.description}{aliases}")
        return 0

    # --- Parse command and context ---
    command = args[0].lstrip("/")
    ctx = RuntimeContext.from_argv(args[1:])
    verbose = ctx.flags.get("verbose") or ctx.flags.get("v")

    # --- Dispatch ---
    try:
        result = registry.dispatch(command, ctx)
    except AgentOSError as e:
        print(str(e), file=sys.stderr)
        return e.exit_code
    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        if verbose:
            import traceback
            traceback.print_exc()
        return 99

    # --- Render ---
    print(render_terminal(result, verbose=bool(verbose)))
    return result.exit_code


def _print_help() -> None:
    print("🤖 Agent OS CLI")
    print("  Usage: run_workflow.py <command> [--flag value]")
    print()
    print("  Commands:")
    for meta in sorted(registry.list_commands(), key=lambda m: m.name):
        print(f"    /{meta.name:<20} {meta.description}")
    print()
    print("  Global flags:")
    print("    --project <id>     Target project (or set AGENT_PROJECT env var)")
    print("    --verbose          Show debug payload")


if __name__ == "__main__":
    raise SystemExit(main())
