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
    profile_asset_structure,
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

The CLI separates evidence extraction, geometry/structure profiling, stabilized Character IR projection, and reversible container writing:

```bash
model2ir extract character.glb -o evidence.json
model2ir profile character.glb -o profile.json
model2ir stabilize character.glb -o character-ir.json
model2ir audit character.glb -o audit.json --repeats 3
model2ir diff a.json b.json -o diff.json
model2ir reconcile image-ir.json model-ir.json -o reconciliation.json
model2ir embed-ir character.glb canonical-ir.json -o reversible.glb --report preservation.json
```

`extract` returns the full Model2IR evidence envelope. `profile` returns only the conservative geometry/rig structure evidence. `stabilize` accepts GLB, glTF, and VRM through the normal loader and returns only the stabilized Canonical Character IR candidate/truth.

`embed-ir` is intentionally narrower. It writes a **new** `.glb` or `.vrm`, rewrites only the JSON chunk to carry the canonical IR sidecar, and preserves every non-JSON chunk byte-for-byte and in order. It refuses in-place overwrite. By default it also rejects non-data external buffer/image URIs so moving the output cannot silently break relative resources.

## Geometry and weak-structure profiling

Model2IR v0.9.1 adds an evidence-only geometry profile for assets that are technically 3D but carry weak volumetric or rig structure, including relief-like AI-generated assets.

The profile keeps these layers separate:

- **Observed:** local accessor bounding-box extents, mesh/primitive/component counts, skin count, joint count, and animation count.
- **Inferred:** axis-anisotropy shape hint (`planar-or-relief-like`, `volumetric-like`, `elongated-or-linear-like`, or `anisotropic-3d`) and a conservative structural signal.
- **Unresolved:** missing or unusable extent evidence.

A `planar-or-relief-like` asset with no skin, no joints, and only one mesh component is classified as `structural_signal: weak`. That is explicitly **not** permission to infer humanoid bones or promote semantic parts. The purpose of the profile is to make weak evidence visible, not to make sparse 3D assets look more complete than they are.

The regression fixture derived from the Meshy relief sample stores only measured metadata and its SHA-256 reference; the uploaded binary/image are not committed. The sample remains `body_plan: unknown`, with no automatic humanoid promotion.

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

## v0.9.2 correctness and compatibility

- Semantic comparison accepts every retained Model2IR envelope version, direct
  candidate/Character IR `parts`, and Image→IR `inferred.parts`. Structured v0.3
  evidence supplies envelope labels; a recovered canonical payload takes
  precedence over carrier node names. Empty-set Jaccard is still conventionally
  1.0, so a semantic score alone is never proof of useful evidence or appearance.
- Both JSON glTF and binary GLB/VRM writers now share the same guard against
  explicitly candidate/inferred/unknown truth statuses. Stabilization yields a
  repeatable candidate, not confirmation. Keep it as standalone JSON until an
  explicit review establishes canonical design intent. No helper promotes it.
- Recovery requires an existing matching digest and rejects explicitly candidate
  payloads, including carriers produced by the older permissive glTF writer.
  These errors leave the source unchanged. Preserve such payloads as candidate
  JSON for review; do not simply remove `truth_status` to evade the boundary.
- Valid legacy IR without `truth_status` remains supported. This is a declared
  status guard for compatibility, not authentication of an author's assertions.
  Digest verification proves integrity, not semantic correctness.
- Ribbon/bow tails are accessory candidates; anatomical tails and ponytails
  retain their separate tail/hair classifications. Naming remains inference.

The v0.4/v0.5/v0.6 regression adapters now explicitly test candidate JSON
preservation plus rejection of unconfirmed canonical embedding. Their report
schemas are v0.9.2: `candidate_json_roundtrip` replaces the misleading
`post_stabilization_reversibility` gate. Canonical carrier round-trips remain
tested separately by the reversible v0.2 and GLB v0.9 suites. The library CI also
runs `tests/test_model2ir_semantic_integrity.py`.

### Character generator integration boundary

This repair does not turn Model2IR into a mesh generator. Extraction measures
structure and recovers embedded data; the reversible compiler requires the
source model. The current candidate projection does not contain enough geometry,
texture coordinates, animation curves, or hair construction parameters to
recreate the source appearance on its own.

For a parameterized Character Blueprint producer, preserve its own versioned
construction description in the existing Character IR payload, alongside an
explicit coordinate/unit convention and pinned asset/compiler references.
Hair curve control points, cross-section width/depth, layers and gradient
positions must originate from that producer; Model2IR must not guess them from
mesh names. Preserve the observed/inferred/assumed provenance of each design
choice. Candidate designs remain standalone JSON until confirmed.

Acceptance for that later integration must include IR-only regeneration by the
identified producer, fixed-camera rendered comparisons, and an intentional hair
parameter edit that changes the expected geometry. Exact payload/container
round-trips alone are insufficient. No new generator or cross-project adapter
is implemented by v0.9.2.

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
