from __future__ import annotations

from typing import Any


def _children(nodes: list[dict[str, Any]], i: int) -> list[int]:
    if not (0 <= i < len(nodes)):
        return []
    return [x for x in (nodes[i].get('children') or []) if isinstance(x, int) and 0 <= x < len(nodes)]


def _chain_len(nodes: list[dict[str, Any]], start: int, limit: int = 8) -> int:
    n = 0; cur = start; seen = set()
    while cur not in seen and n < limit:
        seen.add(cur); n += 1
        ch = _children(nodes, cur)
        if len(ch) != 1: break
        cur = ch[0]
    return n


def infer_humanoid_topology(gltf: dict[str, Any]) -> dict[str, Any]:
    nodes = gltf.get('nodes') or []
    skins = gltf.get('skins') or []
    joint_ids = set()
    for skin in skins:
        joint_ids.update(x for x in (skin.get('joints') or []) if isinstance(x, int))
    if len(joint_ids) < 12:
        return {
            'schema':'model2ir-topology-evidence/v0.6',
            'kind':'unknown','confidence':0.0,'reason':'too-few-joints',
            'joint_count':len(joint_ids),'anonymous_parts':[],'side_assignments':{},
        }

    # Find pelvis-like branch point: two long lower chains plus one trunk continuation.
    candidates=[]
    for i in sorted(joint_ids):
        ch=[x for x in _children(nodes,i) if x in joint_ids]
        if len(ch) < 3: continue
        lens=sorted([(_chain_len(nodes,x),x) for x in ch], reverse=True)
        if sum(1 for ln,_ in lens if ln >= 3) >= 2:
            candidates.append((i,ch,lens))
    if not candidates:
        return {
            'schema':'model2ir-topology-evidence/v0.6',
            'kind':'unknown','confidence':0.15,'reason':'no-pelvis-like-branch',
            'joint_count':len(joint_ids),'anonymous_parts':[],'side_assignments':{},
        }

    best=None
    for pelvis,ch,lens in candidates:
        # Search one child path for an upper branch point with two arm-like chains + neck/head continuation.
        stack=[(x,0) for x in ch]
        seen=set()
        upper=None
        while stack:
            cur,depth=stack.pop()
            if cur in seen or depth>5: continue
            seen.add(cur)
            cc=[x for x in _children(nodes,cur) if x in joint_ids]
            if len(cc)>=3 and sum(1 for x in cc if _chain_len(nodes,x)>=2)>=3:
                upper=(cur,cc); break
            stack.extend((x,depth+1) for x in cc)
        if upper:
            best=(pelvis,ch,upper[0],upper[1]); break
    if best is None:
        return {
            'schema':'model2ir-topology-evidence/v0.6',
            'kind':'unknown','confidence':0.3,'reason':'lower-branch-without-upper-branch',
            'joint_count':len(joint_ids),'anonymous_parts':[],'side_assignments':{},
        }

    pelvis, lower_children, chest, upper_children = best
    lower_rank=sorted(lower_children,key=lambda x:_chain_len(nodes,x),reverse=True)
    upper_rank=sorted(upper_children,key=lambda x:_chain_len(nodes,x),reverse=True)
    anonymous=[
        {'role':'pelvis','node_index':pelvis,'confidence':0.76},
        {'role':'upper_torso_branch','node_index':chest,'confidence':0.72},
    ]
    for idx,x in enumerate(lower_rank[:2]):
        anonymous.append({'role':f'leg_branch_{idx+1}','node_index':x,'chain_length':_chain_len(nodes,x),'confidence':0.7})
    for idx,x in enumerate(upper_rank[:2]):
        anonymous.append({'role':f'arm_branch_{idx+1}','node_index':x,'chain_length':_chain_len(nodes,x),'confidence':0.68})
    return {
        'schema':'model2ir-topology-evidence/v0.6',
        'kind':'humanoid-topology','confidence':0.72,
        'reason':'pelvis-like bilateral lower branches plus upper torso bilateral branches',
        'joint_count':len(joint_ids),
        'anonymous_parts':anonymous,
        'side_assignments':{},
        'policy':'topology can establish body-plan class but does not assign left/right without independent evidence',
    }
