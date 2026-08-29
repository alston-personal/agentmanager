# Character IR Round-trip v0.1

Goal: test whether Character IR can act as a generative intermediate representation rather than metadata only.

## Loop

`Image -> Character IR -> compiled 3D representation -> 3D-derived IR -> semantic diff -> IR refinement`

v0.1 intentionally uses a **compiled scene manifest** for the 3D representation because Character Blueprint v0.5 does not yet export GLB. This is not called mesh decompilation. The contract is designed so a later GLB/mesh extractor can replace the manifest extractor without changing the loop.

## Evidence classes

Every recovered field must carry provenance:

- `observed_2d`: directly visible in source image.
- `inferred_2d`: inferred from image evidence.
- `compiled_3d`: materialized by the IR->3D compiler.
- `inferred_3d_candidate`: inferred from generated 3D and therefore not ground truth.
- `confirmed_user`: explicit human confirmation.
- `assumed_policy`: completion required by a reconstruction policy.

A generated model must never promote unseen geometry to canonical truth merely because it looks plausible.

## v0.1 checks

The first round-trip checks whether the following survive compilation:

- coverage
- semantic part set
- shoulder/hip proportions when available
- backside uncertainty
- body depth assumption
- hair depth assumption
- garment depth assumption

The report separates:

- `preserved`: value survived round-trip.
- `changed`: value differs after round-trip.
- `lost`: source IR contained information not represented in compiled 3D.
- `invented`: 3D-derived IR contains information absent from source IR.

## Success criteria

v0.1 is successful when the loop produces reproducible artifacts and clearly identifies information loss. It is **not** a claim of high-fidelity mesh reconstruction.

Next milestones:

1. expose/export Character Blueprint GLB or a geometry scene snapshot;
2. implement real `GLB -> 3D IR` extraction;
3. run Meshy/Rodin/Tripo GLBs through the same extractor;
4. use disagreements to evolve Character IR schema;
5. close the loop with IR refinement and recompilation.
