# Character Blueprint POC v0.1

Goal: prove that a single character image can be compiled into a structured, evidence-grounded Character IR without requiring an LLM.

## Input constraints
- one person/character
- full-body or mostly full-body
- front or 3/4 view preferred
- limited occlusion

## v0.1 pipeline
1. Browser-local MediaPipe Pose Landmarker
2. observed 2D/world landmarks
3. deterministic geometry ratios and depth spread
4. Character IR split into `observed`, `inferred`, `assumed`
5. simple 3D mannequin projection for validation

## Explicit non-goals for v0.1
- no direct GLB/mesh generation
- no LLM or vision-language token dependency
- no fake claim that hair/clothing/accessory semantics are solved
- no unseen back-side hallucination

## Acceptance
A valid input should produce:
- pose landmarks with confidence
- body proportion ratios
- coarse pose/depth description
- `observed/inferred/assumed` provenance separation
- local 3D mannequin preview
- `llm_tokens: 0`

## Next POC gates
- local foreground/person segmentation -> silhouette
- hair / garment / accessory region proposals
- ambiguity/evidence confidence
- user correction journal
- render-back comparison
