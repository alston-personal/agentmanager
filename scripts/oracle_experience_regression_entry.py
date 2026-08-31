#!/usr/bin/env python3
"""Safe entrypoint for Issue #117 Oracle experience regression.

The GitHub runner identity and the Antigravity executor identity intentionally differ.
Python tempfile directories default to 0700, so a fresh benchmark workspace must be
published through the existing `agentos` shared-group boundary before handing it to
the ubuntu-owned executor. This wrapper changes only benchmark workspace access; it
does not restart or reconfigure the live relay/Core runtime.
"""
from __future__ import annotations

from pathlib import Path

import scripts.oracle_experience_regression as regression
from agentos_node.antigravity_relay import share_relay_path

_original_run_antigravity = regression.run_antigravity


def _run_antigravity_shared(prompt: str, workspace: Path, timeout: int):
    share_relay_path(workspace, directory=True)
    return _original_run_antigravity(prompt, workspace, timeout)


def main() -> int:
    regression.run_antigravity = _run_antigravity_shared
    return regression.main()


if __name__ == "__main__":
    raise SystemExit(main())
