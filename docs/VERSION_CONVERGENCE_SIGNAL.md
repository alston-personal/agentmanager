# Version Convergence Signal (AgentOS #1682)

This is the **source-only contract**, not yet a running ONE/Supervisor fanout.

After a protected-main push, the existing GitHub Actions transport can produce an
immutable-per-SHA `agentos.version-convergence-event/v1` JSON artifact. It
contains the previous/target SHA, affected source domains, and an idempotent ID.
No authority is granted. GitHub CI cannot attest runtime deployment or a
received signal; at this stage the artifact's status is CREATED_NOT_DELIVERED.

The existing ONE Controller / Runner Window should consume this source event
via its authenticated capability routing only after independent verification
of GitHub main HEAD lineage, trusted repository, event generation and delivery
authorization. Each registered affected Executor, including offline peers at
their next heartbeat, then reports a separately verified
`agentos.version-convergence-ack/v1` receipt.

Acknowledgements must retain:
- `NOTIFIED`: event seen, no source or runtime conclusion;
- `SOURCE_CONVERGED`: independent clean/safely-reconciled worktree confirmation;
- `RUNTIME_DEPLOYED`: component-specific installed-source proof, not Git fetch;
- `TASK_RESUMED`: updated task context; and
- `BLOCKED`: conflict, dirty worktree, offline, or permission blocker.

The pure `validate_ack` function verifies only schema and *claimed*
consistency. ONE must authenticate the executor/node/realm and independently
verify source/runtime evidence before persisting any state upgrade. A newer
global main SHA does NOT require immediate rolling restart of unrelated
components. Never reset dirty worktrees, auto-merge unapproved PRs, or
interpret notifying GPT Web as installing source code.

The actual fanout/ack subscriber, offline reconcile, stale-write barrier, and
durable completion ledger remain **NOT IMPLEMENTED**. Do not claim all
Executors have updated. Acceptance requires one real trusted main merge ->
event -> ONE delivery -> actual online/offline/dirty-source acknowledgements
with exact SHA evidence and without loss of ongoing tasks.

Canonical work: https://github.com/alston-personal/agentmanager/issues/1682


## ONE durable announcement journal: push + pull (design requirement, 2026-11-12)

The user requires ONE to broadcast important state changes to all relevant registered Executors, while also making announcements discoverable by newly joined or previously offline units. This must reuse ONE, Supervisor, existing identity/registry/capability routing, rather than introduce a second controller or canonical IR store.

### Publication and delivery

1. After authoritative protected-main or remote-first Canonical IR commit confirmation, ONE writes one idempotent append-only announcement BEFORE attempting delivery. A failed remote IR push is not a published canonical change.
2. Push sends a compact INVALIDATION HINT with `{schema, notice_sequence_or_epoch, scope_hint, adapter_url?, adapter_version?, adapter_digest?}` to subscribed affected units. The optional adapter locator/version are metadata only, not executable content, an install instruction or an authority grant; receivers always fetch an authenticated ONE manifest before use. It does NOT carry announcement body, IR or decisions; receivers must read ONE. Persistent attempts and per-unit ACK records are independent. Offline or quota-exhausted units remain PENDING, never implicitly acknowledged.
3. On ANY invalidation hint, the receiver pulls the current authenticated, scope-filtered announcement feed from ONE, using its last processed cursor, and reconciles all applicable notices in order. Participants also poll on bootstrap, resume, heartbeat and before state-mutating work, whether or not they got a push. Pull and mandatory freshness checks are authoritative; push only reduces latency.
4. New units not present in the original push roster must still discover current applicable mandatory announcements. Expired cursors require a canonical baseline snapshot, not silent skipping. Informational history may expire; mandatory current requirements remain queryable.
5. Publication and ACK are independent: announced means journal-committed; delivered means observed by a unit; fetched/validated means remote version verified; applied means confirmed effective before next work. Source-convergence, deployed-runtime and resumed-task states in this PR remain distinct.

### Minimum record and permission contract

A full ANNOUNCEMENT stored in ONE contains immutable event_id, increasing cursor/sequence, timestamp, scope (global, realm, project, capability), kind (source, canonical-ir, governance, capability, deprecation, incident), severity, affected capability/schema bounds, summary, authoritative remote ref and SHA or IR generation, predecessor, required action (inform, refresh-before-mutation, block-until-updated), supersession/expiry and evidence links. Redact secrets and private IR contents. Global discoverability never grants cross-realm private data access or execution rights.

