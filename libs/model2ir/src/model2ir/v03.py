from __future__ import annotations

from pathlib import Path
from typing import Any

from . import v02 as _v02
from .semantic3d import infer_structured_semantics


def load_asset(path: str | Path):
    return _v02.load_asset(path)


def extract_ir(asset_or_path) -> dict[str, Any]:
    asset = asset_or_path if hasattr(asset_or_path, 'gltf') else _v02.load_asset(asset_or_path)
    out = _v02.extract_ir(asset)
    out['schema'] = 'model2ir-character-ir/v0.3'
    out['semantic_evidence_v03'] = infer_structured_semantics(asset.gltf)
    out['provenance']['extractor'] = 'model2ir/v0.3'
    return out


def diff_ir(a, b):
    return _v02.diff_ir(a, b)


def reconcile_ir(image_ir, model_ir):
    out = _v02.reconcile_ir(image_ir, model_ir)
    out['schema'] = 'model2ir-reconciliation/v0.3'
    sem = model_ir.get('semantic_evidence_v03') or {}
    out['structured_3d_semantic_evidence'] = sem
    return out


def score_roundtrip(source_ir, recovered_ir):
    return _v02.score_roundtrip(source_ir, recovered_ir)

compile_reversible_gltf = _v02.compile_reversible_gltf
save_reversible_gltf = _v02.save_reversible_gltf
