# visual-ir-fusion

`visual-ir-fusion` is a reusable library boundary for visual identity composition.

The library is not a water-drop generator, slime generator, leopard-cat generator, or robot generator. Those are demo/use-case consumers.

## Core pipeline

```text
main visual image -> extractor adapter -> Visual IR --\
                                                    > weighted fusion -> target IR
user photo       -> extractor adapter -> Visual IR --/                    |
                                                                         v
                                                               renderer adapter
                                                                         |
                                                                         v
                                                                  rendered image
                                                                         |
                                                       extractor adapter -> actual IR
                                                                         |
                                                                         v
                                                            preservation score
```

## Public boundary

```python
from visual_ir_fusion import (
    IRSource,
    FusionPolicy,
    fuse_ir,
    score_preservation,
)
```

Extraction and rendering are intentionally injected adapters. The library owns IR fusion semantics and validation, not any particular image model or web UI.

## IR contract

The retained envelope is deliberately small:

```json
{
  "schema": "visual-ir/v0.1",
  "dimensions": {
    "silhouette": {
      "value": "water_drop",
      "confidence": 0.98,
      "status": "observed"
    },
    "material": {
      "value": "transparent_water",
      "confidence": 0.92,
      "status": "inferred"
    }
  }
}
```

A dimension may contain nested dimensions. Leaf fields preserve `status` so observed, inferred, and unresolved evidence are not silently collapsed.

## Fusion policy

Weights operate at two levels:

1. source weight: e.g. main visual = 0.75, uploaded photo = 0.25
2. dimension override: e.g. silhouette favors main visual 0.95/0.05 while accessories may favor the uploaded photo 0.20/0.80

This is the important distinction from a prompt-only "70/30" instruction.

## Example

```python
from visual_ir_fusion import IRSource, FusionPolicy, fuse_ir

result = fuse_ir(
    [
        IRSource("main", main_ir, weight=0.75),
        IRSource("person", person_ir, weight=0.25),
    ],
    FusionPolicy(
        per_dimension={
            "silhouette": {"main": 0.95, "person": 0.05},
            "material": {"main": 0.95, "person": 0.05},
            "accessories": {"main": 0.20, "person": 0.80},
            "props": {"main": 0.10, "person": 0.90},
        }
    ),
)
```

For the water-drop demo this means the body remains unmistakably a droplet while glasses, coffee, companion animals, and other identity cues can come from the uploaded photo.

## Preservation loop

After rendering, re-extract IR from the generated image and compare it to the fused target IR.

```text
target IR -> render -> re-extract -> score_preservation(target, actual)
```

Consumers may retry, change weights, or reject an output if protected dimensions such as silhouette or material fall below threshold.

## Relationship to model2ir

`model2ir` already establishes the repository's Canonical Character IR philosophy: observed evidence must remain distinguishable from inference and unresolved fields must not be invented.

This library follows the same truth policy. It does not replace `model2ir`; it adds a provider-neutral image/reference fusion layer that can feed Character IR consumers and renderers.

## First consumer

`studio-web /drop/` is intended only as a demo of this library:

```text
water-drop reference + uploaded person photo -> fused IR -> generated character
```

Future consumers can substitute slime, leopard cat, robot, brand mascot, scene, clothing, or additional IR sources without changing the core fusion API.
