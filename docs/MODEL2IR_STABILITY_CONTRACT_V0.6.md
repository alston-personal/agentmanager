# model2ir stability contract v0.6

## Claim

model2ir does **not** claim that arbitrary 3D files contain enough information to reconstruct their original human semantic intent losslessly.

The supported contract is:

1. A supported 3D asset is deterministically decompiled into evidence plus a candidate Character IR.
2. Explicit standards (currently VRM humanoid metadata) outrank naming heuristics; naming/scene evidence outranks topology-only inference.
3. Missing or ambiguous semantics remain unresolved rather than being invented.
4. Once an external import is stabilized, the candidate/canonical IR is embedded with an integrity digest and all subsequent IR -> 3D carrier -> IR round-trips are exact.
5. Assets compiled by our own pipeline can be losslessly reversible from the first round-trip by carrying the same contract.

## Stability classes

- `lossless`: embedded canonical IR is present and digest-verified.
- `stable-candidate`: deterministic external extraction with strong standardized or explicit asset semantic evidence.
- `stable-but-ambiguous`: deterministic body-plan inference from topology, but details such as left/right remain unresolved.
- `stable-unknown`: deterministic structural extraction, insufficient evidence for semantic interpretation.
- `unstable`: repeated extraction produces different candidate IR; this is a release blocker.

## Evidence priority

`embedded canonical IR > VRM standard > explicit joint/node/scene evidence > skeleton topology > unknown`

A lower-priority source may add evidence but cannot silently overwrite a higher-priority fact.

## Release gates

A model2ir release is considered stable only when all of the following hold:

- compiled Character IR family: exact canonical round-trip = 1.0;
- tampered embedded IR: digest mismatch is detected;
- arbitrary external assets are never reported lossless before stabilization;
- repeated extraction of the same real asset produces identical candidate digests;
- at least two independently authored humanoid rigs agree on the core humanoid semantic set when evidence exists;
- non-humanoid controls are not classified humanoid;
- a complete unnamed humanoid rig may be recognized at body-plan topology level but must not invent left/right labels;
- an insufficient unnamed rig remains unknown;
- VRM 0.x and VRM 1.0 humanoid mappings produce high-confidence standardized semantics despite opaque node names;
- legacy public API/CLI regression suites remain compatible with the current implementation.

## Why metadata-assisted reversibility is valid

The embedded Character IR is analogous to a source map or debug-symbol table. It does not replace geometry and it does not make an arbitrary third-party model semantically lossless. It guarantees that assets participating in the Character IR toolchain preserve the canonical representation across compilation/decompilation cycles.

## What remains outside v0.6

- semantic recovery from pure polygon geometry with no names, rig, standardized metadata, or other semantic evidence beyond conservative body-plan topology;
- visual/material semantic recognition from textures or rendered views;
- learned semantic classification;
- guarantee that a first-pass inferred candidate is the creator's intended semantics.

Those are quality improvements to the first import, not blockers for reversibility after stabilization.
