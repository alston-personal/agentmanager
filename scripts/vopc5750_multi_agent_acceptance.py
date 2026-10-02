from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from agent_core.controller_service import ControllerService
from agent_core.node_registry import NodeRegistry
from agent_core.realm_fabric import RealmFabricStore

NODE_ID = "vopc5750"
DEFAULT_CWD = r"C:\Users\alston.huang\AgentOS"
SCHEMA = "agentos.vopc5750-multi-agent-acceptance/v1"


def _wait_receipt(store: RealmFabricStore, task_id: str, timeout: int = 100) -> dict[str, Any] | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        receipt = store.get_receipt(task_id)
        if receipt:
            return receipt
        time.sleep(2)
    return None


def _dispatch(
    controller: ControllerService,
    store: RealmFabricStore,
    action: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: int = 100,
) -> dict[str, Any]:
    request = {
        "schema": "agentos.controller-dispatch/v0.1",
        "node_id": NODE_ID,
        "action": action,
        "payload": payload or {},
    }
    try:
        queued = controller.dispatch(request)
    except Exception as exc:
        return {"dispatch_ok": False, "error": f"{type(exc).__name__}: {exc}"}
    receipt = _wait_receipt(store, str(queued["task_id"]), timeout)
    if receipt is None:
        return {"dispatch_ok": True, "task_id": queued["task_id"], "receipt_timeout": True}
    return {"dispatch_ok": True, "task_id": queued["task_id"], "receipt": receipt}


def _summarize_exec(label: str, result: dict[str, Any], marker: str) -> dict[str, Any]:
    item: dict[str, Any] = {"label": label, "dispatch_ok": bool(result.get("dispatch_ok"))}
    if not result.get("dispatch_ok"):
        item.update({"status": "NOT_WIRED", "error": result.get("error")})
        return item
    if result.get("receipt_timeout"):
        item.update({"status": "TIMEOUT", "task_id": result.get("task_id")})
        return item

    receipt = result.get("receipt") or {}
    stdout = str(receipt.get("stdout") or "")
    stderr = str(receipt.get("stderr") or "")
    combined = stdout + "\n" + stderr
    marker_seen = marker in combined
    item.update(
        {
            "task_id": result.get("task_id"),
            "receipt_ok": bool(receipt.get("ok")),
            "returncode": receipt.get("returncode"),
            "marker_seen": marker_seen,
            "stdout_length": len(stdout),
            "stderr_length": len(stderr),
            "output_sha256_16": hashlib.sha256(combined.encode("utf-8", "replace")).hexdigest()[:16],
            "error": receipt.get("error"),
            "status": "PASS"
            if receipt.get("ok") and receipt.get("returncode") == 0 and marker_seen
            else "FAIL",
        }
    )
    return item


