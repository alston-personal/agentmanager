from __future__ import annotations

from pathlib import Path
from typing import Any

from . import v03 as _v03
from .normalize import project_candidate_ir


def load_asset(path: str | Path):
    return _v03.load_asset(path)


def extract_ir(asset_or_path) -> dict[str, Any]:
    out = _v03.extract_ir(asset_or_path)
    out['schema'] = 'model2ir-character-ir/v0.4'
    if out.get('canonical_ir') is None:
        out['candidate_ir'] = project_candidate_ir(out)
        out['stabilization'] = {
            'mode': 'external-import-candidate',
            'candidate_created': True,
            'future_roundtrip_can_be_lossless_if_embedded': True,
        }
    else:
        out['candidate_ir'] = None
        out['stabilization'] = {
            'mode': 'embedded-canonical',
            'candidate_created': False,
            'future_roundtrip_can_be_lossless_if_embedded': True,
        }
    out['provenance']['extractor'] = 'model2ir/v0.4'
    return out


def stabilize_external_ir(model_ir: dict[str, Any]) -> dict[str, Any]:
    if model_ir.get('canonical_ir') is not None:
        return model_ir['canonical_ir']
    c = model_ir.get('candidate_ir')
    return c if isinstance(c, dict) else project_candidate_ir(model_ir)


def diff_ir(a, b): return _v03.diff_ir(a, b)
def reconcile_ir(a, b): return _v03.reconcile_ir(a, b)
def score_roundtrip(a, b): return _v03.score_roundtrip(a, b)
compile_reversible_gltf = _v03.compile_reversible_gltf
save_reversible_gltf = _v03.save_reversible_gltf
