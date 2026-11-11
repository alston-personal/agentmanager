"""ONE-governed, fixed H3 provider acceptance via the EXISTING Action Relay.

This is a bounded executor-job provider, not a generic GitHub workflow
dispatcher or an authority grant derived from Issue text. It first correlates
the recent manually launched smoke; if a recent run exists it NEVER dispatches
another potentially billable GPU session. Actual smoke acceptance remains
separate from an Actions dispatch acknowledgement.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from agentos_node import action_relay
from agentos_node.executor_job_adapter import DEFAULT_PROVIDERS

JOB_TYPE = "media.colab.h3.smoke"
EXECUTOR_CLASS = "oracle-colab-smoke-dispatcher"
REPOSITORY = "alston-personal/agentmanager"
WORKFLOW = "oracle-colab-minimax-h3-smoke.yml"
REF = "main"
FRESHNESS_HOURS = 24


def _parse_time(raw: Any) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except ValueError:
        return None


def _result(classification: str, *, work_id: str = "",
            successful: bool = False, authorized: bool = True,
            routable: bool = True, verdict: str = "BLOCKED",
            observed_head: str = "") -> dict[str, Any]:
    return {
        "executor_available": True,
        "routable": routable,
        "authorized": authorized,
        "successful": successful,
        "verdict": verdict,
        "classification": classification,
        "work_id": work_id,
        "observed_head": observed_head,
        "credential_exposed": False,
    }


def run_h3_smoke(request: Mapping[str, Any]) -> dict[str, Any]:
    # Exact semantic request was already validated by the executor adapter;
    # no repo/path/ref/inputs/commands are read from user-provided fields.
    if request.get("job_type") != JOB_TYPE:
        raise ValueError("unexpected H3 smoke job type")

    listed = action_relay._run([
        "/usr/bin/gh", "run", "list",
        "--repo", REPOSITORY,
        "--workflow", WORKFLOW,
        "--event", "workflow_dispatch",
        "--limit", "20",
        "--json", "databaseId,headSha,status,conclusion,url,createdAt",
    ], cwd=Path.home(), timeout=30)
    if listed["returncode"] != 0:
        return _result("COLAB_SMOKE_RUN_DISCOVERY_UNAVAILABLE", routable=False)
    try:
        rows = json.loads(listed.get("stdout") or "[]")
        if not isinstance(rows, list):
            raise ValueError("run list must be an array")
    except (ValueError, TypeError):
        return _result("COLAB_SMOKE_RUN_DISCOVERY_INVALID", routable=False)

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=FRESHNESS_HOURS)
    recent = [
        item for item in rows
        if isinstance(item, dict)
        and (when := _parse_time(item.get("createdAt"))) is not None
        and cutoff <= when <= now + timedelta(minutes=2)
        and isinstance(item.get("databaseId"), int)
        and item["databaseId"] > 0
    ]
    recent.sort(key=lambda item: item["createdAt"], reverse=True)
    if recent:
        item = recent[0]
        rid = "gh-actions-run-" + str(item["databaseId"])
        sha = str(item.get("headSha") or "")
        status = str(item.get("status") or "")
        conclusion = str(item.get("conclusion") or "")
        # Never rerun a pending, completed or ambiguous attempt merely because
        # ChatGPT/ONE did not see a terminal Receipt. This is the no-double-CU fence.
        if status != "completed":
            return _result("COLAB_SMOKE_EXISTING_RUN_ACTIVE", work_id=rid,
                           verdict="PENDING", observed_head=sha)
        if conclusion == "success":
            return _result("COLAB_SMOKE_ACTIONS_SUCCESS_NEEDS_RECEIPT",
                           work_id=rid, verdict="PENDING_RECEIPT", observed_head=sha)
        return _result("COLAB_SMOKE_EXISTING_RUN_FAILED_NEEDS_TRIAGE",
                       work_id=rid, verdict="BLOCKED", observed_head=sha)

    head = action_relay._run([
        "/usr/bin/gh", "api",
        "repos/" + REPOSITORY + "/commits/" + REF,
        "--jq", ".sha",
    ], timeout=30)
    expected = (head.get("stdout") or "").strip()
    if head["returncode"] != 0 or not re.fullmatch(r"[0-9a-f]{40}", expected):
        return _result("COLAB_SMOKE_HEAD_UNAVAILABLE", routable=False)

    # Reuse the existing immutable allowlist, credential ownership and run
    # correlation. No generic GitHub Action or fallback execution is exposed.
    receipt = action_relay._github_actions_dispatch({
        "repository": REPOSITORY,
        "workflow": WORKFLOW,
        "ref": REF,
        "expected_head_sha": expected,
        "inputs": {},
    })
    rid = receipt.get("run_id")
    if not receipt.get("ok") or not isinstance(rid, int) or rid <= 0:
        return _result("COLAB_SMOKE_DISPATCH_UNVERIFIED", observed_head=expected)
    return _result("COLAB_SMOKE_DISPATCH_ACK_ONLY",
                   work_id="gh-actions-run-" + str(rid),
                   successful=True, verdict="ACK_ONLY", observed_head=expected)


def register_colab_h3_smoke_provider() -> bool:
    if DEFAULT_PROVIDERS.get(JOB_TYPE) is not None:
        return True
    DEFAULT_PROVIDERS.register(
        job_type=JOB_TYPE,
        provider_id="agentos.oracle-colab.h3-smoke",
        executor_class=EXECUTOR_CLASS,
        handler=run_h3_smoke,
    )
    return True
