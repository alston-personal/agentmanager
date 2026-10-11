# AgentOS Current Architecture & Reality

**Status date:** 2026-10-02  
**Purpose:** canonical public map of what is implemented, what is verified, and what is still research.

This document exists to prevent architecture drift between code and prose. It is intentionally narrower than a roadmap: every item marked **Implemented** must have a concrete repository path; every item marked **Verified** must also have a test or evidence path.

## Product goal

AgentOS has one continuity goal:

> A user should be able to switch session, model, executor, or machine and continue useful work without manually reconstructing the project from a large conversation history.

This goal is broader than memory retrieval. AgentOS treats durable project/working state as an external system concern and treats models as replaceable executors.

## Reality map

| Capability | State | Implementation | Verification / evidence |
|---|---|---|---|
| Logic / data separation | Implemented | `agent_core/config.py`, bootstrap/runtime scripts | existing bootstrap/runtime tests |
| Session close / handoff record | Implemented | `agent_core/session_lifecycle.py`, `runtime_core/` | `tests/test_session_close.py` |
| Continuation-state monotonicity | Implemented + tested | `scripts/continuation_state.py` | `tests/test_continuation_state.py` |
| Persistent control plane | Implemented + tested | `agent_core/control_plane.py` | `tests/test_control_plane.py`, `.agentos/evidence/bootstrap-control-plane.txt` |
| Canonical Project Identity | Implemented + tested | `agent_core/project_store.py`, `agent_core/resolve_facade.py` | `tests/test_project_store_canonical.py`, governed Core registration workflow/evidence |
| Project release-lane authority | Implemented + tested | `.agent/governance/project_release_lanes.yaml`, `scripts/check_project_release_lane.py` | `tests/test_project_release_lane.py`, `Project Release Lane Guard` |
| Runtime ownership isolation | Implemented policy + CI guard; Dashboard immutable-runtime migration candidate | `.agent/governance/runtime_ownership.json`, `scripts/check_runtime_ownership.py`, `scripts/deploy_dashboard_release.sh` | `tests/test_runtime_ownership.py`, `Runtime and Completion Governance`, issue #470 |
| Durable work completion ownership | Implemented + live accepted | `scripts/work_completion.py`, Lobster integration in `scripts/lobster.py`, immutable completion-executor runtime | `tests/test_work_completion.py`, Oracle run `36130001931`, issue #470 |
| Pinned project POC candidate deployment | Implemented for LayoutLib candidate path | `.github/workflows/oracle-release-layoutlab-v08-dev.yml` | release-lane static acceptance + public POC acceptance after dispatch |
| Node registry / capability discovery | Implemented + tested | `agent_core/node_registry.py`, `scripts/agentos_node.py` | `tests/test_agentos_node.py`, `tests/test_node_registry_v01.py` |
| Web static index render capability | Implemented candidate + tested | `capabilities/web_static_index/`, `scripts/web_static_index.py`, `agent_core/capability_manifest_adapter.py` | `tests/test_web_static_index.py`, `tests/test_capability_manifest_adapter.py` |
| Google Colab remote compute provider | Declared integration candidate | `capabilities/colab_compute/capability-manifest.json`, `docs/COLAB_GPU_PROVIDER.md` | live Oracle preflight/session/output receipt required |
| MiniMax H3 video generation via Colab | Declared integration candidate | `capabilities/minimax_h3_colab/capability-manifest.json`, upstream `killkli/minimax-h3-colab-skill` | pinned upstream install + end-to-end MP4 receipt required |
| Governance responsibility resolution | Implemented + tested | `agent_core/governance_directory.py` | `tests/test_governance_directory.py`, governance audit workflow/evidence |
| Resource registry / world-state lookup | Implemented + tested | `agent_core/resource_registry.py` | `tests/test_resource_registry.py` |
| Realm / cross-node fabric | Implemented slices + tested | `agent_core/realm_fabric.py`, `agent_core/realm_server.py`, `agent_core/realm_cli.py` | `tests/test_realm_fabric.py`, `.agentos/commands/` |
| Controller dispatch route | Implemented + tested; capability-first selection candidate | `agent_core/controller_service.py`, Realm server `/v1/controller/dispatch` | `tests/test_controller_service.py`; historical Control Inbox evidence proves the route, while capability-auto routing still requires post-merge live acceptance |
| Core deployment authority / generation fence | Implemented + live accepted | governed claim/install/release path, Action Relay deployment fence | `docs/CORE_DEPLOYMENT_AUTHORITY.md`, active-lease conflict proof, Issue #64 acceptance |
| Platform driver abstraction | Implemented + tested | `agent_core/platform/`, `scripts/platform_runtime.py` | `tests/test_platform_runtime.py` |
| Governance drift guard | Implemented + tested | `scripts/drift_guard.py`, constitution/role registries | `tests/test_drift_guard.py` |
| Protected-branch authority guard | Implemented | `.agent/governance/protected_branches.yaml`, `scripts/protected_branch_authority.py` | `tests/test_protected_branch_authority.py`, `docs/governance/decisions/GOV-2026-08-27-001-protected-branch-authority.md` |
| Evidence-first operational acceptance | Implemented | `.agentos/evidence/` | live acceptance files committed by workflows |
| Documentation Reality Guard | Implemented | `scripts/documentation_reality_guard.py` | `.github/workflows/documentation-reality-guard.yml`, `tests/test_documentation_reality_guard.py` |
| Off-chain Credits ledger | Implemented + tested | `agent_core/credit_ledger.py` | `tests/test_credit_ledger.py`, `tests/test_reuse_before_build_credits.py` |
| Credits pricing + shadow metering | Implemented candidate + tested | `agent_core/credit_service.py`, `.agent/governance/credit_pricing.json` | `tests/test_credit_service.py`, `.github/workflows/credits-contract.yml` |
| Local Credits service boundary | Implemented candidate + tested | `agent_core/credit_http.py` | `tests/test_credit_http.py`, `.github/workflows/credits-contract.yml` |
| Model-independent Cognitive IR | Research | operational handoff envelopes exist, but general sufficiency is not canonical | requires repeatable cross-model continuity benchmark |
| Zero-cost model switch with only `continue` | Target / not yet proven generally | depends on portable working-state + canonical resolution layer | continuity benchmark still required |

## Canonical Project Identity contract

### Mio PDCA social observation (#814 candidate)

The currently deployed Persona PDCA sources are on `main`, separately from
the historical Social Runtime patrol workflow on `core/integration`. Do not
infer live PDCA acceptance from a manual patrol run or from either branch head.

`persona_pdca_tick.py` now queues `social.threads.observe` as `pending_external`.
Follow-up candidate: each active, sufficiently energized PDCA heartbeat also
plans a read when the last successful, receipt-linked read would exceed the
freshness goal before the next heartbeat. `social_observation.max_age_minutes`
defaults to `heartbeat_minutes` (60 if omitted); periodic observation can be
disabled with `social_observation.enabled=false`. Invalid interval policy does
not schedule a supplemental read. This environmental input does not replace
the randomly selected creative/reflection intent or compel a public reply.
Sleep/rest and energy below 15 defer periodic reads; an existing candidate or
in-progress read prevents duplicates, and a blocked read prevents supplemental
retry until repair. An explicitly selected observe remains a separate decision.
If all 12 pending slots hold unfinished work, supplemental observation is
deferred with `pending_capacity`; only terminal entries may be evicted for it.
The passive read cost is accounted in energy, and the existing worker prioritizes
the queued observation over a public write candidate. No new timer is introduced.
Freshness is a planning goal sampled at heartbeats, not a wall-clock SLA through
rest, adapter outages or worker backlog. This follow-up is source-tested only;
merge/deployment and a real autonomous read receipt remain required.
The existing short-cycle `run_persona_social_actions_user.sh` consumes that
durable intent through `persona_social_executor.py` and the existing Social
Runtime `post.read` / `replies.read` boundary. It never uses Threads Web DM.
No read, failed required reads, or malformed adapter result cannot produce a
completed observation. The executor stores action/cycle-bound receipts, a
cursor, and a separate last-observation summary. It queues `social.reply.review`
only after fresh externally authored replies are observed. Newest five posts
are read even when `has_replies=false`; the bounded scan covers at most 20 posts
and newly eligible replies at most 42 hours old. It does not prove exhaustive
historical/paginated coverage or successful autonomous reply delivery.

Read failure records BLOCKED plus an open, sanitized Persona incident in the
data layer; the heartbeat and other work continue. These local incidents are
pending repair, not proof that GitHub Incident/repair routing completed.
The public activity projection exposes the last actual read status/time/counts
separately from the heartbeat without comment text, binding IDs or credentials.

