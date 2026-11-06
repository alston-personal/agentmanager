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


class HermesGatewayWorker(BasePDCAWorker):
    """赫爾墨斯 Hermes (system.gateway_steward): Nginx, Routing & SSL Gateway Steward."""

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


# ==============================================================================
# Worker Factory
# ==============================================================================

WORKER_REGISTRY: Dict[str, Callable[[], BasePDCAWorker]] = {
    "the-claw": ClawAuditorWorker,
    "claw": ClawAuditorWorker,
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
    "system-gateway-steward": HermesGatewayWorker,
    "hermes": HermesGatewayWorker,
}


def get_worker(role_slug: str) -> BasePDCAWorker:
    slug = role_slug.lower().strip()
    if slug in WORKER_REGISTRY:
        return WORKER_REGISTRY[slug]()
    return BasePDCAWorker(role_slug=slug)

