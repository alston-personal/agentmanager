#!/usr/bin/env bash
# ============================================================
# AgentOS One-Click Bootstrapper & Installer
# Supports Node Runtime mode and Developer Source Clone mode.
# Compatible with Linux and Windows WSL.
# ============================================================
set -euo pipefail
export PYTHONUTF8=1

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

echo "🛰️  [AgentOS Installer] Initializing Setup (v0.2.0)..."

# Detect Mode: Default is Node Runtime Mode; pass --developer for full source clone mode
INSTALL_MODE="NODE"
if [[ "${1:-}" == "--developer" || "${1:-}" == "--dev" ]]; then
    INSTALL_MODE="DEVELOPER"
fi

echo "📌 Installation Mode: $INSTALL_MODE"

# 1. Ensure Python Virtual Environment
if [ ! -d "venv" ] && [ ! -d ".venv" ]; then
    echo "📦 Creating python virtual environment (venv)..."
    python3 -m venv venv || python3 -m venv .venv || echo "⚠️ Could not create venv. Using system Python."
fi

# Resolve venv python path
PYTHON_BIN="./venv/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="./venv/Scripts/python"
fi
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="./.venv/bin/python3"
fi
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="./.venv/Scripts/python"
fi
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="$(command -v python3 || command -v python)"
fi

# 2. Install dependencies & agentos-runtime package
echo "📦 Installing AgentOS Runtime Package & Dependencies..."
$PYTHON_BIN -m pip install --upgrade pip || true
$PYTHON_BIN -m pip install -e . || $PYTHON_BIN -m pip install --user -e . || pip install -r requirements.txt

# 3. Handle .env file creation
if [ ! -f ".env" ]; then
    echo "📄 .env not found. Creating from .env.example..."
    cp .env.example .env
    echo "💡 Sourced default .env settings."
fi

# 4. Bootstrap Data Layer (if data layer exists or symlinked)
if [ -d "$HOME/agent-data" ] || [ -f "scripts/bootstrap.py" ]; then
    echo "🔗 Initializing Data Layer Bridges..."
    $PYTHON_BIN scripts/bootstrap.py || true
fi

# 5. Run agentos-node status check
echo "🩺 Running agentos-node status check..."
$PYTHON_BIN -m agentos_node.cli status || true

echo "============================================================"
echo "🎉 [AgentOS Installer] Runtime Node Setup Completed!"
echo "🚀 Run 'agentos-node status' or 'python3 scripts/harvest_ecosystem.py' to check status."
echo "============================================================"