A PUSH is only an untrusted wake-up / invalidation hint. The hint may include an opaque monotonic epoch, a non-sensitive scope and an optional ONE adapter locator (URL plus version/digest hints), but is neither a source of truth nor an instruction. The recipient must independently resolve the current signed/trusted adapter manifest through ONE, verify version/compatibility/content digest and obtain installation authority before changing code. Do not attach the announcement body, authority decision, target source SHA, private project identity, or canonical IR to it. If hints arrive duplicated/out of order or are lost, receivers still query ONE for the newest state; never set a local cursor directly from an unverified hint.

ONE must authenticate the actual receiver identity and independently attest source/IR/runtime versions. Self-asserted ACK is insufficient. Deliver at least once, deduplicate by event ID, retain pending obligations through restart. Do not assume network exactly-once delivery. Mutable tasks fail closed when mandatory changes cannot be reconciled; safe read-only diagnosis remains available.

### Design expansion impact sweep (mandatory before rollout)

When feature scope, authority or expected recipient types exceed prior design assumptions, inspect and classify dependent components as UNCHANGED, MIGRATE, REQUIRES_PROOF, or NOT_APPLICABLE with source or runtime evidence: Canonical IR publisher/validation and remote storage; active continuation and resolver; Node/Executor registration/bootstraps; Gemini/Antigravity, Claude, Codex and GPT-Web adapters; Controller dispatch; Supervisor/replay; queued worker freshness; offline onboarding; announcement retention and ACK ledger; permissions/realm isolation; operator web visibility; deployments, rollback, CI and actual receipts. Reuse the existing owner and backlog; no parallel notification authority or automatic scope diversion.

### Required real acceptance

Verify a genuine authoritative remote commit and ONE journal receipt, content-light invalidation hints (optional adapter locator, no event content) to the fanout roster, independent per-Executor pull/read/validated/applied ACKs, duplicated and dropped hints, offline replay by polling, new-unit bootstrap/pull after original broadcast, cursor gap snapshot recovery, stale concurrent IR write rejection and protected realm isolation. Web GPT, Oracle Gemini and another Executor must read the same IR generation and produce correlated receipts. Completion must not be claimed from GitHub Issue comments or green CI alone.

Status: this PR currently creates only a protected-main source event artifact and validates claimed ACK structure. No ONE journal, push/pull transport, Git-remote Canonical IR authority migration, durable ACK delivery or live Executor receipts are yet demonstrated.

## Mandatory announcement subscription at Join (2026-11-12 contract amendment)

ONE announcement updates are an OS-level **mandatory subscription service**, not optional per-Agent messaging. Every governed participant type (Node, Executor, Worker, durable Role/service, and future types) receives a built-in subscription at identity enrollment/Join. Subscription is bound to the authoritative participant and Realm identity, not a user-controlled notification checkbox or executor-local preference.

- Join/claim and subscription establishment must be one **transactional admission invariant**: no successful ACTIVE/JOINED claim without a durable subscription record and initial applicable mandatory-announcement baseline/cursor. A pending/approved but unclaimed join must not be treated as a live subscriber or gain content access.
- Subscription covers global mandatory announcements plus authorized Realm, project and capability scopes as independently determined by ONE. A subscriber cannot unsubscribe from mandatory system notices or spoof wider scope; discretionary informational topics may be filtered only if authorized. Public/global hints carry no private announcement body.
- The subscription is durable across token refresh, reconnect, process restart, provider-quota exhaustion and Executor switching. Revoke or retire when participant identity is explicitly revoked/decommissioned, while preserving audit receipts. Rejoining with the same identity deduplicates and reconciles its cursor instead of creating duplicate subscriptions.
- New participant bootstrap performs an authenticated announcement pull before any mutable work. Initial sync MUST include current applicable mandatory baseline even if published before the unit joined; historical informational notices may obey retention. The initial cursor is not advanced merely because a subscription record was created.
- Existing enrolled participants require an idempotent **migration/backfill** through the current registry; no need to rejoin. Backfill cannot automatically mark old notices read or applied. Unreconciled participants remain pending; mutating tasks fail closed when a mandatory notice is unapplied.
- The push transport sends a minimal invalidation hint (optionally carrying an adapter URL and version/digest locator, never executable contents) to subscribed online identities. All subscribers use pull on hint, heartbeat and task claim/resume, with independently attested ACK. A temporary push outage does not remove subscriptions, and polling is not optional.
- Join responses should expose only harmless capability information (announcement feed/version and sync-required status), never private notice content or other Realm details. All reads and acknowledgements require independently authenticated participant identity and scoped authorization.

