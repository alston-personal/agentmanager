from __future__ import annotations

import copy
from typing import Any


def project_candidate_ir(model_ir: dict[str, Any]) -> dict[str, Any]:
    """Project extracted 3D evidence into a stable, explicit candidate Character IR.

    This is not canonical truth. It is the deterministic import boundary: once
    created, this candidate IR can be embedded in a carrier and round-tripped
    losslessly even if the original external asset had no model2ir metadata.
    """
    sem = model_ir.get('semantic_evidence_v03') or {}
    body = sem.get('body_plan') or {}
    parts_src = sem.get('parts') or {}
    parts = []
    for label, rec in sorted(parts_src.items()):
        parts.append({
            'id': label,
            'state': 'inferred_from_3d',
            'confidence': rec.get('best_confidence', 0.0),
            'evidence_count': rec.get('evidence_count', 0),
        })
    unresolved = []
    for c in (model_ir.get('semantic_ir') or {}).get('unresolved', []) or []:
        unresolved.append({
            'component': c.get('name'),
            'node_index': c.get('node_index'),
            'reason': 'semantic-class-unresolved',
        })
    return {
        'schema': 'character-ir-candidate/v0.4',
        'truth_status': 'candidate',
        'source': {
            'kind': model_ir.get('source_kind'),
            'name': (model_ir.get('source') or {}).get('name'),
            'extractor': (model_ir.get('provenance') or {}).get('extractor'),
        },
        'body_plan': {
            'kind': body.get('kind', 'unknown'),
            'confidence': body.get('confidence', 0.0),
            'extra_appendages': copy.deepcopy(body.get('extra_appendages', [])),
        },
        'parts': parts,
        'skeleton': copy.deepcopy(sem.get('skeleton') or {}),
        'materials': copy.deepcopy(sem.get('materials') or []),
        'morph_targets': copy.deepcopy(sem.get('morph_targets') or []),
        'unresolved': unresolved,
        'provenance': {
            'policy': 'candidate only; no inferred field is automatically canonical truth',
            'semantic_evidence_schema': sem.get('schema'),
        },
    }
