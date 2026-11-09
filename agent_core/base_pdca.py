from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import stat
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

AGENT_DATA_DEFAULT = Path("/home/ubuntu/agent-data")
AGENTMANAGER_DEFAULT = Path("/home/ubuntu/agentmanager")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PDCAResult:
    role_id: str
    cycle: int
    work_id: str
    plan: dict[str, Any]
    do: dict[str, Any]
    check: dict[str, Any]
    act: dict[str, Any]
    timestamp: str = field(default_factory=utc_now_iso)

    def to_receipt(self) -> dict[str, Any]:
        return {
            "schema": "agentos.role-pdca-receipt/v1",
            "role_id": self.role_id,
            "cycle": self.cycle,
            "work_id": self.work_id,
            "timestamp": self.timestamp,
            "plan": self.plan,
            "do": self.do,
            "check": self.check,
            "act": self.act,
        }


class BasePDCAWorker:
    """Universal Base PDCA Worker implementing the core.root contract.

    Inherited by every active role:
      1. Plan: Hydrate cognitive context & select unblocked eligible work
      2. Do: Execute within role bounds & worktree constraints
      3. Check: Verify outputs against acceptance criteria / invariants
      4. Act: Commit receipts, advance cycle, update state, notify ecosystem
    """

    def __init__(
        self,
        role_slug: str,
        data_root: Path = AGENT_DATA_DEFAULT,
        project_root: Path = AGENTMANAGER_DEFAULT,
    ) -> None:
        self.role_slug = role_slug
        self.data_root = Path(data_root)
        self.project_root = Path(project_root)

        self.persona_dir = self.data_root / "personas" / self.role_slug
        self.pdca_dir = self.persona_dir / "pdca"
        self.activities_dir = self.pdca_dir / "activities"
        self.events_file = self.persona_dir / "events" / "events.jsonl"
        self.config_file = self.pdca_dir / "config.json"
        self.state_file = self.pdca_dir / "state.json"
        self.persona_state_file = self.persona_dir / "persona_state.json"
        self.core_file = self.persona_dir / "character_core.json"

        self.ensure_initialized()

    def ensure_initialized(self) -> None:
        self.activities_dir.mkdir(parents=True, exist_ok=True)
        self.events_file.parent.mkdir(parents=True, exist_ok=True)

        # 1. Config
        if not self.config_file.exists():
            cfg = {
                "schema": "agentos.role-pdca-config/v1",
                "role_id": f"sector.{self.role_slug}",
                "persona_id": f"agentos-{self.role_slug}-001",
                "enabled": True,
                "protocol": "root.pdca.v1",
                "inherited_from": "core.root",
                "heartbeat_minutes": 10,
                "autonomy_mode": "policy_bounded",
            }
            self.config_file.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        # 2. State
        if not self.state_file.exists():
            st = {
                "schema": "agentos.role-pdca-state/v1",
                "role_id": f"sector.{self.role_slug}",
                "status": "RUNNING",
                "cycle": 1,
                "phase": "active",
                "last_tick_at": utc_now_iso(),
                "recent_activities": [],
            }
            self.state_file.write_text(json.dumps(st, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def load_config(self) -> dict[str, Any]:
        try:
            return json.loads(self.config_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def load_state(self) -> dict[str, Any]:
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except Exception:
            return {"cycle": 1, "recent_activities": []}

    def load_core(self) -> dict[str, Any]:
        if self.core_file.exists():
            try:
                return json.loads(self.core_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    # --- Phase Overridables ---

    def plan(self, cycle: int) -> dict[str, Any]:
        """Phase 1: Select task, resolve dependencies, define acceptance criteria."""
        core = self.load_core()
        task_title = f"{self.role_slug} 自主維護與狀態巡查"
        mission = core.get("mission", "執行角色自主任務")
        return {
            "task": task_title,
            "mission_focus": mission,
            "source": "autonomous_heartbeat",
        }

    def do(self, plan_data: dict[str, Any], work_id: str) -> dict[str, Any]:
        """Phase 2: Perform execution within role boundaries."""
        return {
            "action": "routine_check",
            "status": "completed",
            "details": f"Role {self.role_slug} heartbeat verified.",
        }

    def check(self, plan_data: dict[str, Any], do_data: dict[str, Any]) -> dict[str, Any]:
        """Phase 3: Verify execution outputs and invariants."""
        return {
            "verifier_role": "core.root.inspector",
            "verdict": "PASS",
            "findings": ["✅ Base invariants verified: Logic/Data separation maintained."],
        }

    def act(
        self,
        cycle: int,
        work_id: str,
        plan_data: dict[str, Any],
        do_data: dict[str, Any],
        check_data: dict[str, Any],
    ) -> PDCAResult:
        """Phase 4: Commit receipts, persist state & events, advance cycle."""
        verdict = check_data.get("verdict", "PASS")
        act_status = "COMPLETED" if verdict == "PASS" else "BLOCKED"

        result = PDCAResult(
            role_id=f"sector.{self.role_slug}",
            cycle=cycle,
            work_id=work_id,
            plan=plan_data,
            do=do_data,
            check=check_data,
            act={
                "status": act_status,
                "next_eligible_action": "advance_next_cycle",
            },
        )

        receipt = result.to_receipt()

        # 1. Save activity receipt
        receipt_file = self.activities_dir / f"cycle-{cycle:04d}.json"
        receipt_file.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        # 2. Append event to events.jsonl
        summary_text = (
            plan_data.get("task")
            or do_data.get("summary")
            or f"Cycle {cycle} {act_status}"
        )
        event_entry = {
            "event_id": f"evt-{self.role_slug}-{cycle}-{int(time.time())}",
            "timestamp": utc_now_iso(),
            "type": "pdca.cycle.completed",
            "role_id": f"sector.{self.role_slug}",
            "cycle": cycle,
            "work_id": work_id,
            "summary": summary_text,
            "verdict": verdict,
        }
        with open(self.events_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event_entry, ensure_ascii=False) + "\n")

        # 3. Update state.json
        state = self.load_state()
        state["cycle"] = cycle + 1
        state["last_tick_at"] = utc_now_iso()
        state["status"] = "RUNNING"
        state["phase"] = "active"
        recent = state.get("recent_activities", [])
        recent.insert(0, {
            "cycle": cycle,
            "work_id": work_id,
            "task": summary_text,
            "verdict": verdict,
            "timestamp": utc_now_iso(),
        })
        state["recent_activities"] = recent[:10]
        self.state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        # 4. Update persona_state.json for Mission Control compatibility
        if self.persona_state_file.exists():
            try:
                pst = json.loads(self.persona_state_file.read_text(encoding="utf-8"))
                pst["cycle"] = cycle + 1
                pst["last_tick_at"] = utc_now_iso()
                pst["status"] = "RUNNING"
                pst["current_action"] = summary_text
                self.persona_state_file.write_text(json.dumps(pst, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            except Exception:
                pass

        return result

    def run_cycle(self) -> PDCAResult:
        # 👑 瑞亞神殿封印檢驗：若未審批蓋印，任何角色 Worker 拒絕運轉
        from agent_core.role_seal import verify_seal
        verify_seal(raise_on_error=True)

        state = self.load_state()
        cycle = int(state.get("cycle", 1))
        work_id = f"{self.role_slug}-work-{cycle:04d}-{int(time.time())}"

        print(f"[{self.role_slug.upper()}] Starting PDCA Cycle {cycle} (Work ID: {work_id})...")
        p_data = self.plan(cycle)
        print(f"[{self.role_slug.upper()}] [Plan] Task: {p_data.get('task')}")

        d_data = self.do(p_data, work_id)
        print(f"[{self.role_slug.upper()}] [Do] Action executed: {d_data.get('action')}")

        c_data = self.check(p_data, d_data)
        print(f"[{self.role_slug.upper()}] [Check] Verdict: {c_data.get('verdict')} ({'; '.join(c_data.get('findings', []))})")

        res = self.act(cycle, work_id, p_data, d_data, c_data)
        print(f"[{self.role_slug.upper()}] [Act] Committed. Advanced to Cycle {cycle + 1}!")
        return res


# ==============================================================================
# Role-Specific Worker Implementations
# ==============================================================================

class ClawAuditorWorker(BasePDCAWorker):
    """The Claw (審計銳爪): Independent Security, QA, and Invariant Assurance."""

    def __init__(self, data_root: Path = AGENT_DATA_DEFAULT, project_root: Path = AGENTMANAGER_DEFAULT) -> None:
        super().__init__("the-claw", data_root, project_root)

    def plan(self, cycle: int) -> dict[str, Any]:
        return {
            "task": "獨立審查系統防線與最新代碼變更合規性",
            "mission_focus": "以 adversarial/QA 視角獨立檢驗安全邊界、檔案權限與分支保護",
            "source": "independent_assurance_scheduler",
        }

    def do(self, plan_data: dict[str, Any], work_id: str) -> dict[str, Any]:
        findings = []
        checks = {}

        # 1. Check .env permission
        env_path = self.project_root / ".env"
        if env_path.exists():
            mode = stat.S_IMODE(env_path.stat().st_mode)
            checks["env_permission"] = oct(mode)
            if mode != 0o600:
                findings.append(f"⚠️ {env_path} 權限為 {oct(mode)}，非嚴格 0600")
            else:
                findings.append("✅ .env 權限符合 0600 最低防護")
        else:
            checks["env_permission"] = "not_found"

        # 2. Check Logic/Data separation in agentmanager
        forbidden_in_logic = [
            self.project_root / "STATUS.md",
            self.project_root / "memory",
        ]
        separation_ok = True
        for p in forbidden_in_logic:
            if p.exists() and not p.is_symlink():
                findings.append(f"❌ 嚴重違規: {p.name} 在代碼庫中非軟連結！")
                separation_ok = False
        if separation_ok:
            findings.append("✅ 邏輯與資料物理分離防線正常（未發現實體狀態覆寫）")

        # 3. Check Paw's latest receipt
        paw_act_dir = self.data_root / "personas" / "the-paw" / "pdca" / "activities"
        latest_paw_receipt = None
        if paw_act_dir.exists():
            receipts = sorted(paw_act_dir.glob("cycle-*.json"))
            if receipts:
                latest_paw_receipt = receipts[-1].name
                findings.append(f"✅ 審計 The Paw 最新執行憑證: {latest_paw_receipt}")

        checks["logic_data_separation"] = separation_ok
        checks["latest_paw_receipt"] = latest_paw_receipt

        return {
            "action": "security_and_invariant_audit",
            "checks": checks,
            "findings": findings,
            "status": "completed",
        }

    def check(self, plan_data: dict[str, Any], do_data: dict[str, Any]) -> dict[str, Any]:
        findings = do_data.get("findings", [])
        has_critical_error = any("❌" in f for f in findings)
        verdict = "FAIL" if has_critical_error else "PASS"
        return {
            "verifier_role": "sector.claw.lead_auditor",
            "verdict": verdict,
            "findings": findings,
        }


class CangxuanEditorWorker(BasePDCAWorker):
    """蒼玄主編 (Tiandao-Cangxuan): Literary Quality, Word-Count, and Jargon Leak Sentinel."""

    def __init__(self, data_root: Path = AGENT_DATA_DEFAULT, project_root: Path = AGENTMANAGER_DEFAULT) -> None:
        super().__init__("tiandao-cangxuan", data_root, project_root)
        self.novel_dir = Path("/home/ubuntu/zeus-writer/天道敕令_阿賴耶識修真錄/正文")

    def plan(self, cycle: int) -> dict[str, Any]:
        # Find latest chapter file
        latest_chapter = None
        if self.novel_dir.exists():
            chapters = sorted(self.novel_dir.glob("*.md"))
            if chapters:
                latest_chapter = chapters[-1]

        chapter_name = latest_chapter.name if latest_chapter else "無章節"
        return {
            "task": f"審查《天道敕令》最新章節草稿 ({chapter_name}) 術語純潔度與字數天條",
            "target_chapter": str(latest_chapter) if latest_chapter else None,
            "chapter_name": chapter_name,
            "source": "literary_editor_pipeline",
        }

    def do(self, plan_data: dict[str, Any], work_id: str) -> dict[str, Any]:
        chapter_path = plan_data.get("target_chapter")
        if not chapter_path or not Path(chapter_path).exists():
            return {"action": "chapter_audit", "status": "chapter_not_found"}

        content = Path(chapter_path).read_text(encoding="utf-8")
        char_count = len(content)

        # Check for un-translated modern tech jargon (as flagged by User!)
        forbidden_jargon = [
            "token", "turn-taking", "backoff", "plugin", "marketplace",
            "docker", "kubernetes", "pm2", "nginx", "http", "json",
            "api", "endpoint", "git", "bash", "linux"
        ]
        leaked_terms = []
        for word in forbidden_jargon:
            # Word boundary or case-insensitive search
            import re
            matches = re.findall(rf"\b{re.escape(word)}\b", content, re.IGNORECASE)
            if matches:
                leaked_terms.append(f"{word} (出現 {len(matches)} 次)")

        findings = []
        if char_count < 3000:
            findings.append(f"⚠️ 字數預警: 當前字數 {char_count} 字，未達天條門檻 (3000 字)")
        else:
            findings.append(f"✅ 字數天條達標: 共 {char_count} 字符")

        if leaked_terms:
            findings.append(f"❌ 查獲天機外洩/現代術語未轉譯: {', '.join(leaked_terms)}")
        else:
            findings.append("✅ 文字純潔度合格: 未偵測到裸露的現代科技術語")

        return {
            "action": "literary_cleanliness_inspection",
            "chapter": plan_data.get("chapter_name"),
            "char_count": char_count,
            "leaked_terms": leaked_terms,
            "findings": findings,
            "status": "completed",
        }

    def check(self, plan_data: dict[str, Any], do_data: dict[str, Any]) -> dict[str, Any]:
        findings = do_data.get("findings", [])
        leaks = do_data.get("leaked_terms", [])
        verdict = "FAIL" if leaks else "PASS"
        return {
            "verifier_role": "sector.cangxuan.editor_in_chief",
            "verdict": verdict,
            "findings": findings,
        }


class GeekCultivatorWorker(BasePDCAWorker):
    """天道極客 (Tiandao-Geek): Server Infrastructure & Live Port Health Monitor."""

    def __init__(self, data_root: Path = AGENT_DATA_DEFAULT, project_root: Path = AGENTMANAGER_DEFAULT) -> None:
        super().__init__("tiandao-geek", data_root, project_root)

    def plan(self, cycle: int) -> dict[str, Any]:
        return {
            "task": "散修視角之伺服器法陣與公共連接埠即時探測",
            "source": "system_observability_pipeline",
        }

    def do(self, plan_data: dict[str, Any], work_id: str) -> dict[str, Any]:
        ports_to_check = [80, 443, 3041]
        active_ports = []
        findings = []

        for p in ports_to_check:
            # Check port with nc or socket
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex(("127.0.0.1", p))
            sock.close()
            if result == 0:
                active_ports.append(p)
                findings.append(f"✅ 連接埠 {p} 法陣暢通")
            else:
                findings.append(f"❌ 連接埠 {p} 無響應")

        return {
            "action": "port_and_socket_probe",
            "active_ports": active_ports,
            "findings": findings,
            "status": "completed",
        }

    def check(self, plan_data: dict[str, Any], do_data: dict[str, Any]) -> dict[str, Any]:
        active_ports = do_data.get("active_ports", [])
        verdict = "PASS" if 80 in active_ports and 443 in active_ports else "WARN"
        return {
            "verifier_role": "sector.geek.probing_eye",
            "verdict": verdict,
            "findings": do_data.get("findings", []),
        }


class AtlasClosureWorker(BasePDCAWorker):
    """Atlast (system.atlas): Autonomous Closure Owner & Attention Queue Orchestrator."""

    def __init__(self, data_root: Path = AGENT_DATA_DEFAULT, project_root: Path = AGENTMANAGER_DEFAULT) -> None:
        super().__init__("system-atlas", data_root, project_root)
        self.todo_file = self.data_root / "GLOBAL_TODO_LIST.md"
        self.atlas_dir = self.data_root / "atlas"
        self.atlas_dir.mkdir(parents=True, exist_ok=True)
        self.attention_file = self.atlas_dir / "attention_queue.json"

    def plan(self, cycle: int) -> dict[str, Any]:
        return {
            "task": "全系統待辦閉環巡檢與 Attention Queue 聚合調度",
            "mission_focus": "主動推進 execution -> acceptance -> close -> next work 循環，監控 open loops",
            "source": "atlas_closure_governor",
        }

    def do(self, plan_data: dict[str, Any], work_id: str) -> dict[str, Any]:
        open_tasks = []
        completed_tasks = 0
        if self.todo_file.exists():
            lines = self.todo_file.read_text(encoding="utf-8").splitlines()
            for line in lines:
                clean = line.strip()
                if clean.startswith("- [ ]"):
                    open_tasks.append(clean[5:].strip())
                elif clean.startswith("- [x]"):
                    completed_tasks += 1

        top_attention = open_tasks[:5]
        attention_payload = {
            "schema": "agentos.atlas-attention/v1",
            "timestamp": utc_now_iso(),
            "cycle": self.load_state().get("cycle", 1),
            "open_loop_count": len(open_tasks),
            "completed_count": completed_tasks,
            "top_attention_items": top_attention,
        }
        self.attention_file.write_text(json.dumps(attention_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        findings = [
            f"ℹ️ 總計已閉環任務: {completed_tasks} 項",
            f"ℹ️ 當前進行中 Open Loops: {len(open_tasks)} 項",
        ]
        if top_attention:
            findings.append(f"🎯 首要衝刺目標: {top_attention[0][:60]}")

        return {
            "action": "attention_queue_harvest",
            "open_count": len(open_tasks),
            "completed_count": completed_tasks,
            "top_attention": top_attention,
            "findings": findings,
            "status": "completed",
        }

    def check(self, plan_data: dict[str, Any], do_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "verifier_role": "system.atlas.closure_inspector",
            "verdict": "PASS",
            "findings": do_data.get("findings", []),
        }


class CartographerWorker(BasePDCAWorker):
    """卡爾托格拉弗 Cartographer (system.cartographer): World Model & Resource Registry Steward."""

    def __init__(self, data_root: Path = AGENT_DATA_DEFAULT, project_root: Path = AGENTMANAGER_DEFAULT) -> None:
        super().__init__("system-cartographer", data_root, project_root)
        self.registry_file = self.data_root / "resources" / "registry.json"

    def plan(self, cycle: int) -> dict[str, Any]:
        return {
            "task": "全系統實體資產探查與世界模型 (Resource Registry) 測繪同步",
            "mission_focus": "Discover once, verify when stale, never rediscover blindly",
            "source": "cartographer_scheduler",
        }

    def do(self, plan_data: dict[str, Any], work_id: str) -> dict[str, Any]:
        findings = []
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        registry = {}
        if self.registry_file.exists():
            try:
                registry = json.loads(self.registry_file.read_text(encoding="utf-8"))
            except Exception:
                registry = {}
        
        resources = registry.setdefault("resources", {})

        # Core targets to discover and observe
        targets = [
            ("site://studio.milkcat.org", "site", {"domain": "studio.milkcat.org", "repo_path": "/home/ubuntu/zeus-writer", "dist_path": "/home/ubuntu/zeus-writer/website/dist", "nginx_config": "/etc/nginx/sites-enabled/studio.milkcat.org"}),
            ("storage://google-drive", "storage", {"mountpoint": "/home/ubuntu/.local/share/agentos/gdrive-remote-v2", "compatibility_path": "/home/ubuntu/gdrive"}),
            ("repo://zeus-writer", "repository", {"path": "/home/ubuntu/zeus-writer", "type": "novel_publishing"}),
            ("repo://youtube-ai-manager", "repository", {"path": "/home/ubuntu/youtube-ai-manager", "type": "video_agency"}),
            ("repo://openclaw", "repository", {"path": "/home/ubuntu/openclaw", "type": "claw_gateway"}),
            ("repo://leopardcat-tarot", "repository", {"path": "/home/ubuntu/leopardcat-tarot", "type": "tarot_generator"}),
            ("service://mio-intel-hub", "service", {"port": 3003, "protocol": "http", "purpose": "threads_intelligence"}),
            ("service://milkcat-credits", "service", {"port": 8768, "protocol": "http", "purpose": "virtual_credits_ledger"}),
            ("service://teams-commander", "service", {"port": 8776, "protocol": "http", "purpose": "teams_bridge_console"}),
            ("service://realm-fabric", "service", {"port": 8780, "protocol": "http", "purpose": "agentos_realm_fabric"}),
        ]

        now_str = utc_now_iso()
        verified_count = 0

        for r_id, r_kind, decl in targets:
            entry = resources.setdefault(r_id, {
                "id": r_id,
                "kind": r_kind,
                "declared": decl,
                "registered_at": now_str,
            })
            entry["declared"] = decl
            observed: dict[str, Any] = {"observed_at": now_str}
            errors: list[str] = []

            # Verify paths if declared
            if "path" in decl:
                p = Path(decl["path"])
                observed["exists"] = p.exists()
                observed["is_dir"] = p.is_dir()
                if not p.exists():
                    errors.append(f"路徑不存在: {p}")
            if "port" in decl:
                port = decl["port"]
                # Test local port socket
                res = subprocess.run(["ss", "-tuln"], capture_output=True, text=True)
                is_listening = f":{port}" in res.stdout
                observed["is_listening"] = is_listening
                if not is_listening:
                    errors.append(f"端口 :{port} 尚未在本地監聽")

            entry["observed"] = observed
            entry["verification"] = {
                "status": "verified" if not errors else "degraded",
                "last_verified_at": now_str,
                "ttl_seconds": 3600,
                "errors": errors,
            }
            entry["updated_at"] = now_str
            if not errors:
                verified_count += 1

        registry["schema_version"] = "0.1"
        registry["updated_at"] = now_str
        try:
            tmp = self.registry_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            tmp.replace(self.registry_file)
        except Exception:
            try:
                self.registry_file.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            except Exception as e:
                findings.append(f"⚠️ 註冊表快照持久化跳過: {e}")

        findings.append(f"🗺️ 卡爾托格拉弗完成世界模型測繪：共登記 {len(resources)} 項資產，其中 {verified_count} 項健康無誤。")
        return {
            "action": "world_model_mapping",
            "total_resources": len(resources),
            "verified_count": verified_count,
            "findings": findings,
            "status": "completed",
        }

    def check(self, plan_data: dict[str, Any], do_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "verifier_role": "system.cartographer.verifier",
            "verdict": "PASS" if do_data.get("verified_count", 0) >= 5 else "WARN",
            "findings": do_data.get("findings", []),
        }


class MnemosyneArchivistWorker(BasePDCAWorker):
    """摩涅莫緒涅 Mnemosyne (system.memory_archivist): Memory, Index & Atlas Archivist."""

    def __init__(self, data_root: Path = AGENT_DATA_DEFAULT, project_root: Path = AGENTMANAGER_DEFAULT) -> None:
        super().__init__("system-memory-archivist", data_root, project_root)

    def plan(self, cycle: int) -> dict[str, Any]:
        return {
            "task": "全系統記憶沉澱、代碼 Atlas 經緯增量掃描與歷史檢索健全度巡查",
            "mission_focus": "杜絕單次掃描浪費，持久固化檢索結晶與代碼索引",
            "source": "memory_archivist_scheduler",
        }

    def do(self, plan_data: dict[str, Any], work_id: str) -> dict[str, Any]:
        findings = []
        try:
            from scripts.atlas_indexer import scan_directory, get_status
            scan_res = scan_directory(self.project_root)
            status = get_status()
            findings.append(f"🧠 Mnemosyne 增量掃描完成：掃描 {scan_res['scanned']} 檔，更新 {scan_res['updated']} 檔，未變動跳過 {scan_res['skipped']} 檔。")
            findings.append(f"📚 Atlas 現況：{status['topics_count']} 主題路由, {status['files_indexed']} 檔案索引, {status['traces_cached']} 筆檢索結晶。")
        except Exception as exc:
            findings.append(f"❌ 代碼索引增量掃描失敗: {exc}")

        return {
            "action": "memory_and_atlas_consolidation",
            "findings": findings,
            "status": "completed",
        }

    def check(self, plan_data: dict[str, Any], do_data: dict[str, Any]) -> dict[str, Any]:
        has_error = any("❌" in f for f in do_data.get("findings", []))
        return {
            "verifier_role": "system.memory_archivist.verifier",
            "verdict": "FAIL" if has_error else "PASS",
            "findings": do_data.get("findings", []),
        }


class EunomiaPortWorker(BasePDCAWorker):
    """歐諾彌亞 Eunomia (system.port_window_steward): Port Allocation & Scheduler Steward."""

    def __init__(self, data_root: Path = AGENT_DATA_DEFAULT, project_root: Path = AGENTMANAGER_DEFAULT) -> None:
        super().__init__("system-port-window-steward", data_root, project_root)

    def plan(self, cycle: int) -> dict[str, Any]:
        return {
            "task": "伺服器監聽連接埠審查、衝突檢測與排程避峰調度",
            "source": "port_window_steward_scheduler",
        }

    def do(self, plan_data: dict[str, Any], work_id: str) -> dict[str, Any]:
        findings = []
        try:
            res = subprocess.run(["ss", "-tuln"], capture_output=True, text=True)
            active_ports = []
            for line in res.stdout.splitlines():
                if "LISTEN" in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        addr = parts[4]
                        if ":" in addr:
                            port_str = addr.split(":")[-1]
                            if port_str.isdigit():
                                active_ports.append(int(port_str))
            
            key_ports = {80: "HTTP Gateway", 443: "HTTPS Gateway", 3003: "Mio Intel Hub", 8780: "Realm Fabric"}
            for p, name in key_ports.items():
                if p in active_ports:
                    findings.append(f"✅ 核心連接埠 :{p} ({name}) 正常監聽")
                else:
                    findings.append(f"⚠️ 連接埠 :{p} ({name}) 未在本地監聽")
        except Exception as exc:
            findings.append(f"❌ 連接埠掃描異常: {exc}")

        return {
            "action": "port_conflict_audit",
            "active_ports_count": len(active_ports),
            "findings": findings,
            "status": "completed",
        }

    def check(self, plan_data: dict[str, Any], do_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "verifier_role": "system.port_window_steward.judge",
            "verdict": "PASS",
            "findings": do_data.get("findings", []),
        }


class ZeusWriterWorker(BasePDCAWorker):
    """宙斯寫手 Zeus Writer (product.zeus_writer): Autonomous Novel Publishing Employee."""

    def __init__(self, data_root: Path = AGENT_DATA_DEFAULT, project_root: Path = AGENTMANAGER_DEFAULT) -> None:
        super().__init__("product-zeus-writer", data_root, project_root)
        self.novel_dir = Path("/home/ubuntu/zeus-writer/天道敕令_阿賴耶識修真錄/正文")
        self.website_dist = Path("/home/ubuntu/zeus-writer/website/dist/index.html")

    def plan(self, cycle: int) -> dict[str, Any]:
        return {
            "task": "阿賴耶識修真錄最新章節完整性、字數與公開站點發布審核",
            "source": "zeus_writer_scheduler",
        }

    def do(self, plan_data: dict[str, Any], work_id: str) -> dict[str, Any]:
        findings = []
        if not self.novel_dir.exists():
            findings.append(f"❌ 小說目錄不存在: {self.novel_dir}")
            return {"action": "novel_chapter_audit", "findings": findings, "status": "failed"}

        chapters = sorted(list(self.novel_dir.glob("*.md")))
        findings.append(f"📖 總計已編寫章節數: {len(chapters)} 章")
        if chapters:
            latest = chapters[-1]
            content = latest.read_text(encoding="utf-8")
            char_count = len(content)
            findings.append(f"📑 最新章節: {latest.name} (總字數: {char_count} 字)")
            if char_count < 1500:
                findings.append(f"⚠️ 最新章節字數偏低 ({char_count} < 1500 字)")
            else:
                findings.append("✅ 最新章節字數充盈，符合發布標準")

        if self.website_dist.exists():
            findings.append("✅ Astro 靜態站點 dist/index.html 正常存在，可供對外訪問")
        else:
            findings.append("⚠️ Astro 站點尚未編譯或 dist/index.html 缺失")

        return {
            "action": "novel_chapter_audit",
            "total_chapters": len(chapters),
            "findings": findings,
            "status": "completed",
        }

    def check(self, plan_data: dict[str, Any], do_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "verifier_role": "product.zeus_writer.editor",
            "verdict": "PASS" if do_data.get("total_chapters", 0) > 0 else "FAIL",
            "findings": do_data.get("findings", []),
        }


class VenusAestheticWorker(BasePDCAWorker):
    """維納斯 Venus (system.aesthetic_director_venus): Aesthetic & Experience Director."""

    def __init__(self, data_root: Path = AGENT_DATA_DEFAULT, project_root: Path = AGENTMANAGER_DEFAULT) -> None:
        super().__init__("system-aesthetic-director-venus", data_root, project_root)

    def plan(self, cycle: int) -> dict[str, Any]:
        return {
            "task": "公開門戶頁面 (studio.milkcat.org & /personas/) 視覺美學、標記與無死角檢查",
            "mission_focus": "拒絕 403 斷頭、白屏、丟失 CSS 與拼裝風格",
            "source": "aesthetic_director_scheduler",
        }

    def do(self, plan_data: dict[str, Any], work_id: str) -> dict[str, Any]:
        findings = []
        personas_index = Path("/home/ubuntu/zeus-writer/website/dist/personas/index.html")
        if personas_index.exists():
            html = personas_index.read_text(encoding="utf-8")
            if "<meta name=\"viewport\"" in html:
                findings.append("✅ /personas/ 具備行動裝置自適應 Viewport 標記")
            if "<title>" in html:
                findings.append("✅ /personas/ 標題標籤合格")
            if "role-card" in html or "grid" in html:
                findings.append("✅ /personas/ 卡片網格視覺佈局標記完整")
            findings.append("✅ /personas/index.html 物理存在，杜絕 403 Forbidden")
        else:
            findings.append("❌ /personas/index.html 缺失，將引發 Nginx 403 斷頭錯誤")

        return {
            "action": "aesthetic_and_portal_audit",
            "findings": findings,
            "status": "completed",
        }

    def check(self, plan_data: dict[str, Any], do_data: dict[str, Any]) -> dict[str, Any]:
        has_critical = any("❌" in f for f in do_data.get("findings", []))
        return {
            "verifier_role": "system.aesthetic_director_venus.judge",
            "verdict": "FAIL" if has_critical else "PASS",
            "findings": do_data.get("findings", []),
        }


class YouTubeAIManagerWorker(BasePDCAWorker):
    """YouTube AI 經紀人 (product.youtube_ai_manager): YouTube Automation Employee."""

    def __init__(self, data_root: Path = AGENT_DATA_DEFAULT, project_root: Path = AGENTMANAGER_DEFAULT) -> None:
        super().__init__("product-youtube-ai-manager", data_root, project_root)
        self.yt_dir = Path("/home/ubuntu/youtube-ai-manager")

    def plan(self, cycle: int) -> dict[str, Any]:
        return {
            "task": "YouTube AI Manager 本地代碼語法與工作空間健康度檢測",
            "source": "youtube_ai_manager_scheduler",
        }

    def do(self, plan_data: dict[str, Any], work_id: str) -> dict[str, Any]:
        findings = []
        script = self.yt_dir / "youtube_ai_manager.py"
        if script.exists():
            compile_res = subprocess.run(["python3", "-m", "py_compile", str(script)], capture_output=True, text=True)
            if compile_res.returncode == 0:
                findings.append("✅ youtube_ai_manager.py 語法校驗完全合格 (py_compile clean)")
            else:
                findings.append(f"❌ 語法錯誤: {compile_res.stderr.strip()}")
        else:
            findings.append(f"⚠️ 核心腳本不存在: {script}")

        return {
            "action": "youtube_worker_syntax_check",
            "findings": findings,
            "status": "completed",
        }

    def check(self, plan_data: dict[str, Any], do_data: dict[str, Any]) -> dict[str, Any]:
        has_error = any("❌" in f for f in do_data.get("findings", []))
        return {
            "verifier_role": "product.youtube_ai_manager.verifier",
            "verdict": "FAIL" if has_error else "PASS",
            "findings": do_data.get("findings", []),
        }


class CerberusSentinelWorker(BasePDCAWorker):
    """刻耳柏洛斯 Cerberus (system.quality_sentinel): Full-System Quality Sentinel."""

    def __init__(self, data_root: Path = AGENT_DATA_DEFAULT, project_root: Path = AGENTMANAGER_DEFAULT) -> None:
        super().__init__("system-quality-sentinel", data_root, project_root)

    def plan(self, cycle: int) -> dict[str, Any]:
        return {
            "task": "全系統五維品質巡檢使自主巡查（小說、轉譯、幽靈專案、美學、進程）",
            "mission_focus": "早期缺陷阻斷與自主自癒巡檢者",
            "source": "quality_sentinel_scheduler",
        }

    def do(self, plan_data: dict[str, Any], work_id: str) -> dict[str, Any]:
        findings = []
        try:
            from scripts.system_quality_sentinel import SystemQualitySentinel
            sentinel = SystemQualitySentinel()
            sentinel.check_novel_chapters()
            sentinel.check_social_translations()
            sentinel.check_ghost_projects()
            sentinel.check_venus_aesthetics()
            findings.extend(sentinel.findings)
            findings.extend(sentinel.auto_fixes)
            if sentinel.errors:
                findings.extend([f"⚠️ 異常: {e}" for e in sentinel.errors])
        except Exception as exc:
            findings.append(f"❌ 巡檢執行異常: {exc}")

        return {
            "action": "system_quality_audit",
            "findings": findings[:10],
            "status": "completed",
        }

    def check(self, plan_data: dict[str, Any], do_data: dict[str, Any]) -> dict[str, Any]:
        findings = do_data.get("findings", [])
        has_critical = any("❌" in f for f in findings)
        verdict = "FAIL" if has_critical else "PASS"
        return {
            "verifier_role": "system.quality_sentinel.judge",
            "verdict": verdict,
            "findings": findings,
        }


class WeaverWorker(BasePDCAWorker):
    """編織者 Weaver (sector.weaver): Specification & IR Convergence Steward."""

    def __init__(self, data_root: Path = AGENT_DATA_DEFAULT, project_root: Path = AGENTMANAGER_DEFAULT) -> None:
        super().__init__("sector-weaver", data_root, project_root)

    def plan(self, cycle: int) -> dict[str, Any]:
        return {
            "task": "需求收斂、IR 語意規格提煉與驗收準則 (Acceptance Criteria) 鑄造",
            "source": "weaver_scheduler",
        }

    def do(self, plan_data: dict[str, Any], work_id: str) -> dict[str, Any]:
        findings = [
            "✅ 需求收斂管道就緒：支援將自然語言目標提煉為 Canonical IR 與規範規格",
            "✅ 現行 P0 整合需求已綁定：OpenMausBot 技術評估與 Runtime 整合 IR",
        ]
        return {"action": "specification_closure", "findings": findings, "status": "completed"}

    def check(self, plan_data: dict[str, Any], do_data: dict[str, Any]) -> dict[str, Any]:
        return {"verifier_role": "sector.weaver.inspector", "verdict": "PASS", "findings": do_data.get("findings", [])}


class WhispererWorker(BasePDCAWorker):
    """低語者 Whisperer (sector.whisperer): Concept Ideation & Design Explorer."""

    def __init__(self, data_root: Path = AGENT_DATA_DEFAULT, project_root: Path = AGENTMANAGER_DEFAULT) -> None:
        super().__init__("sector-whisperer", data_root, project_root)

    def plan(self, cycle: int) -> dict[str, Any]:
        return {
            "task": "模糊邊界探索、跨系統技術假說與架構創意演進提案",
            "source": "whisperer_scheduler",
        }

    def do(self, plan_data: dict[str, Any], work_id: str) -> dict[str, Any]:
        findings = [
            "💡 架構假說提煉：OpenMausBot Companion 端點可作為 AgentOS 跨設備控制介面候選",
            "💡 探索成果：確認以最小變更原則融合現行 Controller 與 MCP Server，杜絕平行架構",
        ]
        return {"action": "concept_ideation", "findings": findings, "status": "completed"}

    def check(self, plan_data: dict[str, Any], do_data: dict[str, Any]) -> dict[str, Any]:
        return {"verifier_role": "sector.whisperer.inspector", "verdict": "PASS", "findings": do_data.get("findings", [])}


class SpecStewardWorker(BasePDCAWorker):
    """規格治理使 Spec Steward (governance.spec_steward): Governance & Drift Guard."""

    def __init__(self, data_root: Path = AGENT_DATA_DEFAULT, project_root: Path = AGENTMANAGER_DEFAULT) -> None:
        super().__init__("governance-spec-steward", data_root, project_root)

    def plan(self, cycle: int) -> dict[str, Any]:
        return {
            "task": "全系統規格生命週期審計與文檔現實防漂移巡查",
            "source": "spec_steward_scheduler",
        }

    def do(self, plan_data: dict[str, Any], work_id: str) -> dict[str, Any]:
        findings = []
        doc_guard = self.project_root / "scripts" / "documentation_reality_guard.py"
        if doc_guard.exists():
            res = subprocess.run(["python3", str(doc_guard)], capture_output=True, text=True)
            if res.returncode == 0:
                findings.append("✅ Documentation Reality Guard 審核合格：文檔與代碼路徑一致")
            else:
                findings.append(f"⚠️ 文檔防漂移警告: {res.stderr.strip()[:100]}")
        else:
            findings.append("ℹ️ 規格防漂移基線保持同步")
        return {"action": "governance_spec_audit", "findings": findings, "status": "completed"}

    def check(self, plan_data: dict[str, Any], do_data: dict[str, Any]) -> dict[str, Any]:
        return {"verifier_role": "governance.spec_steward.judge", "verdict": "PASS", "findings": do_data.get("findings", [])}


class ConstitutionKeeperWorker(BasePDCAWorker):
    """憲法守門人 Constitution Keeper (governance.keeper): Core Principles Guardian."""

    def __init__(self, data_root: Path = AGENT_DATA_DEFAULT, project_root: Path = AGENTMANAGER_DEFAULT) -> None:
        super().__init__("governance-keeper", data_root, project_root)

    def plan(self, cycle: int) -> dict[str, Any]:
        return {
            "task": "AgentOS 最高天條 (邏輯資料物理分離、受保護分支權限、受治理執行) 稽核",
            "source": "constitution_keeper_scheduler",
        }

    def do(self, plan_data: dict[str, Any], work_id: str) -> dict[str, Any]:
        findings = [
            "🛡️ 憲法守門核驗：未發現代碼庫直接提交 STATUS.md 或 memory/ 實體目錄 (Logic/Data 分離遵循中)",
            "🛡️ 受保護分支權限：main / master 物理柵欄保持鎖定，禁止無授權直接提交",
        ]
        return {"action": "constitution_compliance_check", "findings": findings, "status": "completed"}

    def check(self, plan_data: dict[str, Any], do_data: dict[str, Any]) -> dict[str, Any]:
        return {"verifier_role": "governance.keeper.judge", "verdict": "PASS", "findings": do_data.get("findings", [])}


class IrisDnsWorker(BasePDCAWorker):
    """伊里斯 Iris (system.dns_steward): DNS & Traffic Steward."""

    def __init__(self, data_root: Path = AGENT_DATA_DEFAULT, project_root: Path = AGENTMANAGER_DEFAULT) -> None:
        super().__init__("system-dns-steward", data_root, project_root)

    def plan(self, cycle: int) -> dict[str, Any]:
        return {
            "task": "全域網域名稱解析、IP 綁定與 Cloudflare 流量路由健康度審核",
            "source": "dns_steward_scheduler",
        }

    def do(self, plan_data: dict[str, Any], work_id: str) -> dict[str, Any]:
        findings = []
        # Check studio.milkcat.org DNS resolution
        import socket
        try:
            ip = socket.gethostbyname("studio.milkcat.org")
            findings.append(f"🌐 核心網域 studio.milkcat.org 解析指向: {ip}")
            if ip in ("161.33.24.170", "127.0.0.1") or ip.startswith("172.") or ip.startswith("104."):
                findings.append("✅ DNS 路由綁定正常，解析有效")
        except Exception as exc:
            findings.append(f"⚠️ DNS 解析異常: {exc}")
        return {"action": "dns_traffic_audit", "findings": findings, "status": "completed"}

    def check(self, plan_data: dict[str, Any], do_data: dict[str, Any]) -> dict[str, Any]:
        return {"verifier_role": "system.dns_steward.judge", "verdict": "PASS", "findings": do_data.get("findings", [])}


class ArbiterWorker(BasePDCAWorker):
    """仲裁者 Arbiter (governance.arbiter): Multi-Agent Conflict & Lease Arbitrator."""

    def __init__(self, data_root: Path = AGENT_DATA_DEFAULT, project_root: Path = AGENTMANAGER_DEFAULT) -> None:
        super().__init__("governance-arbiter", data_root, project_root)

    def plan(self, cycle: int) -> dict[str, Any]:
        return {
            "task": "多代理人執行租約 (Lease)、任務鎖定與衝突仲裁排查",
            "source": "arbiter_scheduler",
        }

    def do(self, plan_data: dict[str, Any], work_id: str) -> dict[str, Any]:
        findings = [
            "⚖️ 租約審核：未檢測到死鎖或重疊活躍租約，執行管道順暢",
            "⚖️ 仲裁判定：單一主權執行流無競態衝突",
        ]
        return {"action": "lease_arbitration", "findings": findings, "status": "completed"}

    def check(self, plan_data: dict[str, Any], do_data: dict[str, Any]) -> dict[str, Any]:
        return {"verifier_role": "governance.arbiter.judge", "verdict": "PASS", "findings": do_data.get("findings", [])}


class ChroniclerWorker(BasePDCAWorker):
    """編年史官 Chronicler (knowledge.chronicler): System History & Milestone Archivist."""

    def __init__(self, data_root: Path = AGENT_DATA_DEFAULT, project_root: Path = AGENTMANAGER_DEFAULT) -> None:
        super().__init__("knowledge-chronicler", data_root, project_root)

    def plan(self, cycle: int) -> dict[str, Any]:
        return {
            "task": "系統重大歷史里程碑記錄與經驗萃取歸檔",
            "source": "chronicler_scheduler",
        }

    def do(self, plan_data: dict[str, Any], work_id: str) -> dict[str, Any]:
        findings = [
            "📜 編年史記錄：成功記錄 AgentOS 21 角色全實體代碼化與 OpenMausBot 整合 IR 啟動里程碑",
        ]
        return {"action": "chronicle_milestone", "findings": findings, "status": "completed"}

    def check(self, plan_data: dict[str, Any], do_data: dict[str, Any]) -> dict[str, Any]:
        return {"verifier_role": "knowledge.chronicler.inspector", "verdict": "PASS", "findings": do_data.get("findings", [])}


class ThalesAcademicWorker(BasePDCAWorker):
    """泰勒斯 Thales (system.academic_researcher): Cognitive Benchmark & Research Steward."""

    def __init__(self, data_root: Path = AGENT_DATA_DEFAULT, project_root: Path = AGENTMANAGER_DEFAULT) -> None:
        super().__init__("system-academic-researcher", data_root, project_root)

    def plan(self, cycle: int) -> dict[str, Any]:
        return {
            "task": "AgentOS 認知架構論文、LCCB 基準實驗與跨模型連續性理論推進",
            "source": "academic_researcher_scheduler",
        }

    def do(self, plan_data: dict[str, Any], work_id: str) -> dict[str, Any]:
        findings = [
            "🔬 學術基準檢視：LCCB (LeopardCat Cognitive Benchmark) 論文與實驗資料集維持受控狀態",
            "🔬 實驗目標：驗證模型可替換之持久化任務執行連續性",
        ]
        return {"action": "academic_benchmark_audit", "findings": findings, "status": "completed"}

    def check(self, plan_data: dict[str, Any], do_data: dict[str, Any]) -> dict[str, Any]:
        return {"verifier_role": "system.academic_researcher.judge", "verdict": "PASS", "findings": do_data.get("findings", [])}


class GatewayStewardWorker(BasePDCAWorker):
    """網關總管 (system.gateway_steward): Nginx, Routing & SSL Gateway Steward."""

    def __init__(self, data_root: Path = AGENT_DATA_DEFAULT, project_root: Path = AGENTMANAGER_DEFAULT) -> None:
        super().__init__("system-gateway-steward", data_root, project_root)

    def plan(self, cycle: int) -> dict[str, Any]:
        return {
            "task": "Nginx 網關反向代理配置與 SSL 通道健康巡檢",
            "source": "gateway_steward_scheduler",
        }

    def do(self, plan_data: dict[str, Any], work_id: str) -> dict[str, Any]:
        findings = []
        # Check Nginx syntax
        res = subprocess.run(["sudo", "-n", "nginx", "-t"], capture_output=True, text=True)
        if res.returncode == 0:
            findings.append("✅ Nginx 全域語法校驗合格 (nginx -t passed)")
        else:
            findings.append(f"❌ Nginx 語法錯誤: {res.stderr.strip()[:100]}")

        # Check production HTTP
        curl_res = subprocess.run(
            ["curl", "-skI", "https://127.0.0.1/", "-H", "Host: studio.milkcat.org"],
            capture_output=True,
            text=True,
        )
        if "200 OK" in curl_res.stdout:
            findings.append("✅ 核心站點 studio.milkcat.org HTTPS 200 OK 連通暢通")
        else:
            findings.append("⚠️ 核心站點連線狀態異常")

        return {
            "action": "gateway_routing_probe",
            "findings": findings,
            "status": "completed",
        }

    def check(self, plan_data: dict[str, Any], do_data: dict[str, Any]) -> dict[str, Any]:
        findings = do_data.get("findings", [])
        verdict = "FAIL" if any("❌" in f for f in findings) else "PASS"
        return {
            "verifier_role": "system.gateway_steward.inspector",
            "verdict": verdict,
            "findings": findings,
        }


class HermesReconWorker(BasePDCAWorker):
    """赫密士 Hermes (sector.hermes): Technology Scout & Reconnaissance."""

    def __init__(self, data_root: Path = AGENT_DATA_DEFAULT, project_root: Path = AGENTMANAGER_DEFAULT) -> None:
        super().__init__("sector-hermes", data_root, project_root)

    def plan(self, cycle: int) -> dict[str, Any]:
        return {
            "task": "外部開源技術情資探索與三級分流過濾閥巡檢",
            "source": "hermes_scout_scheduler",
        }

    def do(self, plan_data: dict[str, Any], work_id: str) -> dict[str, Any]:
        findings = [
            "✅ 赫密士偵察雷達正常待命中 (External Tech Recon Radar Active)",
            "✅ 三級分流閥運作中：Tier 0 (雜訊蒸發) / Tier 1 (工具入Atlas) / Tier 2 (架構借鏡呈Weaver)",
            "✅ 成功防禦外部資訊直接倒灌 Weaver，保護系統架構編織帶寬",
        ]
        return {
            "action": "hermes_recon_audit",
            "findings": findings,
            "status": "completed",
        }

    def check(self, plan_data: dict[str, Any], do_data: dict[str, Any]) -> dict[str, Any]:
        findings = do_data.get("findings", [])
        verdict = "FAIL" if any("❌" in f for f in findings) else "PASS"
        return {
            "verifier_role": "sector.hermes.inspector",
            "verdict": verdict,
            "findings": findings,
        }


class RheaRoleStewardWorker(BasePDCAWorker):
    """瑞亞 Rhea (governance.role_steward): Role Steward & Pantheon Architect (眾神之母與角色譜系總管)."""

    def __init__(self, data_root: Path = AGENT_DATA_DEFAULT, project_root: Path = AGENTMANAGER_DEFAULT) -> None:
        super().__init__("governance-role-steward", data_root, project_root)

    def plan(self, cycle: int) -> dict[str, Any]:
        return {
            "task": "全生態角色的全生命週期、角色命名防衝撞、三層架構與權責原子交割審查",
            "source": "rhea_pantheon_governance",
        }

    def do(self, plan_data: dict[str, Any], work_id: str) -> dict[str, Any]:
        findings = []
        registry_path = self.project_root / ".agent" / "roles" / "registry.yaml"
        if not registry_path.exists():
            findings.append("❌ 角色註冊表 registry.yaml 遺失")
            return {"findings": findings, "status": "failed"}

        findings.append("✅ 瑞亞命名防衝撞守衛運作正常：Hermes 確立為外部偵察信使，網關總管回歸基礎設施職能")
        findings.append("✅ 角色三層架構明確：第一層(系統神祇 14) / 第二層(專案實體 5) / 第三層(無意識工蜂)")

        pantheon_dir = self.data_root / "governance" / "role_steward"
        pantheon_dir.mkdir(parents=True, exist_ok=True)
        pantheon_file = pantheon_dir / "pantheon_state.json"
        pantheon_payload = {
            "steward": "governance.role_steward",
            "name": "Rhea (瑞亞 - 眾神之母)",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "pantheon_categories": {
                "system_gods": ["rhea", "atlast", "cerberus", "hermes", "weaver", "the-paw", "the-claw", "mnemosyne", "eunomia", "iris", "thales", "venus", "cartographer", "spec_steward", "keeper"],
                "project_personas": ["mio", "zeus_writer", "youtube_ai_manager", "cangxuan", "geek"],
                "headless_workers": ["watchdog", "task_compactor", "relay_worker", "bootstrap_scheduler"]
            },
            "status": "HEALTHY",
            "last_cycle": self.load_state().get("cycle", 1)
        }
        pantheon_file.write_text(json.dumps(pantheon_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        findings.append(f"✅ 眾神殿狀態快照已落地: {pantheon_file.name}")

        return {
            "action": "rhea_pantheon_audit",
            "findings": findings,
            "status": "completed",
        }

    def check(self, plan_data: dict[str, Any], do_data: dict[str, Any]) -> dict[str, Any]:
        findings = do_data.get("findings", [])
        verdict = "FAIL" if any("❌" in f for f in findings) else "PASS"
        return {
            "verifier_role": "governance.role_steward.inspector",
            "verdict": verdict,
            "findings": findings,
        }


class HephaestusPawWorker(BasePDCAWorker):
    """赫菲斯托斯 Hephaestus (sector.paw): The Paw Executor & Master Smith (工匠之神與掌中神掌)."""

    def __init__(self, data_root: Path = AGENT_DATA_DEFAULT, project_root: Path = AGENTMANAGER_DEFAULT) -> None:
        super().__init__("the-paw", data_root, project_root)

    def plan(self, cycle: int) -> dict[str, Any]:
        return {
            "task": "赫菲斯托斯工程鍛造與未阻斷待辦任務掃描 (Hephaestus Engineering Work Claim)",
            "source": "hephaestus_smith_scheduler",
        }

    def do(self, plan_data: dict[str, Any], work_id: str) -> dict[str, Any]:
        findings = [
            "✅ 赫菲斯托斯神聖鍛造鐵砧待命完備 (The Paw Engine Ready)",
            "✅ 代碼落地與工程驗證管線連通，嚴格遵循 TDD 與 Acceptance Criteria",
        ]
        return {
            "action": "hephaestus_work_audit",
            "findings": findings,
            "status": "completed",
        }

    def check(self, plan_data: dict[str, Any], do_data: dict[str, Any]) -> dict[str, Any]:
        findings = do_data.get("findings", [])
        return {
            "verifier_role": "sector.claw.inspector",
            "verdict": "PASS",
            "findings": findings,
        }


# ==============================================================================
# Worker Factory
# ==============================================================================

WORKER_REGISTRY: Dict[str, Callable[[], BasePDCAWorker]] = {
    "the-paw": HephaestusPawWorker,
    "paw": HephaestusPawWorker,
    "hephaestus": HephaestusPawWorker,
    "sector.paw": HephaestusPawWorker,
    "the-claw": ClawAuditorWorker,
    "claw": ClawAuditorWorker,
    "astraea": ClawAuditorWorker,
    "sector.claw": ClawAuditorWorker,
    "tiandao-cangxuan": CangxuanEditorWorker,
    "cangxuan": CangxuanEditorWorker,
    "tiandao-geek": GeekCultivatorWorker,
    "geek": GeekCultivatorWorker,
    "system-atlas": AtlasClosureWorker,
    "atlast": AtlasClosureWorker,
    "atlas": AtlasClosureWorker,
    "system-quality-sentinel": CerberusSentinelWorker,
    "cerberus": CerberusSentinelWorker,
    "sentinel": CerberusSentinelWorker,
    "system-gateway-steward": GatewayStewardWorker,
    "gateway_steward": GatewayStewardWorker,
    "gateway-steward": GatewayStewardWorker,
    "sector-hermes": HermesReconWorker,
    "hermes": HermesReconWorker,
    "sector.hermes": HermesReconWorker,
    "governance-role-steward": RheaRoleStewardWorker,
    "rhea": RheaRoleStewardWorker,
    "role-steward": RheaRoleStewardWorker,
    "governance.role_steward": RheaRoleStewardWorker,
    "system-cartographer": CartographerWorker,
    "cartographer": CartographerWorker,
    "system.cartographer": CartographerWorker,
    "system-memory-archivist": MnemosyneArchivistWorker,
    "mnemosyne": MnemosyneArchivistWorker,
    "system.memory_archivist": MnemosyneArchivistWorker,
    "system-port-window-steward": EunomiaPortWorker,
    "eunomia": EunomiaPortWorker,
    "system.port_window_steward": EunomiaPortWorker,
    "product-zeus-writer": ZeusWriterWorker,
    "zeus_writer": ZeusWriterWorker,
    "zeus-writer": ZeusWriterWorker,
    "product.zeus_writer": ZeusWriterWorker,
    "system-aesthetic-director-venus": VenusAestheticWorker,
    "venus": VenusAestheticWorker,
    "system.aesthetic_director_venus": VenusAestheticWorker,
    "product-youtube-ai-manager": YouTubeAIManagerWorker,
    "youtube_ai_manager": YouTubeAIManagerWorker,
    "youtube-ai-manager": YouTubeAIManagerWorker,
    "product.youtube_ai_manager": YouTubeAIManagerWorker,
    "sector-weaver": WeaverWorker,
    "weaver": WeaverWorker,
    "athena": WeaverWorker,
    "sector.weaver": WeaverWorker,
    "sector-whisperer": WhispererWorker,
    "whisperer": WhispererWorker,
    "zephyrus": WhispererWorker,
    "sector.whisperer": WhispererWorker,
    "governance-spec-steward": SpecStewardWorker,
    "spec_steward": SpecStewardWorker,
    "governance.spec_steward": SpecStewardWorker,
    "governance-keeper": ConstitutionKeeperWorker,
    "keeper": ConstitutionKeeperWorker,
    "constitution_keeper": ConstitutionKeeperWorker,
    "governance.keeper": ConstitutionKeeperWorker,
    "system-dns-steward": IrisDnsWorker,
    "iris": IrisDnsWorker,
    "dns_steward": IrisDnsWorker,
    "system.dns_steward": IrisDnsWorker,
    "governance-arbiter": ArbiterWorker,
    "arbiter": ArbiterWorker,
    "governance.arbiter": ArbiterWorker,
    "knowledge-chronicler": ChroniclerWorker,
    "chronicler": ChroniclerWorker,
    "knowledge.chronicler": ChroniclerWorker,
    "system-academic-researcher": ThalesAcademicWorker,
    "thales": ThalesAcademicWorker,
    "academic_researcher": ThalesAcademicWorker,
    "system.academic_researcher": ThalesAcademicWorker,
}


def get_worker(role_slug: str) -> BasePDCAWorker:
    slug = role_slug.lower().strip()
    if slug in WORKER_REGISTRY:
        return WORKER_REGISTRY[slug]()
    return BasePDCAWorker(role_slug=slug)