### Verified integration targets

Current `main:agent_core/realm_fabric.py` calls `_register_node` from both invite-based `enroll` and approved `claim_join`; `request_join`/`approve_join` alone do not complete enrollment. **Integrate the subscription at successful registration/claim, not exclusively in either UI flow.** Current `main:agent_core/controller_service.py` dispatches tasks to a selected Node, not a multi-recipient subscriber fanout. Other Executor/Worker/Role enrollment paths must be inventoried and connected to the same ONE subscription primitive rather than each implementing an independent notification registry.

### Required tests

Both enrollment flows atomically create one mandatory subscription; denied/expired/pending joins create no active subscription; failed subscription persistence fails admission safely without orphaning an active Node; rejoin/retry is idempotent; revocation disables push/pull while retaining audit; preexisting participants are backfilled; new Executor reads pre-Join mandatory notices; offline push-miss is recovered by pull; cross-Realm scoped notices are never leaked; mutable work cannot start until its applicable mandatory baseline is reconciled.

**Implementation status:** contract only. Join integration, subscriber registry, durable ONE journal, live push, polling endpoint, migration/backfill and ACK receipts are not yet deployed or verified.

## Shared notification transport, pluggable typed handlers (2026-11-12)

The transport/subscription layer is universal and unaware of update-specific execution. All successfully joined Participants are mandatory subscribers. ONE publishes durable announcements, sends minimal invalidation hints with optional adapter locator metadata, exposes authenticated pull, tracks per-recipient cursor/ACK and retries offline recipients. Neither push nor pull directly performs an update.

After a Participant fetches and validates an applicable announcement, a typed dispatcher chooses an allowlisted handler by validated change_kind, schema version, capabilities, realm and authority. No handler can be selected by an untrusted free-form command or path. Unknown kinds remain visible in the journal as UNSUPPORTED/NEEDS_ADAPTER, and any mandatory unsupported update blocks only incompatible mutable operations; no arbitrary code execution or silent skip.

| Change kind | Pluggable handler | Guard |
| --- | --- | --- |
| canonical_ir | Resolve latest ONE-approved remote commit, verify lineage and hydrate | Expected parent generation + no stale mutation |
| policy / announcement | Read and acknowledge applicable policy | Scope and mandatory-effect attestation |
| source_version | Fetch and reconcile source/worktree | No destructive reset or bypass of protected-main review |
| software_ota | Delegate to existing governed installer/deployer | Device authorization, compatibility, rollback and live receipt |
| capability / skill | Update compatible capability manifest/index | Schema compatibility and independently checked authority |
| persona / role | Hydrate governed role state | Realm scope and role-specific permission |

Handler contract: inspect(current_state, announcement), plan(), validate_authority(), apply_or_defer(), verify(), receipt(). Each stage must be idempotent and correlate journal event ID, Participant identity, expected source/IR generation, handler version and evidence. A notification ACK only proves a hint was observed; READ, VALIDATED, APPLIED and BLOCKED are separate substantiated states. Handler failure must not corrupt another handler's state or roll back already published announcement records.

Design-expansion check: when a new Participant or change kind is introduced, join/subscription transport remains unchanged. Register or reuse a typed handler and test compatibility, authorization, rollback, offline replay and real receipt; do not edit every existing Executor subscriber. Preserve distinct OTA installation rights versus read-only policy/IR consumption. Prefer existing AgentOS release and Runtime adapters over a parallel OTA subsystem.

Status: architecture/contract only; no claim that handler registry, journal, subscriptions, fanout or runtime dispatch is deployed.

## ONE-managed adapter distribution and update-before-handle (2026-11-12 amendment)

All event adapters may be published, versioned and discoverable through ONE's trusted adapter catalog. Notifications **may carry an adapter URL** plus advertised adapter version and digest as a bootstrap locator, even though full announcement content is always pulled from ONE. This supersedes the earlier strictly content-free hint requirement; it does not grant permission to run a remote URL.

