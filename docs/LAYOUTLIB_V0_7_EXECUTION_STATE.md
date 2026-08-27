# LayoutLib v0.7 Execution State

Status: active implementation checkpoint
Date: 2026-08-27

## Goal

Finish LayoutLib as the first real AgentOS capability-evolution closed loop, without mixing in unrelated character, trading, or general world-model work.

## Current product flow

`layout image -> analyze -> Spatial IR -> edit/correct -> 3D preview`

The missing product/learning closure is:

`finish/accept -> correction outcome -> CapabilityExperience -> consolidate -> canonical capability state -> fresh-node bootstrap`

## Current architecture

- LayoutLib core remains a pure execution library.
- `capabilities/layoutlib/adapter.py` translates abstract profile features, policies, and correction metrics into AgentOS capability experience.
- `agentos_node/capability_runtime.py` provides generic experience observation, candidate consolidation, evaluation, and explicit governed promotion.
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

No raw image is required in the capability experience payload.

## Immediate implementation sequence

1. Prove cross-node convergence in tests: A/B/C experiences consolidate to a canonical profile policy and a fresh Node D can consume it without local history.
2. Add an explicit UI/product completion event and collect correction metrics from the actual Layout Lab editing session.
3. Bridge browser-generated experience into the governed AgentOS capability runtime rather than leaving canonical learning only in localStorage.
4. Stabilize the Spatial IR schema and topology primitives needed for rooms/openings.
5. Consolidate historical v0.5/v0.6/staged/deploy-hotfix source drift into a canonical v0.7 source/release identity.
6. Add regression fixtures and acceptance metrics before allowing learned policy promotion.

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
