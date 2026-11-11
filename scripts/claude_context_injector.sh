#!/usr/bin/env bash
# ============================================================
# AgentOS Context Injector Hook (Single-Shot + Budget Guard)
# Triggered by: Claude Code UserPromptSubmit hook
# Purpose:
#   1. Inject pulse state + project STATUS.md ONCE per session
#      (or once after /compact shrinks the transcript).
#   2. Stay silent (0 extra tokens) on normal subsequent turns.
#   3. Emit a 2-line notice when transcript size crosses 300KB.
#      Transcript bytes are not measured model tokens or billing usage.
# ============================================================

HOOK_INPUT=""
if [ ! -t 0 ]; then
    HOOK_INPUT="$(cat 2>/dev/null || true)"
fi

SESSION_ID=""
TRANSCRIPT_PATH=""
HOOK_CWD=""
if [ -n "$HOOK_INPUT" ] && command -v python3 >/dev/null 2>&1; then
    eval "$(HOOK_INPUT="$HOOK_INPUT" python3 - <<'PY'
import json, os, shlex
raw = os.environ.get("HOOK_INPUT", "")
try:
    data = json.loads(raw) if raw.strip() else {}
except Exception:
    data = {}
if not isinstance(data, dict):
    data = {}
sid = str(data.get("session_id") or data.get("sessionId") or "").strip()
tpath = str(data.get("transcript_path") or data.get("transcriptPath") or "").strip()
cwd = str(data.get("cwd") or "").strip()
print(f"SESSION_ID={shlex.quote(sid)}")
print(f"TRANSCRIPT_PATH={shlex.quote(tpath)}")
print(f"HOOK_CWD={shlex.quote(cwd)}")
PY
)"
fi

if [ -z "$SESSION_ID" ] && [ -n "$TRANSCRIPT_PATH" ]; then
    SESSION_ID="$(basename "$TRANSCRIPT_PATH" .jsonl)"
fi

TRANSCRIPT_SIZE=0
if [ -n "$TRANSCRIPT_PATH" ] && [ -f "$TRANSCRIPT_PATH" ]; then
    TRANSCRIPT_SIZE=$(wc -c < "$TRANSCRIPT_PATH" 2>/dev/null | tr -d ' ' || echo 0)
fi

if [ -n "$SESSION_ID" ]; then
    SAFE_SID="$(printf '%s' "$SESSION_ID" | tr -cd 'a-zA-Z0-9._-')"
    STAMP_FILE="/tmp/agentos-claude-hydrated-${SAFE_SID}.stamp"
    if [ -f "$STAMP_FILE" ]; then
        PREV_SIZE=$(cat "$STAMP_FILE" 2>/dev/null | tr -d ' ' || echo 0)
        case "$PREV_SIZE" in ''|*[!0-9]*) PREV_SIZE=0 ;; esac
        # Re-hydrate only if transcript shrank by >50% after /compact
        if [ "$PREV_SIZE" -le 30000 ] || [ "$TRANSCRIPT_SIZE" -ge $((PREV_SIZE / 2)) ]; then
            printf '%s\n' "$TRANSCRIPT_SIZE" > "$STAMP_FILE" 2>/dev/null || true
            if [ "$TRANSCRIPT_SIZE" -ge 307200 ] && [ "$PREV_SIZE" -lt 307200 ]; then
                printf '%s\n' "⚠️ [AgentOS Context Budget Guard] Session transcript crossed 300KB; file size is not measured token usage."
                printf '%s\n' "Keep reads and outputs bounded; checkpoint progress before compacting if needed. Continue authorized work serially."
            fi
            exit 0
        fi
    fi
    printf '%s\n' "$TRANSCRIPT_SIZE" > "$STAMP_FILE" 2>/dev/null || true
fi

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-${HOOK_CWD:-$(pwd)}}"
PROJECT_NAME=$(basename "$PROJECT_DIR")

# --- Resolve Data Layer Path ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    [ -f "$HOME/.agentos.secrets" ] && source "$HOME/.agentos.secrets"
    set +a
fi
AGENT_DATA_ROOT="${AGENT_DATA_ROOT:-${AGENT_DATA_DIR:-$HOME/agent-data}}"

# --- Read Pulse State ---
PULSE_FILE="${AGENT_PULSE_FILE:-}"
if [ -z "$PULSE_FILE" ] && command -v python3 >/dev/null 2>&1; then
    PULSE_FILE="$(python3 - <<'PY'
from pathlib import Path
import os, sys
project_root = Path(os.environ.get("AGENT_PROJECT_ROOT", Path.cwd())).resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
from agent_core.platform import get_platform_driver
driver = get_platform_driver(project_root=project_root, data_root=Path(os.environ.get("AGENT_DATA_ROOT", os.path.expanduser("~/agent-data"))))
print(driver.volatile_state_dir() / "pulse.json")
PY
)"
fi
PULSE_FALLBACK="$AGENT_DATA_ROOT/runtime/pulse_snapshot.json"

if [ -f "$PULSE_FILE" ]; then
    PULSE=$(cat "$PULSE_FILE" 2>/dev/null)
elif [ -f "$PULSE_FALLBACK" ]; then
    PULSE=$(cat "$PULSE_FALLBACK" 2>/dev/null)
else
    PULSE='{"status": "unavailable"}'
fi

# --- Read Project STATUS.md ---
STATUS_FILE="$PROJECT_DIR/STATUS.md"
STATUS_DATA_FILE="$AGENT_DATA_ROOT/projects/$PROJECT_NAME/STATUS.md"

if [ -f "$STATUS_FILE" ]; then
    STATUS=$(head -60 "$STATUS_FILE" 2>/dev/null)
elif [ -f "$STATUS_DATA_FILE" ]; then
    STATUS=$(head -60 "$STATUS_DATA_FILE" 2>/dev/null)
else
    STATUS="No STATUS.md found for project: $PROJECT_NAME"
fi

# --- Output Single-Shot Injection Block ---
printf '%s\n' "
---
## 🤖 AgentOS Single-Shot Session Hydration ($(date '+%Y-%m-%d %H:%M'))

**Current Project**: \`$PROJECT_NAME\`
**Project Dir**: \`$PROJECT_DIR\`
**Context Policy**: Hydrated once per session. Continue authorized work serially, keeping reads and outputs bounded. Tool-call count alone does not require delegation or ending the turn.

### 🌐 Swarm Pulse State
\`\`\`json
$PULSE
\`\`\`

### 📊 Project Status (first 60 lines)
\`\`\`markdown
$STATUS
\`\`\`

*This context was injected once at session start by AgentOS.*
---
"
