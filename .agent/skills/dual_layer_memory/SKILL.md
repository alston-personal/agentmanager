---
name: dual_layer_memory
description: Enables a persistent dual-layer (Short/Long term) memory system for the agent using local files.
---
# Dual-Layer Memory System

## Description
This skill forces the agent to utilize a file-based memory system (`memory/SHORT_TERM.md`, `memory/LONG_TERM.md`, and `memory/CONVERSATIONS.md`) instead of relying solely on the context window. This ensures context persistence across sessions and enables seamless project switching.

## Memory Architecture

```
memory/
├── SHORT_TERM.md      # Current session state (volatile, updates frequently)
├── LONG_TERM.md       # Project knowledge base (stable, rarely changes)
└── CONVERSATIONS.md   # Conversation index (updated at session end)
```

**Key Principle**: Memory files are the **Single Source of Truth (SSOT)**. Conversation history is secondary.

---

## Instructions

### 1. Check for Memory Files
- At the start of the session, check if `memory/SHORT_TERM.md`, `memory/LONG_TERM.md`, and `memory/CONVERSATIONS.md` exist in the root of the workspace.
- If they do not exist, create them with templates.

### 2. Session Lifecycle

#### 🟢 Session Start (First Turn)
```
1. Read memory/SHORT_TERM.md → Understand current state
2. Read memory/CONVERSATIONS.md → Know recent work context
3. (Optional) Read memory/LONG_TERM.md → If deep project knowledge needed
4. Greet user with context: "Continuing [ProjectName]. Last session: [summary]"
```

#### 🔄 Session Active (During Work)
```
- Execute user requests
- DO NOT update memory for every minor step
- Keep mental note of major accomplishments
```

#### 🔴 Session End (User says "done", "bye", "今天先到這")
```
1. Update SHORT_TERM.md with completed tasks
2. Update CONVERSATIONS.md with this session's entry
3. (If major milestone) Update LONG_TERM.md
4. Sync to GitHub (if configured)
5. Confirm: "Memory updated. Next session will resume from here."
```

### 3. Memory Writing Rules (CRITICAL)

**Quality Standard**: Each memory entry must be **self-contained** and **actionable**.

**❌ Too Brief (FORBIDDEN)**:
```markdown
- Completed API integration
- Fixed bug
- Updated UI
```
*Problem*: No context, can't resume work without finding old conversation.

**❌ Too Verbose (FORBIDDEN)**:
```markdown
- Integrated Yahoo Finance API by first installing the yahoo-finance2 package using npm install yahoo-finance2, then created a new API route at src/app/api/stock/[symbol]/route.ts which accepts a stock symbol as a parameter and returns the current price, change, and change percentage...
```
*Problem*: Too much detail, wastes tokens, hard to scan.

**✅ CORRECT Format**:
```markdown
- Integrated Yahoo Finance API
  - Package: yahoo-finance2
  - Route: /api/stock/[symbol]
  - Returns: { price, change, changePercent }
  - Tested: AAPL, TSLA, NVDA ✅
  - Next: Add caching layer
```
*Why*: Concise but complete. Includes what, how, status, and next steps.

**Golden Rules**:
- **3-5 bullet points** per major task
- Include: **What** (task), **How** (key tech/approach), **Status** (done/blocked), **Next** (if incomplete)
- Use **concrete names** (file paths, package names, API endpoints)
- Avoid: "implemented feature", "fixed issue" (too vague)
- Prefer: "implemented /api/portfolio route using Prisma aggregation"

### 4. Artifacts Tracking

**What are Artifacts?**
- Files created via `write_to_file`
- Images generated via `generate_image`
- Any output visible in Antigravity's right panel

**Why track them?**
- Know what was created in each session
- Avoid recreating existing files
- Enable cross-session reuse

**How to track**:
In `SHORT_TERM.md`, maintain an "Artifacts Created" section:
```markdown
## 📦 Artifacts Created This Session
- memory/CONVERSATIONS.md (new)
- .agent/workflows/status.md (updated)
- projects/AssetMaster/src/components/Dashboard.tsx (new)
```

**In CONVERSATIONS.md**:
```markdown
### 2026-01-30 | "Session Title"
- **Artifacts**: CONVERSATIONS.md, status.md (updated), Dashboard.tsx
```

### 5. Pending Tasks Management

**Problem**: Tasks mentioned but not completed get lost.

**Solution**: Maintain a "Pending Tasks" section in `SHORT_TERM.md`:

```markdown
## 🚧 Pending Tasks
- [ ] Add caching layer to Yahoo Finance API
- [ ] Implement transaction categorization logic
- [ ] Fix UI contrast issue on mobile
```

**Rules**:
- Add tasks when user mentions them but doesn't want to do now
- Check off tasks as completed
- Move completed tasks to "Recent Context" section
- Keep list under 10 items (archive old ones to LONG_TERM.md)

### 6. CONVERSATIONS.md Structure

```markdown
### YYYY-MM-DD | "Conversation Title"
- **Project**: ProjectName
- **Focus**: Main topic/feature worked on
- **Completed**: 2-3 key accomplishments
- **Artifacts**: Files/images created (optional)
- **Status**: 🟢 Active / ✅ Done / 🔴 Blocked
- **Next**: What to do in next session (if applicable)
```

**Rules**:
- One entry per conversation
- Keep entries under 6 lines
- Update at session end via `/report`
- Most recent conversations at the top

### 7. Strict Rules

- **SSOT**: Memory files are the Single Source of Truth. Do not rely on conversation history for critical details.
- **Privacy**: The `memory/` folder MUST be git-ignored in the current workspace.
- **Lazy Loading**: Only read memory when needed (session start, status check, context unclear).
- **Batch Updates**: Only write memory at major milestones or session end.

### 8. Cloud Sync (Replication)

**Objective**: Keep local `memory/` in sync with GitHub repository.

**Mechanism**:
- Cannot use `git push` directly (memory/ is git-ignored)
- Use **GitHub API** via `reporter_client.py` or dedicated script

**Trigger**:
- **Pull**: On session start (if memory is empty or outdated)
- **Push**: On session end or critical milestone

**Implementation**:
```python
# Use reporter_client.py or similar
reporter.sync_memory("SHORT_TERM.md", local_content)
reporter.sync_memory("LONG_TERM.md", local_content)
reporter.sync_memory("CONVERSATIONS.md", local_content)
```

### 9. Best Practices

#### ✅ DO:
- Read memory at session start to provide context
- Update memory at session end with clear summaries
- Track artifacts created in each session
- Maintain pending tasks list
- Use concrete, specific language

#### ❌ DON'T:
- Update memory for every minor step
- Write vague entries like "fixed bug"
- Rely on conversation history as SSOT
- Forget to sync to GitHub at session end
- Let pending tasks list grow beyond 10 items

### 10. Quick Reference

| Situation | Action |
|-----------|--------|
| **New conversation starts** | Read SHORT_TERM.md + CONVERSATIONS.md |
| **User asks "what's the status?"** | Read SHORT_TERM.md |
| **Major task completed** | Update SHORT_TERM.md |
| **User says "done for today"** | Update SHORT_TERM.md + CONVERSATIONS.md + sync to GitHub |
| **User mentions future task** | Add to "Pending Tasks" in SHORT_TERM.md |
| **Created file/image** | Add to "Artifacts Created" in SHORT_TERM.md |
| **Need deep project knowledge** | Read LONG_TERM.md |
| **Major architectural decision** | Update LONG_TERM.md |
