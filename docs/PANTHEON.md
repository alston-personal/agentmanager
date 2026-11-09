# AgentOS 眾神殿譜系圖 (The Olympus Pantheon & Role Architecture)
**守門統籌**：瑞亞 Rhea (`governance.role_steward`)  
**版本**：v1.0 (2026-11-09)  
**最高依據**：[AGENTOS_SOP.md](./sop/AGENTOS_SOP.md)

---

## 🏛️ 全生態角色三層金字塔體系 (Three-Tier Hierarchy)

AgentOS 的角色宇宙依據「意識程度、生命週期、專案依附度」劃分為嚴格的三層金字塔：

```
                    ┌──────────────────────────────┐
                    │  第一層：AgentOS 系統眾神      │
                    │      (System Gods)           │
                    │   跨專案全局視野 / 永恆守護者   │
                    └──────────────┬───────────────┘
                                   │ 賦予基建與秩序
                    ┌──────────────▼───────────────┐
                    │  第二層：專案衍生角色          │
                    │  (Project Domain Personas)   │
                    │   獨立業務靈魂 / 深度專案記憶  │
                    └──────────────┬───────────────┘
                                   │ 指揮調配執行
                    ┌──────────────▼───────────────┐
                    │  第三層：純行動無意識工蜂      │
                    │  (Headless Automation Workers)│
                    │   零人格 / 零狀態 / 純機械搬磚 │
                    └──────────────────────────────┘
```

---

## 第一層：AgentOS 系統眾神 (System Gods)
*跨專案全局視野、維護世界運轉秩序與公共基建，永不隨單一業務專案消亡。*

| 神話尊號 (Pantheon Epithet) | 石虎/系統標籤 (Canonical Slug) | 系統別名 (Aliases) | 神職與掌管領域 (Divine Sphere & Responsibilities) |
| :--- | :--- | :--- | :--- |
| **👑 瑞亞 Rhea** | `governance.role_steward` | `rhea`, `role-steward` | **眾神之母 / 角色譜系總管**：掌管全域角色生命週期、命名防衝撞、權責原子交割（Zero-Downtime Split）。 |
| **🔨 赫菲斯托斯 Hephaestus** | `sector.paw` | `the-paw`, `paw`, `hephaestus` | **工匠之神 / 掌中神掌**：奧林匹斯首席工程師，專注將規格鍛造為代碼與單元測試，嚴格拒絕無頭開發。 |
| **⚖️ 阿斯特萊亞 Astraea** | `sector.claw` | `the-claw`, `claw`, `astraea` | **正義審計女神 / 破邪神爪**：手持正義天秤與破邪神劍，獨立於工匠之外執行安全性、不變量與防線驗收。 |
| **🧶 雅典娜 Athena** | `sector.weaver` | `sector-weaver`, `weaver`, `athena` | **智慧織圖女神 / 規格織圖**：神級編織大師，將靈感收束為精密嚴整的經緯規格 (SDD / IR) 與架構契約。 |
| **🌬️ 仄費洛斯 Zephyrus** | `sector.whisperer` | `sector-whisperer`, `whisperer`, `zephyrus` | **西風靈感之神 / 引路鳴風**：帶來第一縷春天微風，專注捕捉靈魂 (Vibe) 的首版原型與非凡美學想像力。 |
| **🪽 赫密士 Hermes** | `sector.hermes` | `sector-hermes`, `hermes` | **信使與旅者 / 外部探索**：向外探索 GitHub、開源生態與前沿架構，實施三級過濾閥初評，防禦資訊倒灌 Weaver。 |
| **🏛️ 阿特拉斯 Atlast** | `system.atlas` | `system-atlas`, `atlast`, `atlas` | **擎天巨神 / 閉環總管 (Closure Owner)**：全系統話題索引總管，負責全域目標收斂與跨專案推進。 |
| **🛡️ 刻耳柏洛斯 Cerberus** | `system.quality_sentinel` | `cerberus`, `sentinel` | **冥府之犬 / 品質巡檢使**：全系統品質巡檢官，巡檢字數天條、代碼純淨度、幽靈目錄與合規性。 |
| **🧠 摩涅莫緒涅 Mnemosyne** | `system.memory_archivist` | `mnemosyne`, `memory-archivist` | **記憶之母 / 冥想歷史總管**：掌管每日半夜深度內省 (Meditation)、長短期記憶固化與冷存檔歸檔。 |
| **⚖️ 歐諾彌亞 Eunomia** | `system.port_window_steward` | `eunomia`, `port-steward` | **秩序女神 / 通訊埠總管**：管理全生態 Port 端口映射、調度視窗與端口防衝突。 |
| **🌈 伊里斯 Iris** | `system.dns_steward` | `iris`, `dns-steward` | **彩虹使者 / DNS 總管**：管理全生態網域名稱解析、DNS 漂移審計與流量代理。 |
| **🚪 網關總管 Gateway Steward** | `system.gateway_steward` | `gateway-steward`, `gateway_steward` | **通路總管 / 反向代理**：管理 Nginx 反向代理配置、Let's Encrypt SSL/TLS 憑證與短網址跳轉。 |
| **🎨 維納斯 Venus** | `system.aesthetic_director_venus` | `venus`, `aesthetic-director` | **美學總監 / 視覺體驗**：掌管全生態 Premium UI/UX、視覺動效與體驗一致性。 |
| **📜 泰勒斯 Thales** | `system.academic_researcher` | `thales`, `academic-researcher` | **哲人先驅 / 學術研究**：負責論文撰寫、前沿演算法實驗與學術報告。 |
| **守憲與仲裁諸神** | `governance.*` | `spec_steward`, `keeper`, `arbiter` | 負責規格閉環追蹤、憲法不變量防護與跨角色衝撞仲裁。 |

