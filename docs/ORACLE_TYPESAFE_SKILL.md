# Oracle TypeSafe Skill installation and acceptance

**Status:** source-controlled installer candidate; NOT proof of an Oracle installation.
**Target:** Oracle `ubuntu` user, Antigravity execution surface.
**Source:** [typesafe-ai/skills](https://github.com/typesafe-ai/skills/blob/main/skills/typesafe-ai/SKILL.md).

The project uses the **skills CLI route only**, not Claude Code's plugin marketplace route.
From the authorized Oracle `ubuntu` user session, run:

```bash
bash scripts/install_oracle_typesafe_skill.sh
```

The installer executes one user-global installation:

```bash
npx --yes skills add typesafe-ai/skills --skill typesafe-ai --agent antigravity --global --yes
```

The expected skill file is `/home/ubuntu/.gemini/antigravity/skills/typesafe-ai/SKILL.md`. Check the installer output `TYPE_SAFE_SKILL=FILE_VERIFIED` and confirm `npx skills ls -g -a antigravity` lists `typesafe-ai`.

**Operational acceptance** requires a new Oracle Antigravity session to discover and read the installed Skill; a file existing does not prove that the separate `agy` relay CLI, Gemini extension, Codex extension, or Claude executor loaded it. Record the observed executor identity and a sanitized installation/skill-discovery receipt. Do not advertise Skill availability to unrelated executors without an independent check.

When working on TypeSafe-relevant project code, read the installed `SKILL.md` and follow its links to current [TypeSafe documentation](https://docs.typesafe.ai/llms.txt), including the relevant API/SDK and question guidance. The Skill is an instruction artifact, **not** a credential, a System One API subscription, a new AgentOS capability authorization, or a license to replace deterministic checks with model judgment.

Do not run this installer via an arbitrary-command GitHub Actions job or the ChatGPT Bootstrap Control Inbox. Oracle-side execution must use an already authorized node/local operator boundary, and must not change AgentOS core deployment generations or unrelated services.