Receiver sequence: (1) receive hint or poll; (2) authenticate to ONE and read current announcements plus the authoritative adapter manifest; (3) identify required adapter ID, semantic version and allowed platform/ABI/capabilities; (4) compare installed adapter identity, version and digest; (5) if missing or outdated, use the common, pre-installed trusted updater to obtain and cryptographically verify the adapter package from an allowlisted ONE-controlled endpoint; (6) check update/install policy and require a governed approval where installation modifies privileged system components; (7) install atomically with health checks and rollback, or mark BLOCKED_ADAPTER_UPDATE; (8) execute the typed handler under its existing scoped authority; (9) publish separate receipts for adapter updated and event processed.

An installed adapter must **not** load executable code directly from the URL included in a notification. That URL is an untrusted hint; the source of truth is a trusted, signed or hash-pinned manifest fetched independently from ONE. Reject mismatched host, redirects outside allowed origins, unsigned artifacts, version rollback, incompatible schema/CPU/OS, revoked manifests and expired metadata. Avoid arbitrary URLs, dynamic imports from notices, credentials in manifests and elevated installation without independent device/Realm authorization.

Bootstrap invariant: the core participant runtime includes a minimal immutable or separately governed updater and trust anchor. New future event kinds can add adapters without updating the notification subscription implementation; unsupported kinds are retained for retry after compatible adapter acquisition. If the base updater/trust anchor itself is too old, require a separately governed bootstrap upgrade rather than self-updating arbitrary code from untrusted notices.

Version selection is per participant compatibility and release policy, not blindly newest available. ONE can expose approved stable/canary channels, compatible minimum version and emergency revocation. Adapter updates and event processing must be independently retryable, version-fenced and auditable. A notifier hint never confers elevated execution rights.

Acceptance: missing adapter, older adapter, current adapter, incompatible platform, forged adapter URL, digest/signature mismatch, unauthorized privileged installation, failed install with rollback, offline pull after lost hint, adapter update succeeded but event handler failed, and independent per-stage ONE Receipts. This is a contract update in PR #2271, NOT deployed code, catalog, OTA mechanism or proven all-Executor notification.

## Adapter preflight and independent recovery transport (2026-11-12)

Never update an active adapter without a trusted, independently attested preflight: approved source signature and digest, provenance, event-schema compatibility, OS/ABI/platform compatibility, scoped permissions, sandbox or isolated smoke test, independently healthy recovery communications and an attested last-known-good rollback snapshot. Reject missing/failed checks. The validator in `scripts/version_convergence_signal.py` returns only a staged-install REQUEST and explicitly grants no installation or activation rights.

Stage updates in an inactive slot or isolated versioned directory. Run package and dependency tests before switching; after atomic activation, perform an authenticated ONE handshake, actual event adapter test, heartbeat/health check, and a bounded soak window. On failure or timeout roll back to the verified previous slot and emit a correlated failed-update/rollback receipt; never reset an unrelated dirty worktree. Avoid forcing a rollback to a revoked or vulnerable version: a recovery policy may require quarantine and safe-mode-only operation instead.

Normal participant communication and a minimal recovery lane must be separate failure domains: independent executable/service/watchdog, credential/trust isolation, protected update permissions and a known-compatible minimal ONE recovery protocol. This lane supports only identity/authenticated health, fetching a signed recovery manifest, bounded diagnostics and requesting a governed reinstall/rollback. It is not a generic shell or a backdoor that bypasses Realm/Node approval. Keep at least two separately verified recovery slots if the rescue component itself must be upgraded. Its minimal wire contract stays backward compatible; do not literally freeze a vulnerable implementation or TLS trust indefinitely.

Existing reusable evidence: merged #742/#734 Windows watchdog can restart a crashed client but cannot by itself prove a functioning ONE recovery protocol; merged #1054 separates quick control and maintenance execution. Review Linux/macOS and nonresident GPT-Web bootstrap separately; no claim that a universal recovery lane already exists.

Test acceptance must include invalid signature, incompatible update, missing authorization, bad adapter smoke test, failed normal handshake, interrupted install/power loss, watchdog restart loop, failed rollback, lost ONE connectivity, recovery-only restored update, rescue trust-anchor rotation and scoped Realm isolation. Device must recover via independent ONE rescue transport, or fail safe with an explicit operator-needed receipt.

Status: pure code-level preflight gate and tests are source candidates; no runtime installer, independent rescue agent, real device OTA or recovery Receipt is demonstrated.

## Two-channel update interlock and recovery-first ordering (2026-11-12)

