# image2ir Teacher Loop v0.1

Purpose: measure the current Image→IR system against a stable 3D-derived Character IR teacher before any corrective training is attempted.

## Flow

1. Fetch real humanoid GLBs.
2. `model2ir` audits and stabilizes candidate Character IR.
3. Render deterministic canonical views from the same 3D assets.
4. Feed a canonical render into the current public Character Blueprint image extractor.
5. Normalize the shared humanoid vocabulary (`body` → `torso`).
6. Measure core-part precision/recall/F1 and body-coverage agreement.
7. Preserve teacher unresolved fields outside dense scoring.
8. If the primary detector rejects the image, run a detector-independent silhouette/body-plan fallback and score it against the same teacher.

## Narrow score contract

The two IRs are not yet schema-identical. v0.1 scores only shared observable concepts: head, torso/body, left/right arms, left/right legs, and full-body vs upper-body coverage. Hair, garment, depth assumptions, topology, materials and other unmatched fields are recorded but not automatically treated as hallucinations.

## Truth and correction policy

- Detector rejection is a valid zero baseline.
- Fallback outputs remain candidate unless corroborated.
- Teacher unknown/unresolved fields are not converted into negative labels.
- Teacher/predictor disagreement may indicate a predictor bug or a teacher bug; inspect evidence before assigning blame.
- Scores may not be improved by weakening truth policy or silently removing disagreements.

## Teacher-side repair

Some humanoid rigs terminate the skeleton at a second neck joint instead of naming a separate head bone. `model2ir` may infer a low-authority head anchor only when a strong humanoid body plan, a multi-joint neck chain, one unique terminal neck joint, and no explicit head evidence all agree. This stays inferred evidence, never observed truth.

## Exit gate

Run two independently-authored humanoid teachers across front/yaw45/right/back. The teacher-blind fallback must remain deterministic, produce accepted candidates for all eight cases, maintain core F1 >= 0.75 per case, average shared-field score >= 0.85, and keep all existing model2ir reversibility/stability regressions green.
