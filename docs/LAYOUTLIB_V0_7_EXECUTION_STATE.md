# LayoutLib v0.7 Execution State

Status: RELEASE COMPLETE — production closed loop deployed and accepted
Date: 2026-08-27

## Goal

Finish LayoutLib v0.7 as the first deployed AgentOS capability-evolution closed loop, without mixing in unrelated character, trading, or general world-model work.

## Released product flow

`layout image -> analyze -> Spatial IR -> edit/correct -> 3D preview -> finish`

Learning closure:

`finish/accept -> correction outcome -> CapabilityExperience -> governed transport -> persisted capability experience -> consolidate/evaluate -> governed canonical capability state -> fresh-node bootstrap`

## Released architecture

- LayoutLib core remains a pure execution library.
- `capabilities/layoutlib/adapter.py` translates abstract profile features, policies, and correction metrics into AgentOS capability experience.
- `agentos_node/capability_runtime.py` provides generic experience observation, candidate consolidation, evaluation, seeded canonical state, and explicit governed promotion. Promotion now requires a successful evaluator result as well as an authority receipt.
- `agentos_node/capability_store.py` provides persistent idempotent capability-owned experience and canonical-state storage.
- `agentos_node/capability_http.py` provides the HTTP gateway contract for experience ingestion and canonical-state reads.
- `agentos_node/capability_consolidator.py` loads persisted experience, produces/stores candidate state, and can explicitly promote/store canonical state with governance provenance.
- `web_assets/layoutlab-capability-bridge-v0.7.js` records completion/correction outcomes, keeps an offline edge queue, opportunistically submits queued experience, and bootstraps a canonical profile policy.
- Spatial IR remains the canonical spatial model. 3D preview and exported mesh formats are derived representations.

## Learning signal

Correction cost, not Analyze, is the primary learning reward boundary.

Reference metrics include walls added/deleted, erase length, re-analysis count, manual parameter changes, and accepted/completed outcome. No raw image is required in capability experience. The persistent store rejects obvious raw image/binary telemetry fields at the shared boundary.

## Verification and deployment result

1. Focused v0.7 test suite passed: 15 tests covering runtime governance, persistence/idempotency, raw-image rejection, persisted consolidation, LayoutLib adapter/convergence, and browser bridge asset contract.
2. Browser completion boundary and correction metrics are present in the production v0.7 bridge.
3. Capability Gateway is installed as a reboot-persistent system service bound to `127.0.0.1:8767`, with capability persistence owned by `agentos-node`.
4. nginx now routes `/layout-lab/api/...` to the capability gateway; nginx configuration was syntax-checked before reload with backup/rollback handling.
5. Public experience ingestion was exercised through the real `https://studio.milkcat.org/layout-lab/api/...` route and returned accepted receipts.
6. Three independent proof-node experiences were persisted, consolidated, evaluated, explicitly promoted with an authority receipt, then retrieved through the public canonical-state endpoint.
7. A fresh-node bootstrap proof read the capability-owned canonical profile before any local history. The automated proof verifies convergence/bootstrap mechanics; it does not claim an empirical human correction-cost improvement yet.
8. Production static acceptance passed for the Layout Lab UI, v0.7 bridge, finish boundary, pending queue, capability experience schema, correction-cost signal, canonical-policy bootstrap hook, and existing v0.6 browser library contract.

Release workflow: `Oracle Deploy Tested LayoutLib v0.7 Closed Loop`, run `33033667929`, commit `64dfb587bf073d5c03f539188a3b0cfd83f0494e`.

## Production boundaries

The older LayoutLib parser demo at `127.0.0.1:8766` remains separate and untouched. The AgentOS capability gateway owns `127.0.0.1:8767`.

Browser transport uses the same-origin namespace:

- `POST ./api/capability/experience` with 1..20 abstract experiences.
- `GET ./api/capability/<capability_id>/canonical` for bootstrap.

