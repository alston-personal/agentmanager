# AgentOS Build & Development Guide

## Build and Setup Commands
- Install python dependencies: `pip install -r requirements.txt`
- Run setup: `python3 scripts/setup_env.py`
- Bootstrap: `python3 scripts/bootstrap.py`
- Install systemd user services: `bash scripts/install_systemd_user.sh`

## Verification and Run Commands
- Reboot/heal: `bash scripts/reboot_os.sh`
- System status: `python3 scripts/project_overview.py` or `bin/status`
- Run workflows: `python3 scripts/run_workflow.py <workflow>`
