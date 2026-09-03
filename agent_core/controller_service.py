from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from agent_core.executor_job_contract import validate_executor_job
from agent_core.realm_fabric import RealmFabricStore


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


class ControllerService:
    """Governed ONE control-plane dispatcher for Node actions.

    This service preserves the accepted #64 controller-dispatch contract. Newer
    privileged controller/runtime APIs live in agent_core.controller_api.

    #194 adds exactly one typed local-executor branch. It does not turn the
    compatibility controller into a generic command router.
    """

    REQUEST_SCHEMA = 'agentos.controller-dispatch/v0.1'
    RECEIPT_SCHEMA = 'agentos.controller-dispatch-receipt/v0.1'
    EXECUTOR_JOB_ACTION = 'agentos.executor.job'
    EXECUTOR_JOB_NODE = 'oracle-core-node'

    def __init__(self, fabric: RealmFabricStore, executor_job_dispatcher: Any | None = None):
        self.fabric = fabric
        self._executor_job_dispatcher = executor_job_dispatcher

    def _executor_dispatcher(self):
        if self._executor_job_dispatcher is None:
            from agentos_node.executor_job_action_relay import ActionRelayExecutorJobDispatcher
            self._executor_job_dispatcher = ActionRelayExecutorJobDispatcher()
        return self._executor_job_dispatcher

    def _node_for_dispatch(self, node_id: str) -> dict[str, Any]:
        node_map = self.fabric.node_registry.node_map()
        matches = [node for node in node_map.get('nodes', []) if node.get('node_id') == node_id]
        if not matches:
            raise KeyError(node_id)
        node = matches[0]
        if node.get('status') != 'online':
            raise ValueError(f'target node is not online: {node_id}')
        return node

    def _dispatch_executor_job(self, *, node_id: str, payload: Any, passthrough: dict[str, Any]) -> dict[str, Any]:
        if passthrough:
            raise ValueError(f'unexpected executor-job controller fields: {sorted(passthrough)}')
        if not isinstance(payload, dict):
            raise ValueError('executor-job payload must be an object')
        validate_executor_job(payload)
        if node_id != self.EXECUTOR_JOB_NODE:
            raise ValueError(f'executor job is not routable to target node: {node_id}')
        submission = dict(self._executor_dispatcher().submit(node_id=node_id, request=payload))
        # #50's hardened bridge historically calls the returned opaque id
        # ``task_id``. Preserve that field name as a compatibility alias only;
        # both values are the SAME Action Relay capsule/job ID. The caller's
        # incoming ctl_* hint never becomes execution identity.
        job_id = str(submission.get('job_id') or '')
        if not job_id:
            raise RuntimeError('executor-job dispatcher returned no job_id')
        submission['task_id'] = job_id
        return submission

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(request, dict):
            raise ValueError('controller request must be an object')
        schema = request.get('schema')
        if schema not in (None, self.REQUEST_SCHEMA):
            raise ValueError('invalid controller dispatch schema')

        node_id = str(request.get('node_id') or request.get('target_node') or '').strip()
        action = str(request.get('action') or request.get('capability') or '').strip()
        if not node_id:
            raise ValueError('node_id is required')
        if not action:
            raise ValueError('action is required')

        node = self._node_for_dispatch(node_id)
        payload = request.get('payload')
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            raise ValueError('payload must be an object')

        reserved = {'schema', 'task_id', 'action', 'node_id', 'target_node', 'capability', 'payload'}
        passthrough = {key: value for key, value in request.items() if key not in reserved}

        if action == self.EXECUTOR_JOB_ACTION:
            # A legacy ctl_* task_id may arrive from #50. It is deliberately
            # ignored and cannot select/reuse the Action Relay capsule ID.
            return self._dispatch_executor_job(
                node_id=node_id,
                payload=payload,
                passthrough=passthrough,
            )

        advertised = {str(x) for x in (node.get('capabilities') or []) if str(x)}
        if action not in advertised:
            raise ValueError(f'target node does not advertise capability: {action}')

        task_id = str(request.get('task_id') or ('task-' + uuid.uuid4().hex))
        task = {
            'schema': 'agentos.node-task/v0.1',
            'task_id': task_id,
            'action': action,
            **payload,
            **passthrough,
        }
        queued = self.fabric.queue_task(node_id, task)
        return {
            'schema': self.RECEIPT_SCHEMA,
            'ok': True,
            'controller_entered': True,
            'dispatch_id': 'dispatch-' + uuid.uuid4().hex,
            'node_id': node_id,
            'action': action,
            'task_id': task_id,
            'queued_at': queued.get('queued_at') or _utc_now(),
            'queue_schema': queued.get('schema'),
            'node_status': node.get('status'),
            'advertised_capability': True,
        }
