# Project continuation publisher — consumer cutover acceptance

Status: candidate on PR #1923; NOT deployed or merged.

## Breaking change and compatibility
Existing execution-head / continuity state can no longer be replaced by an unfenced `agentos.project.publish_continuation` call. For a new project state, the caller may publish the initial generation using exactly `project_id`, `execution_head` and `continuation`. For all subsequent generations, it MUST first read the canonical current pair and supply nonempty `expected_index_id` and `expected_ir_id` in the Action params. Both values identify the observed parent generation, not the newly proposed child.

If rejected because the observed generation differs, the caller MUST re-resolve state, re-plan, and retry with a fresh child index and correct `parent_ir_id`. It MUST NOT retry by dropping CAS fields or deleting canonical files.

## Required real-path acceptance (not established by hosted CI)
1. Record the exact deployed Oracle release SHA, Action Relay version, authenticated ONE dispatch actor, and project Governance Directory identity.
2. Read `execution-head.json` and `continuity/latest.json` through the authorized resolver; ensure both expose the same `index_id` and current canonical `ir_id`.
3. Dispatch one new child via `agentos.project.publish_continuation` with the expected pair; verify the action receipt, both file hashes, and readback generation.
4. Replay a stale child using prior expected IDs; require a rejected receipt and unchanged on-disk bytes.
5. Try unguarded overwrite; require fail-closed rejection. Check consumer recovery behavior and that the unrelated projects/services are unaffected.
6. Confirm rollback with the owning immutable release controller, without resetting shared checkout or reverting other service pointers.

## Ownership and safety
- #1682 owns functional migration evidence and closure; #889 coordinates priorities.
- #1680 owns Oracle Runner restoration. An unexecuted queued audit is NOT a pass.
- #1923 is a scoped `main` candidate. Explicit human approval is required for protected-main merge. A successful GitHub-hosted unit run alone cannot authorize production cutover.
- `core/integration` retains current runtime authority pending verified release cutover; no automatic writer enablement merely because PR is merged.

## Security boundary: capsule integrity is not caller authorization
The current `ActionRelayWorker.process_one` validates an **unkeyed SHA-256 digest** of a capsule, then dispatches `ACTIONS[action](params)`. Anyone who can submit an arbitrary capsule to the inbox can recompute an unkeyed digest. Therefore the digest alone proves neither authenticated ONE provenance nor authorized project mutation. Publisher-side `mutation_allowed` governance is necessary but must not be mistaken for caller authentication. Before production activation, the action inbox's writer ACL, ONE dispatch authorization, project scope, and provenance-to-receipt binding must be independently verified at the actual Oracle runtime. The hosted tests and Oracle Governance Directory Audit do not supply that proof. **Do not enable live publication merely because the PR passes CI.**
