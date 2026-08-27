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
3. IN PROGRESS end-to-end: browser edge queue and HTTP transport client exist; persistent AgentOS store and gateway service contract exist. The public `/layout-lab/api/...` proxy/service wiring is not yet proven live, so failed network submission intentionally leaves experience queued locally.
4. NEXT: wire and verify the capability gateway on the Oracle host, then prove a real browser completion produces a server-side stored receipt and that a fresh browser receives canonical bootstrap state.
5. AFTER CLOSED LOOP: stabilize Spatial IR topology/rooms/openings, consolidate historical source/version drift into canonical v0.7 source identity, and add regression fixtures before learned-policy promotion is allowed to influence production broadly.

## Transport contract

Browser transport uses the same-origin Layout Lab API namespace:

- `POST ./api/capability/experience` with 1..20 abstract experiences.
- `GET ./api/capability/<capability_id>/canonical` for bootstrap.

Transport is at-least-once from the browser edge queue. Server-side ingestion is idempotent by `experience_id`: replay of the same payload is accepted as duplicate; reuse of the same ID with a different payload is rejected.

The browser does not write canonical state. Canonical state remains a governed AgentOS output.

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
