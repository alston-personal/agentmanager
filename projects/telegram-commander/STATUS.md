# 🤖 Telegram Commander (Remote Control Interface)

## 📌 Project Overview
The **Telegram Commander** serves as the remote brain and interface for the AI Command Center. It allows the user to monitor projects, trigger workflows, and execute system commands directly from a mobile device or any Telegram client without needing access to the physical computer.

## 🛠 Features
- **Visual Dashboard**: Real-time project status monitoring via `DASHBOARD.md`.
- **Workflow Executor**: One-click execution of `.agent/workflows`.
- **Skill Management**: Remote access to AI Center skills.
- **Secure Control**: Restricted access limited to the authorized owner.
- **System Monitoring**: Resource tracking (disk, CPU, uptime).

## 🚀 Active Commands
- `/start`: Open the visual command center.
- `shell [cmd]`: Execute authorized Linux commands.
- `status`: Quick summary of project health.

## 📈 Current Status
- [x] Base MCP integration.
- [x] Background service (Systemd-like) implementation.
- [x] Inline Keyboard GUI implementation.
- [ ] Multi-level nested menus (In Progress).
- [ ] Skill integration (Planned).

## 📅 Roadmap
- [ ] Integration with Gemini API for natural language command parsing.
- [ ] Automatic alerting for system failures.
- [ ] File upload/download capabilities via Telegram.
