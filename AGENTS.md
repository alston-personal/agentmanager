# AgentOS — agentmanager Project Context

This repository is the **AgentOS logic/runtime root**. Mutable project state belongs in the configured data layer; runtime semantics, contracts, tests, governance, and automation live here.

## Required reading order

Before architecture or system-level changes:

1. `README.md` — current product goal and public architecture.
2. `docs/CURRENT_STATE.md` — canonical map of **Implemented / Verified / Research** capabilities.
3. `docs/AGENTOS_NODE.md` — responsibility/resource discovery contract for cross-project work.
4. `.agent/CONSTITUTION.yaml` and relevant governance/role sources when authority or policy is involved.

Do not rely on older memory/pulse-era documents as current architecture if they disagree with `docs/CURRENT_STATE.md` and executable evidence.

## Current architectural role

AgentOS currently contains, among other components:

- continuation-state reconciliation;
- persistent control-plane coordination;
- session lifecycle / handoff persistence;
- governance and capability responsibility resolution;
- resource/world-state registry;
- Realm cross-node execution surfaces;
- platform runtime drivers;
- operational evidence and drift guards.

The model-independent **Cognitive IR / zero-cost arbitrary model switching** layer is still research unless and until a repeatable benchmark proves it.

## Critical constraints

- Preserve Logic/Data separation: mutable user/project state must not be accidentally committed into the logic repository.
- Discover/resolve existing capability ownership before creating parallel infrastructure.
- Newer user intent must never be rolled back by stale snapshots, replay, or tool results.
- Evidence and tool results do not silently rewrite user intent.
- Claims in documentation must be backed by implementation paths; verified claims also need tests/evidence.
- **Capability does not imply authority.** A tool being available or a PR being mergeable does not authorize a protected-branch mutation.
- **Production runtime truth is node-authoritative.** For runtime parity/health claims, consume the runtime node's `agentos.execution-receipt/v1`. A ChatGPT/container sandbox DNS or HTTP probe must never override or substitute for Oracle/runtime-node evidence. DNS failure, local-service failure, source mismatch, and public HTTP failure must remain distinguishable in the receipt.

## Protected Branch Authority Rule

For `main`, `master`, and `release/*`:

1. agents may create branches, commits, tests, reviews, and pull requests;
2. agents may report a PR as `READY_FOR_MERGE`;
3. agents MUST then stop at `AWAITING_HUMAN_APPROVAL`;
4. CI success, mergeability, positive review, or a generic `continue` instruction are not merge authorization;
5. do not merge or directly push to a protected branch without a separate explicit human authorization event;
6. development repository writes must name an explicit non-protected branch; never rely on an API's omitted/default branch argument;
7. Core deployment authority, live acceptance, or evidence generation never grants repository publication authority;
8. GitHub provider-side protection for `main` is mandatory. AgentOS policy/CI without a provider ref fence is incomplete enforcement.

Evaluate the executable policy with:

```bash
python3 scripts/protected_branch_authority.py \
  --branch main \
  --actor-kind agent \
  --via-pull-request
```

The expected result without explicit human approval is `AWAITING_HUMAN_APPROVAL` and a non-zero exit status.

