"""Shared authority fence for mutable Executor work, at dispatch AND execution.

Only host-injected Git proof is admissible. A model may request a registered
job type, but cannot supply a source branch, fake verdict or exception flag.
"""
from __future__ import annotations

import re
from typing import Any

SHA = re.compile(r"[0-9a-f]{40}\Z")


def require_fresh_code_resume(spec: Any, probe: Any) -> None:
    if getattr(spec, "authority", None) != "bounded-code-fix":
        return
    if not callable(probe):
        raise ValueError("CODE_MAINLINE_PROBE_UNAVAILABLE")
    try:
        verdict = probe(spec)
    except Exception as exc:
        # Never expose remote URLs, local paths, tokens or provider internals.
        raise ValueError("CODE_MAINLINE_EVIDENCE_UNAVAILABLE") from exc
    if (
        not isinstance(verdict, dict)
        or verdict.get("schema") != "agentos.branch-resume-gate/v1"
        or verdict.get("kind") != "code"
        or verdict.get("status") != "MAINLINE_CURRENT"
        or verdict.get("allowed") is not True
        or verdict.get("main_ancestor_of_work") is not True
        or verdict.get("production_authorized") is not False
        or any(not isinstance(verdict.get(k), str) or not SHA.fullmatch(verdict[k])
               for k in ("main_sha", "work_sha", "merge_base_sha"))
        or verdict["main_sha"] != verdict["merge_base_sha"]
    ):
        raise ValueError("CODE_MAINLINE_RECONCILE_REQUIRED")
