# Issue #152 — Gemini → ONE → OpenAI Codex extension E3 verification

Date: 2026-09-02

Verdict: `E3_GEMINI_ONE_CODEX_EXTENSION_CONTINUITY=VERIFIED`

## Scope

This verifies one concrete cross-extension continuity slice:

`Antigravity Gemini extension -> AgentOS ONE -> fresh OpenAI Codex IDE extension thread`

The durable authority remained the ONE-selected Canonical IR. Codex bootstrap/configuration contained discovery/runtime instructions only and did not contain a copied Canonical IR body.

Corrected E3 generation:

- project: `agentos-core`
- index: `idx-core-152-e3-codex-ext-1`
- IR: `ir-core-152-e3-codex-ext-1`
- parent IR: `ir-core-152-e3-1`
- selection source: `ONE_ACTIVE_CONTINUATION`
- Codex surface: `codex-local`
- executor class: `openai-codex-local`
- credential exposed: `false`

## Independent fresh-thread pass 1

A completely fresh OpenAI Codex IDE extension thread received only `繼續` and resolved the active ONE continuation through `agentos-one.one_resolve_active` before workspace-local reconstruction.

Sanitized issue evidence: #152 comment `5503435564`.

Independent terminal receipt after pass 1:

- `verdict=CODEX_ONE_ACTIVE_RESOLVE_OBSERVED`
- `source=ONE_ACTIVE_CONTINUATION`
- `project_id=agentos-core`
- `index_id=idx-core-152-e3-codex-ext-1`
- `ir_id=ir-core-152-e3-codex-ext-1`
- `surface=codex-local`
- `executor_class=openai-codex-local`
- `credential_exposed=false`
- `recorded_at=2026-09-02T02:28:29Z`

## Independent fresh-thread pass 2

A second completely fresh OpenAI Codex IDE extension thread again received only `繼續` and independently resolved the same ONE-selected Canonical IR generation.

Sanitized issue evidence: #152 comment `5503469931`.

Independent terminal receipt after pass 2:

- `verdict=CODEX_ONE_ACTIVE_RESOLVE_OBSERVED`
- `source=ONE_ACTIVE_CONTINUATION`
- `project_id=agentos-core`
- `index_id=idx-core-152-e3-codex-ext-1`
- `ir_id=ir-core-152-e3-codex-ext-1`
- `surface=codex-local`
- `executor_class=openai-codex-local`
- `credential_exposed=false`
- `recorded_at=2026-09-02T02:32:25Z`

The later receipt timestamp proves this was not merely a reread of the first Codex resolve receipt. The user explicitly opened a second fresh Codex extension thread for this regression.

## Contract / boundary evidence

The second live report also recorded:

- ONE connectivity and executor identity boundary: PASS;
- E3 contract suite: 28/28 PASS;
- `credential_exposed=false`;
- Codex `AGENTS.md` and MCP config contained bootstrap/discovery wiring only, not a duplicated Canonical IR body.

The local executor could not write this evidence file because `.agentos/evidence` on the Oracle working tree was owned by `agentos-node:agentos`. Permissions were deliberately not changed. The evidence was therefore persisted through the governed GitHub worker branch instead.

## Architectural conclusion

The earlier expectation that Codex should trigger Gemini's `~/.gemini/config/hooks.json` PreInvocation lifecycle was incorrect. Gemini and OpenAI Codex are separate extensions with separate native bootstrap surfaces.

Verified flow:

```text
Antigravity Gemini extension
        ↓ Gemini PreInvocation
ONE active selector → Canonical IR
        ↑ one_resolve_active
OpenAI Codex IDE extension
        ↑ Codex AGENTS.md + MCP bootstrap
```

Workspace location is not continuation authority. Client-specific bootstrap files do not own or duplicate the Canonical IR.

## Acceptance boundary

This verifies/stabilizes the E3 cross-extension continuity slice for the tested Oracle Gemini/Codex surfaces. It does **not** prove arbitrary model/executor/extension/machine portability, and it does **not** close #152. Broader Node/executor lifecycle extraction, capability truthfulness/freshness, bridge reconciliation, and later real client acceptance remain open.
