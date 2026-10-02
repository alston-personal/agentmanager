#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -ne 1001 ]]; then
  echo "persona_social_timer=WRONG_USER"
  exit 2
fi

CONFIG_ROOT="${HOME}/.config/agentos/personas"
SYSTEMD_ROOT="${HOME}/.config/systemd/user"

mkdir -p "${CONFIG_ROOT}" "${SYSTEMD_ROOT}"

cat > "${SYSTEMD_ROOT}/agentos-persona-social@.service" <<'EOF'
[Unit]
Description=AgentOS Persona Social PDCA (%i)
After=network-online.target agentos-social-runtime.service
Wants=network-online.target

[Service]
Type=oneshot
EnvironmentFile=%h/.config/agentos/personas/%i.env
WorkingDirectory=%h
ExecStart=/usr/bin/python3 ${AGENTOS_PERSONA_SOCIAL_LOOP_SCRIPT}
ExecStartPost=/usr/bin/python3 ${AGENTOS_PERSONA_PDCA_SYNC_SCRIPT}
TimeoutStartSec=240
NoNewPrivileges=true
PrivateTmp=true
EOF

cat > "${SYSTEMD_ROOT}/agentos-persona-social@.timer" <<'EOF'
[Unit]
Description=Wake AgentOS Persona Social PDCA (%i)

[Timer]
OnBootSec=3m
OnUnitActiveSec=20m
RandomizedDelaySec=5m
Persistent=true
Unit=agentos-persona-social@%i.service

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
echo "persona_social_timer=INSTALLED"
echo "persona_social_timer_template=agentos-persona-social@.timer"
echo "persona_social_config_root=${CONFIG_ROOT}"
