# AI Command Center Dashboard Template

This file is a logic-layer template only.

Real dashboard data should come from the data repo:

- `${AGENT_DATA_ROOT}/DASHBOARD.md`
- default local path: `/home/ubuntu/agent-data/DASHBOARD.md`

## What Belongs Here

- dashboard format guidance
- documentation for expected sections
- setup notes for new machines

## What Does Not Belong Here

- personal project lists
- personal service inventory
- live project status
- user-specific notes or scratchpad state

## Expected Data-Layer Sections

- `## Active Projects & Resources`
- `## 系統服務`
- `## 專案孵化器`
- `## Scratchpad`

## Setup

1. Clone `agentmanager`
2. Clone your own data repo
3. Set `AGENT_DATA_ROOT`
4. Run `bash scripts/init-agent-data-links.sh` if you want local convenience symlinks

The runtime now reads dashboard and status data from `AGENT_DATA_ROOT`.