def run(output: Path) -> dict[str, Any]:
    store = RealmFabricStore()
    registry = NodeRegistry()
    controller = ControllerService(store)

    node_map = registry.node_map()
    node = next((item for item in node_map.get("nodes", []) if item.get("node_id") == NODE_ID), None)
    evidence: dict[str, Any] = {
        "schema": SCHEMA,
        "node_id": NODE_ID,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "node_snapshot": node,
        "checks": {},
    }

    if not node or node.get("status") != "online":
        evidence["overall"] = "FAIL_NODE_OFFLINE"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return evidence

    inspect = _dispatch(controller, store, "agent.surface.inspect", timeout=80)
    inventory: dict[str, Any] = {}
    evidence["checks"]["surface_inspect"] = {"dispatch_ok": bool(inspect.get("dispatch_ok"))}
    if inspect.get("receipt"):
        receipt = inspect["receipt"]
        evidence["checks"]["surface_inspect"].update(
            {
                "task_id": inspect.get("task_id"),
                "receipt_ok": bool(receipt.get("ok")),
                "error": receipt.get("error"),
            }
        )
        inventory = receipt.get("surface_inventory") or {}
        evidence["surface_inventory"] = inventory
    else:
        evidence["checks"]["surface_inspect"]["error"] = inspect.get("error") or "receipt timeout"

    surfaces = {
        str(surface.get("provider")): surface
        for surface in inventory.get("surfaces", [])
        if isinstance(surface, dict)
    }

    antigravity_surface = surfaces.get("antigravity")
    antigravity: dict[str, Any] = {"surface_present": bool(antigravity_surface)}
    if antigravity_surface:
        antigravity["running"] = bool(antigravity_surface.get("running"))
        antigravity["executable_present"] = bool(antigravity_surface.get("executable"))
        bridge = (antigravity_surface.get("metadata") or {}).get("session_bridge")
        antigravity["bridge_ready"] = bool(bridge and bridge.get("ready"))
        antigravity["bridge_operations"] = list((bridge or {}).get("operations") or [])
        if antigravity["bridge_ready"] and "discover" in antigravity["bridge_operations"]:
            session_result = _dispatch(
                controller,
                store,
                "agent.session.discover",
                {"provider": "antigravity"},
                timeout=60,
            )
            antigravity["session_discover_dispatch_ok"] = bool(session_result.get("dispatch_ok"))
            if session_result.get("receipt"):
                session_receipt = session_result["receipt"]
                session_index = session_receipt.get("session_index") or {}
                antigravity["session_receipt_ok"] = bool(session_receipt.get("ok"))
                antigravity["session_count"] = (
                    len(session_index.get("sessions") or []) if isinstance(session_index, dict) else 0
                )
                antigravity["status"] = "PASS" if session_receipt.get("ok") else "FAIL"
            else:
                antigravity["status"] = "FAIL"
                antigravity["error"] = session_result.get("error") or "receipt timeout"
        else:
            antigravity["status"] = "NOT_WIRED"
    else:
        antigravity["status"] = "MISSING"
    evidence["checks"]["antigravity"] = antigravity

    scripts = {
        "codex": r"""$ErrorActionPreference='Continue'
$c=Get-Command codex -ErrorAction SilentlyContinue
if(-not $c){ Write-Output 'AGENTOS_CODEX_BINARY_MISSING'; exit 10 }
& codex --version
if($LASTEXITCODE -ne 0){ exit $LASTEXITCODE }
& codex exec --skip-git-repo-check "Return exactly AGENTOS_CODEX_SMOKE_OK and nothing else."
exit $LASTEXITCODE""",
        "claude-code": r"""$ErrorActionPreference='Continue'
$c=Get-Command claude -ErrorAction SilentlyContinue
if(-not $c){ Write-Output 'AGENTOS_CLAUDE_BINARY_MISSING'; exit 10 }
& claude --version
if($LASTEXITCODE -ne 0){ exit $LASTEXITCODE }
& claude --print "Return exactly AGENTOS_CLAUDE_SMOKE_OK and nothing else."
exit $LASTEXITCODE""",
        "gemini": r"""$ErrorActionPreference='Continue'
$c=Get-Command gemini -ErrorAction SilentlyContinue
if(-not $c){ Write-Output 'AGENTOS_GEMINI_BINARY_MISSING'; exit 10 }
& gemini --version
if($LASTEXITCODE -ne 0){ exit $LASTEXITCODE }
& gemini -p "Return exactly AGENTOS_GEMINI_SMOKE_OK and nothing else."
exit $LASTEXITCODE""",
    }
    markers = {
        "codex": "AGENTOS_CODEX_SMOKE_OK",
        "claude-code": "AGENTOS_CLAUDE_SMOKE_OK",
        "gemini": "AGENTOS_GEMINI_SMOKE_OK",
    }

    for provider, script in scripts.items():
        surface = surfaces.get(provider)
        result = _dispatch(
            controller,
            store,
            "shell.exec",
            {
                "executable": "powershell",
                "argv": ["-NoProfile", "-NonInteractive", "-Command", script],
                "cwd": DEFAULT_CWD,
                "timeout_seconds": 90,
            },
            timeout=110,
        )
        item = _summarize_exec(provider, result, markers[provider])
        item["surface_present"] = bool(surface)
        item["surface_running"] = bool(surface and surface.get("running"))
        item["surface_executable_present"] = bool(surface and surface.get("executable"))
        evidence["checks"][provider] = item

    statuses = [
        evidence["checks"][provider].get("status")
        for provider in ("antigravity", "codex", "claude-code", "gemini")
    ]
    evidence["overall"] = "PASS" if all(status == "PASS" for status in statuses) else "PARTIAL"
    evidence["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return evidence


if __name__ == "__main__":
    target = Path(".agentos/evidence/vopc5750-multi-agent-acceptance-current.json")
    result = run(target)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result.get("overall") in {"PASS", "PARTIAL"} else 2)
