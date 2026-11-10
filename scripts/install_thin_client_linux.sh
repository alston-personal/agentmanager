#!/bin/bash
# AgentOS External Linux Node Universal Installer & Join Launcher
set -euo pipefail

REF="${1:-core/integration}"
ONE_URL="${AGENTOS_ONE_URL:-https://studio.milkcat.org/dashboard/api/agentos}"
NODE_ID="${AGENTOS_NODE_ID:-$(hostname)}"
ROOT="$HOME/.local/share/AgentOS"
VENV="$ROOT/venv"
STATE="$HOME/.agentos"
WORKSPACE="$HOME/AgentOS"
LAUNCHER="$ROOT/agentos-client"

echo "============================================================"
echo " 🚀 AgentOS Node Universal Join (Linux)"
echo " Node ID : $NODE_ID"
echo " ONE URL : $ONE_URL"
echo "============================================================"

command -v python3 >/dev/null || { echo "❌ python3 is required"; exit 2; }
command -v git >/dev/null || { echo "❌ git is required"; exit 2; }

mkdir -p "$ROOT" "$STATE" "$WORKSPACE"

if [ ! -d "$VENV" ]; then
  echo "📦 Creating Python virtual environment in $VENV..."
  python3 -m venv "$VENV"
fi

echo "⬇️ Installing AgentOS Thin Client..."
"$VENV/bin/python" -m pip install -q --upgrade pip
"$VENV/bin/python" -m pip install -q --upgrade "git+https://github.com/alston-personal/agentmanager.git@$REF"

cat > "$LAUNCHER" <<EOF
#!/bin/bash
export AGENTOS_CLIENT_HOME="$STATE"
exec "$VENV/bin/agentos-client" "\$@"
EOF
chmod 700 "$LAUNCHER"

# Ensure symlink in ~/.local/bin if available
mkdir -p "$HOME/.local/bin"
ln -sf "$LAUNCHER" "$HOME/.local/bin/agentos-client"

if [ ! -f "$STATE/policy.json" ]; then
  "$LAUNCHER" policy-init --root "$WORKSPACE"
fi

if [ ! -f "$STATE/client.json" ]; then
  echo ""
  echo "🔑 Enrolling as new node to $ONE_URL..."
  echo "Please approve this node on Oracle Core when User Code is displayed."
  echo ""
  exec "$LAUNCHER" join --one "$ONE_URL" --node-id "$NODE_ID" --timeout-seconds 900
fi

"$LAUNCHER" health
"$LAUNCHER" once
echo "============================================================"
echo "✅ agentos_linux_install=PASS"
echo "Node ID: $NODE_ID is online and joined to realm-alston!"
echo "============================================================"

