#!/usr/bin/env bash
# ============================================================
# AgentOS Context Injector Hook
# Triggered by: Claude Code UserPromptSubmit hook
# Purpose: Force-inject pulse state + project STATUS into context
#          so ANY model (local or cloud) gets instant awareness.
# ============================================================

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
PROJECT_NAME=$(basename "$PROJECT_DIR")

# --- Read Pulse State ---
PULSE_FILE="/dev/shm/leopardcat-swarm/pulse.json"
PULSE_FALLBACK="/home/ubuntu/agent-data/runtime/pulse_snapshot.json"

if [ -f "$PULSE_FILE" ]; then
    PULSE=$(cat "$PULSE_FILE" 2>/dev/null)
elif [ -f "$PULSE_FALLBACK" ]; then
    PULSE=$(cat "$PULSE_FALLBACK" 2>/dev/null)
else
    PULSE='{"status": "unavailable"}'
fi

# --- Read Project STATUS.md ---
STATUS_FILE="$PROJECT_DIR/STATUS.md"
STATUS_DATA_FILE="/home/ubuntu/agent-data/projects/$PROJECT_NAME/STATUS.md"

if [ -f "$STATUS_FILE" ]; then
    STATUS=$(head -60 "$STATUS_FILE" 2>/dev/null)
elif [ -f "$STATUS_DATA_FILE" ]; then
    STATUS=$(head -60 "$STATUS_DATA_FILE" 2>/dev/null)
else
    STATUS="No STATUS.md found for project: $PROJECT_NAME"
fi

# --- Output Injection Block ---
# Claude Code reads stdout from UserPromptSubmit hooks and prepends it to context
printf '%s\n' "
---
## 🤖 AgentOS Auto-Context Injection ($(date '+%Y-%m-%d %H:%M'))

**Current Project**: \`$PROJECT_NAME\`
**Project Dir**: \`$PROJECT_DIR\`

### 🌐 Swarm Pulse State
\`\`\`json
$PULSE
\`\`\`

### 📊 Project Status (first 60 lines)
\`\`\`markdown
$STATUS
\`\`\`

*This context was automatically injected by AgentOS. You are now fully up to speed.*
---
"