This candidate uses the existing Oracle-local social worker lane. The unified
AgentOS scheduler route, owner Observer parity, automatic repair routing and
live new-comment acceptance in #814 remain pending. Offline tests prove only
the source contract. Merge approval and exact-generation Oracle deployment
must precede any live-restored claim.


### Mio post reasoning Codex failover and diagnostics (candidate)

`scripts/persona_post_intent_generator.py` records each provider attempt's elapsed
time and a bounded failure classification, including unsupported OAuth clients,
authentication, rate limits, CLI contracts and network failures. Raw CLI output,
prompts and credentials are not persisted. Unmatched errors stay unknown; these
classes are diagnostic hints, not a substitute for provider/node acceptance.
Receipts identify the executing generator by SHA-256 and use completion time.
Post candidates link the receipt and distinguish Claude, Gemini, Codex and deterministic
liveness fallback. Model responses require boolean decision fields before they
can be accepted; missing executors also leave a durable receipt. Noninteractive
CLI invocations have closed stdin. Claude retains its 45-second timeout; Gemini
and Codex each have a 60-second timeout (at most 165 seconds of model calls).
Codex is tried after the existing providers fail, before deterministic fallback.
It composes the existing Codex provider's executable discovery and read-only
`exec` recipe with an ephemeral empty workspace/config home, no shell/apps/MCP
configuration and a local reference to existing OAuth authentication. It cannot
publish; its final answer only enters the existing delayed candidate lane.

`tests/test_persona_post_reasoning.py` exercises failover, redaction, malformed
output, no-post decisions and truthful fallback provenance without live posts.
This candidate improves diagnosis; it does not claim restored model authoring.
The 2026-10-10 Oracle `gemini.cli.health` receipt reported
`GEMINI_CLI_OAUTH_CLIENT_UNSUPPORTED` in Control Inbox #50 (comment 6097605043;
command `chatgpt-mio-gemini-health-20261010T124158678Z`). That provider rejection
requires a supported, independently accepted provider/auth path; retrying or
relabeling fallback text cannot establish recovery. The same Oracle returned
`CODEX_CLI_HEALTH_READY` at 12:46:03Z in #50 comment 6097639114. That accepts the
existing Codex health recipe, not this isolated Mio invocation. Exact-generation
deployment and a new node-authoritative Mio reasoning receipt remain required.

### Mio post history and topic continuity (source candidate)

The existing `scripts/persona_post_intent_generator.py` now filters relevant
events before bounding the model context, instead of allowing raw PDCA
housekeeping to displace earlier published claims. It separately supplies the
last 12 public post objects, with up to 500 characters per post, and the last 20
relevant events with up to 240 characters each. Execution and platform-observed
post records sharing the same object ID are one post; distinct or missing IDs
are not merged merely because their text matches. Own post history is ordered
by publication timestamp, so late ingestion of an older post cannot make it
the newest claim. Post count, gap and liveness calculations use the full parsed,
deduplicated post ledger rather than its last 80 raw entries. These history
bounds are context budgets, not posting or topic quotas.

The authoring instructions ask for a new underlying observation, question or
interpretation when returning to a topic, and preserve evidence-backed interest
exploration without forced rotation. Agreeing comments do not automatically
justify restating a claim in another standalone post. Literal repeats within
the own-post window, ignoring Unicode punctuation, spacing and case, defer
without creating a publish action; the consider stays pending for a later
natural attempt. This guard also applies to the existing safe liveness fallback.
It does not detect arbitrary semantic paraphrases. If every model is unavailable
and the fallback repeats a recent post, publishing remains held rather than
being reported as a successful new post.

Reasoning receipts bind the delivered history with counts, source object IDs
and SHA-256 hashes rather than raw prompt/provider content. Provider PASS or a
delivered history digest does not establish novelty or self-growth; the receipt
explicitly records semantic novelty acceptance as NOT_OBSERVED. No persona IR,
promoted growth, source rights, image policy, energy settings, pending live
actions, timers, provider deadlines or reply routing is changed by this source
candidate. Tests extend `tests/test_persona_post_reasoning.py` and run in the
existing reasoning/media contract workflows. Exact installed generator digest,
natural history-bound reasoning receipts and later post-content review remain
required after separate protected-main approval and deployment; offline provider
doubles do not prove improved topic diversity or real publishing acceptance.

### Mio reviewed single-image delivery (source candidate)

The existing PDCA media worker, draft-only FLUX executor, identity-manifest
validator and `agentos.social_runtime` image publisher remain the owners. This
candidate connects independently reviewed drafts to that publisher; it creates
no second image API, patrol timer, account session or nginx serving root.

`scripts/persona_media_asset.py` binds a `milkcat.image-manifest/v2` review to
the action, caption SHA-256, exact image bytes, current reference pack/visual
policy and world/wardrobe catalog digests. Required content checks cover scene
provenance, wardrobe rights, season, caption facts, final image/caption, world
selection and assembly. Catalog candidates and unverified retail image rights
cannot be upgraded by a model's pass label. Identity validation reuses
`validate_mio_visual_manifest.py`; this initial lane requires the existing
photo-like-face identity checks. A review lives at
`pdca/media_reviews/<action_id>.json`; it is evidence input, not a generated
approval. Generated drafts remain unverified until this review exists.

The existing worker hosts reviewed JPEG/PNG bytes by content hash in the
existing Mio static subtree, verifies the exact public bytes, and records an
action-bound asset receipt. `persona_social_executor.py` rechecks the receipt,
review and public digest before requesting the existing IMAGE acceptance/write.
It completes only after the exact returned platform ID reads back with the
same caption, `media_type=IMAGE`, visible image and permalink. Deferred readback
is read-only and charges the write's energy once, even when the write leaves
energy negative. Missing image prompts/assets defer rather than downgrade to
text. Text and public-reply receipts now retain the provider's top-level object
ID, and public-reply events retain their parent/root IDs.

A private, node-local write journal survives disposable data clones and failed
Git pushes. Once image dispatch starts, subsequent cycles may only reconcile;
timeouts/unknown results cannot trigger another publish. Missing platform ID
requires separate bounded reconciliation/repair, never a blind retry. Image
readback does not prove the visible picture matches Mio's identity; that remains
the independent review's responsibility.

The FLUX executor now requires `AGENTOS_MIO_REFERENCE_IMAGE` to identify bytes
matching the canonical approved reference pack; the public avatar is no longer
a substitute. Node-private optional configuration lives in
`~/.config/agentos/mio-media.env`. The existing deployment installs both shared
asset resolver and visual validator. It does not populate reference bytes,
approve catalog rights, invent reviews or force an image post. Automatic visual
review generation is still not integrated/verified. Current catalog eligibility,
reference availability, provider execution, hosting and real autonomous IMAGE
delivery require independent Oracle receipts after approved merge/deployment.

Offline verification: `tests/test_persona_media_publish.py`,
`tests/test_mio_media_ledger_smoke.py`, `tests/test_persona_post_reasoning.py`,
and `Persona Reviewed Media Contract`. No public test posts or historical asset
reuse are performed. Carousel and media replies remain outside this candidate.

Project identity is explicitly separated from repository, checkout path, runtime path, deployment target, and state storage.

### Mio independent draft review and readiness follow-up (source candidate)

`scripts/persona_media_review.py` extends the existing PDCA media worker; no new
timer, publishing adapter or account session is introduced. Post authoring now
receives only eligible world/wardrobe catalog entries and preserves selected IDs
in media intent. Missing/unusable sources defer the image decision without a
text downgrade. These IDs become part of the media-selection digest, and new
generation receipts bind the caption and selection. Catalog candidates and
unverified rights remain blocked before generation/review; no rights are granted
by inference. Existing generated receipts lacking the new binding require repair,
not automatic retrospective approval.

The reviewer composes the existing isolated Codex CLI recipe with two exact image
attachments: generated draft first, approved canonical reference second. An empty
ephemeral workspace/config disables shell, apps, MCP configuration and web search;
existing OAuth authentication is referenced without reading/printing credentials.
Each tick can make at most one 60-second review call. The current lane requires a
visible realistic Mio face, resolved mirroring, specific identity/content evidence,
natural anatomy/garments and all visible wearables matched to selected IDs.
Unseen input, ambiguity, missing features, unseen/unlisted clothing or failed gates
leave a hold. The model cannot change caption, catalog state, licenses or provenance.
Exact action, image, canonical reference, policy and authority are rechecked after
review. The existing manifest guard and reviewed-asset publisher still decide
hosting/delivery; review success is not publication success.

