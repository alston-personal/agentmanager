# 🛡️ Service Registry

This file defines the services that the **Agent OS Watchdog** must monitor and maintain.

## 📋 Core Services (Mandatory)
These services are essential for the basic operation of the Agent OS.

- **Name**: `tg-commander.service`
  - **Type**: `systemd-user`
  - **Description**: Telegram Bot Bridge (Logic Layer Transport).
- **Name**: `moltbot-gateway.service`
  - **Type**: `systemd-user`
  - **Description**: Inter-Agent Communication Gateway.
- **Name**: `agent-maintenance.timer`
  - **Type**: `systemd-user`
  - **Description**: Periodic maintenance and healthcheck scheduler.

## 🧩 Plugin Services (Optional)
These services are only monitored if the corresponding environment variables are set in `.env`.

- **Name**: `n8n-automation`
  - **Type**: `http-check`
  - **URL**: `${N8N_URL}/healthz`
  - **Enabled-If**: `N8N_URL`
  - **Description**: Self-hosted automation platform.
