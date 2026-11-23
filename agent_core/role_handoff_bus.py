"""
AgentOS Role Task Handoff & Priority ACK Bus
執掌:
1. 實裝跨角色任務交接 (Handoff Envelope)。
2. 雙向確認回執 (ACK Handshake): 上一手發出 (DISPATCHED) -> 下一手簽收 (ACKNOWLEDGED)。
3. 優先權佇列 (Priority Queue): 依 Priority Weight (P0 > P1 > ... > P9) 動態排序排隊。
4. 狀態機: DISPATCHED -> ACKNOWLEDGED -> IN_PROGRESS -> COMPLETED
"""

from __future__ import annotations

import json
import os
import fcntl
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

AGENT_DATA_ROOT = Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
HANDOFF_BUS_FILE = AGENT_DATA_ROOT / "runtime" / "role_handoff_bus.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_bus_file() -> None:
    HANDOFF_BUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not HANDOFF_BUS_FILE.is_file():
        init_data = {
            "schema": "agentos.role-handoff-bus/v1",
            "updated_at": utc_now_iso(),
            "tasks": []
        }
        HANDOFF_BUS_FILE.write_text(json.dumps(init_data, indent=2, ensure_ascii=False), encoding="utf-8")


def dispatch_task(
    source_role: str,
    target_role: str,
    title: str,
    payload: Dict[str, Any],
    priority: str = "P5",
    priority_weight: int = 50,
    task_id: Optional[str] = None,
    callback: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """上一手發出任務至交接總線 (DISPATCHED)，可選帶入宣告式 callback 目標"""
    _ensure_bus_file()
    
    if not task_id:
        ts_slug = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        task_id = f"handoff-{source_role}-to-{target_role}-{ts_slug}"

    envelope = {
        "schema": "agentos.role-task-handoff/v1",
        "task_id": task_id,
        "priority": priority,
        "priority_weight": priority_weight,
        "source_role": source_role,
        "target_role": target_role,
        "created_at": utc_now_iso(),
        "status": "DISPATCHED",
        "progress": {
            "percent": 0,
            "stage": "DISPATCHED",
            "message": "Task dispatched to handoff bus",
            "updated_at": utc_now_iso()
        },
        "callback": callback,
        "payload": {
            "title": title,
            **payload
        },
        "dispatched_receipt": {
            "dispatched_by": source_role,
            "timestamp": utc_now_iso()
        },
        "ack_receipt": None,
        "completed_receipt": None
    }

    with open(HANDOFF_BUS_FILE, "r+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            content = f.read()
            data = json.loads(content) if content else {"tasks": []}
            data.setdefault("tasks", []).append(envelope)
            data["updated_at"] = utc_now_iso()
            f.seek(0)
            f.truncate(0)
            f.write(json.dumps(data, indent=2, ensure_ascii=False))
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)

    return envelope


def _role_matches(target_declared: str, caller_role: str) -> bool:
    """判斷角色是否匹配，支援 canonical id (sector.paw)、slug (sector-paw)、別名 (the-paw / paw)"""
    t_clean = (target_declared or "").strip().lower()
    c_clean = (caller_role or "").strip().lower()
    if t_clean == c_clean:
        return True
    
    t_slug = t_clean.replace(".", "-")
    c_slug = c_clean.replace(".", "-")
    if t_slug == c_slug:
        return True

    t_tail = t_clean.split(".")[-1].replace("the-", "").replace("sector-", "").replace("system-", "").replace("governance-", "")
    c_tail = c_clean.split(".")[-1].replace("the-", "").replace("sector-", "").replace("system-", "").replace("governance-", "")
    return t_tail == c_tail


def acknowledge_tasks_for_role(target_role: str) -> List[Dict[str, Any]]:
    """下一手收到通知，簽收所有指向自己的 DISPATCHED 任務 (回傳 ACK 回執，置入角色專屬 Priority 隊列)"""
    _ensure_bus_file()
    acknowledged = []

    with open(HANDOFF_BUS_FILE, "r+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            content = f.read()
            data = json.loads(content) if content else {"tasks": []}
            tasks = data.get("tasks", [])

            for t in tasks:
                if _role_matches(t.get("target_role", ""), target_role) and t.get("status") == "DISPATCHED":
                    t["status"] = "ACKNOWLEDGED"
                    t["ack_receipt"] = {
                        "received_by": target_role,
                        "ack_at": utc_now_iso(),
                        "queue_state": "QUEUED_BY_PRIORITY"
                    }
                    acknowledged.append(t)

            if acknowledged:
                data["updated_at"] = utc_now_iso()
                f.seek(0)
                f.truncate(0)
                f.write(json.dumps(data, indent=2, ensure_ascii=False))
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)

    return acknowledged


def get_prioritized_queue_for_role(role_id: str) -> List[Dict[str, Any]]:
    """下一手依權重優先級 (priority_weight 大到小) 獲取自己的待辦佇列"""
    _ensure_bus_file()
    try:
        data = json.loads(HANDOFF_BUS_FILE.read_text(encoding="utf-8"))
        tasks = data.get("tasks", [])
    except Exception:
        return []

    role_tasks = []
    for t in tasks:
        if _role_matches(t.get("target_role", ""), role_id) and t.get("status") in ("ACKNOWLEDGED", "IN_PROGRESS"):
            role_tasks.append(t)

    # 權重由大到小排序 (高優先級優先處理)
    role_tasks.sort(key=lambda x: (x.get("priority_weight", 50), x.get("created_at", "")), reverse=True)
    return role_tasks


def update_task_progress(
    task_id: str,
    stage: str,
    percent: int,
    message: str,
    updated_by: Optional[str] = None
) -> bool:
    """Runtime 更新任務執行進度與階段心跳 (Progress Tick)"""
    _ensure_bus_file()
    updated = False

    with open(HANDOFF_BUS_FILE, "r+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            content = f.read()
            data = json.loads(content) if content else {"tasks": []}
            for t in data.get("tasks", []):
                if t.get("task_id") == task_id:
                    if t.get("status") in ("DISPATCHED", "ACKNOWLEDGED"):
                        t["status"] = "IN_PROGRESS"
                    t["progress"] = {
                        "percent": max(0, min(100, int(percent))),
                        "stage": stage,
                        "message": message,
                        "updated_by": updated_by,
                        "updated_at": utc_now_iso()
                    }
                    updated = True
                    break

            if updated:
                data["updated_at"] = utc_now_iso()
                f.seek(0)
                f.truncate(0)
                f.write(json.dumps(data, indent=2, ensure_ascii=False))
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)

    return updated


def get_task_progress(task_id: str) -> Optional[Dict[str, Any]]:
    """Executor 查詢任務執行進度、心跳與結果憑證"""
    _ensure_bus_file()
    try:
        data = json.loads(HANDOFF_BUS_FILE.read_text(encoding="utf-8"))
        for t in data.get("tasks", []):
            if t.get("task_id") == task_id:
                return {
                    "task_id": t.get("task_id"),
                    "status": t.get("status"),
                    "source_role": t.get("source_role"),
                    "target_role": t.get("target_role"),
                    "progress": t.get("progress"),
                    "created_at": t.get("created_at"),
                    "completed_receipt": t.get("completed_receipt")
                }
    except Exception:
        pass
    return None


def complete_handoff_task(task_id: str, completing_role: str, verdict: str, details: Dict[str, Any]) -> bool:
    """任務處理完成，標記閉環 (COMPLETED)，若包含 callback 則自動反向派發回執任務"""
    _ensure_bus_file()
    success = False
    callback_task_to_dispatch = None

    with open(HANDOFF_BUS_FILE, "r+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            content = f.read()
            data = json.loads(content) if content else {"tasks": []}
            for t in data.get("tasks", []):
                if t.get("task_id") == task_id:
                    t["status"] = "COMPLETED"
                    t["progress"] = {
                        "percent": 100,
                        "stage": "COMPLETED",
                        "message": f"Task finalized with verdict={verdict}",
                        "updated_by": completing_role,
                        "updated_at": utc_now_iso()
                    }
                    execution_receipt = {
                        "schema": "agentos.execution-receipt/v1",
                        "task_id": task_id,
                        "completed_by": completing_role,
                        "verdict": verdict,
                        "details": details,
                        "completed_at": utc_now_iso()
                    }
                    t["completed_receipt"] = execution_receipt
                    success = True

                    # 檢查是否有宣告式 callback
                    cb = t.get("callback")
                    if isinstance(cb, dict) and cb.get("target_role"):
                        callback_task_to_dispatch = {
                            "source_role": completing_role,
                            "target_role": cb.get("target_role"),
                            "title": f"回執回報: {t.get('payload', {}).get('title', task_id)}",
                            "priority": cb.get("priority", "P1"),
                            "priority_weight": cb.get("priority_weight", 90),
                            "payload": {
                                "original_task_id": task_id,
                                "intent": cb.get("intent", "task_completed_callback"),
                                "verdict": verdict,
                                "receipt": execution_receipt,
                                "caller_context": cb.get("context", {})
                            }
                        }
                    break

            if success:
                data["updated_at"] = utc_now_iso()
                f.seek(0)
                f.truncate(0)
                f.write(json.dumps(data, indent=2, ensure_ascii=False))
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)

    if success and callback_task_to_dispatch:
        dispatch_task(
            source_role=callback_task_to_dispatch["source_role"],
            target_role=callback_task_to_dispatch["target_role"],
            title=callback_task_to_dispatch["title"],
            payload=callback_task_to_dispatch["payload"],
            priority=callback_task_to_dispatch["priority"],
            priority_weight=callback_task_to_dispatch["priority_weight"]
        )

    return success
