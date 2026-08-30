# model2ir Teacher Dataset Contract v0.7

Goal: turn stable 3D assets into evidence-preserving supervision for image→IR without laundering inference into fact.

## Record shape

Each admitted 3D asset produces:

- `character-ir.json`: the stabilized candidate Character IR.
- `audit.json`: repeatability, semantic authority, coverage, and truth-policy evidence.
- canonical renders at yaw `0°`, `45°`, `90°`, `180°`.
- `manifest.json`: one training example per canonical render, all linked to the exact same IR digest.

## Admission rules

1. `model2ir audit` must not return `unstable`.
2. External first import remains `candidate`; stabilization does not rewrite inferred semantics as observed truth.
3. Unknown/unresolved values are preserved as labels. They are not filled merely to make the dataset dense.
4. Every rendered image records its SHA-256 and exact target IR digest.
5. A case whose repeated candidate extraction changes digest is a release blocker and is not admitted.

## What this dataset can teach

The paired renders can supervise observable and semantically supported Character IR fields, while providing explicit masks for fields that should remain unknown from a particular view.

The initial v0.7 gate intentionally uses a real Khronos humanoid asset and four deterministic views. It proves the data plumbing and truth boundary; it does **not** claim a trained image2ir model yet.

## Next gate

`image2ir-teacher-loop/v0.1` must consume this manifest, predict IR from each view independently, compare it to the teacher IR using observable-field-aware scoring, and show that correction/training reduces held-out IR error without increasing hallucinated fields.
