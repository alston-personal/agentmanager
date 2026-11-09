from __future__ import annotations
import time
from typing import Any
from agent_core.realm_fabric import RealmFabricStore
from agent_core.node_registry import NodeRegistry

def accept_candidate(node_id: str, source_commit: str, *, timeout_seconds: int = 90) -> dict[str, Any]:
    fabric=RealmFabricStore(); registry=NodeRegistry()
    deadline=time.time()+max(15,timeout_seconds)
    heartbeat=None
    while time.time()<deadline:
        node=registry.load().get('nodes',{}).get(node_id) or {}
        runtime=node.get('runtime') or {}
        if node.get('status')=='online' and runtime.get('source_commit')==source_commit:
            heartbeat=node; break
        time.sleep(2)
    if heartbeat is None:
        return {'ok':False,'stage':'candidate_heartbeat','reason':'timeout','node_id':node_id,'source_commit':source_commit}
    task_id=f'ota-accept-{node_id}-{int(time.time())}'
    fabric.queue_task(node_id,{'schema':'agentos.node-task/v0.1','task_id':task_id,'action':'agent.surface.inspect','cognition_ids_used':[]})
    while time.time()<deadline:
        receipt=fabric.get_receipt(task_id)
        if receipt:
            ok=receipt.get('ok') is True
            return {'ok':ok,'stage':'post_switch_probe','node_id':node_id,'source_commit':source_commit,'task_id':task_id,'receipt_ok':ok}
        time.sleep(2)
    return {'ok':False,'stage':'post_switch_probe','reason':'receipt_timeout','node_id':node_id,'source_commit':source_commit,'task_id':task_id}
