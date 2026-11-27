#!/bin/bash
# AgentOS Universal Node One-Click Join (macOS & Linux)
set -euo pipefail

echo "============================================================"
echo "  🚀 AgentOS Universal Node One-Click Join (Unix/macOS)"
echo "============================================================"
echo ""
echo "[1/3] Connecting to Central ONE Realm (studio.milkcat.org)..."
echo "[2/3] Launching automated bootstrap and handshake..."
echo ""

curl -sSL https://studio.milkcat.org/join | bash

echo ""
echo "============================================================"
echo "  ✅ [SUCCESS] Node successfully enrolled and connected!"
echo "  Thin Client daemon is now active."
echo "============================================================"