`pdca/media_review_receipts/` records sanitized outcomes and source/image bindings.
Unchanged failed/successful inputs do not invoke the provider again; policy, image,
reviewer/executor or authentication-file revision changes permit a new review.
Externally supplied reviews are preserved. This bounded mechanism does not claim
that policy edits repair a provider failure or establish visual accuracy.
`pdca/media_readiness.json` reports reference digest match, executable presence,
eligible catalog counts, reviewer/worker source digests and observation time.
It refreshes on changes or after an hour, and distinguishes configuration from
provider/hosting/autonomous-publication acceptance. Optional malformed review
inputs remain local holds rather than discarding a completed social observation.

The existing installer installs the reviewer and enables `codex_cli` review mode
in the social unit; private `mio-media.env` can override it. It does not copy the
canonical reference to Oracle, read another service's API key, promote catalogs,
force image frequency or make a public test post. Workflow-dispatch dependencies
are installed before the one-cycle path and resolved from that installed bundle.
The social runner now reports pending image readback and unknown write outcome
without falsely reporting a definite non-write or failing its receipt assertion.

Offline verification: `tests/test_persona_media_review.py`,
`tests/test_persona_media_publish.py`, `tests/test_persona_post_reasoning.py`, and
`tests/test_mio_media_ledger_smoke.py`. Deployment, node reference configuration,
image-input provider acceptance, real review quality and a natural autonomous IMAGE
delivery remain unverified. The 2026-10-11 source investigation found the existing
reference Library bytes match the approved reference-pack SHA-256; that proves
source availability only, not the Oracle file/environment configuration.

### Mio scene/object image review (source candidate, policy opt-in)

The existing authoring, FLUX draft generator, independent Codex reviewer,
manifest guard and reviewed-image publisher now share an explicit
`subject_mode`: omitted means the unchanged `mio_portrait` lane; `scene_only`
requires `visual_content_policy.json.scene_only_images.enabled` to be the
boolean `true`. Unknown modes, absent/disabled policy and nonempty wardrobe
selections hold the image decision. This is a source candidate, not live policy
activation. The existing production v3 policy has no opt-in; a separately
reviewed data-policy change is required before authoring advertises scene mode.

Scene generation uses a neutral canvas through the existing FLUX Kontext
provider, never the private identity reference as provider input. Its receipt
records subject mode, generation-input hash and `identity_reference_used=false`;
the approved canonical pack remains a bound policy/reference revision. Portrait
generation continues to use exact approved reference bytes. The scene reviewer
receives only the draft and must establish absence of people, human parts,
reflections, silhouettes, mannequins/human depictions and any wearables,
including detached or animal-worn items. A hidden face cannot qualify. All
seven existing content/source/rights checks plus `no_people` and photorealistic
quality require independent evidence; selected usable world IDs remain required.
No unapproved food, animals, props, clothing, logos, real-visit/ownership claims
or commercial assertions are authorized by the scene label.

Scene manifests remain `milkcat.image-manifest/v2` with explicit scene evidence,
without an identity blueprint or a claim that Mio likeness was verified. The
existing validator requires its mutually exclusive `--scene-only` flag; all
portrait checks remain on `--photo-like-face`. Subject choice is bound into the
selection hash only when explicitly present, preserving old portrait receipt
digests. Changed caption, mode, source selection, draft, policy or authority
invalidates review. Hosting, public-byte verification, exact IMAGE readback,
node-local dispatch journal and one-time energy debit reuse the existing lane.
No image intent is converted into text and no timer/post quota is changed.

Readiness separates supported vs policy-enabled modes and binds installed
generator/resolver/validator hashes alongside the existing worker/reviewer
hashes. These configuration receipts remain `NOT_OBSERVED` for provider,
hosting and autonomous publication until real natural requests supply evidence.
Offline `tests/test_persona_scene_media.py` verifies authoring, neutral input,
one-image review, strict absence evidence, stale/revoked policy, subject tampering,
existing host/write/readback/journal/energy behavior and portrait regressions.
No live provider call or public acceptance post is made. Wardrobe extraction
and verified backfill in #1704 remain separate; removing a uniform background
does not identify/extract a target garment from a complete outfit.

### Mio private canonical reference installation (source candidate)

`scripts/persona_reference_install.py` completes the missing reference transfer
on the existing Persona PDCA deployment carrier. Exact Library bytes have been
replicated in the private data repository on `assets/mio-reference-v2.1`, commit
`87320a45ad554ed61453eb8e0acef5b32552d5a6`; SHA-256 remains
`0725379743f3a908babaa711c8fc016daf7161aa1a3d912c3d15ecaf2bd9aa64`.
The installer fetches only this pinned reference/transfer record, verifies the
repository is private and the current main reference pack approves the exact ID
and bytes, then rechecks approval after downloading. It uses the existing node's
GitHub authentication without reading or printing credentials. The reference
is not copied into the public logic repository or public static media subtree.

Only UID 1001 may install into the fixed private Mio reference directory. Atomic
0600 files and a separate `mio-reference.env` configure the existing social unit;
the existing `mio-media.env` is preserved. Identical installs leave asset/config
timestamps unchanged. Symlink paths, digest changes, revoked approval, invalid
source data or a public source repository block installation. A sanitized
node-authoritative `agentos.execution-receipt/v1` is persisted at
`/home/ubuntu/agent-data/runtime/persona-media/reference-install.json` and returned
through the existing carrier. Installation does not call a generation provider,
review an image, publish a post, change catalog eligibility or create a timer.

The #1718 deployment was observed on Oracle at 2026-10-11 11:35 Asia/Taipei.
Its first new-setting readiness report at 11:40:55 confirmed exact worker/reviewer
digests and `codex_cli` mode, but reference availability remained blocked and
eligible world/wardrobe counts were both zero. This follow-up's offline tests
are `tests/test_persona_reference_install.py`; protected-main merge and exact
Oracle installation/readiness evidence remain required. Even a matched reference
does not establish source eligibility, image-provider acceptance, visual-review
quality, hosting or autonomous IMAGE publication/readback.

### Mio wardrobe source inspection (source candidate)

The existing media reviewer now adds a bounded, read-only `wardrobe.source.inspect`
execution receipt to `pdca/media_readiness.json`. The deployment sets
`AGENTOS_MIO_GARMENT_DATA_ROOT=/home/ubuntu/agent-data` so the reader inspects the
existing garment owner's `projects/dressup-simulator/garments/{seeded,imported}`
store, not the disposable social-data clone. Imported records override seeded
records by exact garment ID. Missing configuration does not scan any fallback
directory; it reports `NOT_CONFIGURED`. Unscoped/other-character records are counted
separately. Legacy flat garment fixtures are not active registry inputs.
Catalog joins require explicit `items[].garment_id`; names, prices, retail URLs,
ownership or a try-on result never create that binding or publication authority.

The receipt distinguishes catalog state, unverified product-image rights,
missing rights evidence and a garment link not observed in this bounded scan.
It reports registry absence, unreadable/invalid records, duplicate IDs and scan
limits separately from observed counts. Each directory permits at most 128
enumerated entries, each JSON at most 128 KiB, and at most 24 catalog diagnostics
and 24 safe garment projections are emitted. Symlink/nonregular inputs are rejected. Source snapshot and reviewer
digests bind the observation; raw images, paths, URLs, notes and credentials are
not returned. Declared isolation approvals are explicitly not asset verification.
Only the installed Oracle reviewer under the expected user/node and configured
live store marks runtime-node provenance; offline fixtures remain offline.

This candidate is diagnostic: it does not import products, rewrite the catalog,
grant rights, extract assets, force try-on/review/posting or add a scheduler.
The existing #1704 isolation work remains separate and staged pending a working
extractor/backfill; it cannot be merged to solve social catalog eligibility.
Tests extend `tests/test_persona_media_review.py`. Protected-main approval,
deployment and an actual node receipt are required before claiming this audit
is live or identifying the live registry's contents.

Accepted configuration evidence as of 2026-10-11: #1719 deployed exact source
`3f6e3f9fbd25cf6fe0cc94bf4c3a9184faf61ddf` via Persona PDCA run
`38111271580`; `canonical_reference.install` returned runtime-node `completed`,
`parity=matched` at 12:21:42 Asia/Taipei. The natural 12:30:57 readiness report
after private data PR #38 returned `reference_status=MATCHED`, eligible world
count 5, wardrobe count 0 and `CONFIGURED_NOT_ACCEPTED`. This supersedes the
earlier missing-reference/zero-world observations, but does not establish image
provider, independent review, hosting or autonomous IMAGE publication acceptance.

