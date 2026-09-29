# Oracle TypeSafe Skill

AgentOS installs the TypeSafe skill on Oracle through the existing bounded executor-job transport.

## Fixed contract

```text
ChatGPT / rollout
  -> ONE controller
  -> oracle-core-node
  -> agentos.executor.job
  -> typesafe.skill.install
  -> ubuntu Action Relay
  -> fixed TypeSafe installer
```

The job request contains only the registered semantic identity:

- job type: `typesafe.skill.install`
- project: `agentos-core`
- executor class: `oracle-antigravity-skill-installer`
- workload ref: `skill://typesafe-ai`
- authority: `oracle-user-skill-install`

Generic command, argv, executable, cwd, path, environment, token, credential, secret, and password fields are rejected by the executor-job contract.

The installer uses one installation method only:

```bash
npx --yes skills add typesafe-ai/skills --skill typesafe-ai --agent antigravity --global --copy --yes
```

Expected file-level result:

```text
/home/ubuntu/.gemini/antigravity/skills/typesafe-ai/SKILL.md
/home/ubuntu/agent-data/runtime/skills/typesafe-ai/install-receipt.json
```

The receipt records a SHA-256 and `file_verified=true`. `fresh_session_loaded` and `agy_loaded` remain unknown until independently observed.

## Acceptance boundary

A successful rollout proves only:

1. ONE accepted the fixed semantic job.
2. Oracle routed it through the ubuntu Action Relay.
3. The fixed installer completed.
4. The expected TypeSafe skill file and sanitized install receipt were verified.

It does not prove API credentials, TypeSafe service access, fresh Antigravity IDE loading, or availability to `agy`, Codex, or Claude.

