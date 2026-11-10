#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
System Quality Sentinel (全系統品質巡檢官)
自動化巡檢：小說結構、社群轉譯天條、幽靈專案目錄、Venus美學規範、背景死循環存檔衝突
"""

import os
import sys
import re
import json
import shutil
from pathlib import Path
from datetime import datetime

AGENT_DATA_ROOT = Path("/home/ubuntu/agent-data")
ZEUS_WRITER_ROOT = Path("/home/ubuntu/zeus-writer")
AGENTMANAGER_ROOT = Path("/home/ubuntu/agentmanager")

sys.path.insert(0, str(AGENTMANAGER_ROOT))
try:
    from agent_core.incident_queue import enqueue_incident
except ImportError:
    enqueue_incident = None

class SystemQualitySentinel:
    def __init__(self):
        self.findings = []
        self.errors = []
        self.auto_fixes = []

    def log_finding(self, msg: str):
        print(f"ℹ️  [巡檢記錄] {msg}")
        self.findings.append(msg)

    def log_error(self, msg: str, target: str = "system", incident_type: str = "QUALITY_DEFECT"):
        print(f"❌ [巡檢異常] {msg}")
        self.errors.append(msg)
        if enqueue_incident:
            try:
                enqueue_incident(
                    detector="quality-sentinel",
                    target=target,
                    incident_type=incident_type,
                    severity="medium",
                    summary=msg,
                    evidence={"raw_message": msg}
                )
            except Exception:
                pass

    def log_fix(self, msg: str):
        print(f"🛠️ [自動自癒] {msg}")
        self.auto_fixes.append(msg)

    # ── 1. 小說正文排版與字數檢查 ──
    def check_novel_chapters(self):
        print("\n📖 [檢查 1] 檢測《天道敕令》已發布章節格式與字數...")
        chapters_dir = ZEUS_WRITER_ROOT / "天道敕令_阿賴耶識修真錄" / "正文"
        if not chapters_dir.exists():
            self.log_error("找不到《天道敕令》正文資料夾！")
            return

        for ch_file in sorted(chapters_dir.glob("*.md")):
            content = ch_file.read_text(encoding="utf-8")
            clean_text = re.sub(r"[#\s\-\*\>\_]", "", content)
            char_count = len(clean_text)

            sections = re.findall(r"^##\s+第[一二三四五六七八九十百]+節", content, re.MULTILINE)
            section_count = len(sections)

            if section_count < 5:
                self.log_error(f"{ch_file.name}: 僅有 {section_count}/5 節結構，缺少標準五節劃分！")
            elif char_count < 2700:
                self.log_error(f"{ch_file.name}: 字數不足（僅 {char_count} 漢字，要求 >= 3000）！")
            else:
                self.log_finding(f"{ch_file.name}: 五節齊全，字數達標（{char_count} 漢字）")

    # ── 2. 社群轉譯天條洩漏檢查 ──
    def check_social_translations(self):
        print("\n🕊️ [檢查 2] 檢測全域社群轉譯 (Social Translation) 天條外洩...")
        guard_script = ZEUS_WRITER_ROOT / "scripts" / "social_translation_guard.py"
        if not guard_script.exists():
            self.log_error("找不到 social_translation_guard.py！")
            return

        sys.path.append(str(ZEUS_WRITER_ROOT / "scripts"))
        try:
            from social_translation_guard import scan_all_translations
            if scan_all_translations(str(ZEUS_WRITER_ROOT)):
                self.log_finding("全域轉譯通過沉浸度審查，無任何現代技術詞洩漏。")
            else:
                self.log_error("社群轉譯檔案中包含違規技術名詞或出戲用語！")
        except Exception as e:
            self.log_error(f"執行社群轉譯巡檢失敗: {e}")

    # ── 3. 幽靈 SHA 雜湊專案目錄檢查與自動清理 ──
    def check_ghost_projects(self):
        print("\n👻 [檢查 3] 檢測 agent-data/projects/ 幽靈專案目錄...")
        projects_dir = AGENT_DATA_ROOT / "projects"
        if not projects_dir.exists():
            return

        hash_pattern = re.compile(r"^[0-9a-f]{40}$")
        found_ghosts = []
        for d in projects_dir.iterdir():
            if d.is_dir() and hash_pattern.match(d.name):
                found_ghosts.append(d)

        if found_ghosts:
            for g in found_ghosts:
                self.log_error(f"發現 CI/CD 殘留之幽靈雜湊目錄: {g.name}")
                shutil.rmtree(g, ignore_errors=True)
                self.log_fix(f"已自動清理幽靈專案目錄: {g.name}")
        else:
            self.log_finding("專案目錄結構乾淨，無 40 碼 SHA 幽靈專案。")

    # ── 4. Venus 美學標準檢查 ──
    def check_venus_aesthetics(self):
        print("\n🎨 [檢查 4] 檢測官網 Venus 美學標準與導覽結構...")
        index_astro = ZEUS_WRITER_ROOT / "website" / "src" / "pages" / "index.astro"
        if not index_astro.exists():
            self.log_error("找不到 website/src/pages/index.astro！")
            return

        content = index_astro.read_text(encoding="utf-8")

        # 檢測 Navbar 是否包含 Dropdown
        if "nav-dropdown" not in content:
            self.log_error("Navbar 缺少 nav-dropdown 下拉選單，可能退化為按鈕平鋪！")
        else:
            self.log_finding("Navbar 符合 Venus 下拉選單結構。")

        # 檢測獨立 LoginModal 與 SupportModal 是否存在
        if "login-modal" not in content:
            self.log_error("缺少獨立抽離的 login-modal 元件！")
        if "support-modal" not in content:
            self.log_error("缺少獨立抽離的 support-modal 元件！")

        # 檢測預設視圖是否為 3D 世界
        if "switchView('frame', '/world')" in content or 'data-url="/world"' in content:
            self.log_finding("首頁預設視圖配置符合 3D 沉浸入口標準。")
        else:
            self.log_error("首頁預設視圖未指向 3D 世界！")

    # ── 5. 背景程序死循環與檔案衝突檢測 ──
    def check_file_conflicts_and_deadlocks(self):
        print("\n🔄 [檢查 5] 檢測背景任務是否狂刷 STATUS.md 造成存檔衝突...")
        lobster_log = AGENTMANAGER_ROOT / "logs" / "lobster.log"
        if lobster_log.exists():
            # 讀取最後 100 行
            try:
                with open(lobster_log, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()[-100:]
                log_text = "".join(lines)

                # 檢測短時間內是否有頻繁任務失敗
                fail_matches = re.findall(r"任務失敗|Not a directory|BLOCKED", log_text)
                if len(fail_matches) > 15:
                    self.log_error(f"Lobster 背景程序近 100 行中出現 {len(fail_matches)} 次失敗/阻斷，可能正在死循環狂刷 STATUS.md！")
                else:
                    self.log_finding("Lobster 背景日誌無高頻短週期死循環現象。")
            except Exception as e:
                self.log_finding(f"讀取 lobster 日誌跳過: {e}")

    # ── 6. 角色真實性與紙上談兵防線檢測 ──
    def check_role_reality_guard(self):
        print("\n🎭 [檢查 6] 檢測全域角色真實性（嚴查無代碼、無目錄之紙上假人）...")
        try:
            from scripts.role_reality_guard import check_role_reality
            reports, breaches = check_role_reality()
            if breaches:
                for b in breaches:
                    self.log_error(f"查獲紙上談兵虛假角色: {b}")
            else:
                self.log_finding(f"所有 Active 角色 ({len(reports)} 個) 均具備實體代碼與執行憑證，零紙上假人。")
        except Exception as e:
            self.log_error(f"執行角色真實性守門失敗: {e}")

    def run_all(self):
        print("=" * 60)
        print("🛡️  全系統品質巡檢使 (System Quality Sentinel) 開始巡檢")
        print(f"⏰ 時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        self.check_novel_chapters()
        self.check_social_translations()
        self.check_ghost_projects()
        self.check_venus_aesthetics()
        self.check_file_conflicts_and_deadlocks()
        self.check_role_reality_guard()

        print("\n" + "=" * 60)
        print("📋 巡檢總結報告")
        print("=" * 60)
        print(f"✅ 合規記錄: {len(self.findings)} 項")
        print(f"🛠️ 自癒修復: {len(self.auto_fixes)} 項")
        print(f"❌ 待辦異常: {len(self.errors)} 項")

        report_dir = AGENT_DATA_ROOT / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_file = report_dir / "quality_sentinel_report.md"

        with open(report_file, "w", encoding="utf-8") as f:
            f.write(f"# 🛡️ System Quality Sentinel 巡檢報告\n\n")
            f.write(f"- **巡檢時間**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"- **合規項數**：{len(self.findings)}\n")
            f.write(f"- **自癒項數**：{len(self.auto_fixes)}\n")
            f.write(f"- **異常項數**：{len(self.errors)}\n\n")

            if self.errors:
                f.write("## ❌ 異常發現\n")
                for err in self.errors:
                    f.write(f"- {err}\n")
                f.write("\n")

            if self.auto_fixes:
                f.write("## 🛠️ 自癒處理\n")
                for fix in self.auto_fixes:
                    f.write(f"- {fix}\n")
                f.write("\n")

            f.write("## ✅ 合規項目\n")
            for fin in self.findings:
                f.write(f"- {fin}\n")

        print(f"📄 報告已儲存至: {report_file}")
        return len(self.errors) == 0

if __name__ == "__main__":
    sentinel = SystemQualitySentinel()
    success = sentinel.run_all()
    sys.exit(0 if success else 1)

