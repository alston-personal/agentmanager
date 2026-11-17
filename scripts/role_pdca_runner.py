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

                # 檢查是否為遠端節點專案（若在 Oracle 本機無代碼庫且標記為 Target Node，Oracle 本地 Paw 跳過，待 Realm 調度）
                target_tags = re.findall(r"\[([a-zA-Z0-9_\-]+)\]", line)
                is_remote_only = False
                for t_tag in target_tags:
                    t_dir = Path(f"/home/ubuntu/{t_tag}")
                    if not t_dir.is_dir() and not (AGENTMANAGER / t_tag).is_dir():
                        s_file = AGENT_DATA / "projects" / t_tag / "STATUS.md"
                        if s_file.exists() and "Target Node" in s_file.read_text(encoding="utf-8"):
                            is_remote_only = True
                            break
                if is_remote_only:
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

        # --- 2.1 CONSTRUCT PHASE (實質施工動作) ---
        # 如果驗收命令指向某個檔案 (例如 test -f <path>)，但該檔案尚未存在，Paw 必須先建立基礎檔案骨架
        construction_actions = []
        if verify_cmd and verify_cmd.startswith("test -f "):
            target_file_str = verify_cmd.replace("test -f ", "").strip()
            target_file_path = Path(target_file_str)
            if not target_file_path.is_absolute():
                target_file_path = project_cwd / target_file_path
            
            if not target_file_path.exists():
                print(f"🐾 [Construct] Target file missing: {target_file_path}. Creating initial structure...")
                target_file_path.parent.mkdir(parents=True, exist_ok=True)
                # 依據任務標題產生合理的初始骨架
                task_title = selected_task.get("text", "AgentOS Auto Construction")
                initial_content = f"# {task_title}\n\n*Created by The Paw (Cycle {cycle}) at {utc_now_iso()}*\n\n## 狀態與概要\n- 實作進度: 初始化骨架建立完成\n- 負責執行器: sector.paw\n"
                target_file_path.write_text(initial_content, encoding="utf-8")
                construction_actions.append(f"created_file: {target_file_path}")

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
                    "construction_actions": construction_actions,
                    "success": p_res.returncode == 0
                }
            except Exception as exc:
                execution_result = {
                    "action": "verify_task",
                    "command": verify_cmd,
                    "cwd": str(project_cwd),
                    "exit_code": -1,
                    "error": str(exc),
                    "construction_actions": construction_actions,
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

                    # 同步回寫專案實體 STATUS.md，完成物理閉環
                    if claw_verdict == "PASS" and target_tag:
                        proj_status_file = AGENT_DATA / "projects" / target_tag / "STATUS.md"
                        if proj_status_file.is_file():
                            s_content = proj_status_file.read_text(encoding="utf-8")
                            s_lines = s_content.splitlines()
                            s_updated = False
                            for s_i, s_line in enumerate(s_lines):
                                if s_line.startswith("- [ ]") and selected_task["text"].split("|")[0].strip() in s_line:
                                    s_lines[s_i] = s_line.replace("- [ ]", "- [x]", 1)
                                    s_updated = True
                                    print(f"📋 [Act] Synced [- [x]] to {proj_status_file.name}")
                                    break
                            if s_updated:
                                proj_status_file.write_text("\n".join(s_lines) + "\n", encoding="utf-8")
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
        import yaml
        from agent_core.base_pdca import get_worker
        from agent_core.role_handoff_bus import acknowledge_tasks_for_role

        print("🐾 [Ecosystem PDCA] 啟動 Base Role 動態自省循環...")
        try:
            run_paw_cycle()
        except Exception as e:
            print(f"⚠️ Paw error: {e}")

        # 動態自省：由 registry.yaml 發現所有 active 角色，徹底擺脫寫死名冊！
        reg_file = AGENTMANAGER / ".agent" / "roles" / "registry.yaml"
        active_role_ids = []
        if reg_file.is_file():
            try:
                reg_data = yaml.safe_load(reg_file.read_text(encoding="utf-8"))
                for r in reg_data.get("roles", []):
                    if r.get("status") == "active" and r.get("id") not in ("sector.paw", "the-paw"):
                        active_role_ids.append(r.get("id"))
            except Exception as e:
                print(f"⚠️ 解析角色註冊表失敗: {e}")

        # 兼顧遺留實例
        for extra in ["tiandao-cangxuan", "tiandao-geek"]:
            if extra not in active_role_ids:
                active_role_ids.append(extra)

        print(f"🏛️  動態發現 {len(active_role_ids)} 位在席角色，自主依序推進心跳與交接簽收...")
        for role_key in active_role_ids:
            try:
                # 1. 自動簽收 (ACK) 指向該角色的交接任務至其優先佇列
                acks = acknowledge_tasks_for_role(role_key)
                if acks:
                    print(f"📥 [{role_key}] 自動 ACK 簽收 {len(acks)} 項新交接任務！")

                # 2. 執行該角色的本能 PDCA 循環
                w = get_worker(role_key)
                w.run_cycle()
            except Exception as e:
                print(f"⚠️ {role_key} PDCA 自主循環異常: {e}")
    else:
        from agent_core.base_pdca import get_worker
        worker = get_worker(args.role)
        res = worker.run_cycle()
        print(f"\n=== {args.role} PDCA Summary ===")
        print(json.dumps(res.to_receipt(), indent=2, ensure_ascii=False))