Accepted wardrobe inspection evidence as of 2026-10-11: #1720 deployed exact
source `013c1678c8b90af52c0111e3bc4a545777b9c8dd` via Persona PDCA run
`38113027203`. The natural 12:55:48 Asia/Taipei readiness receipt returned
runtime-node `completed`, canonical registry `OBSERVED`, eight explicitly scoped
active garments, no scan issues and zero catalog links. All eight isolation
declarations were `UNKNOWN`; no asset verification was performed. The five
legacy social wardrobe candidates still had unverified rights and no explicit
canonical links. Eligible wardrobe count remained zero. Source snapshot SHA-256
was `867047f2e2244f6ada6e499a6a481487e714e6942af87bd754abdf3edcf816b3`.
This accepts the diagnostic reader, not isolation, try-on or IMAGE publication.

### Mio canonical wardrobe planning (source candidate)

`scripts/persona_wardrobe_sources.py` reuses the bounded reader above for internal
outfit planning, post ideation and media readiness. It projects the existing
garment owner's exact IDs and normalized layers into at most 24 safe planning
candidates, including clothing, shoes, bags and accessories. Imported records
override seeded IDs. No catalog is copied, joined by retail URL or rewritten.
Canonical candidates are always planning-only and publication-ineligible,
irrespective of declared ownership, wear, rights, successful try-on or isolation.
Internal proposals do not infer real ownership, wear or purchase.

Explicit live-store configuration wins over the legacy persona catalog, including
when the configured store is empty. Absent directories or a partial/unreadable
scan hold planning without falling back to old ZARA/DIANA entries. Legacy persona
catalog compatibility applies only when no live-store configuration exists.
Source snapshot, active record and adapter digests bind the internal proposal;
post reasoning receipts record only safe source provenance/counts. The authoring
prompt treats labels as untrusted hypothetical styling data. Planning IDs never
extend `eligible_media_sources`; the existing rights and media checks still
reject planning-only image selections.

The existing Persona PDCA installer/carrier ships the shared helper and sets
the same explicit garment data root for both heartbeat and social units. Timer
cadence and authoring frequency are unchanged. Readiness exposes the safe
planning projection to verify installed source and owner bindings without forcing
a cycle, provider call, try-on or public post. Tests in
`tests/test_persona_wardrobe_sources.py` cover source precedence, held inputs,
read-only provenance, internal proposals and authoring's image boundary.
This consumer integration remains a source candidate until separate protected-main
approval, deployment and an exact node receipt. #1704 still needs operational
extraction and verified backfill; this integration does not satisfy that gate.

The canonical project document uses schema `agentos.project/v1` and includes at minimum `project_id`, `display_name`, aliases, source repository/branch/path/node, and state locations. `project_id` is a stable logical identity and must not be derived from a repository name or checkout directory.

### Mio optional media fault isolation (source candidate)

On 2026-10-11, an offline malformed media-request fixture reproduced an uncaught
worker exit. The social runner's prior unconditional media invocation under
`set -e` then stopped reply/post cognition and persistence of an already completed
observation. This is a reproduced failure condition, not evidence that production
currently contains a malformed request or that today's silence has this cause.

The existing social runner now treats a missing or nonzero-exit media worker as
an optional media failure. It records a sanitized `persona.media.worker.tick`
execution receipt in `pdca/media_worker_runtime.json`, then continues existing
reply/post cognition and observation persistence. The receipt binds worker/runner
digests and distinguishes installed Oracle runtime-node provenance from offline
fixtures. Repeated unchanged outcomes do not rewrite timestamps. Raw worker
stdout/stderr stay in the disposable clone and are not committed or echoed.
A successful worker tick does not prove image acceptance or grant publication.

Durable persona state must still be a valid JSON object before any adapter call
and after the media worker. Corrupt state stops the lane before cognition or
persistence, including if the failed worker produced that corruption. This guard
does not turn image failures into text posts, bypass visual/rights checks, remove
the global lock, change provider deadlines or alter scheduler/posting frequency.
Tests in `tests/test_persona_media_fault_isolation.py` execute the real shell lane
with offline adapters and Git/gh doubles, including the real media worker against
a malformed request. Separate main approval, deployment and an installed-node
receipt remain required; no bad request is injected into production for testing.

Accepted #1722 evidence: exact source
`1e42503a1080ff0c6f6f85a968764500a2981b58` deployed via Persona PDCA run
`38114235724`. The natural 13:20:51 Asia/Taipei node receipt bound eight canonical
planning candidates and exact adapter/reviewer digests, with eligible world and
wardrobe counts 5/0. At 13:26:50 the natural `oracle_local_timer` advanced cycle
194 to 195 with `reflect / reflection_note`, a matching cognitive IR projection,
and `RUNNING` state. This supersedes the preceding planning source-candidate
installation status; no autonomous wardrobe selection or IMAGE publication was
claimed from that configuration acceptance. #1704 extraction/backfill remains
unaccepted and must not be enabled merely to bypass social media eligibility.

Accepted #1724 evidence: source `af084328d68f4f38146aa201afa4a8a9b8f46a9c`
deployed through the existing main-push Persona PDCA run `38118238636`.
Both timers remained active; stale recovery and an installer live cycle were
skipped. The natural social lane persisted a `persona.media.worker.tick` receipt
at 14:35:52.163832 Asia/Taipei on `instance-20260129-0852`, with runtime-node
authority, production environment, worker exit zero and exact installed runner
and worker hashes. Cycle 196 remained `RUNNING`; its natural 14:30:53 observation
read 13 posts and 66 replies successfully, without a public write. This accepts
the installed optional-worker guard. Its failure behavior is proven offline;
image generation/publication and #1704 extraction/backfill remain unaccepted.

### Mio image holds and independent social actions (source candidate)

An offline executor regression reproduced a second failure boundary: a due,
unvalidated image post at the front of the queue repeatedly consumed the action
turn, leaving an already-due public reply untouched. This is a reproducible queue
condition, not evidence that production currently contains a pending image or
that today's posting cadence was caused by this defect.

The existing `persona_social_executor.py` now selects an independent due action
ahead of an image candidate waiting for media validation. Environmental reads
retain priority, and other due actions retain their queue order. If there is no
independent action, the original image hold is still reported; selection does not
convert it into text, discard it, mark its review complete or bypass publication
checks. Validated images and in-progress writes keep their existing turns. A
node-local image write journal also preserves reconciliation when a failed Git
push leaves a stale candidate in the data repository. Journal resolution is
shared with image dispatch and the depleted-energy recovery check, so changing
selection cannot accidentally create another publish or miss a prior write.
The existing worker runtime receipt also binds the social executor's SHA-256
captured before invocation, alongside worker and runner hashes. This enables
natural installed-source acceptance without injecting a pending image into
production or forcing a public test reply.

`tests/test_persona_social_selection.py` runs the actual executor with offline
adapters, including exact image review/readback and the private write journal.
It covers reply progress behind both image modes and review failures, preserving
the original hold, future due times, read priority, ordinary write order, energy
gates, validated images and read-only recovery at negative energy. Separate main
approval, deployment and a natural installed-node receipt remain required.

## Project release-lane authority

Project identity alone does not authorize a branch mutation or deployment. AgentOS Core models project development, promotion, POC deployment, and production deployment as separate authorities.

For LayoutLib the canonical contract is:

```text
active development: alston-personal/layoutlib/develop or explicit feature/fix/governance branch
promotion state:    alston-personal/layoutlib/main
POC surface:        https://studio.milkcat.org/poc/layout-lab/
POC source:         validated, pinned develop candidate
production surface: https://studio.milkcat.org/layout-lab/
production source:  promoted main/release state
immutable baseline: release/v0.7.9
promotion/deploy authority: AgentOS Core
```

A project-development action targeting LayoutLib `main` is denied. Promotion to `main` is a distinct action requiring an explicit human approval event plus Core governance. A passing test, a mergeable PR, a deployment capability, or the user's generic `continue` instruction is not promotion approval.

Project threads may create project commits, tests, evidence, and candidate requests on the development lane. They must not acquire deployment authority by directly editing `agentmanager` deployment workflows. POC deployment consumes a validated candidate commit selected from the registered development branch; production consumes only promoted state. These rules are machine-readable in `.agent/governance/project_release_lanes.yaml` and enforced by `scripts/check_project_release_lane.py`.

