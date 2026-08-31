from .v06 import (
    load_asset,
    extract_ir,
    stabilize_external_ir,
    diff_ir,
    reconcile_ir,
    score_roundtrip,
    compile_reversible_gltf,
    save_reversible_gltf,
)
from .reversible import ir_digest
from .glb_container import (
    compile_reversible_glb,
    save_reversible_glb,
    verify_glb_container_preservation,
)
from .geometry_profile import GEOMETRY_PROFILE_SCHEMA, profile_asset_structure
from .audit import audit_asset as _audit_asset
from .teacher import (
    CANONICAL_VIEWS,
    TEACHER_DATASET_SCHEMA,
    TeacherDatasetError,
    build_teacher_dataset,
    validate_teacher_dataset_manifest,
)


def audit_asset(path, repeats=3):
    return _audit_asset(path, extract_ir, stabilize_external_ir, repeats=repeats)


__all__ = [
    "load_asset",
    "extract_ir",
    "stabilize_external_ir",
    "diff_ir",
    "reconcile_ir",
    "score_roundtrip",
    "compile_reversible_gltf",
    "save_reversible_gltf",
    "compile_reversible_glb",
    "save_reversible_glb",
    "verify_glb_container_preservation",
    "ir_digest",
    "audit_asset",
    "GEOMETRY_PROFILE_SCHEMA",
    "profile_asset_structure",
    "CANONICAL_VIEWS",
    "TEACHER_DATASET_SCHEMA",
    "TeacherDatasetError",
    "build_teacher_dataset",
    "validate_teacher_dataset_manifest",
]

__version__ = "0.9.1"
