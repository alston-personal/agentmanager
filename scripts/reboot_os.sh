#!/bin/bash
# 🛰️ AgentOS Global Reboot Protocol (v0.6.1-Portable)
# This script detects its own location to avoid hardcoded path errors.

# Auto-detect Base Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGIC_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DATA_ROOT="$(cd "$LOGIC_ROOT/../agent-data" 2>/dev/null && pwd || echo "$HOME/agent-data")"

echo "🌅 [Resurrection] Initializing AgentOS..."
echo "📍 Logic Root: $LOGIC_ROOT"
echo "📍 Data Root:  $DATA_ROOT"

# Restarting Systemd Services (Scoped to User)
echo "⚡ Restarting OS Core Services..."
systemctl --user daemon-reload
systemctl --user restart tg-commander.service
systemctl --user restart os-pulse.service

# Final Health Check
echo "🔍 Performing Quick Audit..."
$LOGIC_ROOT/scripts/recall_chronicle.py

echo "✅ AgentOS is back ONLINE."