For LayoutLib POC deployment, Core additionally requires an exact 40-character `candidate_sha`. The deployment workflow first authorizes `poc_deploy` against `develop`, clones the explicit `develop` branch, verifies the candidate is an ancestor of that branch, checks out the candidate in detached mode, and records both `layoutlib-source-branch=develop` and the exact candidate commit in the public POC document. The release-lane CI guard checks this workflow contract so it cannot silently regress to cloning the repository default branch.

This contract was introduced after the LayoutLib v0.8 development incident in which project development landed directly on project `main` and the project thread then attempted to own Core deployment orchestration. Existing history is not rewritten; the correction establishes the authority boundary from this point forward.

## Runtime ownership and work-completion contract

Production runtime identity is separate from repository checkout identity. The shared Oracle checkout `/home/ubuntu/agentmanager` is a source/cache surface only; it is not a valid authority for deciding which production generation is live. Each service declares a release owner, immutable release root, live pointer and lock namespace in `.agent/governance/runtime_ownership.json`. Newly modified automation is rejected when it adds destructive Git operations against the shared checkout, copies a release into that checkout, or declares a new service runtime directly from it. Existing legacy runtimes are migrated service-by-service rather than silently grandfathered forever.

Promised implementation work is also durable state. Once accepted, a work item remains externally represented until it is either verified Done or explicitly Cancelled. Active work requires an owner, next action, acceptance criteria and an owner lease. A context, chat, model, machine or project switch is represented as a handoff that advances owner generation; it is not completion and it may not erase the work item. While a live owner lease exists, Lobster does not duplicate that work. If the owner disappears and the lease expires, the completion watchdog reclaims the item to `role://completion.controller`, after which it is projected back into the autonomous queue. Blocked work remains owned and records both blocker and next action. Done requires evidence plus a passed verification receipt.

The canonical work ledger is `/home/ubuntu/agent-data/governance/work-items.json` with schema `agentos.work-completion/v1`. `scripts/work_completion.py` performs atomic state transitions and can project unfinished items back into the central `TASK_BOARD.md`. Lobster consumes those `[WI:<id>]` entries before ordinary backlog and may only close the durable item after its existing Inspector/physical-output verification path succeeds. The governed Oracle installation lane is `.github/workflows/oracle-install-completion-controller.yml`; it installs Lobster from an immutable release root and installs a periodic stale-owner watchdog without using the shared checkout as runtime authority. Oracle run `36130001931` accepted the immutable Lobster runtime, active watchdog timer and expired-owner reclaim/projection probe. This closes the failure mode where switching to another project leaves a prior promise as a plan with no executor.

## Dashboard production runtime boundary

The Milkcat Dashboard production process name is `agentos-dashboard`. New Dashboard generations are built from an exact Git commit into service-owned directories below `/home/ubuntu/agent-data/releases/dashboard/apps/`; `/home/ubuntu/agent-data/runtime/dashboard/current` identifies the selected generation. PM2 must run the selected immutable release directory and must not use `/home/ubuntu/agentmanager/dashboard` as its production cwd.

Dashboard secrets and OAuth configuration are configuration state, not source-tree state. The migration controller canonicalizes them in the owner-only file `/home/ubuntu/.config/milkcat/dashboard.env.local`; release builds receive that configuration without logging values. The shared checkout remains a source/cache surface and may move independently.

`scripts/deploy_dashboard_release.sh` owns the release switch, exact listener verification, canary, PM2 replacement, rollback, auth/admin route checks and a regression probe that temporarily removes only the legacy shared `.next` build. A release is accepted only if the public protected routes remain healthy while that legacy build is absent. Until the first successful Oracle receipt, the registry marks this Dashboard migration as candidate rather than live.

## Windows Thin Client self-update receipt boundary

As of 2026-10-06, governed Thin Client upgrades initiated through ONE must not execute the installer inline inside the same `shell.exec` task that is expected to report the rollout receipt. The Windows installer intentionally stops the existing Thin Client process before replacing runtime files; if invoked inline, that process can terminate itself before it submits the task receipt.

The canonical rollout pattern is therefore two-stage: ONE asks the current Thin Client to register a delayed, one-shot Windows Scheduled Task pinned to an immutable source commit; that scheduling action returns a receipt first. The deferred updater then stops/replaces/restarts the Thin Client independently. Live acceptance waits for a fresh heartbeat and only then invokes the new capability. This keeps GitHub Actions as a deployment trigger/audit surface while Windows execution and acceptance continue through ControllerService/ONE.

## Windows one-click node onboarding

The canonical Windows onboarding entry point is `install-agentos.cmd`, backed by `install-agentos.ps1`. A user starts the installer once. The bootstrap resolves an immutable source commit, ensures a real Python 3 interpreter is available, installs the Thin Client files, preserves any existing enrollment identity, and configures the per-user `AgentOS Thin Client` Scheduled Task. The scheduled task is headless: it launches a hidden PowerShell runner rather than a visible `cmd.exe`, so logon starts, watchdog restarts, and task restarts must not flash a console window in the interactive desktop session. Upgrades also remove obsolete `AgentOS Thin Client Watchdog` and `AgentOS Thin Client Headless Switch` tasks from earlier builds, and the successful `.cmd` bootstrap exits automatically instead of pausing in a visible console.

A fresh machine may require one Realm enrollment approval. That approval is the intentional trust boundary: the installer displays the bounded enrollment code and waits for approval, then continues automatically in the same invocation. It must not require a second installer run merely to enable autostart. A machine with an existing `state/client.json` must preserve that identity and token, skip re-enrollment, repair/restart the background task, and proceed directly to readiness verification.

Acceptance is end-to-end rather than file-copy success. The installer only reports `AGENTOS_ONE_CLICK_INSTALL=PASS` after the background Thin Client remains running and `agentos-client verify` succeeds against ONE. The installer may auto-install Python through winget when Python is absent, but Windows Store App Execution Alias stubs are not accepted as a valid interpreter.

## Studio Web production serving authority

As of the 2026-10-02 live Oracle nginx audit, the TLS server for `studio.milkcat.org:443` still serves its default static root from `/home/ubuntu/zeus-writer/website/dist` with `try_files $uri $uri/ /index.html`. This is current observed serving topology, not source-of-truth ownership.

`alston-personal/studio-web` is the canonical platform website source for the extracted shell and root-owned artifacts. The historical `oracle-cutover-milkcat-world-home.yml` did not change nginx root; it built a pinned `studio-web` commit and copied selected generated artifacts into the existing live dist. Therefore earlier language calling that operation a "cutover" referred to content publication, not a serving-root migration.

The legacy Action Relay capability `site.sync_build` is retired from mutation authority and now fails closed rather than fetching/building Zeus Writer. Production publication from `studio-web` must use the governed Studio Web release path. A future nginx-root migration is a separate change and must preserve the route ownership matrix and independent aliases/proxies.

## Hosted Participant enrollment control lane

As of 2026-10-02, the existing Oracle Realm enrollment control workflow is being generalized to carry Participant join requests without creating a second direct-Oracle workflow. Enrollment mutations execute only from `main`; feature-branch pushes may run governance checks but must not create, approve, challenge, or claim live Participants.

For hosted Participant join requests, ONE-issued `claim_secret` is stored only under `/home/ubuntu/agent-data/runtime/participant-enrollment/` and is never committed or printed. The directory/file ACL is limited to the trusted `agentos` service group (`0750` directory, `0640` state file) so the `agentos-node` enrollment ingress can hand the credential to the `ubuntu` GUI Host Runtime without making it world-readable. Repository evidence may contain only non-secret correlation fields such as Participant ID, request ID, user code, negotiated protocol, expiry, and challenge.

The initial live Gemini Web join request proved that the Participant runtime endpoint is reachable and can negotiate protocol 1.0. That request remains an experiment artifact; acceptance does not advance above A0 until the actual Gemini Participant returns the correlated challenge response and ONE records verification.

## Participant runtime enrollment

As of 2026-10-02, Participant Protocol enrollment is implemented as a generic ONE runtime surface rather than documentation-only guidance. The first runtime slice supports hosted or direct Participants without provider-specific Core logic.

Implemented endpoints:

- `POST /v1/participants/join/request`
- `POST /v1/participants/join/status`
- `POST /v1/participants/join/claim`
- `GET /v1/participants/describe?participant_id=...` with Participant bearer credential

ONE negotiates the highest common supported Participant Protocol version from the currently supported set (`1.0`). Enrollment uses a pending request + correlated Participant challenge response + operator approval + claim flow. The challenge response must echo the ONE-issued `request_id`, stable `participant_id`, exact challenge, negotiated protocol, and `ack: ACCEPT`; claim is rejected until ONE records challenge verification. Operator approval is available through `agentos-one participant-approve --code ...`. Claimed enrollment records stable Participant identity separately from `host_runtime_id` and issues a Participant credential to the Host Runtime.

