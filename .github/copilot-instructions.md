# AgentOS Universal Contributor Instructions & Constitutional Invariants

All AI agents, executors (including Web GPT, GitHub PR agents, Copilot, Antigravity, Claude, and Codex), and human developers working across this repository are bound by the **AgentOS Constitution**. There are no exceptions for external, web, or remote contributors.

## Invariant 0: Two-Track Mind-Body Dual Parity (身心合一律 - 動 Code 必動 Doc)

"Any code mutation must atomically mutate documentation; code and documentation are inseparable."

1. **Mandatory Documentation Coupling**:
   - Every Pull Request or commit that introduces or modifies implementation code, scripts, tools, or GitHub Actions workflows (`agent_core/`, `scripts/`, `.github/workflows/`, `runtime_core/`, etc.) **MUST** update at least one authoritative documentation file in the very same commit/PR:
     - `docs/CURRENT_STATE.md`
     - `README.md`
     - `AGENTS.md`
     - `ONBOARDING.md`
     - Or the relevant module/project specification under `docs/` or `agent-data/specs/`.
   - **Zero-Tolerance for Bare Code PRs**: A PR that modifies code, scripts, or workflows without accompanying documentation updates is deemed unconstitutional and will be physically blocked by `scripts/documentation_reality_guard.py` in CI.

2. **Zero False Completion (嚴禁未落實卻標示完工)**:
   - Conversely, claiming a task/spec is `implemented`, `verified`, or `closed` without corresponding code, test receipts, and zero open items is forbidden.

## Read Current Reality First

Before submitting any architectural, workflow, or capability changes:

1. `README.md` — current product goal and public architecture.
2. `docs/CURRENT_STATE.md` — canonical map of **Implemented / Verified / Research** capabilities.
3. `AGENTS.md` — operational rules, protected branch boundaries, and reality guards.
4. `docs/AGENTOS_NODE.md` — responsibility and resource discovery contracts.

Do not rely on stale prompt lore, memory logs, or historical PR assumptions when they conflict with `docs/CURRENT_STATE.md`.

## Essential Invariants

- **Logic / Data Physical Separation**: Code, configurations, and tests belong here (Logic repo). Mutable runtime state, progress logs, and memories belong in `AGENT_DATA_ROOT` (`agent-data/`). Never commit runtime state into logic.
- **Protected Branch Authority**: `main` is protected. All contributions must arrive via Pull Request, pass all CI verification, and halt at `AWAITING_HUMAN_APPROVAL`. Direct pushes to `main` are strictly forbidden.
- **Verification Before Submission**:
  ```bash
  python3 scripts/documentation_reality_guard.py
  python3 scripts/continuation_state.py --self-test
  ```
