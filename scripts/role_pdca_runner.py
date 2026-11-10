#!/usr/bin/env python3
"""AgentOS Universal Role PDCA Engine.

Implements the Base Role (core.root) Universal PDCA Contract:
Inherited by every active role:
  Plan  -> Hydrate Cognitive IR, select eligible unblocked work
  Do    -> Execute within capability grants & worktree boundary
  Check -> Independent verification by The Claw (Inspector PASS)
  Act   -> Commit receipts, advance cycle, atomically claim next eligible task (A -> B)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AGENT_DATA = Path("/home/ubuntu/agent-data")
AGENTMANAGER = Path("/home/ubuntu/agentmanager")
if str(AGENTMANAGER) not in sys.path:
    sys.path.insert(0, str(AGENTMANAGER))
GLOBAL_TODO = AGENT_DATA / "GLOBAL_TODO_LIST.md"
INCIDENT_QUEUE_FILE = AGENT_DATA / "runtime" / "incident_queue.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_paw_cycle(dry_run: bool = False) -> dict[str, Any]:
    paw_dir = AGENT_DATA / "personas" / "the-paw"
    ir_file = paw_dir / "ir" / "current.json"
    state_file = paw_dir / "pdca" / "state.json"
    events_file = paw_dir / "events" / "events.jsonl"
    activities_dir = paw_dir / "pdca" / "activities"
    activities_dir.mkdir(parents=True, exist_ok=True)

    if not ir_file.exists() or not state_file.exists():
        raise RuntimeError("The Paw PDCA workspace not initialized.")

    ir = json.loads(ir_file.read_text(encoding="utf-8"))
    state = json.loads(state_file.read_text(encoding="utf-8"))
    cycle = int(state.get("cycle", 1))

    print(f"🐾 [The Paw PDCA] Starting Cycle {cycle}...")
    print(f"🐾 [Plan] Hydrating Cognitive IR: {ir['cognitive_state']['identity_anchor']}")

    # --- 1. PLAN PHASE ---
    # Scan for actionable engineering tasks in GLOBAL_TODO_LIST.md
    selected_task = None
    todo_lines = []
    in_qualified_section = False
    completed_task_ids = set()

    if GLOBAL_TODO.exists():
        todo_content = GLOBAL_TODO.read_text(encoding="utf-8")
        todo_lines = todo_content.splitlines()

        # 先收集所有已完成的任務 ID
        import re
        for line in todo_lines:
            if line.startswith("- [x]"):
                for m in re.findall(r"\[(task\-[a-zA-Z0-9_\-]+)\]", line):
                    completed_task_ids.add(m)

        for idx, line in enumerate(todo_lines):
            if "## 🎯 Qualified Executable Tasks" in line:
                in_qualified_section = True
                continue
            if "## ⚠️ Blocked" in line or "## ✅ Completed" in line:
                in_qualified_section = False
                break
            if in_qualified_section and line.startswith("- [ ]"):
                # 檢查是否有前置任務依賴
                dep_match = re.search(r"前置:\s*([a-zA-Z0-9_\-]+)", line)
                if dep_match:
                    dep_id = dep_match.group(1).strip()
                    if dep_id.lower() != "none" and dep_id not in completed_task_ids:
                        # 前置未完成，跳過這條（防止隊頭阻塞），繼續尋找下一條合格任務
                        continue

                selected_task = {
                    "line_idx": idx,
                    "text": line.replace("- [ ]", "").strip(),
                    "type": "qualified_todo"
                }
                break

    if not selected_task:
        selected_task = {
            "line_idx": None,
            "text": "在席待命 (隊列無可執行的合格驗收任務)",
            "type": "idle"
        }

    work_id = f"paw-work-{cycle:04d}-{int(time.time())}"
    print(f"🐾 [Plan] Selected Work: {selected_task['text']} (Work ID: {work_id})")

    # --- 2. DO PHASE ---
    execution_result = {}
    if selected_task["type"] == "idle":
        execution_result = {
            "action": "idle",
            "status": "waiting_qualified_tasks",
            "details": "合格隊列為空，保持待命，拒絕執行無驗收要件之抽象任務。"
        }
    else:
        # Extract verification command from task
        import re
        verify_cmd = None
        cmd_match = re.search(r"驗收:\s*`([^`]+)`", selected_task["text"])
        if not cmd_match:
            cmd_match = re.search(r"`([^`]*(?:pytest|python3|npm|test|curl|node|ss|chmod|git|bash)[^`]+)`", selected_task["text"])
        if cmd_match:
            verify_cmd = cmd_match.group(1).strip()

        if cmd_match:
            verify_cmd = cmd_match.group(1).strip()

        # Determine target project working directory
        project_cwd = AGENTMANAGER
        target_tag = None
        for tag in re.findall(r"\[([a-zA-Z0-9_\-]+)\]", selected_task["text"]):
            candidate = Path(f"/home/ubuntu/{tag}")
            if candidate.is_dir():
                project_cwd = candidate
                target_tag = tag
                break
            elif (AGENT_DATA / "projects" / tag).is_dir():
                target_tag = tag

        # 建立健全執行環境變數 (含 .local/bin 與 venv)
        exec_env = os.environ.copy()
        exec_env["PATH"] = f"/home/ubuntu/.local/bin:/home/ubuntu/agentmanager/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:{exec_env.get('PATH', '')}"

        if verify_cmd:
            # 若指定了專案 tag 但本地代碼倉庫不存在（例如遠端節點專案）
            if target_tag and project_cwd == AGENTMANAGER and not (AGENTMANAGER / target_tag).is_dir():
                status_file = AGENT_DATA / "projects" / target_tag / "STATUS.md"
                if status_file.exists() and "Target Node" in status_file.read_text(encoding="utf-8"):
                    execution_result = {
                        "action": "remote_node_dispatch_required",
                        "command": verify_cmd,
                        "project": target_tag,
                        "details": f"專案 {target_tag} 宣告為跨節點/遠端專案，Oracle 本機無工作區，需透過 Realm 分派。",
                        "success": False
                    }
                    verify_cmd = None

        if verify_cmd:
            print(f"🐾 [Do] Executing verification command in {project_cwd}: {verify_cmd}")
            try:
                p_res = subprocess.run(
                    verify_cmd,
                    shell=True,
                    cwd=str(project_cwd),
                    env=exec_env,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                execution_result = {
                    "action": "verify_task",
                    "command": verify_cmd,
                    "cwd": str(project_cwd),
                    "exit_code": p_res.returncode,
                    "stdout": p_res.stdout.strip()[:200],
                    "stderr": p_res.stderr.strip()[:200],
                    "success": p_res.returncode == 0
                }
            except Exception as exc:
                execution_result = {
                    "action": "verify_task",
                    "command": verify_cmd,
                    "cwd": str(project_cwd),
                    "exit_code": -1,
                    "error": str(exc),
                    "success": False
                }
        else:
            execution_result = {
                "action": "unverifiable_task_rejected",
                "status": "rejected",
                "details": "任務缺少可執行命令，執行器拒領。"
            }

    print(f"🐾 [Do] Execution Result: {execution_result}")

    # --- 3. CHECK PHASE (The Claw Independent Assurance) ---
    print("🦅 [Check] Invoking The Claw for independent assurance review...")
    claw_verdict = "PASS"
    claw_findings = []
    
    if execution_result.get("action") == "verify_task":
        if execution_result.get("success"):
            claw_verdict = "PASS"
            claw_findings.append(f"✅ 實體驗收命令通過: `{execution_result.get('command')}` in `{execution_result.get('cwd')}` (exit code 0)")
        else:
            claw_verdict = "FAIL"
            claw_findings.append(f"❌ 實體驗收命令失敗: `{execution_result.get('command')}` in `{execution_result.get('cwd')}` (exit code {execution_result.get('exit_code')})")
    elif execution_result.get("action") == "idle":
        claw_verdict = "PASS"
        claw_findings.append("ℹ️ 合格任務隊列清空，工匠進入標準待命靜息狀態。")
    else:
        claw_verdict = "FAIL"
        claw_findings.append("❌ 任務未滿足 TASK_SPECIFICATION_STANDARD 五大要件，拒絕驗收。")

    print(f"🦅 [Check] The Claw Verdict: {claw_verdict} ({'; '.join(claw_findings)})")

    # --- 4. ACT PHASE (Commit Evidence & Advance Cycle) ---
    receipt = {
        "schema": "agentos.role-pdca-receipt/v1",
        "role_id": "sector.paw",
        "persona_id": "agentos-paw-builder-001",
        "cycle": cycle,
        "work_id": work_id,
        "timestamp": utc_now_iso(),
        "plan": {
            "intent": ir["cognitive_state"]["current_intent"],
            "task": selected_task["text"]
        },
        "do": execution_result,
        "check": {
            "verifier_role": "sector.claw",
            "verdict": claw_verdict,
            "findings": claw_findings
        },
        "act": {
            "status": "COMPLETED" if claw_verdict == "PASS" else "BLOCKED",
            "next_eligible_action": "autonomous_advance_next_todo"
        }
    }

    # Save activity receipt
    receipt_path = activities_dir / f"cycle-{cycle:04d}.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")

    # Update state.json
    state["cycle"] = cycle + 1
    state["last_tick_at"] = utc_now_iso()
    state["status"] = "RUNNING"
    state["phase"] = "active"
    state["recent_activities"].insert(0, {
        "cycle": cycle,
        "work_id": work_id,
        "task": selected_task["text"],
        "verdict": claw_verdict,
        "timestamp": utc_now_iso()
    })
    state["recent_activities"] = state["recent_activities"][:10]
    state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    # Append to events.jsonl
    event_entry = {
        "event_id": f"evt-{int(time.time())}-{cycle}",
        "timestamp": utc_now_iso(),
        "type": "pdca.cycle.completed",
        "role_id": "sector.paw",
        "cycle": cycle,
        "work_id": work_id,
        "task": selected_task["text"],
        "verdict": claw_verdict
    }
    with open(events_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(event_entry, ensure_ascii=False) + "\n")

    # If task came from GLOBAL_TODO_LIST, update it with file lock
    if selected_task.get("text") and GLOBAL_TODO.exists():
        try:
            import fcntl
            with open(GLOBAL_TODO, "r+", encoding="utf-8") as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    fresh_content = f.read()
                    fresh_lines = fresh_content.splitlines()
                    updated = False
                    if claw_verdict == "PASS":
                        for idx, line in enumerate(fresh_lines):
                            if line.startswith("- [ ]") and selected_task["text"] in line:
                                fresh_lines[idx] = line.replace("- [ ]", "- [x]", 1)
                                updated = True
                                print(f"📋 [Act] Marked task as [x] in GLOBAL_TODO_LIST.md (verified)")
                                break
                    else:
                        for idx, line in enumerate(fresh_lines):
                            if line.startswith("- [ ]") and selected_task["text"] in line:
                                failed_line = line.replace("- [ ]", f"- [ ] ⚠️ [CLAW_FAIL: exit {execution_result.get('exit_code')}]", 1)
                                fresh_lines.pop(idx)
                                blocked_idx = -1
                                for b_i, b_line in enumerate(fresh_lines):
                                    if "## ⚠️ Blocked" in b_line:
                                        blocked_idx = b_i
                                        break
                                if blocked_idx != -1:
                                    fresh_lines.insert(blocked_idx + 2, failed_line)
                                else:
                                    fresh_lines.append(failed_line)
                                updated = True
                                print(f"🚫 [Act] Claw rejected task. Demoted to Blocked queue: {selected_task['text']}")
                                break

                    if updated:
                        f.seek(0)
                        f.truncate(0)
                        f.write("\n".join(fresh_lines) + "\n")
                        f.flush()
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
        except Exception as exc:
            print(f"⚠️ [Act] Failed to sync GLOBAL_TODO_LIST: {exc}")

    print(f"✨ [Act] Cycle {cycle} committed. Paw advanced to Cycle {cycle + 1}!")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run role PDCA cycle")
    parser.add_argument("--role", default="the-paw", help="Target role")
    args = parser.parse_args()

    if args.role in ("the-paw", "paw"):
        res = run_paw_cycle()
        print("\n=== Paw PDCA Summary ===")
        print(json.dumps(res, indent=2, ensure_ascii=False))
    elif args.role in ("all", "ecosystem"):
        from agent_core.base_pdca import get_worker, WORKER_REGISTRY
        print("🐾 Running The Paw cycle...")
        run_paw_cycle()
        for role_key in ["the-claw", "tiandao-cangxuan", "tiandao-geek", "atlast", "cerberus", "hermes"]:
            print(f"\n--- Running {role_key} PDCA ---")
            w = get_worker(role_key)
            w.run_cycle()
    else:
        from agent_core.base_pdca import get_worker
        worker = get_worker(args.role)
        res = worker.run_cycle()
        print(f"\n=== {args.role} PDCA Summary ===")
        print(json.dumps(res.to_receipt(), indent=2, ensure_ascii=False))