The normal communication/update channel and independent safe-mode recovery channel MUST NEVER perform an activation or destructive update concurrently. Both share a durable ONE-governed update lock and generation fence; update operations on either channel block the other until post-update attestation or rollback completes. Tests must cover races across Node restart and two concurrent maintenance requests.

### Normal-channel update

1. Before staging a normal runtime/adapter release, independently prove that safe-mode channel is healthy: signed/authenticated ONE handshake, compatible rescue protocol and trust anchors, verified download of a harmless signed manifest, valid rollback material and independent service/credential isolation.
2. Stage and preflight the normal update in an inactive slot. Never overwrite the healthy rescue image or its independent trust material.
3. Activate only the normal candidate; verify authenticated ONE roundtrip and required service/task probes across a bounded observation window.
4. If the candidate fails, keep the recovery channel untouched; use it to revert to a trusted safe version or quarantine the normal channel when rollback would revive a revoked/vulnerable release. Persist receipts for FAILURE, RECOVERY_USED, ROLLED_BACK or HUMAN_REQUIRED.

### Safe-mode channel update (priority over subsequent normal releases)

1. When the rescue channel needs a security or compatibility update, suspend the normal-channel update queue and claim exclusive rescue-update lease. **Do not begin if the normal channel cannot independently communicate with ONE and fetch verified recovery instructions and packages**, or if its own preflight fails. Declare BLOCKED_RESCUE_UPDATE rather than disabling both paths.
2. Preserve the previously tested rescue image in a protected A/B slot. Stage the new rescue candidate, check signatures, integrity, platform and policy, run isolated handshake/smoke tests and confirm the existing normal channel remains healthy.
3. Atomically switch only the rescue channel, then verify it independently reaches ONE over its own process/protocol/credentials, can fetch a trusted recovery manifest and is capable of issuing a bounded rescue request. Do not mistake a local running process for end-to-end health.
4. On failed verification, use the still-functional normal path to roll back the rescue slot and revalidate the original recovery path. If the normal channel fails unexpectedly during this window, an independently bootable protected last-known-good rescue slot must remain available. If neither can be demonstrated healthy, fail closed and require local/operator recovery.
5. Only after RECOVERY_UPDATED_VERIFIED (including independent live ONE receipt and durable slot health) release the mutual exclusion lease and resume queued normal updates. An update of the rescue lane must not be bundled with a normal-channel update in one activation/transaction.

### Safety qualification

A healthy normal channel is a prerequisite for rescue-channel upgrade, but it is not by itself an adequate sole fallback. Keep protected A/B recovery slots, anti-rollback/security-revocation policies, independently verified trust anchors and durable rollback metadata. Literal permanent immutability of the rescue implementation is unsafe; keep its minimal wire protocol stable while permitting rare, independently approved security upgrades. An update must not remove both independent communication paths in any intermediate state.

### Required fault-injection acceptance

Simultaneous update requests; interrupted normal update; rescue update with unhealthy normal channel; rescue update with malformed artifact; rescue candidate starts but cannot authenticate ONE; rescue update loses power before/after activation; normal channel drops unexpectedly during rescue update; rescue rollback with revoked old image; recovery lease expiry and reboot; receipt loss and idempotent reconcile. Every state must result in verified active channel(s), a persisted pending recovery action or explicit HUMAN_REQUIRED; never silently report success.

Implementation status: this is a stronger integration contract for existing #2271 and AgentOS maintenance/release owners, not a deployed dual-channel updater or successful live recovery receipt.


## Existing Maintenance scheduler lock integration (2026-11-12)

The existing `agentos_node/bootstrap_scheduler.py` maintenance policies for `ACTION_NODE_TRANSACTIONAL_OTA`, `ACTION_REPAIR_TRANSPORT`, and `ACTION_RUNTIME_CONVERGE` now share the `node-communication-update` host process mutex, alongside their preexisting resource locks. Read-only OTA/node inspections and fast status controls do not take the update mutex. The current scheduler sorts lock names before acquiring them, avoiding ordering deadlocks. The queue-TTL test suite covers the shared mutex and read-only noninterference.

This is a **short-lived host-level process lock only**; it releases when the worker crashes. The `DurableChannelUpdateStore` state/transaction log is separate and presently not invoked from the actual executor or installer. Before permitting a real channel switch, the authorized update owner must reconcile its durable Participant state and reject stale/pending/failed updates, then use the independent verified fallback and post-switch ONE Receipt. A one-node bootstrap mutex cannot itself enforce a cross-realm, cross-host or long-running reboot-proof update barrier. No production rescue lane/dual-slot mechanism is claimed.


