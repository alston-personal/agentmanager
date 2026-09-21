# Oracle TypeSafe Skill installation and acceptance

**Status:** source-controlled installer candidate; **not** proof of an Oracle installation.
**Target:** Oracle `ubuntu` user's built-in Antigravity **IDE** surface.
**Source:** [typesafe-ai/skills](https://github.com/typesafe-ai/skills/blob/main/skills/typesafe-ai/SKILL.md).

## Installation: exactly one route

This uses the TypeSafe-prescribed skills CLI route, not the Claude Code plugin marketplace.
The authorized Oracle-local `ubuntu` executor runs:

```bash
bash scripts/install_oracle_typesafe_skill.sh
```

The only skill-install command in the script is:

```bash
npx --yes skills add typesafe-ai/skills --skill typesafe-ai --agent antigravity --global --yes
```

This targets a global Antigravity skill under
`/home/ubuntu/.gemini/antigravity/skills/typesafe-ai/SKILL.md`.
It requires the existing AgentOS data root but does not change AgentOS Core,
restart services, modify Oracle credentials, or switch the working repository branch.

## Four independent acceptance stages

| Stage | Evidence | Status until observed |
| --- | --- | --- |
| Source ready | Reviewed PR, intended scope, and non-protected branch | Source candidate |
| File installed | Installer exits zero, verifies `SKILL.md`, and creates `$AGENT_DATA_ROOT/runtime/skills/typesafe-ai/install-receipt.json` with the exact skill SHA-256 | UNVERIFIED |
| Fresh session loads | New built-in **Antigravity IDE** session on Oracle explicitly finds and reads the Skill and identifies the executor; preserve sanitized evidence | UNVERIFIED |
| `agy` / Codex / Claude loads | **Separate** executor-specific skill discovery and read receipt for each executor claimed | UNVERIFIED |

A file-level receipt must not claim fresh-session or other-executor availability.
The receipt is runtime observation data and belongs to `agent-data`, not
the `agentmanager` logic repository. It contains no credentials or IR body.

The Antigravity IDE and the `agy` relay CLI are **not identical executors**.
Selecting `--agent antigravity` installs only for that named IDE target and
must never be reported as proof that the separate `agy` relay process loads
the same instructions. Do not install into a second target speculatively.
First identify the intended executor and its actual Skill discovery contract.

For file-level verification after the authorized Oracle-local installation:

```bash
npx skills ls -g -a antigravity
test -s /home/ubuntu/.gemini/antigravity/skills/typesafe-ai/SKILL.md
cat "${AGENT_DATA_ROOT:-/home/ubuntu/agent-data}/runtime/skills/typesafe-ai/install-receipt.json"
```

Then open a **new Oracle Antigravity IDE session**, ask it to identify and
read its TypeSafe skill by name, and confirm that it can describe the
`Choice`, `Noul`, and `Score` primitives from that file. Record the
observed executor and only sanitized evidence. An answer from a ChatGPT
conversation or generic recall is not evidence of Oracle-side loading.

## Project use after loading

For TypeSafe-relevant semantic work, read the installed `SKILL.md` and
the live [TypeSafe documentation index](https://docs.typesafe.ai/llms.txt).
Read the relevant API/SDK and question-design documentation before implementing
integration. Keep rules, calculations, authorization, and actions in
deterministic AgentOS code; TypeSafe may supply bounded semantic judgments,
not grant new capabilities or policies.

The Skill is an **instruction artifact**, not a System One API credential,
service subscription, or evidence that a TypeSafe HTTP request works.
Integrations involving API access require their own credentials, price/limit
review, tests, and task-level acceptance.

## Transport and publication boundary

Do not run the installer via the ChatGPT Bootstrap Control Inbox, generic
Relay shell text, or an arbitrary-command GitHub Actions job. Oracle-side
installation uses a previously authorized local executor/node boundary.
A source PR, green CI, an installed file, and actual fresh-session skill use
are four distinct facts. Do not merge a protected branch without explicit
human authorization; do not mark the runtime installation complete based on
this PR alone.
