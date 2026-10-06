# AgentOS — agentmanager Project Context

This repository is the **AgentOS logic/runtime root**. Mutable project state belongs in the configured data layer; runtime semantics, contracts, tests, governance, and automation live here.

## Required reading order

Before architecture or system-level changes:

1. `README.md` — current product goal and public architecture.
2. `docs/GROWTH_PROOF.md` — highest-principle contract for demonstrating measurable AgentOS self-growth.
3. `docs/CURRENT_STATE.md` — canonical map of **Implemented / Verified / Research** capabilities.
4. `docs/AGENTOS_NODE.md` — responsibility/resource discovery contract for cross-project work.
5. `.agent/CONSTITUTION.yaml` and relevant governance/role sources when authority or policy is involved.

Do not rely on older memory/pulse-era documents as current architecture if they disagree with `docs/CURRENT_STATE.md` and executable evidence.

## Current architectural role

AgentOS currently contains, among other components:

- continuation-state reconciliation;
- persistent control-plane coordination;
- session lifecycle / handoff persistence;
- governance and capability responsibility resolution;
- resource/world-state registry;
- Realm cross-node execution surfaces;
- platform runtime drivers;
- operational evidence and drift guards.

The model-independent **Cognitive IR / zero-cost arbitrary model switching** layer is still research unless and until a repeatable benchmark proves it.

## Highest principle: AgentOS Growth Proof

AgentOS MUST continuously seek reproducible evidence that accumulated validated experience improves later independent execution. Architecture, memory, IR, runtime, recovery, benchmark, and product changes SHOULD preserve or strengthen the ability to measure this effect.

**Memory, persistence, more context, or a successful one-off repair are not sufficient evidence of growth.** A growth claim requires a reusable validated delta, later independent reuse, and measurable uplift against an appropriate baseline while relevant confounders are controlled.

The canonical proof contract, evidence ladder, metrics, and current proof inventory live in `docs/GROWTH_PROOF.md`.

## Critical constraints

- **Growth Proof is a first-class architectural acceptance criterion.** When a change creates reusable experience, capture enough evidence to determine whether a later execution became better because of that accumulated experience.
- Preserve Logic/Data separation: mutable user/project state must not be accidentally committed into the logic repository.
- Discover/resolve existing capability ownership before creating parallel infrastructure.
- Newer user intent must never be rolled back by stale snapshots, replay, or tool results.
- Evidence and tool results do not silently rewrite user intent.
- Claims in documentation must be backed by implementation paths; verified claims also need tests/evidence.
- **Capability does not imply authority.** A tool being available or a PR being mergeable does not authorize a protected-branch mutation.
- **Production runtime truth is node-authoritative.** For runtime parity/health claims, consume the runtime node's `agentos.execution-receipt/v1`. A ChatGPT/container sandbox DNS or HTTP probe must never override or substitute for Oracle/runtime-node evidence. DNS failure, local-service failure, source mismatch, and public HTTP failure must remain distinguishable in the receipt.

## Protected Branch Authority Rule

For `main`, `master`, and `release/*`:

1. agents may create branches, commits, tests, reviews, and pull requests;
2. agents may report a PR as `READY_FOR_MERGE`;
3. agents MUST then stop at `AWAITING_HUMAN_APPROVAL`;
4. CI success, mergeability, positive review, or a generic `continue` instruction are not merge authorization;
5. do not merge or directly push to a protected branch without a separate explicit human authorization event;
6. development repository writes must name an explicit non-protected branch; never rely on an API's omitted/default branch argument;
7. Core deployment authority, live acceptance, or evidence generation never grants repository publication authority;
8. GitHub provider-side protection for `main` is mandatory. AgentOS policy/CI without a provider ref fence is incomplete enforcement.

Evaluate the executable policy with:

```bash
python3 scripts/protected_branch_authority.py \
  --branch main \
  --actor-kind agent \
  --via-pull-request
```

The expected result without explicit human approval is `AWAITING_HUMAN_APPROVAL` and a non-zero exit status.

Provider-side acceptance is tracked separately and must prove that GitHub rejects a direct `main` push before mutation. See `docs/governance/decisions/GOV-2026-08-30-001-mainline-physical-enforcement.md`.

## Documentation Reality Rule

Architecture-sensitive implementation changes MUST update at least one authoritative entry-point document in the same change set:

- `README.md`
- `docs/CURRENT_STATE.md`
- `ONBOARDING.md`
- `AGENTS.md`

Run:

```bash
python3 scripts/documentation_reality_guard.py
```

CI enforces the same rule. Treat a documentation-drift failure as an architecture regression, not optional cleanup.

## Public Web Surface Machine-Readability Rule

Web surfaces created or materially changed by AgentOS MUST be classified before implementation as one of:

1. **public-discoverable** — intended to be found, shared, indexed, summarized, or understood by humans, search engines, link previewers, or AI agents;
2. **public-noindex** — publicly reachable but intentionally excluded from discovery/indexing;
3. **private/authenticated** — user-specific, administrative, sensitive, or access-controlled.

The reusable implementation owner is **`capability://web.static-index.render`**. Public web generators MUST resolve and invoke that capability; they MUST NOT independently embed another project-specific crawler/AI static-index implementation into application code.

For **public-discoverable** routes:

- Produce an `agentos.web-static-index/v1` input from the page/result's already-authorized public data and invoke `capability://web.static-index.render`.
- Serve the generated semantic HTML as the initial representation of the public route, or as a deterministic public summary/share route included in the product's discovery strategy. Client JavaScript may enhance the page but must not be the only source of its purpose or primary result.
- The static representation must contain a descriptive `<title>`, one meaningful `<h1>`, a concise textual summary, canonical URL, share metadata, correct robots intent, stable URLs, and correct HTTP status codes.
- Product code supplies page-specific data; the shared capability owns escaping, base semantic markup, crawler-facing metadata, and its render receipt. Do not fork/copy its template merely to customize a product.
- Structured data may be supplied only when it accurately represents the public page. Keep `robots.txt`, sitemap, canonical/noindex behavior, and route intent consistent.
- Do not expose private inputs, hidden state, account data, secrets, or internal diagnostics merely to improve discoverability.

For **public-noindex** routes, the same capability may be invoked with an explicit `noindex` robots policy when a machine-readable/shareable representation is useful. For **private/authenticated** routes, access control wins: do not create a public index artifact from private data.

**AI-friendly does not mean blanket training permission.** Content machine-readability and crawler authorization are separate controls. Search, archival, and AI-training crawlers may be allowed or denied independently through deployment policy. Optional conventions such as `llms.txt` may be added as hints, but they do not replace the static-index capability, semantic HTML, access control, or robots directives.

Acceptance for a public-discoverable route requires both the `agentos.web-static-index-receipt/v1` render receipt and a no-JavaScript fetch/inspection proving that a crawler can recover the route's title, primary heading, concise summary, canonical URL, and intended indexability.

## Useful verification

```bash
python3 scripts/continuation_state.py --self-test
python3 -m unittest tests.test_continuation_state tests.test_control_plane -v
python3 -m unittest tests.test_protected_branch_authority -v
python3 -m unittest tests.test_production_parity_receipt -v
python3 scripts/documentation_reality_guard.py
```

## Git reporting

After pushing changes, report the remote/branch and latest commit hash.