## Real ONE OTA acceptance hardening and remaining bootstrap gap (2026-11-12)

The existing production entrypoint is `agentos_node/bootstrap_control.py` -> `scripts/run_realm_node_transactional_ota_user.sh` -> `agent_core/runtime_ota_acceptance.py`. That existing Windows transaction stages a candidate, waits for the target source-commit heartbeat, probes `agent.surface.inspect`, and then queues accept/rollback finalization. The acceptance checker now re-reads NodeRegistry **after** the probe receipt; a successful probe followed by spontaneous rollback or source drift is rejected. A regression test covers both still-target and reverted-target conditions.

This is an incremental correctness hardening of the **existing live OTA acceptance path**, not the dual-channel recovery install gate. The current OTA shell downloads PowerShell tools from a revision-pinned GitHub raw URL and executes them; revision-pinned URL alone is not a verified artifact digest/signature or a protected rescue bootstrap. Before shipping recovery-mode updates, require independent signature/digest and trust verification, recovery-channel health proof, protected A/B rescue slots, durable per-Participant update-gate integration and actual ONE receipts. Do not mark recovery as installed merely because a candidate heartbeat and inspect task succeeded.


## Recovery A/B launcher integrated into canonical Windows bootstrap (2026-11-12)

The canonical \`install-agentos.ps1\` installs \`scripts/windows/recovery_slot_runner.py\` once under \`%LOCALAPPDATA%\AgentOS\recovery\`, outside the normal versioned Thin Client release directories. The existing pinned Windows file installer carries both \`recovery_one_probe.py\` and the slot runner. Initial enrollment creates protected \`slot-A/recovery_one_probe.py\` and an atomically written \`slots.json\` with SHA-256, active slot, LKG slot and optional pending-candidate field. Ordinary normal-channel reinstall never rewrites a pre-existing Recovery launcher or verified LKG. Legacy installed single-file probe is used as the initial source when present, preserving its bytes rather than silently promoting the latest normal release.

The Windows Recovery scheduled task executes the standalone launcher; the launcher verifies its slot digest before running Python in isolated interpreter mode. If, and only if, an explicitly pending candidate slot has become invalid before execution and the previously verified LKG remains intact, the launcher atomically selects LKG. A network failure alone does not automatically flip slots. Invalid/missing LKG or corrupted settled active slots fail closed. Regression tests include initial creation, no-overwrite on normal reinstall, integrity corruption, pending B fallback, network failure and invalid slot metadata.

**Safety boundary:** this is an integrity-checked A/B *launcher and fail-closed recovery bootstrap*, not yet an approved Recovery channel updater or autonomous rescue. A signed package provenance/authority verifier, independently attested working Normal path, trusted B-slot staging, durable activation interlock, post-switch ONE receipt, protected failback policy and real Windows device outage drill remain necessary before any B promotion can be enabled. The existing independent probe still shares Node credentials, Python interpreter, OS, scheduler and ONE dependency; the fallback only protects against one of the possible failure classes. No live device receipt has been obtained.


## Recovery candidate non-activating staging contract (2026-11-12)

The new \`scripts/windows/recovery_upgrade_stage.py\` is intentionally **not** wired to the normal installer, a command endpoint, or an unattended OTA task. It offers a host-authorized **inactive-slot copy only**. Its caller must supply independently trusted callbacks for (1) verifying an authenticated, scoped, nonexpired/replay-protected ONE authorization/signature, (2) confirming that the normal channel can independently contact ONE and obtain trusted recovery material **now**, and (3) running an isolated candidate test. These verifiers remain interfaces pending actual ONE runtime integration; passing dummy/locally forged callbacks is NOT acceptable for production authority. JSON fields alone do not authorize the update.

It checks known-good Recovery integrity, refuses an existing active/pending upgrade or mismatched SHA-256, and reserves the stage operation with an exclusive persistent marker to reject concurrent or interrupted jobs. The inactive candidate is copied and rehashed; Active/LKG and the Recovery launcher are not switched, so loss of power during staging cannot activate unverified code. An abandoned reservation requires an independent, governed reconciliation before retrying. No automatically expiring update lock grants activation.

**Still required:** source-signature verification and real ONE authority callback; fresh normal-channel recovery proof; durable host-side update coordinator that binds stage to the same per-Participant interlock as Normal OTA; protected A/B activation and rollback with actual ONE handshake, receipt and bounded observations; cross-process tamper protection; Windows offline/failure drill. This change is not the production Recovery updater or a live rescue Receipt.


## Recovery pending activation / ONE acceptance primitive (2026-11-12)

\`scripts/windows/recovery_upgrade_promotion.py\` adds **host-only**, unexposed transition primitives. \`activate_pending\` independently checks staged-candidate reservation and operation id, byte digest of the inactive candidate, integrity of the previous LKG and three caller-provided host authority verifiers: independently authorized activation, fresh normal-channel rescue reachability and durable Recovery lane \`ACTIVATE\` gate. It then atomically sets \`active=candidate\`, \`pending=candidate\` **without changing LKG**.

\`accept_pending\` requires a newly attested candidate-to-ONE check, continued normal-channel rescue availability, exact ONE receipt verification and a durable \`VERIFY\` gate before promoting the candidate to LKG. \`revert_pending\` checks protected LKG integrity and the separately authorized/verified rollback gate before reverting to LKG. All transitions preserve the persistent staging reservation for later governed reconciliation; no unattended action or normal installer may use these methods. Local stage JSON cannot assert authority by flipping \`activation_authorized\` or \`one_receipt_attested\`.

**Critical boundary:** The callback interfaces are mockable for tests, and do not supply actual cryptographic verifier, ONE receipts, durable interlock integration, filesystem ACL/anti-tamper, or multi-process exclusion on their own. The module has **no CLI and is not installed** into the Recovery scheduled task or normal Node OTA dispatcher. Promotion is NOT enabled on production Nodes; it cannot be approved merely from unit-test or caller-provided booleans. The next production integration must independently implement/verify these authorities, protect state with OS permissions and a signed immutable source, reconcile interrupted transitions and prove full A/B rollback on a dedicated Windows test Node. A status field indicating success is not sufficient to prove a healthy independent communications lane.


## Recovery/ONE split-store crash reconciliation (2026-11-12)

\`scripts/windows/recovery_update_reconcile.py\` now classifies **read-only** inconsistencies between the independent Windows \`recovery/slots.json\` state and the ONE host's authoritative durable update gate. Since the stores are on different machines, updates to them are not one atomic transaction. Interrupted stage/activation/acceptance/rollback transitions MUST NOT automatically clear the durable ONE lock, promote a candidate, or authorize a new update. Reconciliation returns explicit classifications such as \`AWAITING_ONE_RECEIPT\`, \`AWAITING_AUTHORIZED_ROLLBACK\`, \`GOVERNED_RECONCILIATION_REQUIRED\`, and \`HUMAN_REQUIRED_LKG_CORRUPT\`.

The diagnostic always sets \`new_update_permitted=false\`, \`activation_authorized=false\`, \`rollback_authorized=false\` and \`one_receipt_attested=false\` even for a superficially clean IDLE/slot state. A \`READY\` classification means **eligible for separate authoritative review**, not permission. The updater cannot rely on user JSON, a cached health flag or a locally fabricated receipt for privileged actions. The ONE host must fetch its own database state, independently authenticate and freshly recheck real Normal/Recovery handshake evidence, and reconcile the same operation id and generation against the actual Windows node before releasing its update lock.

Added restart-fault tests include ONE state changed before the A/B slot, A/B slot changed before ONE verification, stage reservation surviving after IDLE, corrupt LKG, tampered pending candidate, and stale operation id. This is a diagnostic layer, NOT a distributed transaction manager, trustworthy attestation source or live deployment. Real ONE runtime binding, anti-tamper controls and Windows device Receipt remain incomplete.


## Canonical IR change handling for #1682 Recovery (2026-11-12)

Recovery progress MUST be reflected through the existing ONE-authoritative \`agentos.ir/v1\` generation, not from a divergent Markdown status, GitHub Issue, executor chat, or a new shadow store. The versioned, source-controlled change proposal is \`docs/recovery-1682-canonical-ir-proposal.json\`; it explicitly records PR #2271 as **Draft, source-and-CI only, not merged, not deployed, and without a real Recovery receipt**. It preserves goal, constraints as decisions, pending integration work, next action and verification evidence.

\`scripts/publish_recovery_1682_ir.py\` prepares existing \`agent_core.canonical_ir_handoff.advance_canonical_ir\` parameters, taking *actual observed* \`expected_index_id\` and \`expected_ir_id\` and separately selected \`new_index_id\` and \`new_ir_id\`. Its default mode is \`PREPARED_NOT_PUBLISHED\`. A governed ONE host operator may use \`--apply\` only after reading current canonical generation from ONE; the existing CAS publisher rejects a stale/missing generation, and the resulting \`publish_receipt\`, new \`execution-head\` and Canonical IR must be read back from the authoritative state store. Never generate a current generation id from chat text or GitHub to bypass CAS.

No Oracle ONE Canonical IR read/write connection or observed current \`index_id/ir_id\` was available in this GitHub-only authoring session. **The IR has NOT been published to ONE**, so the proposal and GitHub Issue comment are durable *source-side handoff artifacts*, not proof that future executors have received a new canonical IR. After a successful publish, verify the active continuation selector is reconciled to the new generation; otherwise a fresh executor must fail closed with \`ONE_IR_HEAD_UNRESOLVED\`, as specified in \`docs/issue-152-ir-bootstrap-note.md\`.

Source/IR governance acceptance is therefore split:
- Source: same PR, updated proposal, CI and governance reviews.
- Canonical IR: observed current generation, CAS publish receipt, exact readback, active selector match.
- Runtime: protected main merge/deployment and independent Windows/ONE Recovery operation and receipt.
No single source-only success may set all three to COMPLETE.


## ONE-observed IR generation and selector CAS (2026-11-12 continuation)

The existing \`scripts/publish_recovery_1682_ir.py\` now offers \`--from-current\` on the authorized ONE host: it invokes the existing \`resolve_continuation("agentos-core")\`, requires matching \`agentos.execution-head/v1\` and \`agentos.ir/v1\` index generations and a real parent IR ID, then produces a new child index/IR generation identifier. It does **not** invent the *current* authoritative parent. \`--from-current\` cannot be mixed with manually supplied generations. Default behavior is read-only \`PREPARED_NOT_PUBLISHED\`; \`--apply\` uses the unchanged canonical CAS publisher and requires post-publish readback matching exact child and parent generation.

An explicitly requested \`--sync-active-selector\` (requires \`--apply\`) only touches a selector already owned by \`agentos-core\` and pointing to the exact old parent. The existing \`agent_core.active_continuation.activate_continuation\` has an optional \`expected_previous\` CAS check **inside its existing file lock**; another Executor switching active projects/generations in between read and write now triggers \`active_continuation_selector_cas_conflict\` rather than getting overwritten. The normal selector API remains backward compatible when the new optional guard is omitted. After a guarded write, the script reads back the exact selector. A missing selector or another active project is never silently taken over.

No Oracle ONE execution has been performed from this GitHub-only session; real Canonical IR still requires an authorized ONE host, \`--apply\`, an observed CAS publish Receipt and selector readback. The generated *child* identifiers and source-only CI are not proof of a published IR. Manual recovery remains necessary if a crash happens after canonical IR CAS succeeds but before selector reconciliation; do not rerun \`--from-current --apply\` blindly to force a second generation.


## Resume an interrupted Canonical IR selector sync without republishing (2026-11-12)

The #1682 Canonical IR CAS publisher and Active Continuation selector CAS cannot be one atomic operation. If the ONE canonical IR generation was successfully committed but the process crashed before updating the active selector, **do not invoke \`--from-current --apply\` again**, as that creates another IR generation. Use the same existing \`scripts/publish_recovery_1682_ir.py --resume-selector-only\` on the authorized ONE host. This mode does **not** publish a new IR; it resolves the currently committed \`agentos-core\` execution-head/IR pair and requires exact Schema, matching index generation, a parent IR id, \`execution_head.source=recovery_1682_handoff_proposal\`, \`ir_published=true\`, still-unaccepted Runtime/Recovery flags, and matching #1682 goal. It refuses missing pointers, other active projects, unrelated old generations, and concurrently modified pointers.

If the selector is already on the published generation, it returns \`ALREADY_CURRENT\` without any write. If it still points to that exact published generation's parent IR, the script uses \`activate_continuation(expected_previous=...)\` to CAS the pointer under the existing selector lock, then verifies exact readback (\`SELECTOR_RESUMED\`). A stale or unverifiable state **fails closed** for authorized ONE reconciliation; no new IR, shadow store, authority bypass or forced takeover is permitted. This remains source-tested only until a real Oracle ONE CAS/selector readback receipt exists.