Enrollment/negotiation may advance a Participant to A3 only. Core conformance, capability verification, ONE-routed execution, correlated receipts, and A7 READY remain separate runtime work and must not be inferred from successful enrollment. Missing required v1.0 methods (for example `shutdown`) are preserved explicitly after enrollment.

The first Gemini Web experiment remains A0 until the new runtime surface is deployed and a Host Runtime submits/claims a real enrollment request. This implementation is generic and must be reused by future model, Agent, service, browser, and Executor Participants.

## Capability-first dispatch ingress

As of 2026-10-02, the ControllerService source contract no longer requires normal callers to provide a concrete node identifier. A caller may submit only an action/capability. ONE then considers online nodes advertising that capability and deterministically prefers lower pending queue depth, then fresher heartbeat, then stable node ID. Explicit `node_id` targeting remains available for diagnostics, conformance, break-glass recovery, or work whose semantics truly require a specific physical target.

This is an implemented and source-tested scheduling step, not yet proof that all production workflows use it. A large grandfathered set of GitHub workflows still encodes `runs-on: [self-hosted, Linux, ARM64, oracle]`; `.agentos/governance/main-legacy-direct-oracle-workflows.txt` is therefore a retirement list, not evidence that migration is complete. New direct-Oracle workflow paths are rejected by `Main Runner Window Guard`.

The canonical caller rule is documented in `docs/DISPATCH_INGRESS.md`: GitHub Actions is an ingress/transport and must not become the scheduler. The target runtime topology is caller → ONE dispatch ingress → capability/policy/load selection → Participant/Node/Executor → correlated receipt. Full production acceptance still requires migrating representative legacy workflows and proving that unrelated jobs no longer block one another merely because they historically shared an Oracle runner label.

## Realm Node Map and capability semantics

The Realm Node Map is persistent ONE-side state. A node record may include heartbeat freshness, reported/effective status, capabilities, tool presence, and surface inventory.

Important distinctions:

- a conceptual/logical surface is not automatically an enrolled live node;
- a capability advertised by a node is not authority to execute it;
- transport reachability is not the same as capability availability;
- reaching ControllerService and receiving a node-level capability error proves the Core dispatch route is alive even though the target node is not yet ready for that action.

The authoritative live node count/status comes from the runtime NodeRegistry, not from architecture diagrams or conversation assumptions.

### Hosted node readiness verification

A freshly enrolled client may complete its readiness regression without requiring an operator to paste a local verification command. The bounded command surface is `.agentos/commands/realm-node-readiness-verify.json`; it names only the target node and an idempotency nonce. The hosted carrier validates that fixed schema, enters Oracle through the existing restricted deploy SSH identity, and uses the live `NodeRegistry` plus `RealmFabricStore` as the execution authority.

The carrier may queue only the fixed local `agentos-client verify` operation through the node's already-advertised `shell.exec` capability. It must require the node to be freshly online, require an allowed readable workspace, and wait for the ordinary Realm node receipt. Acceptance requires a zero process return code plus `node_ready:true`, the expected Realm and node identities, and `benchmark_persisted:true`. Node tokens are never read from Oracle, copied into GitHub Actions, or printed as evidence.

This path preserves the authority boundary: GitHub Hosted Actions is transport/orchestration only; Oracle Core owns node registry and task queuing; the enrolled client enforces its local execution policy; the resulting Realm receipt and persisted readiness benchmark are the end-to-end evidence. If the node is offline, the carrier fails closed rather than bypassing the local lifecycle supervisor or inventing a second control path.

## Web static-index capability contract

Crawler/AI-friendly public rendering is a reusable capability, not product-specific page code. The canonical capability is `web.static-index.render`, declared by `capabilities/web_static_index/capability-manifest.json` and discoverable through the Governance Directory via the generic manifest adapter.

A web-producing agent or workflow classifies the route, prepares only the already-authorized public page summary as `agentos.web-static-index/v1`, resolves the existing capability under Reuse Before Build, and invokes `scripts/web_static_index.py` (or the manifest-declared equivalent). The capability owns the baseline semantic HTML, escaping, metadata, robots intent and render receipt. Product applications own their dynamic UI and page data; they should not copy or fork the crawler-facing template into each project.

The output is a static initial representation or deterministic public summary/share route. Public-discoverable acceptance requires a render receipt plus a no-JavaScript HTTP inspection. Private/authenticated content is never made public merely to satisfy indexing.

## Core runtime authority status

Realm Fabric is a single live Core service governed by canonical deployment state in `/home/ubuntu/agent-data/governance/core-deployment.json`. The deployment state tracks desired/observed commit, monotonic generation, lease owner/expiry, and deployment status. A live generation is converged only when desired and observed commits match and status is `converged`.

A deployment claim and an installation are separate operations. Installation cannot silently advance generation. While a deployment lease is active, another generation advance is rejected even for the same owner; the current generation must first be released/expired according to the deployment contract.

## Milkcat Credits boundary

Milkcat Credits are an off-chain integer accounting primitive for platform services. The canonical ledger is append-only: grants, reservations, commits, releases, and refunds are immutable entries, while balance and outstanding reservations are projections.

Pricing and settlement are separate concerns. Stable action identifiers resolve through `.agent/governance/credit_pricing.json`. `CreditBilling` supports three explicit rollout modes:

- `off`: quoteable but not metered;
- `shadow`: record intended usage and quoted cost without mutating the credit ledger;
- `enforce`: reserve before execution and commit or release after the service result.

Usage receipts use schema `milkcat.credit-usage-receipt/v1` and are idempotent by account plus operation ID. A loopback-first server-to-server HTTP boundary is provided by `agent_core/credit_http.py`; it exposes health, quote, usage receipt, and account usage-summary operations and can require a bearer token. It does not establish user identity itself. A service integration must not trust a browser-supplied account identity as authorization; the account/subject must come from the platform's trusted identity/session boundary, except for explicitly anonymous shadow subjects during pre-login observation. Zero-cost actions remain zero-cost in enforce mode. Current Fengshui prices are seed values for observation, not a claim of final commercial pricing.

## Important invariants

### Newer user intent must never be rolled back

Compaction, replay, stale tool results, or executor switching must not replace a newer goal/correction with an older one.

### Evidence is not intent

Tool results and execution evidence can inform decisions, but they do not silently rewrite the user's active goal.

### Capability does not imply authority

The presence of a mutation tool, a mergeable pull request, a node capability, or passing CI does not itself authorize mutation. Protected-branch, Core-deployment, project-source, project-release-lane, and effect-level authority remain separate checks.

### Discover before invent

Reusable/cross-project work should resolve existing responsibility, project identity, node capability, resources, and release lane before creating parallel implementations.

### Models are executors, not the durable source of truth

AgentOS does not assume access to model activations or model-specific internal state. Durable coordination and continuity state must remain external and transportable.

### Receipts are first-class evidence

A successful process start, health endpoint, or workflow status is not enough to claim end-to-end correctness. Architecture-sensitive acceptance should preserve capability/action receipts and, when relevant, real transport-path evidence under `.agentos/evidence/`.

## Memory and Cognitive IR boundary

Historical three-layer memory remains a useful conceptual model: L1 immediate/working state, L2 project/continuation state, and L3 stable cross-project knowledge and learned patterns. Current AgentOS separates canonical project state, continuation/work state, governance state, runtime state, receipts/evidence, and validated knowledge.

Model-independent Cognitive IR remains a research hypothesis until repeatable cross-model continuity benchmarks demonstrate preservation of active goal, decisions/constraints, rejected paths, open questions, and next direction.

## Deprecated / historical paths

Historical or compatibility surfaces must not be described as current canonical architecture by themselves, including pulse files/brain dumps as canonical state, repository name as Project Identity, direct GitHub rediscovery as the normal continuation path, process health alone as deployment proof, installer-side implicit generation advance, and project threads directly owning Core deployment orchestration.

## Documentation ownership rule

`README.md`, `ONBOARDING.md`, `AGENTS.md`, `docs/CURRENT_STATE.md`, and `docs/CORE_CONTROL_ROOM.md` are authoritative entry points. Architecture-sensitive implementation changes must update at least one appropriate canonical document in the same change set.

When implementation contradicts this file, fix the file immediately; do not preserve an obsolete narrative for continuity's sake.

## Low-latency interactive GUI execution

The Windows Thin Client now has an explicit low-latency interactive execution path in addition to single-step desktop actions. Idle long-poll waits are state-change driven: an empty task pull does not rewrite Realm state, and the server watches the fabric file signature while idle rather than reparsing/writing it at a fixed 20 Hz cadence.

