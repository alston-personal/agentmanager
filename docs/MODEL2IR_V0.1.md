# model2ir v0.1

`model2ir` is the reusable 3D asset → Character IR decompiler and regression layer for Character Blueprint research.

## Public API

```python
from model2ir import load_asset, extract_ir, diff_ir, reconcile_ir, score_roundtrip

ir = extract_ir('character.glb')
diff = diff_ir(ir_a, ir_b)
report = reconcile_ir(image_ir, ir)
score = score_roundtrip(source_ir, recovered_ir)
```

Supported containers in v0.1:

- `.glb`
- `.gltf`
- `.vrm` as a GLB-compatible container; VRM extension semantics are preserved as structural evidence but are not yet fully interpreted.

## Truth policy

The library separates factual asset observations from semantic hypotheses:

- geometry counts, scene graph, node hierarchy, materials, skins and accessor bounds are structural evidence;
- semantic labels inferred from names are candidates only;
- unresolved components remain unresolved;
- no 3D generator result is automatically promoted into canonical Character IR.

## v0.1 IR layers

- `structural_ir`: meshes, primitives, nodes/components, scene edges, skins, transforms, bounds, extensions.
- `semantic_ir`: conservative name-derived candidates plus unresolved components.
- `relations`: node-child and skin-binding relations.
- `provenance`: extractor version and truth policy.

## Family regression

`benchmarks/model2ir/family-v0.1.json` defines three controlled families. v0.1 intentionally uses synthetic glTF manifests for regression isolation, while CI also runs against the real Khronos CesiumMan GLB. The synthetic families do not replace future licensed real-model families.

The first schema-gap report deliberately exposes missing representation/extraction capacity:

- hair style/length detail;
- garment subtype/layer detail;
- extra appendages such as tail/wing;
- semantic attachment relations;
- material-driven semantic evidence.

Those gaps are expected research output, not hidden failures.

## Next evidence layer

The next step is to collect licensed, structurally similar real character model families and run the same `extract_ir → pairwise diff → gap report` protocol. Learned semantic extraction should be trained only after corrected/gold IR pairs exist; v0.1 is deterministic by design.
