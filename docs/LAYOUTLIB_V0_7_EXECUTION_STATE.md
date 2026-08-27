# LayoutLib v0.7 Execution State

Status: active implementation checkpoint
Date: 2026-08-27

## Goal

Finish LayoutLib as the first real AgentOS capability-evolution closed loop, without mixing in unrelated character, trading, or general world-model work.

## Current product flow

`layout image -> analyze -> Spatial IR -> edit/correct -> 3D preview -> finish`

The remaining learning closure is:

`finish/accept -> correction outcome -> CapabilityExperience -> governed transport -> consolidate -> canonical capability state -> fresh-node bootstrap`

## Current architecture

- LayoutLib core remains a pure execution library.
- `capabilities/layoutlib/adapter.py` translates abstract profile features, policies, and correction metrics into AgentOS capability experience.
- `agentos_node/capability_runtime.py` provides generic experience observation, candidate consolidation, evaluation, and explicit governed promotion.
- `agentos_node/capability_store.py` provides persistent idempotent capability-owned experience and canonical-state storage.
- `agentos_node/capability_http.py` provides a minimal same-purpose HTTP gateway contract for experience ingestion and canonical-state reads.
- `web_assets/layoutlab-capability-bridge-v0.7.js` records completion/correction outcomes, keeps an offline edge queue, opportunistically submits queued experience, and can bootstrap a canonical profile policy.
- Spatial IR is the canonical model. 3D preview and exported mesh formats are derived representations.
- The current 3D browser preview is rendered from Spatial IR; it is not a stored 3D asset format.

## Learning signal

Use correction cost rather than Analyze as the primary reward signal.

Reference metrics currently include:

- walls added;
- walls deleted;
- erase length;
- re-analysis count;
- manual parameter changes;
- accepted/completed outcome.

No raw image is required in the capability experience payload. The persistent store rejects obvious raw image/binary telemetry fields at the shared boundary.

## Progress

1. DONE in unit-level architecture proof: A/B/C experiences can consolidate to a canonical profile policy and a fresh Node D can consume that policy without local history.
2. DONE in the real browser UI: explicit `finishModel` completion boundary and correction metrics are emitted from the Layout Lab session.
3. DONE locally on the Oracle capability node: the persistent capability gateway is running on `127.0.0.1:8767`; health returns HTTP 200 and abstract experience ingestion returns HTTP 202 with an idempotent receipt. Current persistence root is `/home/agentos-node/.local/share/agentos/capabilities`.
4. BLOCKED only at the public transport boundary: current nginx has no `/layout-lab/api/` proxy, so those URLs fall through to the Studio SPA and return HTML with HTTP 200. The nginx configuration is root-owned and the runner has no non-interactive sudo. A reviewed route snippet is staged at `ops/nginx/layoutlib-capability-gateway.conf` but is not installed.
5. NEXT after that route is installed/reloaded: prove a real public browser completion creates a server-side stored receipt; then publish a governed canonical state and verify a fresh browser bootstraps it before any local history.
6. AFTER CLOSED LOOP: stabilize Spatial IR topology/rooms/openings, consolidate historical source/version drift into canonical v0.7 source identity, and add regression fixtures before learned-policy promotion is allowed to influence production broadly.

## Verified host facts

The Oracle host already had a separate legacy LayoutLib web demo at `127.0.0.1:8766`; it exposes `/api/health` and `/api/parse`. It is not the new AgentOS capability gateway and must not be confused with it.

The new capability gateway runs independently at `127.0.0.1:8767` so the old parser demo remains untouched.

The capability gateway user-systemd unit is staged, but the GitHub runner session currently has no usable user D-Bus. The current verified process therefore uses the controlled `nohup` fallback with `RUNNER_TRACKING_ID` removed so GitHub cleanup does not kill the intentional daemon. The unit remains the desired reboot-persistent mechanism once the user service bus is available.

## Transport contract

Browser transport uses the same-origin Layout Lab API namespace:

- `POST ./api/capability/experience` with 1..20 abstract experiences.
- `GET ./api/capability/<capability_id>/canonical` for bootstrap.

Transport is at-least-once from the browser edge queue. Server-side ingestion is idempotent by `experience_id`: replay of the same payload is accepted as duplicate; reuse of the same ID with a different payload is rejected.

The browser does not write canonical state. Canonical state remains a governed AgentOS output.

Required nginx mapping is conceptually:

`/layout-lab/api/... -> http://127.0.0.1:8767/...`

The exact staged snippet is source-controlled in `ops/nginx/layoutlib-capability-gateway.conf`.

## Parked branches

Do not expand these until the LayoutLib closed loop is measured:

- Character IR and IP Genome integration;
- Blender/Unity native adapters;
- glTF/GLB/USD/IFC expansion beyond the current exporter proof;
- trading strategy capability;
- autonomous graph/plasticity engine;
- universal Semantic IR core extraction.

These are valid future applications, but are not on the active LayoutLib execution path.

## Success criterion

The first capability-evolution experiment succeeds when:

- Nodes A/B/C independently produce abstract LayoutLib experience;
- experience converges to the LayoutLib semantic owner;
- a candidate policy is evaluated and explicitly promoted;
- Node D starts with no local history;
- Node D receives the canonical policy before its first local learning event;
- Node D's measured correction cost is lower than an equivalent no-shared-learning baseline;
- provenance shows why the canonical policy exists and can be rolled back.