- `/v1/tasks` accepts bounded `wait_seconds` long polling so an enrolled Node does not need to sleep for the historical five-second polling interval before seeing work.
- the Thin Client keeps heartbeat cadence independent from task delivery and waits for work through the long-poll channel;
- Windows manifests advertise `desktop.plan.execute`;
- `desktop.plan.execute` runs a bounded, allowlisted desktop plan locally on the Node and returns one structured receipt containing per-step status, elapsed time and the failed step when applicable;
- non-ASCII or long `desktop.keyboard` input uses Unicode clipboard paste so GUI execution does not depend on the user's active IME;
- GitHub Actions remains a deployment/governance/audit mechanism and is not the intended per-click interactive runtime.

This is not yet a claim of fully human-equivalent desktop autonomy. WebSocket/SSE transport, desktop session leasing/mutex, cancellation, durable plan checkpoints, semantic Gemini/Threads skills and vision fallback for canvas/WebGL remain follow-up work. See `docs/LOW_LATENCY_GUI_AGENT.md`.

## Governed VOPC5750 multi-agent acceptance

VOPC5750 is an enrolled Windows Realm Node, but surface discovery alone is not sufficient evidence that a local model/IDE provider is operational through AgentOS. The canonical acceptance path now distinguishes discovery from execution:

- `agent.surface.inspect` proves the live Thin Client can report its current Antigravity, Codex, Claude Code and Gemini surfaces.
- Antigravity is considered wired only when its session bridge is ready and an actual governed `agent.session.discover` task returns a Node receipt.
- Codex, Claude Code and Gemini CLI are accepted only after a minimal governed `shell.exec` smoke reaches VOPC5750 through the Controller/Realm task transport and the expected response marker is observed in the returned receipt.
- Acceptance evidence is sanitized and uploaded as a workflow artifact. The acceptance workflow must not push evidence directly to protected `main`; source changes and promotions remain PR-governed.
- A provider that is merely installed/running but has no working AgentOS invocation path must be reported as `NOT_WIRED` or `FAIL`, never promoted to READY from presence alone.

The reusable probe lives in `scripts/vopc5750_multi_agent_acceptance.py` and is triggered by `.agentos/commands/vopc5750-multi-agent-acceptance.json` or changes to its workflow/probe definition.

## Windows Node self-healing lifecycle

A Windows Node must not be considered durable merely because enrollment succeeded or the Thin Client process started once.

The canonical Windows one-click supervisor now uses two independent Scheduled Tasks:

- `AgentOS Thin Client`: the hidden interactive-user Thin Client that owns Realm heartbeat, task transport and desktop/GUI capabilities.
- `AgentOS Thin Client Watchdog`: a separate one-minute liveness supervisor that does not share process lifetime with the Thin Client.

Every successful Realm heartbeat writes a local non-secret liveness marker at `state/heartbeat.json`. The watchdog evaluates both process/task presence and heartbeat freshness. A missing process/task is restarted on the next watchdog cycle; a still-running client whose heartbeat marker remains stale beyond the bounded threshold is treated as wedged and restarted. Restart attempts are rate-limited and written to the local watchdog log/state so recovery loops remain diagnosable.

This watchdog is an immediate reliability layer, not the final machine lifecycle architecture. The intended next boundary is to separate a machine-level AgentOS Node Daemon (heartbeat, transport, recovery, OTA and health) from the interactive session adapter (desktop, GUI Worker, Antigravity, Codex, Claude and Gemini). Loss of the interactive user session must eventually degrade only interactive capabilities, not make the entire Node disappear from the Realm.

Windows Node Ready therefore requires recovery acceptance in addition to enrollment: process termination and intentional Scheduled Task stop must self-recover without human intervention, fresh heartbeat must return, and a governed task receipt must succeed after recovery.

## Google web media providers

Google Flow and Google Vids are now represented as governed AgentOS media providers rather than assumed API integrations.

- `capability://media.video.generate.google-flow` represents Google Flow as an authenticated web/GUI provider for generative filmmaking.
- `capability://media.video.compose.google-vids` represents Google Vids as an authenticated web/GUI provider for composition, editing and export workflows when those features are available to the active account.
- Both capabilities begin in `declared` lifecycle state. Public reachability alone is not verification.
- The canonical first acceptance is a read-only provider probe through the existing Realm desktop-inspection lane on `vopc5750`. The probe opens only allowlisted Flow and Vids URLs, waits for each page, inspects visible window titles/processes, and records only non-sensitive screenshot metadata after stripping image bytes.
- Probe classification is conservative: `READY`, `AUTH_REQUIRED`, or `UNKNOWN`. It does not generate media, enter credentials, purchase credits, or bypass provider challenges.
- Provider-specific quota discovery and effect execution require later evidence and remain subject to ordinary capability, policy and receipt gates.

The current probe command is carried by `.agentos/commands/realm-desktop-inspect.json`; this reuses an existing governed desktop lane instead of adding another direct Oracle workflow.


## Invoice whole-image comparison candidate

`services/invoice_intake/vision_ocr.py` extends the existing financial-intake reader
with the Gemini Interactions transport previously used only by the benchmark.
`INVOICE_VISION_MODE=off|shadow|primary` defaults to off. Both enabled modes require
`GEMINI_API_KEY` and an explicit `GEMINI_INVOICE_MODEL`; CONFIGURED is not READY.
The existing service deployment reads an optional private
`/home/ubuntu/invoice-intake-service/vision.env` (restrict it to the service owner).
No credentials are committed, copied from another service, or enabled by default.
The provider receives the exact archived image bytes, independently of legacy OCR.
Shadow mode records differences without replacing fields; primary uses validated
vision candidates and always requires human review. Missing credentials, provider
failure and rate limits remain explicit and cannot be presented as vision success.

Buyer, line-item and stamp text/address/contact candidates are preserved in the
existing immutable extraction JSON. The authenticated invoice detail API exposes
`recognition`; no public route or automatic stamp learning is added. Physical
stamp identity remains owned by `document.stamp-recognition`, whose current
contract alone does not prove matching or a populated stamp database.

The local template reader no longer selects the first page-wide tax ID as the
seller of a three-part invoice, and vendor selection excludes the buyer header.
A vendor without sufficient confidence requires review. The legacy stamp fallback
now imports its checksum validator rather than failing when that path executes.

Verification: `tests/test_invoice_vision.py`, existing invoice DB/regression tests,
and the existing public fixture recall gate. Production model quality, credential
availability, frontend consumption of extended fields, and Oracle runtime parity
remain unverified until a pinned rollout and node receipt exist. Run
`python scripts/invoice_vision_benchmark.py --image /path/to/original.jpg --model MODEL --out /private/comparison.json`
to compare the same archived bytes without writing to the production database.
Model responses are provisional evidence, not ground truth; use independent human
labels and additional samples before promoting accuracy claims.

## Read-only ONE runtime inspection trigger

`.agentos/commands/realm-one-runtime-inspect.json` is a bounded read-only trigger for the existing Oracle Realm/ONE inspection carrier. Changing its nonce requests a fresh observation of live identity, processes, listeners, user/system services, the local ONE health surface, Node Map, current shared-checkout HEAD/dirty-count, and a bounded projection of recent runtime-converge Action Relay receipts. Receipt projection excludes raw stdout/stderr, paths, argv, credentials, and free-form error text; only a short error type and allowlisted convergence fields may be emitted.

Inspection evidence is uploaded as a short-retention GitHub Actions artifact. The workflow does not commit or push evidence directly to protected `main`.

On 2026-10-06 this trigger is being used to diagnose the shared Core runtime-convergence failure blocking #200/#470 completion-ownership acceptance for Market Master #1200. A successful inspection is evidence only; it is not a deployment or completion claim.

### 2026-10-06 vopc5750 rollout diagnostic

After the first semantic-preview rollout attempted an inline Thin Client self-update, the expected rollout receipt was not returned. A second attempt using deferred self-update also failed before the deferred task could be scheduled, indicating that vopc5750 was no longer consuming ONE tasks. The recovery sequence therefore treats node liveness as the blocker: refresh the existing ONE runtime inspection, verify NodeRegistry heartbeat freshness and bootstrap/health surfaces, restore the Windows Thin Client transport if stale, and only then resume semantic-preview live acceptance. No semantic-preview PASS is claimed until a new node receipt is observed.

