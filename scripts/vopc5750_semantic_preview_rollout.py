from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from agent_core.controller_service import ControllerService
from agent_core.realm_fabric import RealmFabricStore

NODE_ID = "vopc5750"
SOURCE_REF = "090c61ca562a275cb38803145526e6a5e411bbfb"
SCHEMA = "agentos.vopc5750-semantic-preview-rollout/v1"


def wait_receipt(store: RealmFabricStore, task_id: str, timeout: int = 240) -> dict[str, Any] | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        receipt = store.get_receipt(task_id)
        if receipt:
            return receipt
        time.sleep(2)
    return None


def dispatch(controller: ControllerService, store: RealmFabricStore, action: str, payload: dict[str, Any], timeout: int = 240) -> dict[str, Any]:
    queued = controller.dispatch({
        "schema": "agentos.controller-dispatch/v0.1",
        "node_id": NODE_ID,
        "action": action,
        "payload": payload,
    })
    task_id = str(queued["task_id"])
    receipt = wait_receipt(store, task_id, timeout)
    return {"task_id": task_id, "receipt": receipt}


def run(output: Path) -> dict[str, Any]:
    store = RealmFabricStore()
    controller = ControllerService(store)
    evidence: dict[str, Any] = {
        "schema": SCHEMA,
        "node_id": NODE_ID,
        "source_ref": SOURCE_REF,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "checks": {},
    }

    install = r"""
$ErrorActionPreference='Stop'
$uri='https://raw.githubusercontent.com/alston-personal/agentmanager/090c61ca562a275cb38803145526e6a5e411bbfb/install-agentos.ps1'
$target=Join-Path $env:TEMP 'agentos-rollout-semantic-preview.ps1'
$runner=Join-Path $env:TEMP 'agentos-rollout-semantic-preview-runner.ps1'
Invoke-WebRequest -UseBasicParsing -Headers @{'Cache-Control'='no-cache'} -Uri $uri -OutFile $target
@"
$ErrorActionPreference='Stop'
& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File '$target' -SourceRef '090c61ca562a275cb38803145526e6a5e411bbfb' *> '$env:TEMP\agentos-semantic-preview-update.log'
exit $LASTEXITCODE
"@ | Set-Content -Encoding UTF8 -LiteralPath $runner

$taskName='AgentOS Deferred Semantic Preview Update'
$existing=Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if($existing){ Unregister-ScheduledTask -TaskName $taskName -Confirm:$false }
$action=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $runner + '"')
$trigger=New-ScheduledTaskTrigger -Once -At (Get-Date).AddSeconds(12)
$settings=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -Hidden
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Output 'AGENTOS_DEFERRED_UPDATE_SCHEDULED'
exit 0
"""
    deploy = dispatch(
        controller,
        store,
        "shell.exec",
        {
            "executable": "powershell",
            "argv": ["-NoProfile", "-NonInteractive", "-Command", install],
            "cwd": r"C:\Users\alston.huang\AgentOS",
            "timeout_seconds": 220,
        },
        timeout=250,
    )
    deploy_receipt = deploy.get("receipt") or {}
    evidence["checks"]["rollout"] = {
        "task_id": deploy.get("task_id"),
        "receipt_ok": bool(deploy_receipt.get("ok")),
        "returncode": deploy_receipt.get("returncode"),
        "error": deploy_receipt.get("error"),
        "stdout_tail": str(deploy_receipt.get("stdout") or "")[-4000:],
        "stderr_tail": str(deploy_receipt.get("stderr") or "")[-2000:],
        "deferred_update_scheduled": "AGENTOS_DEFERRED_UPDATE_SCHEDULED" in str(deploy_receipt.get("stdout") or ""),
    }
    if (
        not deploy_receipt
        or not deploy_receipt.get("ok")
        or deploy_receipt.get("returncode") != 0
        or "AGENTOS_DEFERRED_UPDATE_SCHEDULED" not in str(deploy_receipt.get("stdout") or "")
    ):
        evidence["overall"] = "FAIL_ROLLOUT"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return evidence

    # The current Thin Client must return this scheduling receipt before the deferred updater stops it.
    # Allow time for the one-shot updater, supervisor restart, and a fresh heartbeat.
    time.sleep(45)

    preview = dispatch(
        controller,
        store,
        "desktop.semantic_preview",
        {"max_pixels": 160000},
        timeout=90,
    )
    receipt = preview.get("receipt") or {}
    preview_data = receipt.get("preview") or {}
    evidence["checks"]["semantic_preview"] = {
        "task_id": preview.get("task_id"),
        "receipt_ok": bool(receipt.get("ok")),
        "error": receipt.get("error"),
        "schema": receipt.get("schema"),
        "preview_schema": receipt.get("schema"),
        "foreground": receipt.get("foreground"),
        "state_hash": receipt.get("state_hash"),
        "read_only": receipt.get("read_only"),
        "mode": receipt.get("mode"),
        "denied_surfaces": receipt.get("denied_surfaces"),
        "preview": {
            "mime_type": preview_data.get("mime_type"),
            "width": preview_data.get("width"),
            "height": preview_data.get("height"),
            "bytes": preview_data.get("bytes"),
            "sha256": preview_data.get("sha256"),
        },
    }
    evidence["overall"] = "PASS" if receipt.get("ok") and receipt.get("read_only") is True and receipt.get("state_hash") else "FAIL_PREVIEW"
    evidence["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return evidence


if __name__ == "__main__":
    target = Path(".agentos/evidence/vopc5750-semantic-preview-rollout-current.json")
    result = run(target)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result.get("overall") == "PASS" else 2)
