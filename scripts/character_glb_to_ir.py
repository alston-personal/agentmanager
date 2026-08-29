#!/usr/bin/env python3
import argparse, json, struct
from pathlib import Path

JSON_CHUNK = 0x4E4F534A


def read_glb(path):
    data = Path(path).read_bytes()
    if len(data) < 20:
        raise ValueError('GLB too small')
    magic, version, total = struct.unpack_from('<4sII', data, 0)
    if magic != b'glTF':
        raise ValueError('not a GLB file')
    if version != 2:
        raise ValueError(f'unsupported GLB version {version}')
    if total > len(data):
        raise ValueError('declared GLB length exceeds file size')
    off = 12
    gltf = None
    chunks = []
    while off + 8 <= total:
        length, ctype = struct.unpack_from('<II', data, off)
        off += 8
        payload = data[off:off+length]
        off += length
        chunks.append({'type': ctype, 'length': length})
        if ctype == JSON_CHUNK:
            gltf = json.loads(payload.rstrip(b'\x00 \t\r\n').decode('utf-8'))
    if gltf is None:
        raise ValueError('GLB missing JSON chunk')
    return gltf, chunks, len(data)


def accessor(gltf, idx):
    if idx is None:
        return None
    arr = gltf.get('accessors', [])
    return arr[idx] if 0 <= idx < len(arr) else None


def semantic_hint(name):
    s = (name or '').lower().replace('-', '_').replace(' ', '_')
    rules = [
        ('hair', ['hair','bang','pony','braid']),
        ('head', ['head','face','skull']),
        ('garment', ['cloth','shirt','dress','coat','robe','jacket','skirt','garment']),
        ('left_arm', ['left_arm','l_arm','arm_l']),
        ('right_arm', ['right_arm','r_arm','arm_r']),
        ('left_leg', ['left_leg','l_leg','leg_l']),
        ('right_leg', ['right_leg','r_leg','leg_r']),
        ('body', ['body','torso','chest','hips','pelvis']),
        ('accessory', ['crown','book','weapon','accessory','prop','hat','bag']),
        ('effect', ['effect','magic','aura','ring','spell']),
    ]
    for label, keys in rules:
        if any(k in s for k in keys):
            return {'label': label, 'confidence': 0.72, 'source': 'mesh-node-name-heuristic'}
    return {'label': 'unknown', 'confidence': 0.0, 'source': 'unresolved'}


def extract(gltf, chunks, file_bytes, source_name):
    meshes = gltf.get('meshes', [])
    nodes = gltf.get('nodes', [])
    materials = gltf.get('materials', [])
    primitives = []
    total_vertices = 0
    total_indices = 0
    total_faces = 0
    global_min = [float('inf')] * 3
    global_max = [float('-inf')] * 3
    bbox_samples = 0

    for mi, mesh in enumerate(meshes):
        mname = mesh.get('name') or f'mesh-{mi}'
        for pi, prim in enumerate(mesh.get('primitives', [])):
            pos_idx = (prim.get('attributes') or {}).get('POSITION')
            pos = accessor(gltf, pos_idx)
            ind = accessor(gltf, prim.get('indices'))
            vc = int((pos or {}).get('count', 0))
            ic = int((ind or {}).get('count', 0))
            mode = prim.get('mode', 4)
            faces = ic // 3 if mode == 4 and ic else (vc // 3 if mode == 4 else None)
            total_vertices += vc
            total_indices += ic
            if faces is not None: total_faces += faces
            pmin, pmax = (pos or {}).get('min'), (pos or {}).get('max')
            if pmin and pmax and len(pmin) >= 3 and len(pmax) >= 3:
                for k in range(3):
                    global_min[k] = min(global_min[k], float(pmin[k]))
                    global_max[k] = max(global_max[k], float(pmax[k]))
                bbox_samples += 1
            primitives.append({
                'mesh_index': mi,
                'primitive_index': pi,
                'name': mname,
                'vertices': vc,
                'indices': ic,
                'faces': faces,
                'material_index': prim.get('material'),
                'semantic_candidate': semantic_hint(mname),
            })

    components = []
    for ni, node in enumerate(nodes):
        if 'mesh' not in node: continue
        name = node.get('name') or meshes[node['mesh']].get('name') or f'node-{ni}'
        components.append({
            'node_index': ni,
            'mesh_index': node['mesh'],
            'name': name,
            'semantic_candidate': semantic_hint(name),
            'translation': node.get('translation'),
            'rotation': node.get('rotation'),
            'scale': node.get('scale'),
        })

    bbox = None
    if bbox_samples:
        bbox = {
            'min_local_untransformed': global_min,
            'max_local_untransformed': global_max,
            'extent_local_untransformed': [global_max[i]-global_min[i] for i in range(3)],
            'warning': 'accessor min/max are aggregated without node transforms in v0.1',
        }

    known = [c for c in components if c['semantic_candidate']['label'] != 'unknown']
    return {
        'schema': 'character-3d-derived-ir/v0.2',
        'source_kind': 'glb',
        'evidence_class': 'observed_3d_geometry',
        'source': {'name': source_name, 'bytes': file_bytes, 'glb_version': 2},
        'observed_3d': {
            'geometry': {
                'mesh_count': len(meshes),
                'primitive_count': len(primitives),
                'node_mesh_component_count': len(components),
                'vertices_sum': total_vertices,
                'indices_sum': total_indices,
                'triangle_faces_sum': total_faces,
                'material_count': len(materials),
                'bbox': bbox,
            },
            'components': components,
            'primitives': primitives,
        },
        'semantic_hypothesis': {
            'resolved_component_count': len(known),
            'unresolved_component_count': len(components)-len(known),
            'policy': 'names-only-v0.1; unresolved geometry is not promoted to canonical Character IR',
        },
        'provenance': {
            'extractor': 'character_glb_to_ir.py/v0.1',
            'chunks': chunks,
            'truth_policy': 'geometry observations may be factual; semantic labels remain hypotheses unless separately confirmed',
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input-glb', required=True)
    ap.add_argument('--output', required=True)
    args = ap.parse_args()
    gltf, chunks, size = read_glb(args.input_glb)
    out = extract(gltf, chunks, size, Path(args.input_glb).name)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n')
    g = out['observed_3d']['geometry']
    print(json.dumps({'ok': True, 'schema': out['schema'], **{k:g[k] for k in ['mesh_count','primitive_count','vertices_sum','triangle_faces_sum']}}, ensure_ascii=False))

if __name__ == '__main__':
    main()
