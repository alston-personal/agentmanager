from __future__ import annotations

from typing import Any


def _normalize_vrm_bone(name: str) -> str:
    aliases = {
        'hips':'pelvis', 'spine':'torso', 'chest':'torso', 'upperChest':'torso',
        'neck':'neck', 'head':'head',
        'leftUpperArm':'left_arm', 'leftLowerArm':'left_arm', 'leftHand':'left_hand',
        'rightUpperArm':'right_arm', 'rightLowerArm':'right_arm', 'rightHand':'right_hand',
        'leftUpperLeg':'left_leg', 'leftLowerLeg':'left_leg', 'leftFoot':'left_foot', 'leftToes':'left_foot',
        'rightUpperLeg':'right_leg', 'rightLowerLeg':'right_leg', 'rightFoot':'right_foot', 'rightToes':'right_foot',
        'leftEye':'left_eye', 'rightEye':'right_eye', 'jaw':'jaw',
    }
    return aliases.get(name, name)


def extract_vrm_humanoid(gltf: dict[str, Any]) -> dict[str, Any] | None:
    ext = gltf.get('extensions') or {}
    nodes = gltf.get('nodes') or []
    records: list[dict[str, Any]] = []
    version = None

    vrm1 = ext.get('VRMC_vrm')
    if isinstance(vrm1, dict):
        hb = ((vrm1.get('humanoid') or {}).get('humanBones') or {})
        if isinstance(hb, dict):
            version = '1.0'
            for bone, spec in hb.items():
                if not isinstance(spec, dict) or not isinstance(spec.get('node'), int):
                    continue
                idx = spec['node']
                records.append({
                    'vrm_bone': bone,
                    'label': _normalize_vrm_bone(bone),
                    'node_index': idx,
                    'node_name': nodes[idx].get('name') if 0 <= idx < len(nodes) else None,
                    'confidence': 0.995,
                    'source': 'VRMC_vrm.humanoid.humanBones',
                })

    vrm0 = ext.get('VRM')
    if version is None and isinstance(vrm0, dict):
        hb = ((vrm0.get('humanoid') or {}).get('humanBones') or [])
        if isinstance(hb, list):
            version = '0.x'
            for spec in hb:
                if not isinstance(spec, dict) or not isinstance(spec.get('bone'), str) or not isinstance(spec.get('node'), int):
                    continue
                bone, idx = spec['bone'], spec['node']
                records.append({
                    'vrm_bone': bone,
                    'label': _normalize_vrm_bone(bone),
                    'node_index': idx,
                    'node_name': nodes[idx].get('name') if 0 <= idx < len(nodes) else None,
                    'confidence': 0.99,
                    'source': 'VRM.humanoid.humanBones',
                })

    if version is None:
        return None

    labels: dict[str, list[dict[str, Any]]] = {}
    for rec in records:
        labels.setdefault(rec['label'], []).append(rec)
    core = {'pelvis','torso','head','left_arm','right_arm','left_leg','right_leg'}
    coverage = len(core & set(labels)) / len(core)
    return {
        'schema': 'model2ir-vrm-humanoid-evidence/v0.6',
        'vrm_version': version,
        'body_plan': 'humanoid' if coverage >= 0.7 else 'partial-humanoid',
        'core_coverage': round(coverage, 4),
        'parts': labels,
        'bone_count': len(records),
        'confidence': round(min(0.999, 0.9 + coverage * 0.099), 4),
        'policy': 'VRM humanoid mapping is explicit standardized asset metadata and outranks naming heuristics',
    }
