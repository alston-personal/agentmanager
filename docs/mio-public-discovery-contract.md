### Mio public discovery contract (candidate for #1825)

The stand-alone `scripts/persona_public_discovery_contract.py` supports an offline,
bounded **read-only projection** of public Threads post candidates, not discovery itself.
It requires an independently verified authorized public-feed/public-post adapter
receipt, bound to the Mio account; the existing `post.read` owned-post adapter
receipt is explicitly **insufficient**. It rejects private, stale, self-authored,
unbounded, duplicate, or missing-provenance items. The projection sets
`write_allowed=false`, each candidate remains `UNDECIDED`, and no publish or
external reply authority is granted. It does not read credentials or DM content,
schedule a PDCA action, or write persona state. Production adapter ownership,
account isolation, a node-authoritative actual public read, IR-based evaluation,
and exact-parent real reply receipts all remain **unverified / not implemented**
by this stage. Growth Proof is not claimed. Tests run without platform writes.

### Existing public search probe — reuse, not a live adapter

Existing `scripts/probe_threads_public_search.py` and workflow
`.github/workflows/oracle-probe-threads-public-search.yml` already expose a
no-login, no-write, no-antibot-bypass public-search **URL probe**, originally
for vendor discovery. Its output schema `milkcat.threads-public-search-probe/v2`
provides search terms, filters, discovered post URLs, and flags
`post_text_emitted=false`, `db_written=false`. The probe can inform candidate
URL acquisition where platform use is permitted, but cannot establish verified
content, root/parent IDs, public visibility, account-bound access or author
context. Its evidence is not a `public.feed.read` or `public.post.read`
receipt. Do **not** feed probe URL rows directly to the projection or create
`reply.send` candidates from them.

Integration path: shared social capability owner validates a safe public
post-content read for each candidate URL (or explicitly returns BLOCKED),
binds reader identity `mio.milkcat`, emits sanitized per-source
`receipt_id` with `operation=public.post.read`, and only then hands bounded
post objects to this projection. No GUI session reuse from
`oursong_alstonhuang`. Platform-read failure must not be hidden by fabricated
success receipts. Any terms/seeds should derive from IR and actual observed
interests, not copy the vendor search probe's vendor-service query list.

### Official Threads API discovery path (verified public documentation 2026-10-12)

Meta's official Threads API documents `GET https://graph.threads.net/keyword_search`,
request parameters `q`, `search_type=TOP|RECENT` and requested `fields`.
It uses the `threads_keyword_search` OAuth permission. Source:
https://www.postman.com/meta/threads/request/m9j4i2x/search-for-threads-posts
and https://www.postman.com/meta/threads/documentation/dht3nzz/threads-api .

This is the **preferred authorized public-read integration candidate** ahead of
the existing HTML URL probe. Production access is UNVERIFIED: the current Mio
social binding/credential's actual granted scopes, application review status,
token account identity, keyword-search reachability, result field availability,
and governance owner must be checked **from the Oracle node**, with only
sanitized receipt metadata returned (never token values). A successful owned
`post.read` call is not evidence that `threads_keyword_search` is available.

The initial executable acceptance should be strictly read-only:
1. Inspect an authenticated, existing Mio social binding (without exporting secrets).
2. Resolve official public keyword search scope; if absent report
   `AUTH_SCOPE_REQUIRED` instead of using another account.
3. On an approved, bounded 1-query probe, verify the resulting post object
   provenance, content, author (if available), post id/root id, public visibility
   and timestamp **individually**. A field not returned is unknown, never
   invented. If the API cannot attest `visibility=public` or root identity,
   hold as `UNVERIFIED` rather than marking the contract PASS.
4. Emit a node-authoritative receipt with account binding, API operation,
   sanitized result counts, source receipt id, scopes present/missing and
   failure classification; do not publish, reply or mutate persona IR.
5. Only wire an authorized adapter to the existing no-write projection
   after the runtime reading contract is demonstrably compatible.

App review and per-account availability may restrict search independently of
the presence of a public endpoint; do not treat authorization errors or empty
results as account acceptance. This discovery is documentation only and
**does not** establish a successful live API call.

### Minimal executable keyword permission probe (still not deployed)

`scripts/persona_threads_keyword_probe.py` can issue **one bounded read-only**
`GET /keyword_search` via the official Threads endpoint when and only when the
approved existing binding owner supplies `AGENTOS_THREADS_BOUND_ACCOUNT`,
`AGENTOS_THREADS_GRANTED_SCOPES`, and
`AGENTOS_THREADS_ACCESS_TOKEN` through a protected runtime environment.
It is *not* wired to, or allowed to search, local browser credentials. It sends
a bearer token as an HTTP header and does not emit it, source content, query
results, or raw error bodies in its sanitized receipt. It never posts, replies,
or changes IR. Missing scope or mismatched binding fails closed, as do absent
credentials. Even a successful response is `UNVERIFIED`, not the stronger
`public.post.read` acceptance; a separate item-level content/provenance/root
verification stage is still required.

