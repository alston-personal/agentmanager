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
from .audit import audit_asset as _audit_asset


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
    "ir_digest",
    "audit_asset",
]

__version__ = "0.6.0"
