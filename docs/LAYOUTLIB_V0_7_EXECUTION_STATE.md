# LayoutLib v0.7 Execution State

Status: RELEASE COMPLETE — production closed loop deployed and editor semantic ownership corrected
Date: 2026-08-27

## Goal

Finish LayoutLib v0.7 as the first deployed AgentOS capability-evolution closed loop, without mixing in unrelated character, trading, or general world-model work.

## Released product flow

`layout image -> analyze -> Spatial IR -> edit/correct -> 3D preview -> finish`

Learning closure:

`finish/accept -> correction outcome -> CapabilityExperience -> governed transport -> persisted capability experience -> consolidate/evaluate -> governed canonical capability state -> fresh-node bootstrap`

## Released architecture

- LayoutLib core remains a pure execution library.
- `web_assets/layoutlib-browser-v0.5.js` remains the historical-name parser core.
- `web_assets/layoutlib-editor-v0.7.js` is the versioned LayoutLib editor-semantics extension. It owns editable-document creation, wall query/selection geometry, delete semantics, correction evidence matching, correction replay/rebase, correction-session state, and the first `moveWallPx` primitive.
- `web_assets/layoutlab-editor-ui-v0.7.js` is demo UI/input wiring only. It maps pointer/selection/delete interactions to LayoutLib APIs and renders selection state.
- `web_assets/layoutlab-v0.7-release-fix.js` is UI-only release presentation/navigation: version badge, keyboard Delete mapping, 2D pan/zoom, fixed-frame 3D zoom, and labels. It no longer defines Spatial IR mutation semantics.
- `capabilities/layoutlib/adapter.py` translates abstract profile features, policies, and correction metrics into AgentOS capability experience.
- `agentos_node/capability_runtime.py` provides generic experience observation, candidate consolidation, evaluation, seeded canonical state, and explicit governed promotion. Promotion requires a successful evaluator result and authority receipt.
- `agentos_node/capability_store.py` provides persistent idempotent capability-owned experience and canonical-state storage.
- `agentos_node/capability_http.py` provides the HTTP gateway contract for experience ingestion and canonical-state reads.
- `agentos_node/capability_consolidator.py` loads persisted experience, produces/stores candidate state, and can explicitly promote/store canonical state with governance provenance.
- `web_assets/layoutlab-capability-bridge-v0.7.js` records completion/correction outcomes, keeps an offline edge queue, opportunistically submits queued experience, and bootstraps a canonical profile policy.
- Spatial IR remains the canonical spatial model. 3D preview and exported mesh formats are derived representations.

## Learning signal

Correction cost, not Analyze, is the primary learning reward boundary.

Reference metrics include walls added/deleted, erase length, re-analysis count, manual parameter changes, and accepted/completed outcome. No raw image is required in capability experience. The persistent store rejects obvious raw image/binary telemetry fields at the shared boundary.

## Verification and deployment result

1. Focused v0.7 runtime/capability tests previously passed for governance, persistence/idempotency, raw-image rejection, persisted consolidation, LayoutLib adapter/convergence, and browser bridge contracts.
2. Browser completion boundary and correction metrics are present in the production v0.7 bridge.
3. Capability Gateway is installed as a reboot-persistent system service bound to `127.0.0.1:8767`, with capability persistence owned by `agentos-node`.
4. nginx routes `/layout-lab/api/...` to the capability gateway.
5. Public experience ingestion and canonical-state bootstrap were exercised through the real public route.
6. Three independent proof-node experiences were persisted, consolidated, evaluated, explicitly promoted with an authority receipt, then retrieved through the public canonical-state endpoint.
7. A fresh-node bootstrap proof read capability-owned canonical profile state before local history. This proves convergence/bootstrap mechanics, not yet empirical human correction-cost improvement.
8. v0.7.9 release workflow `33044098450` passed governed runtime refresh, semantic-ownership guard, deployment, and public acceptance.
9. The release gate now mechanically requires delete/move/evidence/replay/session semantics to exist in `layoutlib-editor-v0.7.js`, rejects those semantic implementations in the release UI overlay, and rejects deployment-time `HOTFIX` injection.

Current production patch: `v0.7.9`.

## Production boundaries

The older LayoutLib parser demo at `127.0.0.1:8766` remains separate and untouched. The AgentOS capability gateway owns `127.0.0.1:8767`.

Browser transport uses the same-origin namespace:

- `POST ./api/capability/experience` with 1..20 abstract experiences.
- `GET ./api/capability/<capability_id>/canonical` for bootstrap.

Transport is at-least-once from the browser edge queue. Server ingestion is idempotent by `experience_id`: replay of the same payload is accepted as duplicate; reuse of the same ID with a different payload is rejected. The browser cannot write canonical state.

## Demo/library ownership invariant

Layout Lab is a demo/validation surface for LayoutLib, not the semantic owner of editing behavior. Any behavior that changes Spatial IR meaning or correction semantics must live in LayoutLib (or a clearly versioned LayoutLib editor module) and be called by the demo. The website may own presentation/input wiring such as buttons, pointer gestures, viewport pan/zoom, labels, status text, and transport/bootstrap glue.

Required ownership target:

`LayoutLib: analyze + Spatial IR + select/query + add/erase/delete/move + correction journal + replay/rebase`

`Layout Lab: render + pointer/keyboard mapping + viewport navigation + call LayoutLib APIs + display results`

As of v0.7.9, the deployment-time semantic HOTFIX has been removed and the previously misplaced delete/evidence/manual-correction behavior has been moved behind `LayoutLibEditor`. CI now enforces this boundary for the release path. No new semantic editor primitive may be implemented only in `layoutlab-v0.7-release-fix.js`, `layoutlab_v0_5.html`, or deployment code.

## Correction lineage and moved-wall semantics

A moved auto-detected wall cannot be represented only by changing `source:auto` to `source:manual`, because a later parser run may rediscover the original wall and create a duplicate. The correction journal preserves both negative and positive intent:

`move_wall = suppress(original evidence) + add(replacement geometry)`

The original evidence is source-space geometry/provenance, not regenerated wall ID alone. During re-analysis/rebase, LayoutLib matches newly detected candidates against stored original evidence within controlled geometry tolerances. A matched candidate is suppressed, then replacement manual geometry is applied. A materially different candidate remains part of the new auto base.

Parser output and user corrections remain separate layers:

`new auto base -> correction rebase/matching -> suppress matched originals -> replay manual replacements/additions/deletions -> final Spatial IR`

The same lineage mechanism serves delete and move so threshold changes do not resurrect a wall intentionally removed or relocated.

`moveWallPx` now exists in the LayoutLib editor module, but the Layout Lab drag-to-move gesture is not yet wired; that UI work must call the library primitive rather than reimplement it.

## What v0.7 proves

v0.7 proves the deployed mechanics of:

`independent nodes -> abstract experience -> lowest semantic owner -> persistent convergence -> evaluator/governance -> canonical capability state -> fresh-node bootstrap`

This is the engineering proof of shared capability convergence. The stronger research claim — that a fresh Node D measurably requires less correction than an equivalent no-shared-learning baseline on real floorplans — remains a post-release controlled experiment, not a release blocker.

## Next active work after v0.7

- harden correction evidence matching with ambiguity/conflict reporting rather than unsafe suppression when two candidates are equally plausible;
- wire Layout Lab drag-to-move and endpoint adjustment strictly through LayoutLib editor APIs;
- add functional regression tests for correction rebase across threshold changes, including move/delete resurrection prevention;
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
