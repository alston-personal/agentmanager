#!/usr/bin/env python3
"""
⚖️ 忒彌斯 Themis (Sacred Invocations & Command Steward)
狀態盤點與歷史時序差異比對引擎 (Inventory Snapshot & State Delta Engine)

功能：
1. 全域掃描：採集 61+ 專案島嶼、STATUS.md 狀態、TODO 統計（Open/Closed/AC 標記）、Git HEAD、Atlas 週期。
2. 歷史保存：將快照安全持久化於資料層 ($AGENT_DATA_ROOT/snapshots/inventory/)，嚴格遵守邏輯/資料分離架構。
3. 時序差異 (Delta Diffing)：自動讀取上一次的 latest.json 基準，精準比對「兩次盤點間」的專案推進、任務增減與神祇週期。
4. 人機友好：輸出 Markdown 儀表盤與 JSON 憑證。
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

AGENTMANAGER_DEFAULT = Path("/home/ubuntu/agentmanager")
AGENT_DATA_DEFAULT = Path("/home/ubuntu/agent-data")


def get_git_info(repo_path: Path) -> Dict[str, Any]:
    """獲取 Git 分支、HEAD SHA 及工作區乾淨度。"""
    try:
        branch = subprocess.check_output(
            ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
            text=True, stderr=subprocess.DEVNULL
        ).strip()
        sha = subprocess.check_output(
            ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
            text=True, stderr=subprocess.DEVNULL
        ).strip()
        status = subprocess.check_output(
            ["git", "-C", str(repo_path), "status", "--porcelain"],
            text=True, stderr=subprocess.DEVNULL
        ).strip()
        return {
            "branch": branch,
            "commit_sha": sha,
            "is_clean": len(status) == 0,
        }
    except Exception as e:
        return {
            "branch": "unknown",
            "commit_sha": "unknown",
            "is_clean": False,
            "error": str(e),
        }


def scan_projects(data_root: Path) -> Tuple[Dict[str, Any], Dict[str, int]]:
    """掃描全生態專案島嶼之 STATUS.md 與 TODO 統計。"""
    projects_dir = data_root / "projects"
    project_map: Dict[str, Any] = {}
    total_open = 0
    total_closed = 0
    total_with_ac = 0

    if not projects_dir.exists():
        return project_map, {"total_open": 0, "total_closed": 0, "total_with_ac": 0}

    for p in sorted(projects_dir.iterdir()):
        if not p.is_dir() or p.name.startswith("."):
            continue

        status_file = p / "STATUS.md"
        has_status = status_file.exists()
        open_todos: List[str] = []
        closed_todos: List[str] = []
        todos_with_ac: List[str] = []

        if has_status:
            try:
                content = status_file.read_text(encoding="utf-8")
                for line in content.splitlines():
                    clean = line.strip()
                    if clean.startswith("- [ ]"):
                        task_text = clean[5:].strip()
                        open_todos.append(task_text)
                        # 檢查驗收標準標記 (如 [AC: ...], (驗收: ...), 或包含「驗收」)
                        if any(marker in task_text for marker in ("[AC:", "[驗收:", "驗收標準", "acceptance")):
                            todos_with_ac.append(task_text)
                    elif clean.startswith("- [x]"):
                        closed_todos.append(clean[5:].strip())
            except Exception:
                pass

        total_open += len(open_todos)
        total_closed += len(closed_todos)
        total_with_ac += len(todos_with_ac)

        project_map[p.name] = {
            "has_status": has_status,
            "open_count": len(open_todos),
            "closed_count": len(closed_todos),
            "ac_count": len(todos_with_ac),
            "open_todos": open_todos[:5],  # 截取前 5 項代表
        }

    summary = {
        "total_projects": len(project_map),
        "documented_projects": sum(1 for p in project_map.values() if p["has_status"]),
        "undocumented_projects": sum(1 for p in project_map.values() if not p["has_status"]),
        "total_open": total_open,
        "total_closed": total_closed,
        "total_with_ac": total_with_ac,
    }
    return project_map, summary


def get_atlas_state(data_root: Path) -> Dict[str, Any]:
    """獲取阿特拉斯 Atlas 的當前運行週期與佇列狀況。"""
    atlas_dir = data_root / "atlas"
    attention_file = atlas_dir / "attention_queue.json"
    persona_pdca_dir = data_root / "personas" / "system-atlas" / "pdca"
    state_file = persona_pdca_dir / "state.json"

    latest_cycle = 0
    if state_file.exists():
        try:
            st = json.loads(state_file.read_text(encoding="utf-8"))
            latest_cycle = st.get("cycle", 0)
        except Exception:
            pass

    attention_data = {}
    if attention_file.exists():
        try:
            attention_data = json.loads(attention_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    return {
        "latest_cycle": latest_cycle,
        "open_loop_count": attention_data.get("open_loop_count", 0),
        "completed_count": attention_data.get("completed_count", 0),
        "top_attention_items": attention_data.get("top_attention_items", [])[:3],
    }


def get_roles_state(data_root: Path) -> Dict[str, Any]:
    """採集核心角色 (The Paw / The Claw / Hermes 等) 之 PDCA 狀態與最新活動。"""
    personas_dir = data_root / "personas"
    key_roles = [
        ("the-paw", "The Paw (工匠貓爪)"),
        ("the-claw", "The Claw (安全審查)"),
        ("sector-hermes", "Hermes (技術偵察使)"),
        ("system-atlas", "Atlas (守護神)"),
    ]

    roles_info: Dict[str, Any] = {}
    for slug, display_name in key_roles:
        state_file = personas_dir / slug / "pdca" / "state.json"
        if not state_file.is_file():
            roles_info[slug] = {
                "display_name": display_name,
                "status": "UNKNOWN",
                "cycle": 0,
                "latest_task": None,
                "latest_verdict": None,
                "last_tick_at": None,
            }
            continue

        try:
            st = json.loads(state_file.read_text(encoding="utf-8"))
            activities = st.get("recent_activities", [])
            latest_act = activities[0] if activities else {}
            roles_info[slug] = {
                "display_name": display_name,
                "status": st.get("status", "ACTIVE"),
                "cycle": st.get("cycle", 0),
                "latest_task": latest_act.get("task"),
                "latest_verdict": latest_act.get("verdict"),
                "last_tick_at": st.get("last_tick_at"),
            }

            # 若為 Hermes，額外讀取情資成果台帳 (recon_ledger.json)
            if slug == "sector-hermes":
                recon_ledger_file = personas_dir / slug / "recon_ledger.json"
                if recon_ledger_file.is_file():
                    try:
                        ledger_data = json.loads(recon_ledger_file.read_text(encoding="utf-8"))
                        records = ledger_data.get("records", [])
                        if records:
                            latest_recon = records[-1]
                            roles_info[slug]["recon_summary"] = (
                                f"共引進 {len(records)} 項武器 (最新: {latest_recon.get('name')} ⭐{latest_recon.get('stars', 0)})"
                            )
                    except Exception:
                        pass
        except Exception as e:
            roles_info[slug] = {
                "display_name": display_name,
                "status": "ERROR",
                "cycle": 0,
                "error": str(e),
            }

    return roles_info


def capture_snapshot(project_root: Path = AGENTMANAGER_DEFAULT, data_root: Path = AGENT_DATA_DEFAULT) -> Dict[str, Any]:
    """採集當前全生態狀態快照。"""
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    timestamp_iso = now.isoformat()

    git_info = get_git_info(project_root)
    project_map, summary = scan_projects(data_root)
    atlas_state = get_atlas_state(data_root)
    roles_state = get_roles_state(data_root)

    snapshot = {
        "schema": "agentos.inventory-snapshot/v1",
        "steward": "governance.themis_command_steward",
        "timestamp": timestamp_iso,
        "git": git_info,
        "projects_summary": summary,
        "projects": project_map,
        "atlas": atlas_state,
        "roles": roles_state,
    }
    return snapshot


def compute_delta(baseline: Optional[Dict[str, Any]], current: Dict[str, Any]) -> Dict[str, Any]:
    """比對當前快照與歷史基準，計算時序差異 (Delta)。"""
    if not baseline:
        return {
            "has_baseline": False,
            "message": "首次建立盤點基準 (Initial Baseline Snapshot)，無歷史差異可比對。",
        }

    curr_git = current.get("git", {})
    base_git = baseline.get("git", {})

    git_changed = curr_git.get("commit_sha") != base_git.get("commit_sha")
    old_sha = base_git.get("commit_sha", "unknown")[:8]
    new_sha = curr_git.get("commit_sha", "unknown")[:8]

    # 專案變遷
    curr_projects = current.get("projects", {})
    base_projects = baseline.get("projects", {})

    new_projects = [p for p in curr_projects if p not in base_projects]
    removed_projects = [p for p in base_projects if p not in curr_projects]

    newly_documented = [
        p for p, data in curr_projects.items()
        if data.get("has_status") and not base_projects.get(p, {}).get("has_status", False)
    ]

    # 任務與統計變遷
    curr_sum = current.get("projects_summary", {})
    base_sum = baseline.get("projects_summary", {})

    open_delta = curr_sum.get("total_open", 0) - base_sum.get("total_open", 0)
    closed_delta = curr_sum.get("total_closed", 0) - base_sum.get("total_closed", 0)
    ac_delta = curr_sum.get("total_with_ac", 0) - base_sum.get("total_with_ac", 0)

    # 各專案 TODO 異動細節
    project_task_changes = []
    for p_name, p_curr in curr_projects.items():
        if p_name in base_projects:
            p_base = base_projects[p_name]
            p_open_delta = p_curr.get("open_count", 0) - p_base.get("open_count", 0)
            p_closed_delta = p_curr.get("closed_count", 0) - p_base.get("closed_count", 0)
            if p_open_delta != 0 or p_closed_delta != 0:
                project_task_changes.append({
                    "project": p_name,
                    "open_delta": p_open_delta,
                    "closed_delta": p_closed_delta,
                })

    # Atlas 週期進展
    curr_atlas = current.get("atlas", {})
    base_atlas = baseline.get("atlas", {})
    cycle_delta = curr_atlas.get("latest_cycle", 0) - base_atlas.get("latest_cycle", 0)

    return {
        "has_baseline": True,
        "baseline_timestamp": baseline.get("timestamp"),
        "current_timestamp": current.get("timestamp"),
        "git_delta": {
            "changed": git_changed,
            "old_sha": old_sha,
            "new_sha": new_sha,
            "clean_status": curr_git.get("is_clean", False),
        },
        "project_delta": {
            "new_projects": new_projects,
            "removed_projects": removed_projects,
            "newly_documented": newly_documented,
        },
        "todo_delta": {
            "open_delta": open_delta,
            "closed_delta": closed_delta,
            "ac_delta": ac_delta,
            "project_changes": project_task_changes,
        },
        "atlas_delta": {
            "old_cycle": base_atlas.get("latest_cycle", 0),
            "new_cycle": curr_atlas.get("latest_cycle", 0),
            "cycle_delta": cycle_delta,
        },
    }


def format_markdown_report(current: Dict[str, Any], delta: Dict[str, Any]) -> str:
    """生成人類與 Agent 友好的 Markdown 時序盤點報告。"""
    c_sum = current.get("projects_summary", {})
    git = current.get("git", {})
    atlas = current.get("atlas", {})

    lines = [
        "# ⚖️ 忒彌斯 Themis 聖諭盤點與時序差異報告",
        f"**盤點時間**：`{current.get('timestamp', 'unknown')}`  ",
        f"**執掌神祇**：`governance.themis_command_steward` (天規聖諭與口令女神)  ",
        f"**代碼主幹**：`{git.get('branch', 'unknown')}` @ `{git.get('commit_sha', 'unknown')[:8]}` (Clean: `{git.get('is_clean', False)}`)  ",
        "",
        "---",
        "",
        "## 📊 1. 全域生態概況 (Current Inventory Summary)",
        f"- **專案島嶼總數**：`{c_sum.get('total_projects', 0)}` 座（已建構進度檔：`{c_sum.get('documented_projects', 0)}`，未建構：`{c_sum.get('undocumented_projects', 0)}`）",
        f"- **待辦任務池 (Open TODOs)**：`{c_sum.get('total_open', 0)}` 項",
        f"- **已閉環任務 (Closed TODOs)**：`{c_sum.get('total_closed', 0)}` 項",
        f"- **具備驗收標記 (With AC)**：`{c_sum.get('total_with_ac', 0)}` 項",
        f"- **阿特拉斯 Atlas 週期**：`cycle-{atlas.get('latest_cycle', 0):04d}`",
        "",
        "---",
        "",
        "## ⏱️ 2. 時序歷史差異比對 (Temporal Delta Diff)",
    ]

    if not delta.get("has_baseline"):
        lines.append(f"> ℹ️ **初始基準快照**：{delta.get('message')}")
    else:
        lines.append(f"> 基準點：`{delta['baseline_timestamp']}` ➔ 當前點：`{delta['current_timestamp']}`")
        lines.append("")

        # Git SHA
        gd = delta["git_delta"]
        if gd["changed"]:
            lines.append(f"- **代碼版本變遷**：`{gd['old_sha']}` ➔ `{gd['new_sha']}` (有新代碼提交)")
        else:
            lines.append(f"- **代碼版本變遷**：保持在 `{gd['new_sha']}` (無代碼變更)")

        # Atlas cycles
        ad = delta["atlas_delta"]
        lines.append(f"- **阿特拉斯 Atlas 週期推進**：`cycle-{ad['old_cycle']}` ➔ `cycle-{ad['new_cycle']}` (Δ: `{ad['cycle_delta']:+d}` 週期)")

        # TODOs
        td = delta["todo_delta"]
        lines.append(f"- **全系統待辦任務 (Open)**：`{c_sum['total_open']}` (Δ: `{td['open_delta']:+d}`)")
        lines.append(f"- **全系統已閉環任務 (Closed)**：`{c_sum['total_closed']}` (Δ: `{td['closed_delta']:+d}`)")
        lines.append(f"- **合格驗收標準任務 (AC)**：`{c_sum['total_with_ac']}` (Δ: `{td['ac_delta']:+d}`)")

        # 專案異動
        pd = delta["project_delta"]
        if pd["new_projects"]:
            lines.append(f"- 🆕 **新開闢專案島嶼**：{', '.join(pd['new_projects'])}")
        if pd["newly_documented"]:
            lines.append(f"- 📝 **新補齊 STATUS.md 專案**：{', '.join(pd['newly_documented'])}")

        # 專案推進細節
        if td["project_changes"]:
            lines.append("")
            lines.append("### 🎯 專案推進動態明細")
            for ch in td["project_changes"]:
                lines.append(f"  - **`{ch['project']}`**：Open `{ch['open_delta']:+d}`, Closed `{ch['closed_delta']:+d}`")

    # 3. 核心執行器與守護角色在席狀態
    roles_state = current.get("roles", {})
    if roles_state:
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 🐾 3. 核心執行器與守護角色在席狀態 (Roles & Executors)")
        for slug, r_info in roles_state.items():
            name = r_info.get("display_name", slug)
            status = r_info.get("status", "UNKNOWN")
            cycle = r_info.get("cycle", 0)
            latest_task = r_info.get("latest_task")
            latest_verdict = r_info.get("latest_verdict")

            status_desc = f"`{status}` (Cycle: `{cycle}`)"
            detail = ""
            if latest_task:
                # 截斷過長任務名
                task_snippet = (latest_task[:70] + "...") if len(latest_task) > 70 else latest_task
                verdict_snippet = f" ➔ `[{latest_verdict}]`" if latest_verdict else ""
                detail = f"\n  - 最新動作: {task_snippet}{verdict_snippet}"

            recon_summary = r_info.get("recon_summary")
            if recon_summary:
                detail += f"\n  - 情資成果: {recon_summary}"

            lines.append(f"- **{name}**: {status_desc}{detail}")

    lines.append("")
    lines.append("---")
    lines.append("*守護不變量：邏輯與資料物理分離，快照歷史安全保留於 `$AGENT_DATA_ROOT/snapshots/inventory/`。*")
    return "\n".join(lines)


def validate_authoritative_data_root(data_root: Path) -> None:
    """Fail closed when executed on a non-Oracle host without authoritative agent-data."""
    projects_dir = data_root / "projects"
    governance_dir = data_root / "governance" / "directory.json"
    if not projects_dir.is_dir():
        raise ValueError(
            f"NON_AUTHORITATIVE_DATA_ROOT: missing projects directory under {data_root}; "
            "dispatch /status-diff to Oracle via scripts/submit_agentos_command.sh instead of scanning local disk."
        )
    has_documented = any(
        (p / "STATUS.md").is_file()
        for p in projects_dir.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )
    if not governance_dir.is_file() and not has_documented:
        raise ValueError(
            f"NON_AUTHORITATIVE_DATA_ROOT: {data_root} has no governance/directory.json and 0 documented projects; "
            "this host is not the Oracle truth center. Dispatch /status-diff to Oracle via scripts/submit_agentos_command.sh."
        )


DEFAULT_COOLDOWN_SECONDS = 6 * 3600  # 預設 6 小時冷卻期


def should_persist_snapshot(
    snapshot_dir: Path,
    current: Dict[str, Any],
    delta: Dict[str, Any],
    cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
) -> Tuple[bool, str]:
    """判斷是否應持久化保存快照：
    1. 若尚無任何快照，必須保存。
    2. 若檢測到實質生態變更（Git SHA 變遷、新專案、TODOs 變化），值得保存。
    3. 若距上一筆快照已超過冷卻週期（如 6 小時），作為定期定錨保存。
    4. 其餘常態例行盤點（無實質異動且在冷卻期內）跳過存檔，避免垃圾快照碎片化。
    """
    latest_file = snapshot_dir / "latest.json"
    if not latest_file.is_file():
        return True, "INITIAL_BASELINE"

    # 檢測實質變更
    if delta.get("has_baseline"):
        gd = delta.get("git_delta", {})
        if gd.get("changed"):
            return True, "GIT_SHA_CHANGED"

        pd = delta.get("project_delta", {})
        if pd.get("new_projects") or pd.get("removed_projects") or pd.get("newly_documented"):
            return True, "PROJECT_INVENTORY_CHANGED"

        td = delta.get("todo_delta", {})
        if td.get("open_delta", 0) != 0 or td.get("closed_delta", 0) != 0:
            return True, "TODO_STATUS_CHANGED"

    # 檢測冷卻時間
    try:
        latest_data = json.loads(latest_file.read_text(encoding="utf-8"))
        latest_ts_str = latest_data.get("timestamp")
        if latest_ts_str:
            latest_dt = datetime.datetime.fromisoformat(latest_ts_str)
            now_dt = datetime.datetime.fromisoformat(current.get("timestamp"))
            elapsed = (now_dt - latest_dt).total_seconds()
            if elapsed >= cooldown_seconds:
                return True, f"COOLDOWN_ELAPSED ({int(elapsed)}s >= {cooldown_seconds}s)"
            else:
                return False, f"COOLDOWN_ACTIVE ({int(elapsed)}s < {cooldown_seconds}s, no material change)"
    except Exception as exc:
        return True, f"ERROR_READING_LATEST ({exc})"

    return False, "NO_MATERIAL_CHANGE"


def run_inventory_diff(
    project_root: Path = AGENTMANAGER_DEFAULT,
    data_root: Path = AGENT_DATA_DEFAULT,
    save: bool = True,
    output_json: bool = False,
    base_target: Optional[str] = None,
    previous_n: Optional[int] = None,
    is_user_invocation: bool = False,
    cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
) -> Tuple[Dict[str, Any], str]:
    """執行全流程盤點、比對與快照儲存。"""
    """執行全流程盤點、比對與快照儲存。

    支援：
    1. 使用者呼叫模式 (is_user_invocation=True)：預設以今日起點 (start-of-day) 或 user_latest 為基準，且預設不覆寫系統 latest。
    2. 系統排程模式：受冷卻閥 (cooldown_seconds) 與實質變更守衛保護，避免每 10 分鐘洗牌。
    """
    snapshot_dir = data_root / "snapshots" / "inventory"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    latest_file = snapshot_dir / "latest.json"
    user_latest_file = snapshot_dir / "user_latest.json"

    # 1. 讀取 baseline
    baseline = None
    all_snapshots = sorted(snapshot_dir.glob("snapshot-*.json"))

    if base_target:
        if base_target in ("start-of-day", "today"):
            # 尋找今日最早的快照
            today_str = datetime.datetime.now(
                datetime.timezone(datetime.timedelta(hours=8))
            ).strftime("%Y%m%d")
            today_snaps = [s for s in all_snapshots if s.name.startswith(f"snapshot-{today_str}")]
            if today_snaps:
                try:
                    baseline = json.loads(today_snaps[0].read_text(encoding="utf-8"))
                except Exception:
                    baseline = None
        else:
            cand = Path(base_target)
            if not cand.exists() and (snapshot_dir / base_target).exists():
                cand = snapshot_dir / base_target
            if cand.exists():
                try:
                    baseline = json.loads(cand.read_text(encoding="utf-8"))
                except Exception:
                    baseline = None
    elif previous_n is not None and previous_n > 0:
        # 指定比對倒數第 N 個歷史快照
        if len(all_snapshots) >= previous_n:
            target_snap = all_snapshots[-previous_n]
            try:
                baseline = json.loads(target_snap.read_text(encoding="utf-8"))
            except Exception:
                baseline = None
    elif is_user_invocation:
        # 使用者互動查詢：優先比對上次使用者查詢點，若無則比對今日起點
        if user_latest_file.exists():
            try:
                baseline = json.loads(user_latest_file.read_text(encoding="utf-8"))
            except Exception:
                baseline = None
        if not baseline:
            today_str = datetime.datetime.now(
                datetime.timezone(datetime.timedelta(hours=8))
            ).strftime("%Y%m%d")
            today_snaps = [s for s in all_snapshots if s.name.startswith(f"snapshot-{today_str}")]
            if today_snaps:
                try:
                    baseline = json.loads(today_snaps[0].read_text(encoding="utf-8"))
                except Exception:
                    baseline = None
        if not baseline and latest_file.exists():
            try:
                baseline = json.loads(latest_file.read_text(encoding="utf-8"))
            except Exception:
                baseline = None
    elif latest_file.exists():
        try:
            baseline = json.loads(latest_file.read_text(encoding="utf-8"))
        except Exception:
            baseline = None

    # 2. 採集當前快照
    current = capture_snapshot(project_root, data_root)

    # 3. 計算 Delta
    delta = compute_delta(baseline, current)

    # 4. 生成報告
    report_md = format_markdown_report(current, delta)

    # 5. 存檔（若 save=True）
    # 5. 存檔與冷卻判定
    saved = False
    save_reason = "SAVE_DISABLED"

    if save:
        timestamp_str = datetime.datetime.now(
            datetime.timezone(datetime.timedelta(hours=8))
        ).strftime("%Y%m%d_%H%M%S")
        history_file = snapshot_dir / f"snapshot-{timestamp_str}.json"
        if is_user_invocation:
            # 使用者查詢記錄存至 user_latest.json，不污染系統 baseline
            user_latest_file.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            saved = True
            save_reason = "USER_INVOCATION_RECORDED"
        else:
            # 系統排程自動盤點：執行冷卻閥與變更過濾
            should_save, reason = should_persist_snapshot(snapshot_dir, current, delta, cooldown_seconds)
            save_reason = reason
            if should_save:
                timestamp_str = datetime.datetime.now(
                    datetime.timezone(datetime.timedelta(hours=8))
                ).strftime("%Y%m%d_%H%M%S")
                history_file = snapshot_dir / f"snapshot-{timestamp_str}.json"

        # 寫入歷史存檔
        history_file.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        # 更新 latest.json
        latest_file.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                history_file.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                latest_file.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                saved = True

    result = {
        "schema": "agentos.inventory-diff-receipt/v1",
        "steward": "governance.themis_command_steward",
        "current": current,
        "delta": delta,
        "persistence": {
            "saved": saved,
            "reason": save_reason,
            "is_user_invocation": is_user_invocation,
        },
    }

    return result, report_md


def main():
    parser = argparse.ArgumentParser(description="Themis State Inventory & Temporal Delta Diff Engine")
    parser.add_argument("--no-save", action="store_true", help="Do not persist the current snapshot to disk")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON instead of markdown")
    parser.add_argument("--base", type=str, default=None, help="Baseline snapshot (snapshot filename, path, or 'start-of-day')")
    parser.add_argument("--previous", type=int, default=None, help="Compare with Nth snapshot from the end (e.g. 1 for previous snapshot)")
    parser.add_argument("--allow-non-authoritative", action="store_true", help="Allow running against a non-Oracle local data_root")
    parser.add_argument("--system-scheduled", action="store_true", help="Mark as background system scheduled invocation (applies cooldown & updates system latest)")
    args = parser.parse_args()

    data_root = Path(os.environ.get("AGENT_DATA_ROOT") or AGENT_DATA_DEFAULT)
    if not args.allow_non_authoritative:
        try:
            validate_authoritative_data_root(data_root)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(2)

    is_user = not args.system_scheduled

    result, report_md = run_inventory_diff(
        data_root=data_root,
        save=not args.no_save,
        output_json=args.json,
        base_target=args.base,
        previous_n=args.previous,
        is_user_invocation=is_user,
    )

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(report_md)


if __name__ == "__main__":
    main()