This script is a **diagnostic integration entry**, not an already installed
social-runtime capability. There is no assertion that the Oracle binding owner
currently exports those variables or that official app review is granted.
An operator should execute it only under the approved existing binding after
confirming source ownership, preferably through existing governed node
dispatch. No user needs to paste token values into chat or GitHub.

### Social exploration triage (candidate, not deployed)

`scripts/persona_social_discovery_triage.py` ranks a bounded set of verified,
read-only public discovery candidates, using observed topic overlap
(animals, walks, outfits, daily life), author familiarity and previous
contact/blocklist history. Previously contacted posts and blocked accounts
are omitted; newly discovered people are considered before already-seen
authors. A lack of interesting candidates is a **successful non-action**, not
a quota failure. This is not limited to cats: multiple interest lanes make
Mio's discovery less repetitive, and should eventually be sourced from
validated persona IR rather than this initial offline fixture vocabulary.

All triage output has `write_allowed=false` and `reply_allowed=false`.
A later independent context review must prove the conversation welcomes a
reply, check time/repetition/relationship history, enforce the persona's
energy and decision autonomy, verify exact root/parent and write authority,
and obtain a real platform receipt. There is no requirement to follow or
reply to every candidate, no automatic DM, and no guaranteed growth.

This component is not yet integrated with the actual Oracle social runtime,
and no real third-party Threads post or author has been read by this change.

### IR-grounded exploration topic policy

The read-only triage now optionally accepts a current persona IR and derives candidate matching lanes from `current_self.interests_with_evidence` when at least one source basis is present. Only bounded known-topic synonyms are expanded. No source evidence, malformed IR or no evidenced interests yields a BLOCKED decision; this prevents nearby trends or a single stranger's post from silently becoming Mio's own enduring interest. The static topic vocabulary remains a legacy fallback **only when the caller does not supply an IR**, so runtime integration must supply the authoritative IR to enforce grounded interests. This is currently a tested contract, not a deployed social feed reader.

### Implementation owner rediscovered on core/integration (2026-10-12)

An existing **actual provider operation** is present on the
`core/integration` branch, at `agentos_node/social/threads.py`:
`ThreadsProvider.read(request)` accepts `operation="keyword.search"`,
uses the existing `CredentialVault` account binding and calls
`transport.paged("keyword_search", ..., max_pages=1)` with a
10-item limit and the official `id,text,timestamp,username,permalink`
projection. `agentos_node/social/contracts.py` already validates
`query`, `search_type` and `search_mode`.
`scripts/diagnose_mio_threads_search_scope_user.py` also exists on
that branch and probes `/debug_token`, returning only grant status.

**This is the preferred owner and integration path.** The stand-alone
`persona_threads_keyword_probe.py` in this PR is only an offline-tested
diagnostic fallback, **not** a competing production provider and should not
be deployed in parallel with that runtime. Before adding any new runtime
operation, determine which immutable social-runtime version is installed
on Oracle; do not promote an old integration branch wholesale to main.

Crucially, `threads.py` already records that a historical Meta
`/debug_token` check found the then-current token to be missing
`threads_keyword_search`. Treat that as a historical observation,
not proof of current grant status. Current node-authoritative acceptance
must prove (1) exact Mio account binding, (2) scope status from the
existing diagnostic or credential owner, (3) whether the installed runtime
supports `keyword.search`, (4) one safe read-only search and its
source receipt if authorized, and (5) no cross-account session reuse.
If scope is absent, classify AUTH_SCOPE_REQUIRED and route to the
approved reauthorization/app-review workflow, rather than retrying
scrapers or constructing fake evidence. Do not alter Mio's current
posting/reply/heartbeat paths.

### Offline-tested read bridge to native Social Runtime

`scripts/persona_keyword_social_runtime_bridge.py` is an injectable,
fail-closed read-only bridge targeting the existing operation
`keyword.search` (rather than creating a second OAuth transport). It
requires explicit `mio.milkcat`/persona binding, provider account ID,
bounded query, and an exact identity-matching Social Runtime receipt.
Missing scope, rejected reads, malformed/overlarge results and own-only
search are separately classified. No raw post content or token is
emitted. Tests use an injected offline read function rather than live
Oracle or social-platform calls. Importantly, this is **not** installed
in the live persona worker and no node-authoritative receipt has been
seen. Integration needs approval of the existing runtime owner and a
safe, independently observed Oracle readback. No write authority is
implied by keyword search.
