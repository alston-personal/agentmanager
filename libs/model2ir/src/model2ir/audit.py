from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .reversible import ir_digest

HUMANOID_CORE = {'pelvis','torso','head','left_arm','right_arm','left_leg','right_leg'}


def _candidate_labels(candidate: dict[str, Any]) -> set[str]:
    return {p.get('id') for p in (candidate.get('parts') or []) if isinstance(p, dict) and p.get('id')}


def audit_asset(path: str | Path, extract_fn: Callable[[Any], dict[str, Any]], stabilize_fn: Callable[[dict[str, Any]], dict[str, Any]], repeats: int = 3) -> dict[str, Any]:
    if repeats < 2:
        raise ValueError('audit repeats must be >= 2')
    runs = [extract_fn(path) for _ in range(repeats)]
    candidates = [stabilize_fn(x) for x in runs]
    digests = [ir_digest(x) for x in candidates]
    deterministic = len(set(digests)) == 1
    first = runs[0]
    candidate = candidates[0]
    vrm = first.get('vrm_humanoid_evidence')
    topo = first.get('topology_evidence') or {}
    semantic = first.get('semantic_evidence_v03') or {}
    labels = _candidate_labels(candidate)
    core_coverage = len(HUMANOID_CORE & labels) / len(HUMANOID_CORE)
    unresolved_count = len(candidate.get('unresolved') or [])
    part_count = len(candidate.get('parts') or [])

    if first.get('reversibility', {}).get('lossless'):
        authority = 'embedded-canonical'
    elif vrm is not None and vrm.get('core_coverage', 0) >= .7:
        authority = 'standardized-vrm'
    elif semantic.get('body_plan', {}).get('kind') == 'humanoid':
        authority = 'explicit-asset-semantics'
    elif topo.get('kind') == 'humanoid-topology':
        authority = 'topology-only'
    else:
        authority = 'insufficient-semantic-evidence'

    stabilizable = isinstance(candidate, dict) and deterministic
    if authority == 'embedded-canonical':
        status = 'lossless'
    elif authority in {'standardized-vrm','explicit-asset-semantics'} and deterministic:
        status = 'stable-candidate'
    elif authority == 'topology-only' and deterministic:
        status = 'stable-but-ambiguous'
    else:
        status = 'stable-unknown' if deterministic else 'unstable'

    return {
        'schema':'model2ir-stability-audit/v0.6',
        'asset':str(path),
        'repeats':repeats,
        'candidate_digests':digests,
        'candidate_repeatable':deterministic,
        'semantic_authority':authority,
        'status':status,
        'reversible_now':bool(first.get('reversibility',{}).get('lossless')),
        'stabilizable':stabilizable,
        'after_stabilization_contract':'lossless-canonical-roundtrip' if stabilizable else None,
        'coverage':{
            'humanoid_core_semantic_coverage':round(core_coverage,4),
            'candidate_part_count':part_count,
            'unresolved_count':unresolved_count,
            'vrm_core_coverage':None if vrm is None else vrm.get('core_coverage'),
            'joint_count':(semantic.get('skeleton') or {}).get('joint_count',0),
        },
        'truth_policy':{
            'candidate_is_canonical':authority == 'embedded-canonical',
            'unknown_is_allowed':True,
            'automatic_promotion_of_inference':False,
        },
    }
