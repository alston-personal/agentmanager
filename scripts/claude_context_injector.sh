#!/usr/bin/env bash
# ============================================================
# AgentOS Context Injector Hook
# Triggered by: Claude Code UserPromptSubmit hook
# Purpose: Force-inject pulse state + project STATUS into context
#          so ANY model (local or cloud) gets instant awareness.
# ============================================================

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
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
if [ -z "$PULSE_FILE" ]; then
    PYTHON_BIN="python3"
    if [ -x "$PROJECT_ROOT/venv/bin/python3" ]; then
        PYTHON_BIN="$PROJECT_ROOT/venv/bin/python3"
    fi
    if command -v "$PYTHON_BIN" >/dev/null 2>&1; then
        PULSE_FILE="$("$PYTHON_BIN" - <<'PY'
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
