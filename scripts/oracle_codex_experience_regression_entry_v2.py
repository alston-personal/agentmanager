#!/usr/bin/env python3
"""Compatibility entry for #117 Codex Experience regression.

Codex has had multiple config-merge regressions around partial `-c mcp_servers.*`
overrides.  The #117 benchmark does not need to mutate/partially shadow the MCP
transport at all: baseline access is proven absent by the hydration receipt, while
the hydrated process must produce a new receipt.

This entry reuses the v1 scorer/evidence contract but replaces only the process
launcher so both fresh processes load the complete installed Codex config.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from scripts import oracle_codex_experience_regression as regression


def run_codex(exe: Path, *, hydrated: bool, timeout: int) -> dict[str, object]:
    argv = [
        str(exe),
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--color",
        "never",
        regression.prompt(hydrated=hydrated),
    ]
    with tempfile.TemporaryDirectory(
        prefix=f"agentos-exp117-codex-{'hydrated' if hydrated else 'baseline'}-"
    ) as tmp:
        try:
            proc = subprocess.run(
                argv,
                cwd=tmp,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                env={**os.environ, "CI": "1"},
                check=False,
            )
            return {
                "returncode": proc.returncode,
                "timed_out": False,
                "stdout": proc.stdout[-12000:],
                "stderr_tail": proc.stderr[-3000:],
                "argv_family": "codex exec --sandbox read-only (complete installed MCP config)",
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "returncode": None,
                "timed_out": True,
                "stdout": (exc.stdout or "")[-12000:] if isinstance(exc.stdout, str) else "",
                "stderr_tail": (exc.stderr or "")[-3000:] if isinstance(exc.stderr, str) else "",
                "argv_family": "codex exec --sandbox read-only (complete installed MCP config)",
            }


def _output_arg() -> Path | None:
    for index, value in enumerate(sys.argv[:-1]):
        if value == "--output":
            return Path(sys.argv[index + 1])
    return None


def _correct_method_evidence(path: Path | None) -> None:
    if path is None or not path.is_file():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    method = payload.get("method")
    if isinstance(method, dict):
        method["baseline"] = (
            "fresh Codex process + empty cwd; complete installed MCP config; prompt forbids all tool calls; "
            "Experience non-access is independently required by an unchanged hydration receipt"
        )
        method["hydrated"] = (
            "independent fresh Codex process + empty cwd; complete installed MCP config; "
            "must call agentos-experience.one_experience_hydrate and produce a new sanitized receipt"
        )
    payload["config_override_used"] = False
    payload["baseline_experience_server_visibility_note"] = (
        "The MCP server definition may be visible to the baseline harness, but no Experience payload is accepted "
        "unless the hydration tool is called; an unchanged receipt is an acceptance requirement."
    )
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    regression.run_codex = run_codex
    rc = regression.main()
    _correct_method_evidence(_output_arg())
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
