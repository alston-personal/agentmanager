#!/usr/bin/env bash
# ============================================================
# AgentOS One-Click Bootstrapper & Installer
# Compatible with Linux and Windows WSL.
# ============================================================
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

echo "🛰️  [AgentOS Installer] Initializing One-Click Setup..."

# Detect WSL or native Windows (MSYS/Cygwin)
IS_WSL=false
if grep -qEi "(Microsoft|WSL)" /proc/version 2>/dev/null; then
    IS_WSL=true
fi

# 1. Ensure Python Virtual Environment
if [ ! -d "venv" ] && [ ! -d ".venv" ]; then
    echo "📦 Creating python virtual environment (venv)..."
    python3 -m venv venv || python3 -m venv .venv || echo "⚠️ Could not create venv. Using system Python."
fi

# Resolve venv python path
PYTHON_BIN="./venv/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="./.venv/bin/python3"
fi
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="$(command -v python3)"
fi

# 2. Install dependencies
echo "📦 Installing Python dependencies..."
$PYTHON_BIN -m pip install --upgrade pip || true
$PYTHON_BIN -m pip install -r requirements.txt || pip install -r requirements.txt

# 3. Handle .env file creation
if [ ! -f ".env" ]; then
    echo "📄 .env not found. Creating from .env.example..."
    cp .env.example .env
    echo "💡 Sourced default .env settings. Please update GITHUB_TOKEN and GEMINI_API_KEY in your .env later."
fi

# Load local environment
set -a
# shellcheck disable=SC1090
source .env
set +a
AGENT_DATA_ROOT="${AGENT_DATA_ROOT:-${AGENT_DATA_DIR:-$HOME/agent-data}}"

# 4. Bootstrap Data Layer
echo "🔗 Bootstrapping Data Layer and establishing symlinks..."
$PYTHON_BIN scripts/bootstrap.py

# 5. Propagate rules to workspaces
echo "🧠 Propagating Swarm directives and rules..."
$PYTHON_BIN scripts/propagate_possession_rules.py

# 6. Run reboot and services initialization
echo "⚡ Booting OS services and recalling memory..."
if [ "$IS_WSL" = true ]; then
    echo "🕶️ [WSL Mode] WSL detected. Re-linking and running in Client/Daemon Mode."
fi
bash scripts/reboot_os.sh

echo "============================================================"
echo "🎉 [AgentOS Installer] Setup completed successfully!"
echo "🚀 Run './bin/status' to check system health."
echo "============================================================"