Transport is at-least-once from the browser edge queue. Server ingestion is idempotent by `experience_id`: replay of the same payload is accepted as duplicate; reuse of the same ID with a different payload is rejected. The browser cannot write canonical state.

## Demo/library ownership audit — mandatory invariant

Layout Lab is a demo/validation surface for LayoutLib, not the semantic owner of editing behavior. Any behavior that changes Spatial IR meaning or correction semantics must live in LayoutLib (or a clearly versioned LayoutLib editor module) and be called by the demo. The website may own only presentation/input wiring such as buttons, pointer gestures, viewport pan/zoom, labels, status text, and transport/bootstrap glue.

Current audit found this invariant is not yet fully satisfied. The browser library already owns raster analysis, coordinate transforms, `addWallPx`, erase preview/application, geometry updates, and basic edit replay. However production currently injects or overlays additional semantic editing behavior from the demo/deploy layer, including editable-document creation, wall selection helpers, delete-wall semantics/evidence replay, and the durable manual-correction layer. These must be migrated back into LayoutLib before treating the demo as a faithful consumer-only reference implementation.

Required ownership target:

`LayoutLib: analyze + Spatial IR + select/query + add/erase/delete/move + correction journal + replay/rebase`

`Layout Lab: render + pointer/keyboard mapping + viewport navigation + call LayoutLib APIs + display results`

No new semantic editor primitive may be implemented only in `layoutlab-v0.7-release-fix.js`, `layoutlab_v0_5.html`, or deployment-time HOTFIX injection.

## Correction lineage and moved-wall semantics

A moved auto-detected wall cannot be represented only by changing `source:auto` to `source:manual`, because a later parser run may rediscover the original wall and create a duplicate. The correction journal must preserve both negative and positive intent:

`move_wall = suppress(original evidence) + add(replacement geometry)`

The original evidence must be source-space geometry/provenance, not regenerated wall ID alone. During re-analysis/rebase, LayoutLib matches newly detected candidates against the stored original evidence within controlled geometry/topology tolerances. A matched candidate is suppressed, then the replacement manual geometry is applied. If a new candidate is materially different and cannot be matched confidently, it is not silently suppressed; the rebase result should surface an unresolved/ambiguous correction conflict for review.

This means parser output and user corrections are separate layers:

`new auto base -> correction rebase/matching -> suppress matched originals -> replay manual replacements/additions/deletions -> final Spatial IR`

The same lineage mechanism should serve delete and move so threshold changes cannot resurrect a wall that the user intentionally removed or relocated.

## What v0.7 proves

v0.7 now proves the deployed mechanics of:

`independent nodes -> abstract experience -> lowest semantic owner -> persistent convergence -> evaluator/governance -> canonical capability state -> fresh-node bootstrap`

This is the engineering proof of shared capability convergence. The stronger research claim — that a fresh Node D measurably requires less correction than an equivalent no-shared-learning baseline on real floorplans — remains a post-release controlled experiment, not a release blocker.

## Next active work after v0.7

- migrate semantic editor behavior out of Layout Lab HOTFIX/overlay code and into LayoutLib APIs, with regression tests;
- implement a first-class correction journal/rebase contract, including geometry-evidence matching and ambiguity handling;
- add `move_wall` and endpoint-adjustment primitives on top of that correction lineage contract;
- measure real fresh-node correction-cost improvement against a no-shared-learning baseline;
- stabilize Spatial IR topology and add rooms/openings;
- consolidate historical source/version filename drift into a clean canonical source identity;
- grow the fixture/regression corpus before learned policies influence broader production behavior.

## Parked branches

Keep these parked until the LayoutLib result is measured:

- Character IR and IP Genome integration;
- Blender/Unity native adapters;
- glTF/GLB/USD/IFC expansion beyond the current exporter proof;
- trading strategy capability;
- autonomous graph/plasticity engine;
- universal Semantic IR core extraction.
