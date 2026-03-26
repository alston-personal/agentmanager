---
name: secret_manager
description: 整合 GitHub Organization Secrets，實現自動化的密鑰管理與同步。
---

# Secret Manager Skill

## 🎯 Purpose

Enable the AI Agent to securely handle secrets across different environments. This skill supports a **Dual-Mode** architecture to ensure flexibility and security.

1.  **🔒 Bitwarden Mode (Enterprise)**: Highly secure, zero-trace on local disk.
2.  **📄 Local Mode (Standard)**: Uses standard `.env` files for environments without Bitwarden.

---

## 🚀 Modes of Operation

### 1. **Bitwarden Mode (Preferred)**
Secrets are fetched on-the-fly from a self-hosted or cloud Bitwarden instance.
- **Backend**: `SECRET_BACKEND=bitwarden` in main `.env`.
- **Requirements**: `bw` CLI installed and `BW_SESSION` exported.
- **Workflow**:
  ```bash
  export BW_SESSION=$(bw unlock --raw)
  # Agent then uses BW to fetch and inject into temporary project environments.
  ```

### 2. **Local Mode (Fallback)**
Secrets are stored in a central, Git-ignored folder within the data layer.
- **Backend**: `SECRET_BACKEND=local` in main `.env`.
- **Storage**: `/home/ubuntu/agent-data/secrets/<project-name>.env`
- **Workflow**: Agent reads from the central data-layer and links/copies to the project's logic-layer.

---

## 📋 Core Workflows

### `/setup` (Initialization)
Determines the backend and initializes the necessary files.
- **Bitwarden**: Prompts for server URL and login.
- **Local**: Prompts for key-value pairs to store in the central data-layer.

### `/inject-secrets` (Deployment/Runtime)
Injects the necessary secrets into the current workspace.
1.  Check `SECRET_BACKEND`.
2.  If **Bitwarden**: Fetch item matching project name and generate `.env`.
3.  If **Local**: Copy/Link from `agent-data/secrets/` to workspace `.env`.

---

## 🔧 Automation Tools

| Tool | Description |
| :--- | :--- |
| `get_secret.py` | Unified script that abstracts the backend logic. |
| `env_to_bw.py` | Migration tool to move `.env` files to Bitwarden items. |

---

## ⚠️ Security Protocols

1.  **Zero-Leak Policy**: Never print plain-text secrets in terminal logs or conversation history.
2.  **Volatile Memory**: In Bitwarden mode, `.env` files should be temporary and wiped after use if possible (or at least strictly `.gitignore`d).
3.  **No Hardcoding**: Tokens must be loaded via shell variables or temporary files, never hardcoded in scripts.
