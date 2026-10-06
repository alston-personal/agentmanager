#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: run as ubuntu" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
PORT_MANAGER_REL="scripts/core_services/port_manager.py"
PORT_MANAGER="$REPO/$PORT_MANAGER_REL"
CONFIG=/home/ubuntu/.config/milkcat/dashboard.env.local
UNIT_DIR=/home/ubuntu/.config/systemd/user
NGINX_SITE=/etc/nginx/sites-enabled/studio.milkcat.org
NGINX_AVAIL=/etc/nginx/sites-available/studio.milkcat.org
STATE_DIR=/home/ubuntu/agent-data/runtime/dashboard-blue-green
SLOT_A_PORT=3040
SLOT_B_PORT=3041

test -f "$PORT_MANAGER"
test -f "$CONFIG"
mkdir -p "$UNIT_DIR" "$STATE_DIR"

python3 "$PORT_MANAGER" ensure "$SLOT_A_PORT" agentos-dashboard-blue --desc "AgentOS Dashboard blue slot"
python3 "$PORT_MANAGER" ensure "$SLOT_B_PORT" agentos-dashboard-green --desc "AgentOS Dashboard green slot"
echo "dashboard_blue_green_ports=PASS"

cat > "$UNIT_DIR/agentos-dashboard-blue.service" <<EOF
[Unit]
Description=AgentOS Dashboard Blue
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/ubuntu/agent-data/runtime/dashboard/blue
Environment=NODE_ENV=production
Environment=PORT=$SLOT_A_PORT
EnvironmentFile=-$CONFIG
ExecStart=/usr/bin/npm start
Restart=always
RestartSec=3
KillMode=control-group
TimeoutStopSec=20

[Install]
WantedBy=default.target
EOF

cat > "$UNIT_DIR/agentos-dashboard-green.service" <<EOF
[Unit]
Description=AgentOS Dashboard Green
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/ubuntu/agent-data/runtime/dashboard/green
Environment=NODE_ENV=production
Environment=PORT=$SLOT_B_PORT
EnvironmentFile=-$CONFIG
ExecStart=/usr/bin/npm start
Restart=always
RestartSec=3
KillMode=control-group
TimeoutStopSec=20

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
echo "dashboard_blue_green_units=PASS"

# Install a single nginx upstream block inside the existing TLS server.
# Keep the current port 3000 route serving until at least one slot is healthy.
if ! grep -q 'BEGIN AGENTOS DASHBOARD BLUE GREEN' "$NGINX_SITE"; then
  sudo -n cp "$NGINX_SITE" "$NGINX_SITE.pre-dashboard-blue-green"
  sudo -n python3 - "$NGINX_SITE" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text()
old="""    location /dashboard {
        proxy_pass http://localhost:3000;
"""
if old not in s:
    raise SystemExit("dashboard nginx location not found")
new="""    # BEGIN AGENTOS DASHBOARD BLUE GREEN
    set $agentos_dashboard_upstream http://127.0.0.1:3000;
    # END AGENTOS DASHBOARD BLUE GREEN

    location /dashboard {
        proxy_pass $agentos_dashboard_upstream;
"""
p.write_text(s.replace(old,new,1))
PY
fi
sudo -n nginx -t
sudo -n systemctl reload nginx
echo "dashboard_blue_green_nginx_foundation=PASS"

grep -q 'BEGIN AGENTOS DASHBOARD BLUE GREEN' "$NGINX_SITE"
echo "dashboard_blue_green_foundation=PASS"
