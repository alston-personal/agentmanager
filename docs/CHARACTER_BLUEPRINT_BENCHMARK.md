# Character Blueprint Image-to-3D Benchmark Suite v0.1

## Purpose

Character Blueprint must not be evaluated only against its previous release. This benchmark compares the same input images across Character Blueprint and established image-to-3D systems using a fixed evidence package and scorecard.

Primary question:

> How close can Character Blueprint get to useful image-to-3D geometry while preserving structured IR, explicit uncertainty, editability, determinism, and local-first operation?

## Reference systems

### Primary benchmark: Meshy

Use the current standard Image-to-3D model with texture disabled for geometry comparison, then optionally repeat with texture enabled for presentation comparison.

Why primary:
- mature commercial Image-to-3D product
- direct single-image input
- supports A-pose generation and explicit mesh output formats
- multi-view thumbnails can provide repeatable front/right/back/left evidence
- API automation is practical when credentials are available

### Quality ceiling: Hyper3D Rodin

Use the current Rodin image-to-3D model.

Why ceiling:
- strong character-oriented 3D generation
- supports one or multiple images
- useful as a higher-fidelity reference even when API access is more expensive/restricted

### Sanity benchmark: Tripo

Use the current Image-to-3D endpoint/model.

Why include:
- independent generation family
- seed can be fixed for repeatability
- supports GLB and character-oriented downstream workflows
- gives evidence that a result is not only good/bad relative to one vendor

## Benchmark systems

| id | system | role |
|---|---|---|
| character-blueprint | Character Blueprint | system under test |
| meshy | Meshy Image-to-3D | primary commercial baseline |
| rodin | Hyper3D Rodin | quality ceiling |
| tripo | Tripo Image-to-3D | independent sanity baseline |

## Test cases

Minimum v0.1 set:

1. `fullbody-front-clean`
   - full body
   - front facing
   - simple background
   - minimal occlusion
2. `upperbody-portrait`
   - half body
   - long hair
   - lower body not visible
   - validates uncertainty / no fabricated legs
3. `anime-fullbody`
   - stylized character
   - clean silhouette
   - exaggerated hair/clothing
4. `real-person-fullbody`
   - realistic anatomy and clothing
5. `occluded-character`
   - partial arm/body occlusion
   - tests whether the system marks uncertainty instead of inventing confident geometry
6. `loose-garment`
   - clothing silhouette differs strongly from underlying body
7. `accessory-character`
   - obvious accessory separated from body/hair
8. `three-quarter-pose`
   - non-frontal body orientation

Every test case must have a stable source asset or immutable URL plus license/provenance.

## Required output evidence

For every system/case pair retain:

- source image hash
- system/model/version
- generation timestamp
- generation settings
- generation duration
- billed credits / estimated cost when available
- raw output model (prefer GLB)
- front render
- 45-degree render
- right-side render
- back render
- polygon/vertex count when measurable
- failure/error state
- evaluator notes

Character Blueprint additionally retains:

- Character IR
- observed / inferred / confirmed / assumed split
- proxy/reconstruction method id
- correction journal when applicable
- token/inference cost metadata

## Metrics

Scores use 0-5 unless otherwise stated.

### A. Source-view fidelity

How well does a front render reproduce source evidence?

Measure/score:
- silhouette IoU where render segmentation is available
- landmark reprojection error where compatible
- body proportion similarity
- head/hair/clothing outline fidelity

### B. Novel-view plausibility

Inspect 45°, 90° and 180° renders.

Penalize:
- collapsed or flat geometry
- implausible backside
- disconnected head/limbs
- severe asymmetry unsupported by input
- intersecting major body regions

### C. Semantic fidelity

Can the geometry distinguish meaningful character parts?

Score separate handling of:
- body
- head/face
- hair
- upper garment
- lower garment
- accessories

Character Blueprint should report semantic structure directly from IR. For opaque generators, evaluate visible/model part structure only; do not award hidden semantics without evidence.

### D. Geometry quality

Inspect:
- watertightness where relevant
- self-intersections
- disconnected components
- degenerate faces
- topology density / cleanliness
- surface continuity

### E. Uncertainty honesty

This is intentionally a separate metric.

Reward systems that avoid presenting unseen geometry as observed fact.

Character Blueprint target behavior:
- unseen regions remain `assumed` or `unknown`
- partial-body input must not silently claim observed lower-body evidence

Opaque generators may still create plausible back geometry, but it must be scored as plausible generation, not observed fidelity.

### F. Editability and traceability

Evaluate:
- can a user identify which evidence drove a shape?
- can one semantic region be corrected without regenerating everything?
- are corrections replayable?
- is there a structured intermediate representation?

### G. Determinism / repeatability

Run the same input/settings at least three times where the product permits it.

Record:
- identical output hash: yes/no
- silhouette variance
- major semantic variance

### H. Cost / latency / privacy

Record:
- wall-clock generation time
- paid credits/cost
- cloud upload required
- local/offline capability
- mandatory LLM/VLM token cost

## Scorecard

Do not collapse everything into one vanity score. Report two summaries:

### Reconstruction quality score

Average of:
- source-view fidelity
- novel-view plausibility
- semantic fidelity
- geometry quality

### System quality score

Average of:
- uncertainty honesty
- editability/traceability
- determinism
- cost/latency/privacy

This prevents a visually attractive opaque mesh from automatically winning the entire product comparison, while also preventing Character Blueprint from claiming victory merely because its IR is better structured.

## Character Blueprint release rule

Starting with the first release wired to this benchmark:

1. no release may regress a previously passing geometry sanity case;
2. every material reconstruction change must run the same fixed benchmark cases;
3. screenshots/renders must be retained as evidence;
4. benchmark failures must be classified as functional, geometric, visual, or fixture/infrastructure failures;
5. claims such as “better than Meshy/Rodin/Tripo” are forbidden unless supported by the same fixed test cases and metric.

## Initial target

Character Blueprint does **not** need to beat Meshy/Rodin/Tripo on photorealistic appearance in v0.x.

The first meaningful target is:

> Reach recognizably source-driven geometry on front and 45° views, while materially outperforming opaque generators on semantic structure, uncertainty provenance, correction locality, and repeatability.

Once this is achieved, external generators can also be evaluated as optional geometry backends consuming Character IR rather than only as competitors.
