# model2ir

`model2ir` is the reusable 3D asset → Canonical Character IR boundary extracted from the AgentOS research codebase.

Its job is not to make every 3D asset look humanoid. Its job is to preserve what the source actually supports, keep inference distinguishable from observation, and make the resulting Character IR stable enough for reversible round-trips, regression, and teacher-data generation.

## Public boundary

```python
from model2ir import (
    load_asset,
    extract_ir,
    stabilize_external_ir,
    audit_asset,
    diff_ir,
    reconcile_ir,
    score_roundtrip,
    compile_reversible_gltf,
    save_reversible_gltf,
    compile_reversible_glb,
    save_reversible_glb,
    verify_glb_container_preservation,
    ir_digest,
    build_teacher_dataset,
    validate_teacher_dataset_manifest,
)
```

The package can also be invoked with:

```bash
model2ir --help
# or
python -m model2ir --help
```

## CLI contract

The CLI separates evidence extraction, stabilized Character IR projection, and reversible container writing:

```bash
model2ir extract character.glb -o evidence.json
model2ir stabilize character.glb -o character-ir.json
model2ir audit character.glb -o audit.json --repeats 3
model2ir diff a.json b.json -o diff.json
model2ir reconcile image-ir.json model-ir.json -o reconciliation.json
model2ir embed-ir character.glb canonical-ir.json -o reversible.glb --report preservation.json
```

`extract` returns the full Model2IR evidence envelope. `stabilize` accepts GLB, glTF, and VRM through the normal loader and returns only the stabilized Canonical Character IR candidate/truth.

`embed-ir` is intentionally narrower. It writes a **new** `.glb` or `.vrm`, rewrites only the JSON chunk to carry the canonical IR sidecar, and preserves every non-JSON chunk byte-for-byte and in order. It refuses in-place overwrite. By default it also rejects non-data external buffer/image URIs so moving the output cannot silently break relative resources.

## Two different lossless claims

Model2IR treats these as separate invariants:

1. **Canonical-IR lossless** — embedded Canonical Character IR is recovered exactly with a verified digest.
2. **GLB container preservation** — every non-JSON chunk, including BIN and unknown chunks, is byte-identical after embedding.

A successful `verify_glb_container_preservation(...)` requires both, plus an exact expected JSON transformation. This prevents the older mistake of treating “IR sidecar round-trips” as proof that the whole binary 3D container was preserved.

The original JSON `.gltf` reversible API remains available for compatibility. Multi-file `.gltf` bundles with relative buffers/textures are **not** yet covered by the v0.9 container-level lossless guarantee.

## Truth invariants

1. A first import of an external model is not automatically canonical truth.
2. Standardized metadata such as VRM humanoid mappings outranks weaker naming/topology inference.
3. Inferred semantics remain inferred; stabilization never launders them into observed facts.
4. Unknown and unresolved fields are retained instead of filled merely to make the IR dense.
5. Reversibility and semantic certainty are separate dimensions. An embedded Canonical Character IR may round-trip exactly even when the original external asset required inference.

## Teacher dataset API

The multi-view teacher contract is library-owned. Rendering is intentionally an injected adapter so `model2ir` itself does not depend on Playwright, Three.js, a browser, or an AgentOS repository layout.

```python
from pathlib import Path
from model2ir import build_teacher_dataset


def render_four_views(local_glb: Path, case_dir: Path):
    # Call any renderer. It must create these files under case_dir.
    return {
        "front": "canonical-front.png",
        "yaw45": "canonical-yaw45.png",
        "right": "canonical-right.png",
        "back": "canonical-back.png",
    }

manifest = build_teacher_dataset(
    "character.glb",
    "character-a",
    "teacher-out",
    renderer=render_four_views,
)
```

`build_teacher_dataset` owns 3D inspection, repeatability audit, stable Character IR projection, admission, hashes, unresolved-label preservation, and manifest construction. The renderer owns only image production.

The retained `model2ir-teacher-dataset/v0.7` schema is intentional: moving the implementation behind a library API does not silently rewrite the already established dataset contract.

## Current format boundary

Core extraction and stabilization support GLB, glTF, and VRM. Reversible **binary-container** output in v0.9 is limited to GLB/VRM. The teacher-data builder also stages self-contained `.glb` only.

Multi-file glTF requires a separate bundle contract covering URI resolution, path containment, resource copying/rewriting, and resource hashes. That work should be explicit rather than inferred from a standalone `.gltf` JSON file.

## Repository adapters

Repository-level scripts may provide renderers, benchmark harnesses, CI, downloads, and product integration. They should call the package API rather than reimplement extraction, truth policy, hashing, admission, manifest semantics, or container preservation.

This boundary lets Image→IR, Character Blueprint, future training pipelines, and external repositories consume the same 3D→IR behavior without depending on AgentOS internals.
