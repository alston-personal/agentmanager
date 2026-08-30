from __future__ import annotations

import re
from typing import Any


def _norm(name: str | None) -> str:
    return re.sub(r'[^a-z0-9]+', '_', (name or '').lower()).strip('_')


def _side(name: str) -> str | None:
    n = _norm(name)
    if re.search(r'(^|_)l($|_)|left', n): return 'left'
    if re.search(r'(^|_)r($|_)|right', n): return 'right'
    return None


def _part(name: str | None) -> tuple[str | None, float]:
    n = _norm(name)
    if not n: return None, 0.0
    side = _side(n)
    if any(k in n for k in ['head','face','skull']): return 'head', 0.9
    if 'neck' in n: return 'neck', 0.9
    if any(k in n for k in ['spine','torso','chest']): return 'torso', 0.88
    if any(k in n for k in ['pelvis','hips','hip']): return 'pelvis', 0.88
    if any(k in n for k in ['arm','shoulder','clavicle']): return f'{side}_arm' if side else 'arm', 0.86
    if any(k in n for k in ['hand','wrist']): return f'{side}_hand' if side else 'hand', 0.86
    if any(k in n for k in ['leg','thigh','knee']): return f'{side}_leg' if side else 'leg', 0.86
    if any(k in n for k in ['foot','ankle']): return f'{side}_foot' if side else 'foot', 0.86
    if any(k in n for k in ['hair','bang','pony','braid']): return 'hair', 0.82
    if any(k in n for k in ['dress','shirt','coat','robe','jacket','skirt','cloth','garment']): return 'garment', 0.8
    if any(k in n for k in ['tail']): return 'tail', 0.82
    if any(k in n for k in ['wing']): return 'wing', 0.82
    if any(k in n for k in ['book','weapon','sword','staff','crown','hat','bag']): return 'accessory', 0.78
    if any(k in n for k in ['magic','aura','effect','spell']): return 'effect', 0.78
    return None, 0.0


def infer_structured_semantics(gltf: dict[str, Any]) -> dict[str, Any]:
    nodes = gltf.get('nodes', []) or []
    skins = gltf.get('skins', []) or []
    meshes = gltf.get('meshes', []) or []
    materials = gltf.get('materials', []) or []

    joint_ids = set()
    for s in skins:
        joint_ids.update(s.get('joints', []) or [])

    evidence = []
    labels: dict[str, list[dict[str, Any]]] = {}
    for i, node in enumerate(nodes):
        name = node.get('name')
        label, conf = _part(name)
        if not label:
            continue
        rec = {
            'label': label,
            'confidence': conf + (0.06 if i in joint_ids else 0.0),
            'node_index': i,
            'name': name,
            'source': 'joint-name+scene-hierarchy' if i in joint_ids else 'node-name',
            'is_joint': i in joint_ids,
        }
        rec['confidence'] = min(0.98, rec['confidence'])
        evidence.append(rec)
        labels.setdefault(label, []).append(rec)

    required = ['torso','left_arm','right_arm','left_leg','right_leg']
    humanoid_hits = sum(1 for x in required if x in labels)
    if 'pelvis' in labels or 'neck' in labels: humanoid_hits += 1

    # Conservative topology corroboration for rigs that terminate the skeleton at
    # a second neck joint instead of naming a separate head bone (e.g. CesiumMan).
    # Do not apply this to weak/non-humanoid rigs and never override explicit head evidence.
    if humanoid_hits >= 5 and 'head' not in labels:
        neck_joint_recs = [r for r in labels.get('neck', []) if r.get('is_joint')]
        if len(neck_joint_recs) >= 2:
            terminal = []
            for rec in neck_joint_recs:
                idx = rec['node_index']
                joint_children = [c for c in (nodes[idx].get('children') or []) if c in joint_ids]
                if not joint_children:
                    terminal.append(rec)
            if len(terminal) == 1:
                src = terminal[0]
                inferred = {
                    'label': 'head',
                    'confidence': 0.74,
                    'node_index': src['node_index'],
                    'name': src.get('name'),
                    'source': 'terminal-neck-joint+humanoid-body-plan',
                    'is_joint': True,
                    'inference_reason': 'strong humanoid rig has a multi-joint neck chain whose unique terminal joint is the head anchor',
                }
                evidence.append(inferred)
                labels.setdefault('head', []).append(inferred)

    body_plan = {
        'kind': 'humanoid' if humanoid_hits >= 4 else 'unknown',
        'confidence': round(min(0.97, 0.35 + humanoid_hits * 0.1), 3) if humanoid_hits else 0.0,
        'evidence_labels': sorted(labels),
        'extra_appendages': sorted(x for x in ['tail','wing'] if x in labels),
    }

    morphs = []
    for mi, mesh in enumerate(meshes):
        target_names = ((mesh.get('extras') or {}).get('targetNames') or [])
        max_targets = max([len(p.get('targets', []) or []) for p in mesh.get('primitives', []) or []] or [0])
        if max_targets:
            morphs.append({'mesh_index': mi, 'mesh_name': mesh.get('name'), 'target_count': max_targets, 'target_names': target_names[:max_targets]})

    material_summary = []
    for i, m in enumerate(materials):
        pbr = m.get('pbrMetallicRoughness') or {}
        material_summary.append({
            'index': i,
            'name': m.get('name'),
            'base_color_factor': pbr.get('baseColorFactor'),
            'metallic_factor': pbr.get('metallicFactor'),
            'roughness_factor': pbr.get('roughnessFactor'),
            'alpha_mode': m.get('alphaMode', 'OPAQUE'),
            'double_sided': bool(m.get('doubleSided', False)),
        })

    return {
        'schema': 'model2ir-semantic-evidence/v0.3',
        'body_plan': body_plan,
        'parts': {k: {'best_confidence': max(x['confidence'] for x in v), 'evidence_count': len(v), 'evidence': v} for k, v in sorted(labels.items())},
        'skeleton': {
            'skin_count': len(skins),
            'joint_count': len(joint_ids),
            'joint_node_indices': sorted(joint_ids),
        },
        'morph_targets': morphs,
        'materials': material_summary,
        'policy': 'semantic evidence is inferred from explicit asset structure; it is not promoted to canonical truth without corroboration',
    }
