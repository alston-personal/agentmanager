# LayoutLib Semantic MVP Contract

Date: 2026-08-27
Status: functional MVP deployed; commercial-quality benchmark pending real annotated floorplans

## Product promise

A user supplies a real 2D floor plan. LayoutLib produces an editable Spatial IR that contains enough spatial meaning to support immediate basic 3D generation and downstream automation without requiring a cloud AI token call.

## Required output contract

The analyzed Spatial IR MUST expose:

- `walls`
- `openings`
- `doors`
- `windows`
- `rooms`
- `semantic_summary`

`semantic_summary.engine` identifies the semantic engine and `semantic_summary.token_cost` MUST report the mandatory inference-token cost. The current deterministic MVP reports `token_cost: 0`.

## Door-first priority

Door recognition is the primary semantic quality target. A door record should preserve, when inferable:

- opening reference
- wall association
- width
- door type
- hinge side / endpoint
- swing side / direction evidence
- connected rooms
- confidence

Window and room quality remain required, but a release does not qualify as a commercially testable MVP if doors are not measurable.

## Functional MVP acceptance

Functional MVP is present when the full pipeline runs:

`floor-plan raster -> wall parsing -> opening candidates -> door/window classification -> room segmentation -> Spatial IR -> basic 3D`

The pipeline must remain usable with zero mandatory third-party AI API calls.

## Commercial MVP gate

Real annotated floorplans are scored with:

```bash
python3 scripts/layoutlib_semantic_benchmark.py prediction.json ground_truth.json --json
```

Default door gate:

- precision >= 0.80
- recall >= 0.80

This threshold is intentionally only the first sellable-MVP gate, not the final production-quality target. The benchmark also reports window precision/recall/F1, room count error, opening count error, and token cost.

## Ground truth

See `benchmarks/layoutlib/ground_truth_example.json`.

Door/window matching uses source-image midpoint distance with a default tolerance of 24 px. Ground-truth annotation should be made against the source raster coordinate frame so parser parameter changes can be compared on the same image.

## Development rule

Do not optimize the MVP around prettier 3D rendering while door recall is poor. The optimization order is:

1. wall topology sufficient to support openings
2. door/opening recall
3. door precision and swing/hinge semantics
4. windows
5. room topology/connectivity
6. correction speed
7. derived 3D presentation

## Evidence required to claim commercial MVP

A commercial-MVP claim requires a versioned real-floorplan corpus and a benchmark report. A successful deployment or the mere presence of `doors/windows/rooms` fields is not sufficient evidence.
