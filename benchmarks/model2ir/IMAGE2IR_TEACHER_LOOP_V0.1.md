# image2ir Teacher Loop v0.1

Purpose: measure the current Image→IR system against a stable 3D-derived Character IR teacher before any corrective training is attempted.

## Flow

1. Fetch a real humanoid GLB.
2. `model2ir` audits and stabilizes its candidate Character IR.
3. Render deterministic canonical views from the same 3D asset.
4. Feed the front render into the current public Character Blueprint image extractor.
5. Normalize the shared humanoid part vocabulary (`body` → `torso`).
6. Measure core-part precision/recall/F1 and body-coverage agreement.
7. Preserve teacher unresolved fields outside dense scoring.

## Why the first score is intentionally narrow

The two IRs are not yet schema-identical. A full object diff would mostly measure schema mismatch rather than perception quality. v0.1 therefore scores only shared, observable concepts:

- head
- torso/body
- left/right arms
- left/right legs
- full-body vs upper-body coverage

Hair, garment, depth assumptions, topology, materials, morphs, and other unmatched fields are recorded but not automatically labelled as hallucinations.

## Exit condition for the next stage

The baseline must produce a deterministic evidence artifact. The next correction stage must improve held-out shared-field score without increasing unsupported confident fields. Only after this gate is measurable should we add learned or rule-based correction from the teacher dataset.
