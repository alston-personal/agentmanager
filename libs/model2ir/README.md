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

## Truth invariants

1. A first import of an external model is not automatically canonical truth.
2. Standardized metadata such as VRM humanoid mappings outranks weaker naming/topology inference.
3. Inferred semantics remain inferred; stabilization never launders them into observed facts.
4. Unknown and unresolved fields are retained instead of filled merely to make the IR dense.
5. Reversibility and semantic certainty are separate dimensions. An embedded Canonical Character IR may round-trip exactly even when the original external asset required inference.

## Teacher dataset API

The multi-view teacher contract is now library-owned. Rendering is intentionally an injected adapter so `model2ir` itself does not depend on Playwright, Three.js, a browser, or an AgentOS repository layout.

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

Core extraction supports the formats handled by the existing loader stack, including the current GLB/glTF/VRM paths. The teacher-data builder currently stages self-contained `.glb` only because copying a standalone `.gltf` file without its referenced buffers/textures would create a misleading dataset artifact. Multi-file glTF staging should be added as an explicit bundle feature rather than guessed.

## Repository adapters

Repository-level scripts may provide renderers, benchmark harnesses, CI, downloads, and product integration. They should call the package API rather than reimplement extraction, truth policy, hashing, admission, or manifest semantics.

This boundary is what allows Image→IR, Character Blueprint, future model-training pipelines, and external repositories to consume the same 3D→IR behavior without depending on AgentOS internals.
