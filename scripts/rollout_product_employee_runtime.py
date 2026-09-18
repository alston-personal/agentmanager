from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Mapping

from agentos_node.runtime_converge_action_relay import ActionRelayRuntimeConvergeDispatcher


ALLOWED_REPOSITORY = "alston-personal/agentmanager"
ALLOWED_REF = "refs/heads/core/integration"
SOURCE_REF = "core/integration"
NODE_ID = "oracle-core-node"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def build_request(env: Mapping[str, str]) -> dict[str, Any]:
    repository = str(env.get("GITHUB_REPOSITORY") or "").strip()
    ref = str(env.get("GITHUB_REF") or "").strip()
    sha = str(env.get("GITHUB_SHA") or "").strip()
    if repository != ALLOWED_REPOSITORY:
        raise RuntimeError("product_employee_rollout_repository_not_allowed")
    if ref != ALLOWED_REF:
        raise RuntimeError("product_employee_rollout_ref_not_allowed")
    if SHA_RE.fullmatch(sha) is None:
        raise RuntimeError("product_employee_rollout_sha_invalid")
    return {
        "schema": "agentos.runtime-converge-request/v1",
        "request_id": f"product-employee-rollout-{sha}",
        "node_id": NODE_ID,
        "repository": ALLOWED_REPOSITORY,
        "source_ref": SOURCE_REF,
        "source_commit": sha,
    }


def _safe_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {
        "schema",
        "ok",
        "action",
        "task_id",
        "request_id",
        "node_id",
        "repository",
        "source_ref",
        "source_commit",
        "previous_commit",
        "resulting_commit",
        "health",
        "rollback",
        "status",
        "classification",
        "idempotent",
        "credential_exposed",
        "observed_at",
    }
    return {key: receipt.get(key) for key in sorted(allowed) if key in receipt}


def rollout(
    env: Mapping[str, str] | None = None,
    *,
    dispatcher: ActionRelayRuntimeConvergeDispatcher | None = None,
    timeout_seconds: int = 420,
    poll_seconds: float = 1.0,
) -> dict[str, Any]:
    environment = dict(os.environ if env is None else env)
    request = build_request(environment)
    runtime = dispatcher or ActionRelayRuntimeConvergeDispatcher()
    submission = runtime.submit(request=request)
    if submission.get("ok") is not True:
        raise RuntimeError("product_employee_rollout_submission_unknown")
    task_id = str(submission.get("task_id") or "").strip()
    if not task_id:
        raise RuntimeError("product_employee_rollout_task_id_missing")

    deadline = time.monotonic() + int(timeout_seconds)
    receipt = None
    while time.monotonic() < deadline:
        receipt = runtime.inspect(task_id)
        if receipt is not None:
            status = str(receipt.get("status") or "")
            if status in {"completed", "failed", "unknown"}:
                break
        time.sleep(max(0.05, float(poll_seconds)))

    if receipt is None:
        raise RuntimeError("product_employee_rollout_receipt_timeout")
    safe = _safe_receipt(receipt)
    if safe.get("credential_exposed") is not False:
        raise RuntimeError("product_employee_rollout_credential_boundary_invalid")
    if safe.get("status") != "completed" or safe.get("ok") is not True:
        raise RuntimeError(f"product_employee_rollout_failed:{safe.get('classification') or 'unknown'}")
    if safe.get("source_commit") != request["source_commit"]:
        raise RuntimeError("product_employee_rollout_source_commit_mismatch")
    if safe.get("resulting_commit") != request["source_commit"]:
        raise RuntimeError("product_employee_rollout_resulting_commit_mismatch")
    if safe.get("health") != "passed":
        raise RuntimeError("product_employee_rollout_health_failed")
    return safe


def main() -> int:
    receipt = rollout()
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