The ONE runtime inspection now also emits only task_id/action/queued_at metadata for vopc5750's pending queue during this recovery, so a stale self-update action can be detected before the Windows Thin Client is restarted. Payloads, credentials, and receipt contents are not exposed by this queue diagnostic.

### Windows visible-console recovery guard

Windows repair must never start an already-registered Thin Client task before validating/replacing its action. A legacy task may still point at a visible cmd.exe launcher even when current source defines a hidden PowerShell supervisor. The one-click repair therefore stops legacy tasks first, reinstalls the runtime, atomically re-registers both Thin Client and watchdog actions with `-WindowStyle Hidden`, verifies those registered actions are hidden PowerShell, and only then starts them. The low-level installer also includes `agentos_node/semantic_preview.py` so a repaired node cannot advertise code paths whose runtime module was omitted.

### Windows stale Thin Client file-lock recovery

Stopping the Scheduled Task alone is insufficient on Windows because a previously spawned Python Thin Client child can outlive the task wrapper and retain locks on installed modules. Repair therefore enumerates and terminates all recognized Thin Client process shapes (module invocation, launcher cmd, and installed thin_client/client_cli paths) before replacing files, then rechecks until no matching process remains or fails closed. This prevents in-place upgrade from partially overwriting a locked runtime.

### Windows repair watchdog race guard

Windows in-place repair must stop and temporarily disable the independent Thin Client watchdog before stopping/killing the Thin Client. Otherwise the watchdog can observe the intentional repair stop as a liveness failure, immediately restart the client, and re-lock installed source files during overwrite. The canonical order is: stop/disable watchdog, stop/disable primary task, terminate surviving Thin Client processes, replace files, re-register validated hidden actions, then start the repaired runtime.

### Non-admin Windows repair task ownership

Windows repair is expected to succeed from a normal user PowerShell. If a legacy scheduled task was created under a more privileged ACL and cannot be overwritten by the current user, repair keeps the legacy task stopped/disabled and creates a new current-user-owned hidden task instead. The fallback primary and watchdog remain hidden PowerShell tasks, and the watchdog is rebound to the effective primary task name. Administrator elevation is not a normal prerequisite for repair.

### Windows non-admin HKCU runtime fallback

If Task Scheduler registration is denied for a normal user, one-click repair does not require elevation and does not retry with another task name. It switches to a per-user runtime: hidden PowerShell autorun entries under HKCU start the Thin Client and a persistent 60-second watchdog loop. Protected legacy scheduled tasks remain stopped/disabled. The fallback verifies both autorun commands contain `-WindowStyle Hidden` before reporting success.

### Windows immutable versioned runtime cutover

Windows Thin Client upgrades no longer overwrite the active runtime in place. The canonical installer writes each source commit into `%LOCALAPPDATA%\AgentOS\versions\<commit>` and keeps enrollment, policy, and runtime state in the shared `%LOCALAPPDATA%\AgentOS\state` directory. Supervisor and per-user fallback launch the immutable version root. This removes file-lock races from an old Thin Client or watchdog that is still exiting or cannot be fully governed by the current user's Task Scheduler ACL. New-version installation must therefore succeed without modifying locked files belonging to the previous version.

### Windows shared-state preservation

Versioned runtime repair treats `state\policy.json` as persistent configuration. If it already exists, the installer preserves it byte-for-byte and never rewrites it during runtime upgrades; the default policy is created only on first install when the file is absent. This prevents an active or protected legacy Thin Client from blocking a versioned upgrade by holding the shared policy file open.

### Windows managed-endpoint supervisor policy

Per-user persistence via HKCU Run plus hidden PowerShell watchdog is not an acceptable fallback on managed endpoints because endpoint security products can classify that pattern as malicious behavior. The canonical installer therefore fails closed with `WINDOWS_SUPERVISOR_APPROVAL_REQUIRED` when Task Scheduler registration is denied. Recovery must use an administrator/IT-approved supervisor installation path; AgentOS must not attempt to bypass endpoint security or recreate persistence through alternate user autorun mechanisms.

### Windows runtime dependency closure

The Windows Thin Client installer must ship every transitive `agentos_node.*` module imported by the installed CLI/runtime. `thin_client_transport.py` imports `agentos_node.onboarding`, so `onboarding.py` is part of the required runtime payload. CI now guards this dependency to prevent readiness failures caused by incomplete file manifests.

### Windows immutable install instance

A Windows repair run must never overwrite files in an already-running version directory, even when reinstalling the same source commit. The installer therefore creates a unique runtime instance under `%LOCALAPPDATA%\AgentOS\versions\<commit>\<install-id>` for every repair execution. Only after readiness passes does it write `current-runtime.txt` to point at the accepted instance. This makes same-commit repair idempotent with respect to Windows file locks.

### Realm task lease / receipt acknowledgement

ONE task delivery is at-least-once rather than destructive-on-pull. Pulling a node task now places a bounded lease on the task instead of deleting it. A successful node receipt acknowledges and removes the task. If the client crashes, execution fails before receipt submission, or the receipt transport fails, the lease expires and the task becomes eligible for redelivery. This closes the pull-to-receipt loss window observed during live vopc5750 semantic-preview and desktop-session canaries.

### Windows single hidden supervisor

The canonical Windows runtime no longer uses a separate one-minute Scheduled Task watchdog. Managed endpoints can visibly flash a console when Task Scheduler creates a new PowerShell process every minute even when `-WindowStyle Hidden` is requested. The primary `AgentOS Thin Client` Scheduled Task is now a single long-running hidden PowerShell supervisor that launches the Python Thin Client, waits for exit, and restarts it after a short delay. Installer repair removes/disables legacy auxiliary task names including `AgentOS Thin Client Watchdog`, `AgentOS Thin Client Watchdog User`, `AgentOS Thin Client User`, and `AgentOS Thin Client Headless Switch`. This eliminates periodic process creation while preserving automatic Thin Client recovery.

### Windows accepted runtime pointer semantics

A successful readiness verification is authoritative. Each accepted immutable install instance writes a unique record under `accepted-runtimes/<install-id>.txt`. The legacy `current-runtime.txt` file is only a compatibility mirror and is updated best-effort after readiness. If another process holds that compatibility file open, the installer reports a warning but must not convert an already-running, readiness-verified runtime into `AGENTOS_ONE_CLICK_INSTALL=FAIL`.

### Thin Client active runtime provenance

Each immutable Windows runtime instance writes `runtime-provenance.json` with its exact source ref, source commit, instance path and installation timestamp. The Thin Client reads the provenance file adjacent to its own loaded package and includes it in every capability manifest/heartbeat. NodeRegistry therefore records the runtime that is actually sending the heartbeat instead of preserving stale provenance from an older instance.

### Semantic preview native-call isolation

Windows semantic preview capture runs inside a short-lived spawned worker process rather than inside the Thin Client transport process. Native GDI stages report progress (`session_info`, `foreground_window`, `capture_bmp`) to the parent. The parent enforces a bounded timeout and terminates a wedged worker, ensuring heartbeat/task receipt transport remains live even if a GDI call hangs. A timeout receipt identifies the last completed stage for diagnosis.

### Semantic preview subprocess isolation

The initial multiprocessing-spawn isolation still failed to produce a receipt in the managed Windows Scheduled Task environment. Semantic preview therefore uses a bounded child interpreter launched as `python -m agentos_node.semantic_preview --worker` with `CREATE_NO_WINDOW`. The parent uses `communicate(timeout=...)`, kills the child on timeout, and reports the last native stage emitted on stderr. This avoids Windows multiprocessing bootstrap/pickle behavior while retaining native-call isolation.

### Semantic preview proven screenshot backend

Live acceptance on vopc5750 showed the established `desktop.screenshot` PowerShell/System.Drawing path returns receipts reliably, while custom GDI and Python-worker isolation paths did not. Semantic preview therefore reads foreground-window identity/bounds first and calls `Graphics.CopyFromScreen` only for that rectangle, scales the result to the configured pixel cap in memory, and returns JPEG evidence. It never captures the full desktop and then crops it; background-window pixels outside the foreground bounds are not requested from the capture backend.

### Thin Client receipt envelope integrity

Capability results may carry their own schema and metadata, but they must never overwrite the canonical `agentos.node-receipt/v0.1` envelope. Thin Client execution now preserves reserved receipt fields including schema, node/task identity, action, timestamps, cognition ids, and final ok status. A capability-level `schema` is projected as `result_schema`; other reserved result keys are projected with a `result_` prefix. This closes the live vopc5750 failure where semantic preview produced `agentos.desktop-semantic-preview/v0.1` and accidentally replaced the receipt schema, causing ONE to reject the receipt with `invalid receipt schema`.