Provider-side acceptance is tracked separately and must prove that GitHub rejects a direct `main` push before mutation. See [`docs/governance/decisions/GOV-2026-08-27-001-protected-branch-authority.md`](file:///home/ubuntu/agentmanager/docs/governance/decisions/GOV-2026-08-27-001-protected-branch-authority.md).

## Documentation Reality Rule (Atomic Doc-Code Parity)

Architecture-sensitive implementation changes and code modifications MUST update at least one authoritative entry-point document in the same change set:

- `README.md`
- `docs/CURRENT_STATE.md`
- `ONBOARDING.md`
- `AGENTS.md`

### Three Lines of Defense:
1. **First Line (Active Development & PDCA Lifecycle)**: "動 Code 必動 Doc，兩者為不可分割的原子操作"。Paw 的實作完成標準 (Definition of Done) 必須包含文檔同步；Claw 在 Check 階段主動執行工作區同步審計 (`python3 scripts/documentation_reality_guard.py --worktree`)，若代碼變更而文檔未動，直接裁定 `FAIL` 打回重做。
2. **Second Line (Pre-Commit Physical Hook)**: Git pre-commit hook 強制執行 `python3 scripts/documentation_reality_guard.py --staged`。任何未帶權威文檔更新的代碼暫存變更在提交時立即被物理攔截。
3. **Third Line (CI & Protected Branch Authority)**: GitHub Actions CI 執行 `python3 scripts/documentation_reality_guard.py --base origin/main`，拒絕任何文檔滯後的分支合併入 `main`。

Run:

```bash
python3 scripts/documentation_reality_guard.py --worktree
python3 scripts/documentation_reality_guard.py --staged
```

Treat a documentation-drift failure as an architecture regression, not optional cleanup.

## Two-Track Mind-Body Dual Parity Rule (身心合一雙軌律)

為了兼顧「憲法體制不可妥協之嚴肅性」與「產品創新探索必然之研發週期」，AgentOS 嚴格區分治理層與專案層之身心合一標準：

1. **軌道一：核心治理與體制層（Constitutional & Governance Track）**
   - **範圍**：`.agent/CONSTITUTION.yaml`、`AGENTS.md`、`.agent/roles/`、Agent Rules。
   - **標準**：**永恆零時差身心合一 (Strict Zero-Lag Immediate Parity)**。
   - **鐵律**：條文與代碼必須雙向同步。凡在憲法中宣示之守則，代碼層必須有物理守衛攔截（Guard/Hook/Fail-closed check），嚴禁空洞宣誓；動 code 必動 doc，文檔修改若無實裝代碼支撐亦屬違憲。由 `ConstitutionKeeperWorker` 與 `drift_guard.py` 實時裁決。

2. **軌道二：產品與專案研發層（Product & Feature Engineering Track）**
   - **範圍**：專案開發、新功能發想、PRD 架構、`agent-data/specs/*.md`、`docs/CURRENT_STATE.md`。
   - **標準**：**生命週期受控演進 (Lifecycle Controlled Evolution)**。
   - **允許發想先行**：允許專案存在研發孕育期（發想、架構設計、任務拆解早於代碼完工），但必須誠實受控：
     - 明確標示狀態：`proposed`（已發想/待立案）或 `in-progress`（實作中）；
     - 必須聲明 `owner`、`target_projects` 與清晰的待辦清單（`[ ]`）。
   - **絕對紅線 (Zero False Completion)**：
     - **嚴禁未落實卻標示完工**：凡標記為 `closed`、`implemented`、`verified` 之規格，必須完成項清零（0 open items）並具備實體代碼/驗證憑據。
     - 若宣稱完成但有未勾選項目或缺乏憑證，`scripts/spec_steward.py --check` 直接裁定 `FALSE_COMPLETION` 並阻斷。
     - 嚴禁無人維護之陳舊遊魂（超過 60 天無人推進之 proposed 規格強制標記警告）。

## Public Web Surface Machine-Readability Rule

Web surfaces created or materially changed by AgentOS MUST be classified before implementation as one of:

1. **public-discoverable** — intended to be found, shared, indexed, summarized, or understood by humans, search engines, link previewers, or AI agents;
2. **public-noindex** — publicly reachable but intentionally excluded from discovery/indexing;
3. **private/authenticated** — user-specific, administrative, sensitive, or access-controlled.

The reusable implementation owner is **`capability://web.static-index.render`**. Public web generators MUST resolve and invoke that capability; they MUST NOT independently embed another project-specific crawler/AI static-index implementation into application code.

For **public-discoverable** routes:

- Produce an `agentos.web-static-index/v1` input from the page/result's already-authorized public data and invoke `capability://web.static-index.render`.
- Serve the generated semantic HTML as the initial representation of the public route, or as a deterministic public summary/share route included in the product's discovery strategy. Client JavaScript may enhance the page but must not be the only source of its purpose or primary result.
- The static representation must contain a descriptive `<title>`, one meaningful `<h1>`, a concise textual summary, canonical URL, share metadata, correct robots intent, stable URLs, and correct HTTP status codes.
- Product code supplies page-specific data; the shared capability owns escaping, base semantic markup, crawler-facing metadata, and its render receipt. Do not fork/copy its template merely to customize a product.
- Structured data may be supplied only when it accurately represents the public page. Keep `robots.txt`, sitemap, canonical/noindex behavior, and route intent consistent.
- Do not expose private inputs, hidden state, account data, secrets, or internal diagnostics merely to improve discoverability.

For **public-noindex** routes, the same capability may be invoked with an explicit `noindex` robots policy when a machine-readable/shareable representation is useful. For **private/authenticated** routes, access control wins: do not create a public index artifact from private data.

**AI-friendly does not mean blanket training permission.** Content machine-readability and crawler authorization are separate controls. Search, archival, and AI-training crawlers may be allowed or denied independently through deployment policy. Optional conventions such as `llms.txt` may be added as hints, but they do not replace the static-index capability, semantic HTML, access control, or robots directives.

Acceptance for a public-discoverable route requires both the `agentos.web-static-index-receipt/v1` render receipt and a no-JavaScript fetch/inspection proving that a crawler can recover the route's title, primary heading, concise summary, canonical URL, and intended indexability.

## Public Web Surface Machine-Readability Rule

Web surfaces created or materially changed by AgentOS MUST be classified before implementation as one of:

1. **public-discoverable** — intended to be found, shared, indexed, summarized, or understood by humans, search engines, link previewers, or AI agents;
2. **public-noindex** — publicly reachable but intentionally excluded from discovery/indexing;
3. **private/authenticated** — user-specific, administrative, sensitive, or access-controlled.

The reusable implementation owner is **`capability://web.static-index.render`**. Public web generators MUST resolve and invoke that capability; they MUST NOT independently embed another project-specific crawler/AI static-index implementation into application code.

For **public-discoverable** routes:

- Produce an `agentos.web-static-index/v1` input from the page/result's already-authorized public data and invoke `capability://web.static-index.render`.
- Serve the generated semantic HTML as the initial representation of the public route, or as a deterministic public summary/share route included in the product's discovery strategy. Client JavaScript may enhance the page but must not be the only source of its purpose or primary result.
- The static representation must contain a descriptive `<title>`, one meaningful `<h1>`, a concise textual summary, canonical URL, share metadata, correct robots intent, stable URLs, and correct HTTP status codes.
- Product code supplies page-specific data; the shared capability owns escaping, base semantic markup, crawler-facing metadata, and its render receipt. Do not fork/copy its template merely to customize a product.
- Structured data may be supplied only when it accurately represents the public page. Keep `robots.txt`, sitemap, canonical/noindex behavior, and route intent consistent.
- Do not expose private inputs, hidden state, account data, secrets, or internal diagnostics merely to improve discoverability.

For **public-noindex** routes, the same capability may be invoked with an explicit `noindex` robots policy when a machine-readable/shareable representation is useful. For **private/authenticated** routes, access control wins: do not create a public index artifact from private data.

**AI-friendly does not mean blanket training permission.** Content machine-readability and crawler authorization are separate controls. Search, archival, and AI-training crawlers may be allowed or denied independently through deployment policy. Optional conventions such as `llms.txt` may be added as hints, but they do not replace the static-index capability, semantic HTML, access control, or robots directives.

Acceptance for a public-discoverable route requires both the `agentos.web-static-index-receipt/v1` render receipt and a no-JavaScript fetch/inspection proving that a crawler can recover the route's title, primary heading, concise summary, canonical URL, and intended indexability.

## Useful verification

```bash
python3 scripts/continuation_state.py --self-test
python3 -m unittest tests.test_continuation_state tests.test_control_plane -v
python3 -m unittest tests.test_protected_branch_authority -v
python3 -m unittest tests.test_production_parity_receipt -v
python3 -m unittest tests.test_role_reality tests.test_role_runtime -v
python3 scripts/documentation_reality_guard.py --worktree
python3 scripts/documentation_reality_guard.py --staged
```

## Git reporting

After pushing changes, report the remote/branch and latest commit hash.


## Growth Proof ownership

AgentOS has a fixed **Growth Auditor** responsibility. Executors perform work; the Closure Owner / Atlast keeps goals moving through execution -> acceptance -> close -> next work; the Growth Auditor independently evaluates whether accumulated validated experience caused later execution to improve.

Architecture-sensitive runtimes that reuse prior experience SHOULD emit Growth Auditor observations after acceptance. Mutable proof evidence belongs in `$AGENT_DATA_ROOT/growth-proof/ledger.json`; do not commit live evidence into this repository.

The Growth Auditor must classify conservatively:

- persistence/source experience alone is not self-growth;
- independent later reuse may qualify as G2;
- causal/measured before-vs-after uplift is required for G3;
- cross-boundary measured transfer may qualify as G4;
- G5 is longitudinal and must not be inferred from one event.

See `docs/GROWTH_AUDITOR.md` for the runtime contract.
