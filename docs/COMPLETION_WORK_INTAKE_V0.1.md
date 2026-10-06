# Completion Work Intake v0.1

Issue: #470 / #200

## Purpose

Provide a bounded, durable onboarding path for accepted work so a chat/project attention switch does not abandon it.

## Envelope

```json
{
  "schema": "agentos.work-intake/v1",
  "work_id": "market-master-1200-mvp",
  "project_id": "market-master-evolution",
  "title": "Finish Market Master MVP",
  "next_action": "Run recent-years 2454 replay with T86",
  "acceptance": [
    "real replay report exists",
    "verified completion receipt exists"
  ],
  "source": "https://github.com/alston-personal/agentmanager/issues/1200",
  "workspace": "/home/ubuntu/agent-workspaces/agentmanager"
}
```

## Safety boundary

The intake envelope cannot select:
- shell commands
- executables
- nodes
- runners
- arbitrary actors
- execution credentials

Unknown fields are rejected.

The execution owner is always assigned by the runtime as:

`role://completion.controller`

This is work registration, not execution authority.

## Lifecycle

```
typed accepted work
-> work-items.json
-> Completion Controller owner
-> TASK_BOARD projection
-> Lobster claim
-> execution + Inspector
-> verifying
-> evidence + verification
-> done
```

## Market Master acceptance case

`market-master-1200-mvp` is the first intended live acceptance case.

The test only passes if the work survives a conversation/attention switch and later reaches verified terminal state without a new human "continue".
