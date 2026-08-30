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
8. If the primary detector rejects the image, run a detector-independent silhouette/body-plan fallback and score it against the exact same teacher.

## First measured result

The current public Character Blueprint (`0.5.0`) rejects the CesiumMan canonical front render with “沒有偵測到足夠清楚的人物”, producing an observable baseline score of `0.0`. This is treated as valid evidence of a detector-domain gap, not as a benchmark infrastructure failure.

A teacher-blind silhouette fallback based only on image foreground shape raised the same case to a positive shared-field score. Before teacher semantic repair the first successful run measured core recall `1.0`, core F1 `0.9091`, coverage agreement `true`, and score `0.9318`.

The comparison exposed a reverse-direction bug: the 3D teacher labelled two terminal `neck_joint` nodes but emitted no `head`, while the rendered image visibly contained a head-shaped region. Rather than hiding that disagreement in the scorer, `model2ir` now uses a conservative corroboration rule: only a strong humanoid rig with a multi-joint neck chain, one unique terminal neck joint, and no explicit head evidence may infer a low-authority head anchor. Existing model2ir family/reversibility gates must remain green after this repair.

After repair, the fallback reached `1.0` shared body-plan score on CesiumMan. The cross-family gate then tested two independently authored humanoid rigs (CesiumMan and RiggedFigure) across front, 45°, right, and back views: 8/8 cases passed, with average and worst shared body-plan score both `1.0`.

## Why the score is intentionally narrow

The two IRs are not yet schema-identical. A full object diff would mostly measure schema mismatch rather than perception quality. v0.1 therefore scores only shared, observable concepts:

- head
- torso/body
- left/right arms
- left/right legs
- full-body vs upper-body coverage

Hair, garment, depth assumptions, topology, materials, morphs, and other unmatched fields are recorded but not automatically labelled as hallucinations.

## Truth and correction policy

- A detector rejection is a valid zero baseline.
- A fallback may improve coverage, but its outputs remain `candidate` unless corroborated.
- Teacher unknown/unresolved fields are not converted into negative labels merely because the teacher lacks a value.
- A teacher/predictor disagreement may indicate a predictor bug **or a teacher bug**. The loop must inspect evidence before assigning blame.
- Benchmark scores may not be improved by weakening truth policy or silently removing disagreements.

## Exit condition for the next stage

The loop must produce deterministic evidence, demonstrate a real improvement over the primary detector on out-of-domain cases, and keep all model2ir stability/reversibility regressions green. The next stage expands the score beyond body-plan presence into proportions, landmarks, silhouette geometry, and semantic regions before introducing learned correction.