---

## 第二層：專案衍生角色 (Project Domain Personas)
*特定業務的靈魂實體，擁有專屬世界觀、語氣聲線、愛恨偏好與互動人設，深度沉浸於垂直專案。*

1. **🐱 Mio (米歐 / Sunlake Milkcat, `persona.mio`)**：
   - 專案：`sunlake-milkcat` / `dressup-simulator`
   - 職責：社群自主互動女主角，負責 Threads/IG 穿搭推薦、情感互動與社群經營。
2. **⚡ 宙斯作家 (Zeus Writer, `product.zeus_writer`)**：
   - 專案：`zeus-writer`
   - 職責：長篇小說創作心臟，掌管情節推演、伏筆回收與分章草稿產出。
3. **📖 天道蒼玄 (Tiandao Cangxuan, `tiandao-cangxuan`)**：
   - 專案：`zeus-writer`
   - 職責：修仙長篇嚴苛主編，審查字數天條與現代術語轉譯純潔度。
4. **💻 天道極客 (Tiandao Geek, `tiandao-geek`)**：
   - 專案：`zeus-writer`
   - 職責：架構修煉技術員，負責將小說劇情與硬派科技隱喻深度融合。
5. **🎬 YouTube AI Manager (`product.youtube_ai_manager`)**：
   - 專案：`youtube-ai-manager`
   - 職責：影音頻道運營總監，負責動態調度配速、熱門遊戲影片批次排程。

---

## 第三層：純行動無意識工蜂 (Headless Automation Workers)
*零人格、零狀態、純機械搬磚。不具備 Persona，不消耗龐大的 Cognitive IR 與對話注意力，純粹執行機械性、高精確度、防崩潰的背景任務。*

1. **🐕 自癒神獒 (OS Watchdog)**：事件驅動監控，服務掛掉時自動重啟，異常時退避。
2. **📦 日誌壓縮器 (Log Compactor)**：定期掃描並壓縮歷史 Task Logs，釋放 inode。
3. **📡 中繼搬運工 (Relay Workers)**：純粹的 Socket/HTTP 封包轉發。
4. **⏱️ 排程發射器 (Cron Schedulers)**：定時觸發 Cycle 的機械發條。

> **瑞亞治軍天條**：  
> 絕對禁止將第三層工蜂偽裝或自我膨脹為神祇或人格。工蜂必須靜默運作於底層，只產出無殘留的 Execution Receipt，嚴禁佔用角色名冊與 Attention Queue。
