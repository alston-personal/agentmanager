from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from . import v04 as _v04
from .geometry_profile import profile_asset_structure
from .standards import extract_vrm_humanoid
from .topology import infer_humanoid_topology


def load_asset(path: str | Path):
    return _v04.load_asset(path)


def _fused_candidate(out: dict[str, Any], vrm: dict[str, Any] | None, topo: dict[str, Any]) -> dict[str, Any]:
    base = copy.deepcopy(out.get('candidate_ir') or {})
    base['schema'] = 'character-ir-candidate/v0.6'
    base.setdefault('evidence_fusion', {})

    # Explicit standardized VRM metadata outranks author naming and topology inference.
    if vrm is not None:
        base['body_plan'] = {
            'kind': 'humanoid' if vrm.get('body_plan') == 'humanoid' else 'partial-humanoid',
            'confidence': vrm.get('confidence', 0.0),
            'source': f"VRM-{vrm.get('vrm_version')}-humanoid-standard",
            'extra_appendages': copy.deepcopy((base.get('body_plan') or {}).get('extra_appendages', [])),
        }
        by_id = {p.get('id'): p for p in (base.get('parts') or []) if p.get('id')}
        for label, evidence in sorted((vrm.get('parts') or {}).items()):
            best = max((e.get('confidence', 0.0) for e in evidence), default=0.0)
            prev = by_id.get(label)
            if prev is None or best >= prev.get('confidence', 0.0):
                by_id[label] = {
                    'id': label,
                    'state': 'observed_standard_metadata',
                    'confidence': best,
                    'evidence_count': len(evidence),
                    'source': 'vrm-humanoid-standard',
                }
        base['parts'] = [by_id[k] for k in sorted(by_id)]
        base['evidence_fusion']['primary_body_plan_source'] = 'vrm-standard'
    else:
        current = base.get('body_plan') or {}
        current_kind = current.get('kind', 'unknown')
        if current_kind == 'unknown' and topo.get('kind') == 'humanoid-topology':
            base['body_plan'] = {
                'kind': 'humanoid',
                'confidence': topo.get('confidence', 0.0),
                'source': 'skeleton-topology',
                'extra_appendages': copy.deepcopy(current.get('extra_appendages', [])),
                'side_assignment_status': 'unresolved',
            }
            base['evidence_fusion']['primary_body_plan_source'] = 'topology'
        else:
            base['evidence_fusion']['primary_body_plan_source'] = 'name-or-scene-evidence'

    base['topology_evidence'] = copy.deepcopy(topo)
    base['vrm_humanoid_evidence'] = copy.deepcopy(vrm)
    base['provenance'] = {
        **(base.get('provenance') or {}),
        'fusion_policy': 'VRM standard > explicit scene/joint semantics > skeleton topology; ambiguity remains unresolved',
    }
    return base


def extract_ir(asset_or_path) -> dict[str, Any]:
    asset = asset_or_path if hasattr(asset_or_path, 'gltf') else _v04.load_asset(asset_or_path)
    out = _v04.extract_ir(asset)
    vrm = extract_vrm_humanoid(asset.gltf)
    topo = infer_humanoid_topology(asset.gltf)
    out['schema'] = 'model2ir-character-ir/v0.6'
    out['vrm_humanoid_evidence'] = vrm
    out['topology_evidence'] = topo
    out['geometry_profile_evidence'] = profile_asset_structure(out)
    if out.get('canonical_ir') is None:
        out['candidate_ir'] = _fused_candidate(out, vrm, topo)
    out['provenance']['extractor'] = 'model2ir/v0.6'
    return out


def stabilize_external_ir(model_ir: dict[str, Any]) -> dict[str, Any]:
    if model_ir.get('canonical_ir') is not None:
        return model_ir['canonical_ir']
    candidate = model_ir.get('candidate_ir')
    if isinstance(candidate, dict):
        return candidate
    return _v04.stabilize_external_ir(model_ir)


def diff_ir(a, b): return _v04.diff_ir(a, b)
def reconcile_ir(a, b): return _v04.reconcile_ir(a, b)
def score_roundtrip(a, b): return _v04.score_roundtrip(a, b)
compile_reversible_gltf = _v04.compile_reversible_gltf
save_reversible_gltf = _v04.save_reversible_gltf
